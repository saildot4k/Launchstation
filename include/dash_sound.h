//--------------------------------------------------------------
//File name:   dash_sound.h
//Dashboard UI sounds (audsrv ADPCM one-shots). Every call is a
//safe no-op when sound is off or the driver failed to start.
//--------------------------------------------------------------
#ifndef DASH_SOUND_H
#define DASH_SOUND_H

enum DashSound {
	DASH_SND_CURSOR = 0,
	DASH_SND_CONFIRM,
	DASH_SND_CANCEL,
	DASH_SND_TRANSITION,
	DASH_SND_MESSAGE,
	DASH_SND_BOOT,
	DASH_SND_CONNECT,
	DASH_SND_DISCONNECT,
	DASH_SND_COUNT
};

int dashSoundInit(void);
void dashSoundShutdown(void);
void dashSoundSuspend(void); /* mute while a launch can still return */
void dashSoundPlay(int id);
void dashSoundApplyVolume(void);
void dashSoundGetStatus(char *out, int out_size); /* cached counters/status; no IO */
void dashBgmStart(void);
void dashBgmStop(void); /* settings Off: retains the 10% playback workaround */
int dashBgmRequestedVolume(void); /* user-visible gain; zero when music is Off */
void dashBgmSetVolume(void); /* apply requested gain or the 10% runtime override */
/* Main loop: restores audio and the music workaround after an IOP reboot,
 * even with both visible sound switches Off. Tries once per IOP session. */
void dashSoundMaintain(void);

#endif
