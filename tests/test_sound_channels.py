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
code += "\n".join(re.findall(r"^#define (?:DASH_BGM_CHANNEL|SND_\w+) .+$", source, re.M)) + "\n"
code += r'''
static audsrv_adpcm_t samples[DASH_SND_COUNT];
static struct { int sound,sound_vol,bgm,bgm_vol; } dashCfg={1,60,1,80};
static unsigned generation,sound_reboot_generation;
static int sound_ready=1,parked,bgm_channel=23,bgm_tried;
static int volumes[24],available[24],plays[24],volume_writes[24];
static int calls,automatic,init_calls,last_channel=-1,fail_sample;
static u64 now=1000;
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
    available[ch]=0;plays[ch]++;last_channel=ch;return ch;
}
static int audsrv_adpcm_set_volume_and_pan(int ch,int volume,int pan) {
    assert(!parked && generation==sound_reboot_generation && ch>=0 && ch<24 && !pan);
    assert(volume>=0 && volume<=100);volumes[ch]=volume;volume_writes[ch]++;return 0;
}
static int dashSoundInit(void) { init_calls++;return sound_ready; }
'''
for signature in ("static int soundAlive(", "void dashSoundApplyVolume(",
                  "void dashBgmSetVolume(", "void dashBgmStop("):
    code += function(signature)
if "static int soundPlayChannel(" in source:
    code += function("static int soundPlayChannel(")
code += function("void dashSoundPlay(")
# Exercise the real settings toggle: the volume left by Sound Off must be
# restored even when audsrv is already initialized for music.
start = settings.index("\t\tcase S_SOUND:", settings.index("static void setChoice("))
end = settings.index("\t\tcase S_SVOL:", start)
code += "enum { S_SOUND };\nstatic void setSound(int v) { switch(S_SOUND) {\n"
code += settings[start:end] + "}}\n"
code += r'''
static void reset(void) {
    dashCfg.sound=1;dashCfg.sound_vol=60;dashCfg.bgm=1;dashCfg.bgm_vol=80;
    generation=sound_reboot_generation=parked=0;sound_ready=1;
    bgm_channel=23;bgm_tried=1;calls=automatic=init_calls=fail_sample=0;last_channel=-1;
    memset(plays,0,sizeof(plays));memset(volume_writes,0,sizeof(volume_writes));
    for(int i=0;i<24;i++) {volumes[i]=60;available[i]=1;}
    volumes[23]=80;
    for(int i=0;i<DASH_SND_COUNT;i++)samples[i].buffer=&samples[i];
    now+=1000;
}
static void check_music_muted(int off) {
    reset();
    if(off) {dashCfg.bgm=0;dashBgmStop();}
    else {dashCfg.bgm_vol=0;dashBgmSetVolume();}
    assert(volumes[23]==0);
    int music_writes=volume_writes[23];
    /* Saturated SFX pool: never steal the muted music voice. */
    for(int i=0;i<23;i++)available[i]=0;
    dashSoundPlay(DASH_SND_CONFIRM);
    assert(!automatic && !plays[23] && last_channel==-1);
    /* A free SFX voice still plays at the interface volume. */
    available[18]=1;volumes[18]=0;
    dashSoundPlay(DASH_SND_CONFIRM);
    assert(last_channel==18 && volumes[18]==60 && !available[18]);
    assert(!plays[23] && volumes[23]==0 && volume_writes[23]==music_writes);
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
int main(void) {
    check_music_muted(0);check_music_muted(1);
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
    puts("PASS: muted/off/missing BGM cannot consume SFX, bounded voice contention, per-effect volume, sound toggles and IOP/error guards");
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
