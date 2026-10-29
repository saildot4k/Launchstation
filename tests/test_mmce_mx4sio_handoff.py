"""Exercise real MMCE/MX4SIO loaders through directory preparation.

Mock only IOP services: assert reset -> target-module load -> target access for
both MMCE slots, with refusal/failure checks in exFAT and legacy USB builds.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
init = (root / "src/init.c").read_text()
filer = (root / "src/filer.c").read_text()
device = (root / "src/filer_device.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MMCE 1
#define MX4SIO 1
#define TRUE 1
#define FALSE 0
#define DPRINTF(...) ((void)0)
#define STORAGE_STACK_DEFAULT 0
#define STORAGE_STACK_MMCE 1
#define STORAGE_STACK_MX4SIO 2
#define BLOCK_STACK_HDD 1
#define BLOCK_STACK_ATA 2
static int have_mmce,have_mx4sio,mx4sio_driver_running,storage_driver_stack_mode;
static int have_usbd,have_usb_mass,have_HDD_modules,block_storage_stack_mode,have_cdvd;
static int have_bdm,have_bdmfs,USB_mass_loaded,hddNparties[2];
#ifdef EXFAT
static int have_ata_bd,pccf_loaded;
#endif
static char mmceman_irx[1],mx4sio_bd_irx[1];
static int size_mmceman_irx=1,size_mx4sio_bd_irx=1;
static int resets,modules,reads,worker,allow_reset=1,module_failure,core_ready;
static int events[16],nevents,pending_mc;
enum {EV_RESET=1,EV_MMCE,EV_MX4SIO,EV_READ};
static void event(int e) { assert(nevents<16);events[nevents++]=e; }
static void filerRootMcPollIdle(void) { pending_mc=0; }
static void ensureCoreIoStackReady(void) { core_ready=1; }
static void showLoadingModulesMsg(const char *name) { assert(name); }
static void resetRuntimeDeviceState(int show) {
    assert(show==TRUE);
    if(!allow_reset || worker)return;
    filerRootMcPollIdle();event(EV_RESET);resets++;
    have_mmce=have_mx4sio=mx4sio_driver_running=0;
    have_usbd=have_usb_mass=have_bdm=have_bdmfs=USB_mass_loaded=0;
    storage_driver_stack_mode=STORAGE_STACK_DEFAULT;core_ready=1;
}
static int SifExecModuleBuffer(void *image,int size,int argc,void *args,int *result) {
    assert(core_ready && size==1 && !argc && !args && !pending_mc && !worker);
    if(image==mmceman_irx) {
        assert(!mx4sio_driver_running && !have_mx4sio);
        event(EV_MMCE);
    } else {
        assert(image==mx4sio_bd_irx && !have_mmce);event(EV_MX4SIO);
    }
    modules++;*result=module_failure?-1:0;return module_failure?-1:1;
}
static int loadBdmCoreModules(void) { have_bdm=have_bdmfs=1;return 1; }
static void loadUsbModules(void) { have_usbd=have_usb_mass=USB_mass_loaded=1; }
static void resetUsbMassScanState(void) { }
static int loadHddModules(void) { return 1; }
static int loadAtaModules(void) { return 1; }
static void loadCdModules(void) { }
static int isPcCardCfPath(const char *p) { (void)p;return 0; }
static int loadPcCardCfModules(void) { return 0; }
static int isPcCardCfOnline(void) { return 0; }
static int getHddDeviceFromPath(const char *p,char *dev) { (void)p;(void)dev;return -1; }
static int getHddUnitFromDevice(const char *dev) { (void)dev;return -1; }
static void setPartyListForDevice(const char *dev) { (void)dev; }
'''
for source, signature in (
    (init, "int isPathDeviceStackLoaded(const char *path)\n{"),
    (init, "void ensureMemoryCardPortAccessible(int port)\n{"),
    (init, "static int switchStorageDriverStack(int target_mode)\n{"),
    (init, "int loadMmceModules(void)\n{"),
    (init, "int loadMmceModulesForGameID(void)\n{"),
    (init, "int loadMx4sioModules(void)\n{"),
    (device, "static int isMc1Path("),
    (device, "int ensurePathDeviceStackReady("),
    (filer, "int filerDirReadNeedsPrep("),
    (filer, "int filerPrepareDirRead("),
):
    code += function(source, signature)
code += r'''
static void clear_counts(void) { resets=modules=reads=nevents=0; }
static void cold(void) {
    have_mmce=have_mx4sio=mx4sio_driver_running=0;
    storage_driver_stack_mode=STORAGE_STACK_DEFAULT;
    worker=module_failure=pending_mc=core_ready=0;allow_reset=1;clear_counts();
}
static void read_target(const char *path) {
    assert(isPathDeviceStackLoaded(path));reads++;event(EV_READ);
}
static void start_source(const char *path) {
    cold();assert(filerPrepareDirRead(path));read_target(path);clear_counts();
}
int main(void) {
    const char *mmce[]={"mmce0:/","mmce1:/"};
    for(int slot=0;slot<2;slot++)for(int reverse=0;reverse<2;reverse++) {
        const char *src=reverse?mmce[slot]:"mx4sio:/";
        const char *dst=reverse?"mx4sio:/":mmce[slot];
        const int target_event=reverse?EV_MX4SIO:EV_MMCE;
        start_source(src);pending_mc=1;
        assert(filerDirReadNeedsPrep(dst));
        assert(filerPrepareDirRead(dst));read_target(dst);
        assert(resets==1 && modules==1 && reads==1 && nevents==3);
        assert(events[0]==EV_RESET && events[1]==target_event && events[2]==EV_READ);
        assert(!isPathDeviceStackLoaded(src) && !filerDirReadNeedsPrep(dst));
        assert(filerPrepareDirRead(dst) && resets==1 && modules==1);
        assert(filerPrepareDirRead(src));read_target(src);
        assert(resets==2 && events[3]==EV_RESET && events[5]==EV_READ);

        /* A refused/worker-thread reset leaves the source owner intact and
         * never executes a target module or starts target I/O. */
        for(int on_worker=0;on_worker<2;on_worker++) {
            start_source(src);worker=on_worker;allow_reset=0;
            assert(!filerPrepareDirRead(dst));
            assert(!resets && !modules && !reads && !nevents);
            assert(isPathDeviceStackLoaded(src) && !isPathDeviceStackLoaded(dst));
        }
        /* Failure after retiring the old stack cannot authorize a read.
         * A retry may load into the already-clean session without a reset. */
        start_source(src);module_failure=1;
        assert(!filerPrepareDirRead(dst) && resets==1 && modules==1 && !reads);
        assert(!isPathDeviceStackLoaded(dst));module_failure=0;
        assert(filerPrepareDirRead(dst) && resets==1 && modules==2);
    }
    /* Both ports share one MMCE driver and stay usable in one IOP session. */
    start_source(mmce[0]);assert(filerPrepareDirRead(mmce[1]));read_target(mmce[1]);
    assert(!resets && !modules && reads==1 && isPathDeviceStackLoaded(mmce[0]));
    /* Automatic Game ID requests preserve a live MX4SIO source. */
    start_source("mx4sio:/");assert(!loadMmceModulesForGameID());
    assert(!resets && !modules && !reads && isPathDeviceStackLoaded("mx4sio:/"));
    puts("PASS: MMCE0/MMCE1 <-> MX4SIO reset before load/read; refused/failed switches stop, MMCE ports share a session");
}
'''
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-mmce-mx4sio-") as tmp:
    source = Path(tmp) / "handoff.c"
    source.write_text(code)
    for exfat in (False, True):
        executable = Path(tmp) / ("exfat" if exfat else "legacy")
        subprocess.run([compiler,"-std=c99","-Wall","-Wextra","-Werror","-Wno-unused-function",
                        *(["-DEXFAT"] if exfat else []),str(source),"-o",str(executable)],check=True)
        subprocess.run([str(executable)],check=True)
