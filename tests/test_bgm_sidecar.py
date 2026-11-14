"""Execute full background music loading/lifetime and real boot path guards."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from dash_sound_harness import run

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_sound.c").read_text()


def function(signature, text=source):
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


assert "EMBED_FILE(music_adpcm" not in (root / "src/embed_blobs.S").read_text()
assert "music_adpcm.o" not in (root / "Makefile").read_text()
assert "music_adpcm.s:" not in (root / "embed.make").read_text()
track = (root / "res/music.sad").read_bytes()
assert track[:8] == b"APCM\x01\x01\x01\x00" and len(track) % 16 == 0

run(r'''
static void reset_music(void) {
    reset();sound_ready=1;sound_reboot_generation=generation;
}
static void start_music(void) {dashBgmStart();settle();}
int main(void) {
    for(int effects=0;effects<2;effects++)for(int music=0;music<2;music++)
    for(int volume=0;volume<=40;volume+=40) {
        reset_music();dashCfg.sound=effects;dashCfg.bgm=music;dashCfg.bgm_vol=volume;
        start_music();assert(bgm_channel==23 && volumes[23]==(music && volume?volume:10));
        assert(opens==1 && music_uploads==1 && plays[23]==1);
        for(int i=0;i<20;i++)dashSoundMaintain();
        assert(submitted==1 && opens==1 && music_uploads==1 && plays[23]==1);
        assert(dashCfg.sound==effects && dashCfg.bgm==music && dashCfg.bgm_vol==volume);
        dashSoundSuspend();assert(volumes[23]==0);
        dashSoundMaintain();assert(volumes[23]==0);
        start_music();assert(volumes[23]==(music && volume?volume:10));
        dashSoundShutdown();assert(volumes[23]==0 && !allocations);
    }
    reset_music();start_music();assert(!strcmp(opened,"usb0:/BOOT/BGM.ADP"));
    assert(track[17]==0 && track[33]==0 && track[49]==0); /* Never change disk data. */
    int old_quits=quits,old_resets=adpcm_calls;
    dashSoundSuspend();dashSoundMaintain();dashSoundApplyVolume();start_music();
    assert(quits==old_quits && adpcm_calls==old_resets && music_uploads==1 && plays[23]==1);
    /* Volume changes defer safely during other worker IO and apply once idle. */
    active=1;int before=rpc_calls;dashCfg.bgm=0;dashBgmStart();
    assert(before==rpc_calls && volumes[23]==80);
    dashCfg.bgm=1;dashCfg.bgm_vol=30;dashBgmSetVolume();assert(before==rpc_calls);
    active=0;dashSoundMaintain();assert(volumes[23]==30 && plays[23]==1);
    dashCfg.bgm_vol=0;start_music();assert(volumes[23]==10 && plays[23]==1);
    /* The path and result buffer belong to the queued job, until UI completion. */
    reset_music();dashBgmStart();strcpy(LaunchElfBootDir,"mc1:/OTHER/");
    assert(!opens && !music_uploads && !bgm_loaded);settle();
    assert(!strcmp(opened,"usb0:/BOOT/BGM.ADP") && bgm_loaded && allocations==1);
    reset_music();exists=0;start_music();
    for(int i=0;i<20;i++)dashSoundMaintain();assert(opens==1 && !music_uploads && sound_ready);
    exists=1;dashBgmStop();start_music();assert(opens==2 && plays[23]==1);
    reset_music();stack_loaded=0;dashBgmStart();assert(!submitted && !bgm_tried);
    stack_loaded=1;dashSoundMaintain();settle();assert(opens==1 && plays[23]==1);
    reset_music();parked=1;dashBgmStart();assert(!opens && !submitted);parked=0;
    for(int i=0;i<9;i++) {
        reset_music();
        switch(i) {
            case 0:file_bytes=32;break;
            case 1:track[0]='X';break;
            case 2:track[4]=0;break;
            case 3:track[5]=2;break;
            case 4:track[8]=track[9]=0;break;
            case 5:file_size=31;break;
            case 6:file_size=BGM_MAX_BYTES+16;break;
            case 7:close_error=1;break;
            case 8:track[9]=0xff;break;
        }
        start_music();assert(!music_uploads && !plays[23] && !allocations && bgm_tried);
        dashSoundMaintain();assert(opens==1 && submitted==1);
    }
    reset_music();upload_error=1;start_music();assert(music_uploads==1 && !plays[23] && !allocations);
    reset_music();volume_error=1;start_music();assert(!plays[23] && bgm_channel<0 && warnings==1);
    for(int i=0;i<20;i++)dashSoundMaintain();assert(warnings==1 && !plays[23]);
    reset_music();bad_channel_reply=1;start_music();assert(plays[23]==1 && bgm_channel<0);
    for(int i=0;i<20;i++)dashSoundMaintain();assert(plays[23]==1 && warnings==1);
    reset_music();start_music();generation++;dashSoundMaintain();settle();
    assert(allocations==1 && opens==2 && music_uploads==2 && plays[23]==2 && soundAlive());
    dashSoundShutdown();assert(!allocations && !bgm_sample.buffer && !bgm_loaded);
    reset_music();dashCfg.sound=0;start_music();assert(plays[23]==1);
    reset();
    puts("PASS: background sidecar loading, loop validation, live setting deferral, snapshots, missing/invalid files, one-shot failures and cleanup");
    return 0;
}
''', 'sidecar')
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"

# Exercise real boot-path preparation and residency guards as well as the
# mocked music IO above. Disc boot reads must not use the writable CNF path.
startup = (root / "src/main_startup.c").read_text()
init = (root / "src/init.c").read_text()
boot_header = (root / "include/main_startup.h").read_text()
bootcode = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 1024
#define MAX_NAME 256
#define EXFAT 1
#define MMCE 1
#define MX4SIO 1
#define UDPFS 1
#define ETH 1
#define XFROM 1
#define DVRP 1
#define DPRINTF(...) ((void)0)
#define BLOCK_STACK_HDD 1
#define BLOCK_STACK_ATA 2
#define STORAGE_STACK_MMCE 1
#define STORAGE_STACK_MX4SIO 2
static char LaunchElfDir[MAX_PATH], LaunchElfBootDir[MAX_PATH], LastDir[MAX_PATH];
static int console_is_PSX;
static int have_usbd, have_usb_mass, have_HDD_modules, block_storage_stack_mode;
static int have_ps2host, have_ps2ip, have_ps2smap, ps2dev9_loaded;
static int have_Flash_modules, have_DVRP_HDD_modules, have_ata_bd, have_bdmfs;
static int have_mmce, have_mx4sio, storage_driver_stack_mode, have_udpfs_ioman, have_cdvd;
static int mx4sio_driver_running;
static int have_bdm, pccf_loaded;
static int isPcCardCfPath(const char *path) { (void)path; return 0; }
"""
bootcode += boot_header[boot_header.index("enum BOOT_DEVICE {"):boot_header.index("enum BOOT_DEVICE prepare")]
signatures = ("static void normalizeBootPath(", "static int isSlashRootedBootPathDevice(",
              "static int isDevicePathTerminator(", "static int isBootUsbMassPath(",
              "static int isBootAtaPath(", "static int isBootHddPath(",
              "static int isBootXfromPath(", "static void buildBootBlockPath(")
# Start after the forward declarations, so extraction takes the definitions.
definitions = startup[startup.index("static void normalizeBootPath(char *path)\n{"):]
for sig in signatures:
    bootcode += function(sig, definitions).split("{", 1)[0] + ";\n"
for sig in signatures:
    bootcode += function(sig, definitions)
bootcode += function("enum BOOT_DEVICE prepareBootDeviceAndPath(", startup)
bootcode += function("int isPathDeviceStackLoaded(", init)
bootcode += r"""
int main(void) {
    char path[MAX_PATH];
    assert(prepareBootDeviceAndPath("cdrom0:\\APPS\\BOOT.ELF;1",path,sizeof(path))==BOOT_DEVICE_CDVD);
    assert(!strcmp(LaunchElfBootDir,"cdfs:/APPS/"));
    assert(!strcmp(LaunchElfDir,"mc0:/SYS-CONF/"));
    assert(prepareBootDeviceAndPath("cdfs:/BOOT.ELF",path,sizeof(path))==BOOT_DEVICE_CDVD);
    assert(!strcmp(LaunchElfBootDir,"cdfs:/"));
    assert(prepareBootDeviceAndPath("usb0:/APPS/BOOT.ELF",path,sizeof(path))==BOOT_DEVICE_MASS);
    assert(!strcmp(LaunchElfBootDir,"usb0:/APPS/") && !strcmp(LaunchElfDir,LaunchElfBootDir));
    assert(prepareBootDeviceAndPath("hdd0:__common:pfs:/BOOT/BOOT.ELF",path,sizeof(path))==BOOT_DEVICE_HDD);
    assert(!strcmp(LaunchElfBootDir,"hdd0:/__common/BOOT/"));
    assert(!isPathDeviceStackLoaded("cdfs:/") && !isPathDeviceStackLoaded("pfs0:/"));
    have_cdvd=1; assert(isPathDeviceStackLoaded("cdfs:/") && isPathDeviceStackLoaded("cdrom0:/"));
    have_HDD_modules=1; block_storage_stack_mode=BLOCK_STACK_HDD;
    assert(isPathDeviceStackLoaded("hdd0:/") && isPathDeviceStackLoaded("pfs0:/"));
    have_ps2host=have_ps2ip=have_ps2smap=ps2dev9_loaded=1;
    assert(isPathDeviceStackLoaded("host:/"));
    have_Flash_modules=have_DVRP_HDD_modules=1;
    assert(isPathDeviceStackLoaded("xfrom0:/") && isPathDeviceStackLoaded("dvr_pfs0:/"));
    assert(!isPathDeviceStackLoaded("unknown:/"));
    puts("PASS: actual USB/HDD/disc boot folders, writable disc config fallback, active-stack aliases");
}
"""
with tempfile.TemporaryDirectory(prefix="wle-bgm-") as tmp:
    for name, harness_code in (("boot", bootcode),):
        harness = Path(tmp) / f"{name}.c"
        exe = Path(tmp) / f"{name}.exe"
        harness.write_text(harness_code)
        subprocess.run([compiler, "-std=gnu11", str(harness), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
