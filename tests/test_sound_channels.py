"""Run production SFX routing and music controls with SPU2 voice contention."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_sound.c").read_text()
settings = (root / "src/dash_settings.c").read_text()
header = (root / "include/dash_sound.h").read_text()


def function(signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
typedef struct { void *buffer; } audsrv_adpcm_t;
'''
code += header[header.index("enum DashSound {"):header.index("};") + 2] + "\n"
stats_start = source.index("typedef struct SoundPlaybackStats {")
stats_end = source.index("static SoundPlaybackStats playback;", stats_start) + len("static SoundPlaybackStats playback;")
code += source[stats_start:stats_end] + "\n"
code += "\n".join(re.findall(r"^#define (?:DASH_BGM_CHANNEL|BGM_WORKAROUND_VOLUME|SND_\w+) .+$", source, re.M)) + "\n"
code += r'''
static audsrv_adpcm_t samples[DASH_SND_COUNT];
static struct { int sound,sound_vol,bgm,bgm_vol; } dashCfg={1,60,1,80};
static unsigned generation,sound_reboot_generation;
static int sound_ready=1,parked,bgm_channel=23,bgm_tried;
static int volumes[24],available[24],plays[24],volume_writes[24];
static int calls,automatic,init_calls,last_channel=-1,fail_sample,fail_volume,bad_channel_reply;
static u64 now=1000;
static u64 last_play_ms;
static u64 Timer(void) { return now; }
static unsigned getIopResetGeneration(void) { return generation; }
static int dashIopParked(void) { return parked; }
static int audsrv_ch_play_adpcm(int ch,audsrv_adpcm_t *sample) {
    assert(!parked && generation==sound_reboot_generation);
    assert(sample>=samples && sample<samples+DASH_SND_COUNT && sample->buffer);
    calls++;
    if(ch<0) {
        automatic++;
        /* Match audsrv: ENDX can report the looping music voice available. */
        for(ch=1;ch<24 && !available[ch];ch++);
    }
    if(ch>=24 || !available[ch] || fail_sample)return -1;
    if(bad_channel_reply)return 24; /* a positive result is not necessarily our channel */
    assert(volumes[ch]==dashCfg.sound_vol); /* gain must be set before key-on */
    available[ch]=0;plays[ch]++;last_channel=ch;last_play_ms=Timer();return ch;
}
static int audsrv_adpcm_set_volume_and_pan(int ch,int volume,int pan) {
    assert(!parked && generation==sound_reboot_generation && ch>=0 && ch<24 && !pan);
    if(fail_volume)return -1;
    assert(volume>=0 && volume<=100);volumes[ch]=volume;volume_writes[ch]++;return 0;
}
static int dashSoundInit(void) { init_calls++;return sound_ready; }
'''
for signature in ("int dashBgmRequestedVolume(", "static int bgmPlaybackVolume(",
                  "static int soundAlive(", "void dashSoundApplyVolume(",
                  "void dashBgmSetVolume(", "void dashBgmStop("):
    code += function(signature)
if "static int soundPlayChannel(" in source:
    code += function("static void soundPlayFailed(")
    code += function("void dashSoundGetStatus(")
    code += function("static int soundPlayChannel(")
code += function("void dashSoundPlay(")
# Exercise the real settings toggle: the volume left by Sound Off must be
# restored even when audsrv is already initialized for music.
start = settings.index("\t\tcase S_SOUND:", settings.index("static void setChoice("))
end = settings.index("\t\tcase S_SVOL:", start)
code += "enum { S_SOUND };\nstatic void setSound(int v) { switch(S_SOUND) {\n"
code += settings[start:end] + "}}\n"
code += "static void dashBgmStart(void) { dashBgmSetVolume(); }\n"
start = settings.index("\t\tcase S_BGM:", settings.index("static int choiceInfo("))
end = settings.index("\t\tcase S_START:", start)
code += "enum { S_BGM, S_BGMVOL };\nstatic const char *const pct_names[11];\n"
code += "static int musicChoice(int id,int *cur,const char *const **names) { switch(id) {\n"
code += settings[start:end] + "} return 0; }\n"
start = settings.index("\t\tcase S_BGM:", settings.index("static void setChoice("))
end = settings.index("\t\tcase S_START:", start)
code += "static void setMusic(int id,int v) { switch(id) {\n" + settings[start:end] + "}}\n"
code += r'''
static void reset(void) {
    dashCfg.sound=1;dashCfg.sound_vol=60;dashCfg.bgm=1;dashCfg.bgm_vol=80;
    generation=sound_reboot_generation=parked=0;sound_ready=1;
    memset(&playback,0,sizeof(playback));
    bgm_channel=23;bgm_tried=1;calls=automatic=init_calls=fail_sample=fail_volume=bad_channel_reply=0;last_channel=-1;
    memset(plays,0,sizeof(plays));memset(volume_writes,0,sizeof(volume_writes));
    for(int i=0;i<24;i++) {volumes[i]=60;available[i]=1;}
    volumes[23]=80;
    for(int i=0;i<DASH_SND_COUNT;i++)samples[i].buffer=&samples[i];
    now+=1000;
}
static void check_music_workaround(int off) {
    reset();
    if(off) {dashCfg.bgm=0;dashBgmStop();}
    else {dashCfg.bgm_vol=0;dashBgmSetVolume();}
    assert(volumes[23]==5 && dashBgmRequestedVolume()==0);
    int music_writes=volume_writes[23];
    /* Saturated SFX pool: never steal the workaround's music voice. */
    for(int i=0;i<23;i++)available[i]=0;
    dashSoundPlay(DASH_SND_CONFIRM);
    assert(!automatic && !plays[23] && last_channel==-1);
    /* A free SFX voice still plays at the interface volume. */
    available[18]=1;volumes[18]=0;
    dashSoundPlay(DASH_SND_CONFIRM);
    assert(last_channel==18 && volumes[18]==60 && !available[18]);
    assert(!plays[23] && volumes[23]==5 && volume_writes[23]==music_writes);
    /* Repeated effects share SFX headroom, then resume when a voice ends. */
    for(int id=0;id<DASH_SND_COUNT;id++) {
        for(int i=0;i<23;i++)available[i]=0;
        available[22]=1;now+=100;
        dashSoundPlay(id);
        assert(last_channel==22 && volumes[22]==60 && !automatic && !plays[23]);
    }
    dashCfg.bgm=1;dashCfg.bgm_vol=80;dashBgmSetVolume();
    assert(volumes[23]==80 && volumes[22]==60);
}
static void check_cursor_cadence(void) {
    /* These intervals cover normal and accelerated controller repeat, plus
     * separate quick direction presses. The old 45ms audio gate discarded
     * valid 40/41ms navigation events, regardless of the music settings. */
    const int intervals[]={83,50,45,44,41,40,33,17};
    for(int music=0;music<3;music++)
        for(unsigned rate=0;rate<sizeof(intervals)/sizeof(intervals[0]);rate++) {
            reset();
            if(music==1) {dashCfg.bgm=0;dashBgmStop();}
            if(music==2) {dashCfg.bgm_vol=0;dashBgmSetVolume();}
            int music_volume=volumes[23],music_writes=volume_writes[23];
            for(int event=0;event<60;event++) {
                now+=intervals[rate];
                /* A 36ms cursor clip has ended before a voice in the
                 * rotating six-voice pool can be reused at these rates. */
                for(int ch=8;ch<14;ch++)available[ch]=1;
                int previous_calls=calls;
                dashSoundPlay(DASH_SND_CURSOR);
                assert(calls==previous_calls+1 && last_play_ms==now);
                assert(last_channel>=8 && last_channel<14 && volumes[last_channel]==60);
                assert(volumes[23]==music_volume && volume_writes[23]==music_writes);
            }
        }
}
int main(void) {
    check_cursor_cadence();
    check_music_workaround(0);check_music_workaround(1);
    /* Both routes display Off/0 without writing the runtime 5% into settings.
     * Raising volume enables normal music; the toggle also escapes zero. */
    reset();setMusic(S_BGM,0);
    assert(dashCfg.bgm==0 && dashCfg.bgm_vol==80 && volumes[23]==5);
    int choice=-1;const char *const *names=NULL;
    assert(musicChoice(S_BGM,&choice,&names)==2 && choice==0);
    assert(musicChoice(S_BGMVOL,&choice,&names)==11 && choice==0);
    assert(dashCfg.bgm==0 && dashCfg.bgm_vol==80);
    setMusic(S_BGMVOL,4);
    assert(dashCfg.bgm==1 && dashCfg.bgm_vol==40 && volumes[23]==40);
    assert(musicChoice(S_BGM,&choice,&names)==2 && choice==1);
    setMusic(S_BGMVOL,0);
    assert(dashCfg.bgm==1 && dashCfg.bgm_vol==0 && volumes[23]==5);
    assert(musicChoice(S_BGM,&choice,&names)==2 && choice==0);
    setMusic(S_BGM,1);
    assert(dashCfg.bgm==1 && dashCfg.bgm_vol==10 && volumes[23]==10);
    /* Preferred cursor/transition pools and fixed effects remain deterministic. */
    reset();
    for(int id=0;id<DASH_SND_COUNT;id++) {
        for(int i=0;i<24;i++)available[i]=1;
        now+=100;dashSoundPlay(id);
        assert(last_channel>=0 && last_channel<23 && volumes[last_channel]==60 && !automatic);
    }
    /* No music sidecar: voice 23 is reserved even when it has never played. */
    reset();bgm_channel=-1;dashCfg.bgm=0;
    for(int i=0;i<23;i++)available[i]=0;
    dashSoundPlay(DASH_SND_CANCEL);assert(!plays[23] && !automatic);
    /* Volume and toggle changes do not tear down/restart the shared service. */
    reset();setSound(0);
    for(int i=0;i<23;i++)assert(volumes[i]==0);
    dashSoundPlay(DASH_SND_CONFIRM);assert(!calls && volumes[23]==80);
    setSound(1);assert(init_calls==1);
    for(int i=0;i<23;i++)assert(volumes[i]==60);
    dashCfg.sound_vol=30;dashSoundApplyVolume();
    dashSoundPlay(DASH_SND_CONFIRM);assert(volumes[last_channel]==30 && volumes[23]==80);
    /* Respect dead/parked IOPs, invalid IDs, failed uploads and driver errors. */
    reset();parked=1;dashSoundPlay(DASH_SND_CONFIRM);assert(!calls);
    parked=0;generation++;dashSoundPlay(DASH_SND_CONFIRM);assert(!calls);
    generation=0;dashSoundPlay(-1);dashSoundPlay(DASH_SND_COUNT);assert(!calls);
    samples[DASH_SND_CONFIRM].buffer=NULL;dashSoundPlay(DASH_SND_CONFIRM);assert(!calls);
    reset();fail_sample=1;dashSoundPlay(DASH_SND_CONFIRM);
    assert(!automatic && last_channel==-1 && calls<=23);
    reset();bad_channel_reply=1;dashSoundPlay(DASH_SND_CONFIRM);
    assert(!automatic && last_channel==-1 && calls==23);
    char report[512];dashSoundGetStatus(report,sizeof(report));assert(strstr(report,"(24)"));
    bad_channel_reply=0;available[DASH_SND_CONFIRM]=0;dashSoundPlay(DASH_SND_CONFIRM);
    dashSoundGetStatus(report,sizeof(report));
    assert(playback.started==1 && playback.failed==1 && strstr(report,"(24)"));
    reset();fail_volume=1;dashSoundPlay(DASH_SND_CONFIRM);assert(!calls);
    assert(playback.requests==1 && playback.failed==1 && !playback.started);
    dashSoundGetStatus(report,sizeof(report));
    assert(strstr(report,"Requested: 1; started: 0; failed: 1"));
    assert(strstr(report,"Confirm: audsrv rejected playback (-1)"));
    /* A later success must preserve the error code of the last failure. */
    fail_volume=0;dashSoundPlay(DASH_SND_CONFIRM);dashSoundGetStatus(report,sizeof(report));
    assert(playback.started==1 && playback.failed==1 && strstr(report,"(-1)"));
    /* Reports never issue RPC, even when the old service is gone/parked. */
    generation++;parked=1;int previous_calls=calls;
    dashSoundGetStatus(report,sizeof(report));
    assert(strstr(report,"Service: unavailable") && calls==previous_calls);
    char bounded[2]={0};dashSoundGetStatus(bounded,sizeof(bounded));assert(bounded[1]==0);
    dashSoundGetStatus(NULL,0);
    puts("PASS: every cursor event at 17-83ms intervals with music on/off/0%, gain before key-on, independent buses, voice contention and IOP/error guards");
}
'''
with tempfile.TemporaryDirectory(prefix="sound-channels-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    compiler = shutil.which("gcc") or shutil.which("clang")
    assert compiler, "Host C compiler required"
    binary = path / "test"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "test.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=10)
