//--------------------------------------------------------------
//File name:   dash_sound.c
//Dashboard SFX: the shared worker loads audsrv and uploads ADP samples.
//The UI publishes readiness and plays them on ADPCM channels. Degrades to silent no-ops on any
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
static void *bgm_data; /* retain sidecar storage until audio shutdown */
static int bgm_channel = -1;
static unsigned int sound_reboot_generation; /* reset epoch when audsrv was started */
static unsigned int sound_tried_generation = (unsigned int)-1; /* last automatic attempt */
static int sound_retry;

/* The UI owns this slot until submission, then the single storage worker
 * owns its RPC calls and result buffers until soundJobDone publishes them.
 * UI settings may change during a load: the worker reads only this snapshot.
 * audsrv uses sample-object addresses as IDs, so uploads use the permanent
 * samples/bgm_sample objects; UI sample access is excluded until completion. */
typedef struct SoundJob {
	unsigned int generation;
	int initialize, effects, effects_volume;
	char directory[MAX_PATH];
	int ready, failed_samples, bgm_attempted;
	void *bgm_data;
	char warning[128];
} SoundJob;
static SoundJob sound_job;
static int sound_job_id;
static int sound_closing, sound_volume_pending, sound_boot_pending, sound_music_pending;

static int loadBgmSidecar(SoundJob *job);
static void soundJobRun(void *arg);
static void soundJobDone(void *arg);

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
#define BGM_WORKAROUND_VOLUME 10
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

/* Physical consoles still lose/cut SFX when music is muted. Match the reported
 * working Music On / 10% setting; never write this gain to settings.
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

/* No UI entry point may touch audsrv while the worker owns its RPC client.
 * A queued job reserves ownership too, so a later dispatch cannot overlap a
 * UI call that cooperatively renders while waiting for its RPC. */
static int soundRpcReady(void)
{
	return !sound_job_id && !sound_closing && soundAlive() && !DashIoBusy();
}

static void soundJobRun(void *arg)
{
	SoundJob *job = (SoundJob *)arg;
	int i, r;

	if (job->generation != getIopResetGeneration())
		return;
	if (job->initialize) {
		/* These modules do not reset the IOP or replace storage drivers. */
		if (SifExecModuleBuffer(libsd_irx, size_libsd_irx, 0, NULL, &r) < 0 || r < 0) {
			snprintf(job->warning, sizeof(job->warning), "Sound unavailable: libsd would not start");
			return;
		}
		if (SifExecModuleBuffer(audsrv_irx, size_audsrv_irx, 0, NULL, &r) < 0 || r < 0) {
			snprintf(job->warning, sizeof(job->warning), "Sound unavailable: audsrv would not start");
			return;
		}
		if (audsrv_init() != 0) {
			snprintf(job->warning, sizeof(job->warning), "Sound unavailable: audsrv init failed");
			return;
		}
		if (audsrv_adpcm_init() != 0) {
			audsrv_quit();
			snprintf(job->warning, sizeof(job->warning), "Sound unavailable: adpcm init failed");
			return;
		}
		for (i = 0; i < DASH_SND_COUNT; i++) {
			if (audsrv_load_adpcm(&samples[i], blob_data(i), blob_size(i)) != 0) {
				samples[i].buffer = NULL;
				job->failed_samples++;
			}
		}
		/* Keep the healthy service for music even if all effects failed. */
		if (job->effects && job->failed_samples == DASH_SND_COUNT)
			snprintf(job->warning, sizeof(job->warning), "Sound unavailable: no samples loaded");
		else if (job->effects && job->failed_samples)
			snprintf(job->warning, sizeof(job->warning), "%d sound effect%s unavailable",
			         job->failed_samples, job->failed_samples == 1 ? "" : "s");
		if (job->effects)
			for (i = 0; i < SND_SFX_CH_MAX; i++)
				audsrv_adpcm_set_volume_and_pan(i, job->effects_volume, 0);
	}
	job->ready = 1;
	/* Optional music may use only an already resident boot storage stack. */
	if (isPathDeviceStackLoaded(job->directory)) {
		job->bgm_attempted = 1;
		loadBgmSidecar(job);
	}
}

static void soundJobDone(void *arg)
{
	SoundJob *job = (SoundJob *)arg;

	/* Completion runs on the UI thread, before the next queued job starts. */
	sound_job_id = 0;
	if (job->generation != getIopResetGeneration()) {
		free(job->bgm_data);
		job->bgm_data = NULL;
		return;
	}
	if (job->initialize && job->ready) {
		sound_reboot_generation = job->generation;
		sound_ready = 1;
		if (job->effects != dashCfg.sound || job->effects_volume != dashCfg.sound_vol)
			sound_volume_pending = 1;
	}
	if (job->initialize && !job->ready)
		sound_boot_pending = 0;
	if (job->bgm_attempted)
		bgm_tried = 1;
	if (job->bgm_data != NULL) {
		bgm_data = job->bgm_data;
		job->bgm_data = NULL;
		bgm_loaded = 1;
		sound_music_pending = 1;
	}
	if (job->warning[0])
		dashToast(DASH_TOAST_WARN, job->warning);
	if (!sound_closing)
		dashSoundMaintain();
}

int dashSoundInit(void)
{
	if (!sound_job_id && !soundAlive())
		sound_retry = 1; /* an explicit settings action may retry a failed start */
	dashSoundMaintain();
	return soundRpcReady();
}

void dashSoundRequestBoot(void)
{
	if (!sound_closing)
		sound_boot_pending = 1;
}

void dashSoundMaintain(void)
{
	const char *directory;
	int initialize;

	if (sound_closing || sound_job_id || dashIopParked() || dashIoBusy())
		return;
	initialize = !soundAlive();
	directory = LaunchElfBootDir[0] ? LaunchElfBootDir : LaunchElfDir;
	if (initialize) {
		if (sound_tried_generation == getIopResetGeneration() && !sound_retry)
			return;
		/* Discard only EE state from a dead IOP; never call its stale client. */
		if (sound_ready)
			dashSoundShutdown();
	} else if (bgm_loaded || bgm_tried || !isPathDeviceStackLoaded(directory)) {
		if (!soundRpcReady())
			return;
		if (sound_volume_pending) {
			dashSoundApplyVolume();
			dashBgmSetVolume();
		}
		if (bgm_loaded && sound_music_pending) {
			sound_music_pending = 0;
			dashBgmStart();
		}
		if (sound_boot_pending) {
			sound_boot_pending = 0;
			dashSoundPlay(DASH_SND_BOOT);
		}
		return;
	}
	memset(&sound_job, 0, sizeof(sound_job));
	sound_job.generation = getIopResetGeneration();
	sound_job.initialize = initialize;
	sound_job.effects = dashCfg.sound;
	sound_job.effects_volume = dashCfg.sound_vol;
	snprintf(sound_job.directory, sizeof(sound_job.directory), "%s", directory);
	sound_job_id = dashWorkerSubmit("Preparing audio", DASH_JOB_VISIBLE,
	                               soundJobRun, soundJobDone, &sound_job);
	if (sound_job_id < 0) {
		sound_job_id = 0; /* retry submission later; no blocking UI fallback */
		return;
	}
	if (initialize) {
		sound_tried_generation = sound_job.generation;
		sound_retry = 0;
	}
}

void dashSoundShutdown(void)
{
	/* Launch/reset cannot destroy a live worker RPC or its upload buffer.
	 * Suppress automatic restarts while the queue is being drained. */
	sound_closing = 1;
	if (sound_job_id)
		dashWorkerAwait(sound_job_id, "Finishing audio", 0);
	sound_boot_pending = 0;
	sound_music_pending = 0;
	sound_volume_pending = 0;
	if (soundAlive()) {
		/*
		 * BGM is a looping SPU2 ADPCM voice. Merely setting its volume to
		 * zero and dropping the EE RPC client can leave the IOP/SPU2 voice
		 * alive across a keep-IOP ExecPS2 handoff. audsrv_adpcm_init() is the
		 * library's hard reset for ADPCM state: it stops every voice and frees
		 * the uploaded sample list before audsrv_quit() releases RPC.
		 */
		/* Settings Off keeps low-volume playback; a real shutdown must mute instead. */
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
	sound_closing = 0;
}

void dashSoundSuspend(void)
{
	int i;

	if (!soundRpcReady())
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

	if (!soundRpcReady()) {
		sound_volume_pending = 1;
		return;
	}
	sound_volume_pending = 0;
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
	         sound_job_id ? "loading" : soundAlive() ? "ready" : "unavailable",
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
	if (!soundRpcReady()) {
		soundPlayFailed(id, 0, "IOP busy");
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

static int loadBgmSidecar(SoundJob *job)
{
	char path[MAX_PATH], fixed[MAX_PATH];
	const char *dir = job->directory;
	int fd, size, got, n, closed;
	u8 *data;

	n = snprintf(path, sizeof(path), "%s%sBGM.ADP", dir,
	             dir[0] && dir[strlen(dir) - 1] != '/' && dir[strlen(dir) - 1] != '\\' && dir[strlen(dir) - 1] != ':' ? "/" : "");
	if (n < 0 || n >= (int)sizeof(path))
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
	job->bgm_data = data;
	return 1;
}

void dashBgmSetVolume(void)
{
	if (!soundRpcReady()) {
		sound_volume_pending = 1;
		return;
	}
	if (bgm_channel < 0)
		return;
	audsrv_adpcm_set_volume_and_pan(bgm_channel, bgmPlaybackVolume(), 0);
}

void dashBgmStop(void)
{
	bgm_tried = 0; /* an explicit off/on can discover a newly added sidecar */
	/* This is the user-facing Off action; the workaround keeps the existing
	 * voice at the workaround gain. Maintain starts it later if the sidecar
	 * is not loaded yet. */
	dashBgmSetVolume();
}

void dashBgmStart(void)
{
	int ch;

	if (!soundRpcReady()) {
		sound_music_pending = 1;
		dashSoundMaintain();
		return;
	}
	sound_music_pending = 0;
	if (bgm_channel >= 0) {
		dashBgmSetVolume();
		return;
	}
	if (!bgm_loaded) {
		dashSoundMaintain(); /* queues the read/upload; never loads on the UI */
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
