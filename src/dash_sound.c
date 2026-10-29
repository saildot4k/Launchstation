//--------------------------------------------------------------
//File name:   dash_sound.c
//Dashboard SFX: loads audsrv, uploads the embedded ADP samples and
//plays them on ADPCM channels. Degrades to silent no-ops on any
//failure (driver missing, sample rejected, sound disabled).
//--------------------------------------------------------------
#include "launchelf.h"
#include "dash_internal.h"
#include "dash_sound.h"
#include "init.h"
#include <audsrv.h>
#include <iopcontrol.h>

extern u8 audsrv_irx[];
extern int size_audsrv_irx;
extern u8 libsd_irx[];
extern int size_libsd_irx;
extern u8 sfx_cursor_adp[];
extern int size_sfx_cursor_adp;
extern u8 sfx_confirm_adp[];
extern int size_sfx_confirm_adp;
extern u8 sfx_cancel_adp[];
extern int size_sfx_cancel_adp;
extern u8 sfx_transition_adp[];
extern int size_sfx_transition_adp;
extern u8 sfx_message_adp[];
extern int size_sfx_message_adp;
extern u8 sfx_boot_adp[];
extern int size_sfx_boot_adp;
extern u8 sfx_connect_adp[];
extern int size_sfx_connect_adp;
extern u8 sfx_disconnect_adp[];
extern int size_sfx_disconnect_adp;

static audsrv_adpcm_t samples[DASH_SND_COUNT];
static audsrv_adpcm_t bgm_sample;
static int sound_ready;
static int bgm_loaded;
static int bgm_tried;
static void *bgm_data; /* audsrv uses this buffer address as the sample ID */
static int bgm_channel = -1;
static unsigned int sound_reboot_generation; /* reset epoch when audsrv was started */
static unsigned int sound_tried_generation = (unsigned int)-1; /* last automatic attempt */
static int sound_retry;

typedef struct SoundPlaybackStats {
	unsigned int requests, started, failed;
	int last_result, failed_result, failed_id;
	const char *failed_reason;
} SoundPlaybackStats;
static SoundPlaybackStats playback;


/* audsrv lives on the IOP: after any IOP reboot the server and the uploaded
 * samples are gone, and calling into the stale RPC client hangs. Every
 * entry point checks this first. */
static int soundAlive(void)
{
	return sound_ready && getIopResetGeneration() == sound_reboot_generation;
}

/* SPU2 voice allocation (24 hardware voices total):
 *   0..7: fixed single-voice SFX (boot, confirm, cancel, message, connect, disconnect)
 *   8..13: cursor SFX (6-voice rotating pool)
 *  14..17: transition SFX (4-voice rotating pool for L1/R1, #136)
 *  18..22: general SFX headroom
 *     23: DASH_BGM_CHANNEL (looping background music, isolated from SFX)
 */
#define DASH_BGM_CHANNEL 23
#define BGM_WORKAROUND_VOLUME 5
#define SND_SFX_CH_MAX 23
#define SND_CURSOR_CH_BASE 8
#define SND_CURSOR_CH_COUNT 6
#define SND_TRANS_CH_BASE 14
#define SND_TRANS_CH_COUNT 4
#define SND_FALLBACK_CH_BASE 18

int dashBgmRequestedVolume(void)
{
	return dashCfg.bgm ? dashCfg.bgm_vol : 0;
}

/* Physical consoles still lose/cut SFX when music is muted. Keep a nonzero
 * music voice as the requested workaround; never write this gain to settings.
 * Suspend/shutdown deliberately bypass it when handing control to another app. */
static int bgmPlaybackVolume(void)
{
	int requested = dashBgmRequestedVolume();
	return requested > 0 ? requested : BGM_WORKAROUND_VOLUME;
}

static void *blob_data(int id)
{
	switch (id) {
		case DASH_SND_CURSOR: return sfx_cursor_adp;
		case DASH_SND_CONFIRM: return sfx_confirm_adp;
		case DASH_SND_CANCEL: return sfx_cancel_adp;
		case DASH_SND_TRANSITION: return sfx_transition_adp;
		case DASH_SND_MESSAGE: return sfx_message_adp;
		case DASH_SND_BOOT: return sfx_confirm_adp;
		case DASH_SND_CONNECT: return sfx_connect_adp;
		default: return sfx_disconnect_adp;
	}
}

static int blob_size(int id)
{
	switch (id) {
		case DASH_SND_CURSOR: return size_sfx_cursor_adp;
		case DASH_SND_CONFIRM: return size_sfx_confirm_adp;
		case DASH_SND_CANCEL: return size_sfx_cancel_adp;
		case DASH_SND_TRANSITION: return size_sfx_transition_adp;
		case DASH_SND_MESSAGE: return size_sfx_message_adp;
		case DASH_SND_BOOT: return size_sfx_confirm_adp;
		case DASH_SND_CONNECT: return size_sfx_connect_adp;
		default: return size_sfx_disconnect_adp;
	}
}

int dashSoundInit(void)
{
	int i, r, failed;

	if (sound_ready && soundAlive())
		return 1;
	if (sound_ready)
		dashSoundShutdown(); /* stale after an IOP reboot: forget it */
	/* the UI thread must not load modules while a background job may */
	if (dashWorkerIoBusy() || dashIopParked()) {
		sound_retry = 1; /* dashSoundMaintain() tries again */
		return 0;
	}
	sound_tried_generation = getIopResetGeneration();
	/* The music workaround also needs audsrv when both visible buses are Off. */
	/* audsrv imports sceSd* from the libsd module: it must be resident first */
	if (SifExecModuleBuffer(libsd_irx, size_libsd_irx, 0, NULL, &r) < 0 || r < 0) {
		dashToast(DASH_TOAST_WARN, "Sound unavailable: libsd would not start");
		return 0;
	}
	if (SifExecModuleBuffer(audsrv_irx, size_audsrv_irx, 0, NULL, &r) < 0 || r < 0) {
		dashToast(DASH_TOAST_WARN, "Sound unavailable: audsrv would not start");
		return 0;
	}
	if (audsrv_init() != 0) {
		dashToast(DASH_TOAST_WARN, "Sound unavailable: audsrv init failed");
		return 0;
	}
	if (audsrv_adpcm_init() != 0) {
		audsrv_quit();
		dashToast(DASH_TOAST_WARN, "Sound unavailable: adpcm init failed");
		return 0;
	}
	failed = 0;
	for (i = 0; i < DASH_SND_COUNT; i++) {
		samples[i].buffer = NULL;
		if (audsrv_load_adpcm(&samples[i], blob_data(i), blob_size(i)) != 0) {
			samples[i].buffer = NULL; /* sample stays silent */
			failed++;
		}
	}
	/* Keep SFX preloaded even when their toggle is off so they can be enabled
	 * later without reinitializing audsrv (BGM may already own the service). */
	if (dashCfg.sound && failed == DASH_SND_COUNT) {
		dashToast(DASH_TOAST_WARN, "Sound unavailable: no samples loaded");
		/* The server is healthy even if its SFX uploads failed. Retain its
		 * lifetime so BGM can use its independent sample and shutdown can
		 * release the live RPC client before the next IOP reset. */
	} else if (dashCfg.sound && failed > 0) {
		char msg[64];

		snprintf(msg, sizeof(msg), "%d sound effect%s unavailable", failed, failed == 1 ? "" : "s");
		dashToast(DASH_TOAST_WARN, msg);
	}
	/* Channel map and volumes: boot..disconnect on voices 0..7, cursor
	 * rotating over 8..13, transition rotating over 14..17, general SFX 18..22. */
	if (dashCfg.sound) {
		for (i = 0; i < SND_SFX_CH_MAX; i++)
			audsrv_adpcm_set_volume_and_pan(i, dashCfg.sound_vol, 0);
	}
	sound_reboot_generation = getIopResetGeneration();
	sound_ready = 1;
	return 1;
}

void dashSoundMaintain(void)
{
	if (dashWorkerIoBusy() || dashIopParked())
		return;
	if (soundAlive()) {
		/* A sidecar read deferred by IO/driver startup is tried when idle.
		 * Missing/invalid files are attempted once, not on every frame. */
		if (bgm_channel < 0 && !bgm_tried)
			dashBgmStart();
		return;
	}
	/* one automatic attempt per IOP session (a broken driver would
	 * otherwise be retried every frame), plus retries that were deferred */
	if (sound_tried_generation == getIopResetGeneration() && !sound_retry)
		return;
	sound_tried_generation = getIopResetGeneration();
	sound_retry = 0;
	if (dashSoundInit())
		dashBgmStart();
}

void dashSoundShutdown(void)
{
	if (soundAlive()) {
		/*
		 * BGM is a looping SPU2 ADPCM voice. Merely setting its volume to
		 * zero and dropping the EE RPC client can leave the IOP/SPU2 voice
		 * alive across a keep-IOP ExecPS2 handoff. audsrv_adpcm_init() is the
		 * library's hard reset for ADPCM state: it stops every voice and frees
		 * the uploaded sample list before audsrv_quit() releases RPC.
		 */
		/* Settings Off keeps 5% playback; a real shutdown must mute instead. */
		if (bgm_channel >= 0 && !dashIopParked())
			audsrv_adpcm_set_volume_and_pan(bgm_channel, 0, 0);
		audsrv_adpcm_init();
		audsrv_stop_audio();
		audsrv_quit();
	}
	sound_ready = 0;
	bgm_loaded = 0;
	bgm_tried = 0;
	bgm_channel = -1;
	bgm_sample.buffer = NULL;
	free(bgm_data);
	bgm_data = NULL;
}

void dashSoundSuspend(void)
{
	int i;

	if (!soundAlive() || dashIopParked())
		return;
	/* Keep the RPC client and samples valid until the launch is committed.
	 * audsrv_quit() destroys client state that audsrv_init() cannot recreate
	 * in the same IOP session. Failed launches must be able to resume music. */
	for (i = 0; i < SND_SFX_CH_MAX; i++)
		audsrv_adpcm_set_volume_and_pan(i, 0, 0);
	if (bgm_channel >= 0)
		audsrv_adpcm_set_volume_and_pan(bgm_channel, 0, 0);
}

void dashSoundApplyVolume(void)
{
	int i;

	if (!soundAlive())
		return;
	for (i = 0; i < SND_SFX_CH_MAX; i++)
		audsrv_adpcm_set_volume_and_pan(i, dashCfg.sound ? dashCfg.sound_vol : 0, 0);
}

static void soundPlayFailed(int id, int result, const char *reason)
{
	playback.failed++;
	playback.failed_id = id;
	playback.failed_result = result;
	playback.failed_reason = reason;
}

void dashSoundGetStatus(char *out, int out_size)
{
	static const char *const names[DASH_SND_COUNT] = {
	    "Cursor", "Confirm", "Cancel", "Section switch", "Notification",
	    "Startup", "Device connect", "Device disconnect"};
	char failure[128];

	if (out == NULL || out_size <= 0)
		return;
	if (playback.failed)
		snprintf(failure, sizeof(failure), "%s: %s (%d)", names[playback.failed_id],
		         playback.failed_reason, playback.failed_result);
	else
		snprintf(failure, sizeof(failure), "None");
	/* EE snapshots only: opening diagnostics must never probe a stale IOP. */
	snprintf(out, out_size,
	         "Service: %s\nEffects: %s %d%%; music: %s %d%%\n"
	         "Requested: %u; started: %u; failed: %u\nLast failure: %s",
	         soundAlive() ? "ready" : "unavailable",
	         dashCfg.sound ? "On" : "Off", dashCfg.sound_vol,
	         dashBgmRequestedVolume() > 0 ? "On" : "Off", dashBgmRequestedVolume(),
	         playback.requests, playback.started, playback.failed, failure);
}

static int soundPlayChannel(int ch, int id)
{
	int result;

	/* Restore the interface gain before key-on, so a previously muted voice
	 * cannot lose the attack of a short effect while a second RPC unmutes it. */
	result = audsrv_adpcm_set_volume_and_pan(ch, dashCfg.sound_vol, 0);
	if (result != 0) {
		playback.last_result = result;
		return 0;
	}
	result = audsrv_ch_play_adpcm(ch, &samples[id]);
	if (result != ch) {
		playback.last_result = result;
		return 0;
	}
	playback.started++;
	return 1;
}

void dashSoundPlay(int id)
{
	static int cursorSlot;
	static int transSlot;
	int ch, i;

	if (!dashCfg.sound || id < 0 || id >= DASH_SND_COUNT)
		return;
	playback.requests++;
	if (!soundAlive()) {
		soundPlayFailed(id, 0, "audio service unavailable");
		return;
	}
	if (dashIopParked()) {
		soundPlayFailed(id, 0, "IOP parked for a worker job");
		return;
	}
	if (samples[id].buffer == NULL) {
		soundPlayFailed(id, 0, "sample not loaded");
		return;
	}
	if (id == DASH_SND_CURSOR) {
		/* Input already applies the scroll repeat delay/ramp (down to 40ms).
		 * A separate 45ms sound gate drops valid navigation feedback. The
		 * rotating voices let short cursor effects overlap without a gate. */
		ch = SND_CURSOR_CH_BASE + cursorSlot;
		cursorSlot = (cursorSlot + 1) % SND_CURSOR_CH_COUNT;
	} else if (id == DASH_SND_TRANSITION) {
		ch = SND_TRANS_CH_BASE + transSlot;
		transSlot = (transSlot + 1) % SND_TRANS_CH_COUNT;
	} else {
		ch = id; /* any fixed voice < 8; cursor occupies 8..13, transition 14..17 */
	}
	if (soundPlayChannel(ch, id))
		return;
	/* Prefer spare voices, then other SFX voices. audsrv's automatic (-1)
	 * allocation includes the music voice; a looping/muted track can appear
	 * available through ENDX, causing silent effects or replacing the music. */
	for (i = 0; i < SND_SFX_CH_MAX; i++) {
		int fallback = (SND_FALLBACK_CH_BASE + i) % SND_SFX_CH_MAX;
		if (fallback != ch && soundPlayChannel(fallback, id))
			return;
	}
	soundPlayFailed(id, playback.last_result, "audsrv rejected playback");
}

//--------------------------------------------------------------
// Background music
//
// Optional BGM.ADP beside the boot ELF: an adpenc-produced mono PS-ADPCM
// track is uploaded once to SPU2 RAM, then the SPU2 loops it in hardware.
// Voice 23 is reserved exclusively for BGM; interface sounds use 0..22.
//--------------------------------------------------------------

#define BGM_MAX_BYTES (1024 * 1024)

/* SPU2 does not loop merely because the audsrv APCM header requests it.
 * The 16-byte ADPCM frames ALSO require a loop-start marker (6), a
 * repeating section (2), and an end/repeat marker (3). A one-shot-encoded
 * BGM can otherwise continue reading stale SPU RAM at the end of the sample,
 * producing a sustained buzzing/horn note. Work on our own EE copy only;
 * never rewrite a user's BGM.ADP sidecar. */
static int prepareBgmLoop(u8 *data, int size)
{
	int i, end;

	if (data == NULL || size < 16 + 32 || ((size - 16) & 15))
		return 0;
	end = size - 16;
	for (i = 16; i < size; i += 16) {
		/* Mask away old one-shot flags rather than keeping an incompatible
		 * loop/end combination from whichever encoder was used. */
		data[i + 1] = (i == 16) ? 6 : (i == end) ? 3 : 2;
	}
	data[6] = 1; /* APCM 'loop' byte */
	return 1;
}

static int loadBgmSidecar(void)
{
	char path[MAX_PATH], fixed[MAX_PATH];
	const char *dir = LaunchElfBootDir[0] ? LaunchElfBootDir : LaunchElfDir;
	int fd, size, got, n, closed;
	u8 *data;

	n = snprintf(path, sizeof(path), "%s%sBGM.ADP", dir,
	             dir[0] && dir[strlen(dir) - 1] != '/' && dir[strlen(dir) - 1] != '\\' && dir[strlen(dir) - 1] != ':' ? "/" : "");
	if (n < 0 || n >= sizeof(path))
		return 0;
	filerRootMcPollIdle();
	if (genFixPath(path, fixed) < 0)
		return 0;
	fd = genOpen(fixed, FIO_O_RDONLY);
	if (fd < 0)
		return 0; /* entirely optional, including on read-only boot devices */
	size = genLseek(fd, 0, SEEK_END);
	if (size < 32 || size > BGM_MAX_BYTES || (size & 15) || genLseek(fd, 0, SEEK_SET) < 0) {
		genClose(fd);
		return 0;
	}
	data = memalign(64, size + 64); /* padded for audsrv's DMA transfer */
	if (data == NULL) {
		genClose(fd);
		return 0;
	}
	memset(data, 0, size + 64);
	for (got = 0; got < size; got += n) {
		n = genRead(fd, data + got, size - got);
		if (n <= 0) break;
	}
	closed = genClose(fd);
	/* audsrv reads a 16-byte APCM header before transferring 16-byte ADPCM
	 * blocks. Only mono tracks with a valid SPU2 pitch fit our one voice. */
	if (got != size || closed < 0 || memcmp(data, "APCM", 4) || data[4] != 1 ||
	    data[5] != 1 || data[6] > 1 || data[7] != 0 ||
	    *(u32 *)(data + 8) == 0 || *(u32 *)(data + 8) > 0x3fff) {
		free(data);
		return 0;
	}
	/* The soundtrack is a permanent looping voice, unlike one-shot SFX.
	 * Normalize SPU2 per-frame loop control BEFORE audsrv DMA uploads it. */
	if (!prepareBgmLoop(data, size)) {
		free(data);
		return 0;
	}
	bgm_sample.buffer = NULL;
	if (audsrv_load_adpcm(&bgm_sample, data, size) != 0) {
		free(data);
		bgm_sample.buffer = NULL;
		return 0;
	}
	bgm_data = data;
	bgm_loaded = 1;
	return 1;
}

void dashBgmSetVolume(void)
{
	if (!soundAlive() || bgm_channel < 0 || dashIopParked())
		return;
	audsrv_adpcm_set_volume_and_pan(bgm_channel, bgmPlaybackVolume(), 0);
}

void dashBgmStop(void)
{
	bgm_tried = 0; /* an explicit off/on can discover a newly added sidecar */
	/* This is the user-facing Off action; the workaround keeps the existing
	 * voice at 5%. Maintain starts it later if the sidecar is not loaded yet. */
	dashBgmSetVolume();
}

void dashBgmStart(void)
{
	int ch;

	if (dashIopParked())
		return;

	/* A running voice can change gain during storage work without reading
	 * the sidecar or loading drivers. Never lose a live Off/volume change. */
	if (soundAlive() && bgm_channel >= 0) {
		dashBgmSetVolume();
		return;
	}
	if (dashWorkerIoBusy())
		return;
	if (!soundAlive() && !dashSoundInit())
		return;

	if (!bgm_loaded) {
		const char *dir = LaunchElfBootDir[0] ? LaunchElfBootDir : LaunchElfDir;
		/* Use only an already active boot stack. Reading music must not start
		 * storage drivers or reset the IOP merely to look for an optional file. */
		if (bgm_tried || !isPathDeviceStackLoaded(dir))
			return;
		bgm_tried = 1;
		if (!loadBgmSidecar())
			return;
	}

	/* Apply the override before key-on, avoiding a full-volume startup burst. */
	if (audsrv_adpcm_set_volume_and_pan(DASH_BGM_CHANNEL, bgmPlaybackVolume(), 0) != 0) {
		dashToast(DASH_TOAST_WARN, "Music unavailable: could not set playback volume");
		return;
	}
	ch = audsrv_ch_play_adpcm(DASH_BGM_CHANNEL, &bgm_sample);
	if (ch != DASH_BGM_CHANNEL) {
		dashToast(DASH_TOAST_WARN, "Music unavailable: reserved SPU2 voice busy");
		return;
	}
	bgm_channel = ch;
	dashBgmSetVolume();
}
