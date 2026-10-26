"""Execute the production root memory-card presence poll with a mocked libmc.

Regression: a slot whose libmc requests keep failing (for example slot 2 while
the MX4SIO stack owns it) stayed "Checking..." forever, could not be opened
from the dashboard and also stopped slot 1 from being re-polled.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
filer = (root / "src/filer.c").read_text(encoding="utf-8")
files = (root / "src/dash_files.c").read_text(encoding="utf-8")
lib = (root / "src/dash_lib.c").read_text()
devices = (root / "src/dash_devices.c").read_text(encoding="utf-8")


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


state = "\n".join(line for line in filer.splitlines()
                  if line.startswith(("#define ROOT_MC_", "static int root_mc_", "static u64 root_mc_"))) + "\n"
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>
#define MAX_PATH 128
#define MAX_NAME 64
#define MAX_ENTRY 16
#define DASH_PATH_MAX 128
#define DASH_MAX_APPS 8
#define DASH_MAX_SCAN 4
#define SCAN_MAX_SUBDIRS 48
#define DASH_APP_TRANSIENT 2
#define MC_BROWSER_RETRY_COUNT 4
#define MC_BROWSER_RETRY_DELAY_US 100000
#define MX4SIO 1
#define sceMcResSucceed 0
#define sceMcResChangedCard -1
#define sceMcResFailDetect -3
#define sceMcFileAttrSubdir 0x20
#define stricmp strcmp
typedef struct { int AttrFile,FileSizeByte;char EntryName[32]; } sceMcTblGetDir;
typedef struct { char name[MAX_NAME];sceMcTblGetDir stats; } FILEINFO;
typedef struct { char path[DASH_PATH_MAX];int flags; } DashApp;
static int mctype_PSx,time_valid,size_valid,mx4sio_loaded,card_result,changed_card;
static int pending_result,dir_reads,prepared[2],retry_delays;
static void ensureMemoryCardPortAccessible(int p) { assert(p!=1 || !mx4sio_loaded);prepared[p]++; }
static void DelayThread(int us);
#define TRUE 1
#define FALSE 0
typedef unsigned long long u64;
static u64 now_ms;
static u64 Timer(void) { return now_ms; }
static int fail_port1_start, fail_port1_sync, pending_port = -1;
static int mcGetInfo(int port, int slot, int *type, int *free, int *format) {
    (void)slot; (void)format;
    if (port == 1 && fail_port1_start) return -1;
    if(type)*type=2;if(free)*free=4096;pending_port=port;
    pending_result=changed_card ? (changed_card--,-1) : card_result;return 0;
}
static int mcSync(int mode, int *cmd, int *result) {
    (void)mode; (void)cmd;
    if(pending_port<0)return -1;
    if (pending_port == 1 && fail_port1_sync) { pending_port = -1; return -1; }
    pending_port = -1;if(result)*result=pending_result;return 1;
}
static void DelayThread(int us) { retry_delays++;now_ms+=us/1000; }
static int mcGetDir(int p,int slot,const char *path,int mode,int max,sceMcTblGetDir *out) {
    (void)slot;(void)mode;assert(max>0 && !strcmp(path,"/APPS/*"));
    dir_reads++;memset(out,0,sizeof(*out));strcpy(out->EntryName,"BOOT.ELF");
    out->FileSizeByte=4096;pending_port=p;pending_result=1;return 0;
}
static void DashStorageProbeStatus(const char *s) { (void)s; }
#define DPRINTF(...) ((void)0)
'''
code += state
code += function(filer, "static int memoryCardResultIndicatesPresent(")
code += function(filer, "static void rootMcPollFailed(")
code += function(filer, "int pollRootMemoryCardDevices(")
code += function(filer, "int filerRootMcPresent(")
code += function(filer, "void filerRootMcPollIdle(void)\n{")
code += function(filer, "static int waitMemoryCardReadyForBrowse(")
code += function(filer, "int filerPrepareMemoryCardRead(")
code += function(filer, "int readMC(")
code += lib[lib.index("typedef struct\n{\n\tDashApp *old;"):lib.index("#define SCAN_MAX_SUBDIRS")]
job_end = lib.index("} ScanJob;") + len("} ScanJob;")
job_start = lib.rfind("typedef struct", 0, job_end)
code += lib[job_start:job_end] + "\n"
code += lib[lib.index("static ScanJob *scan_job"):lib.index("static void scanRun(")]
code += r'''
static DashApp dashApps[DASH_MAX_APPS];
static int dashAppCount,cache_saves;
static int dashLibScanStart(int interactive) { (void)interactive;assert(!"Unexpected repeat scan");return -1; }
static void dashArtFlushAll(void) {}
static int dashLibSaveCache(void) { cache_saves++;return 0; }
static void dashStrCopy(char *out,const char *in,int n) { snprintf(out,n,"%s",in); }
static void dashWorkerStatus(const char *s,int done,int total) { (void)s;(void)done;(void)total; }
static int isPathDeviceStackLoaded(const char *p) { return !strcmp(p,"mx4sio:/") && mx4sio_loaded; }
static int genCmpFileExt(const char *p,const char *ext) { const char *dot=strrchr(p,'.');return dot && !strcmp(dot+1,ext); }
static int wle_ascii_tolower(int c) { return tolower((unsigned char)c); }
static int getDir(const char *p,FILEINFO *out) { return readMC(p,out,MAX_ENTRY); }
static int titleCmp(const void *a,const void *b) { return strcmp(((const DashApp*)a)->path,((const DashApp*)b)->path); }
static void scanAddElf(ScanCtx *sc,const char *dir,const char *name) {
    assert(sc->nfresh<DASH_MAX_APPS);snprintf(sc->fresh[sc->nfresh++].path,DASH_PATH_MAX,"%s%s",dir,name);
}
'''
for sig in ("static int isElfName(", "static void scanDir(", "static int cheapToScan(",
            "static int prefixMatchNoCase(", "static int dirPrefixMatch(", "static void scanRun(",
            "static void scanFree(", "static void scanDone(", "int dashLibScanRunning(",
            "int dashLibApplyScan("):
    code += function(lib, sig)
code += r'''
static void run(int steps) { int i; for (i = 0; i < steps; i++) { pollRootMemoryCardDevices(); now_ms += 600; } }
int main(void) {
    /* Slot 2 never answers its sync: slot 1 still resolves and slot 2 stops
     * reporting "not polled yet" (-1) after the failure limit. */
    fail_port1_sync = 1;
    run(40);
    assert(filerRootMcPresent(0, NULL, NULL) == 1);
    assert(filerRootMcPresent(1, NULL, NULL) == -2);
    /* The slot recovers as soon as libmc answers again. */
    fail_port1_sync = 0;
    run(8);
    assert(filerRootMcPresent(1, NULL, NULL) == 1);

    /* Same for a request that cannot even be started. */
    fail_port1_start = 1;
    run(40);
    assert(filerRootMcPresent(0, NULL, NULL) == 1);
    assert(filerRootMcPresent(1, NULL, NULL) == 1); /* last known state kept */
    /* Startup scans precede the first root-card poll. Read the real MC
     * directory after the normal changed-card handshake and publish presence
     * so the completed library is visible without a trip through Files. */
    fail_port1_start=0;root_mc_polled[0]=root_mc_polled[1]=0;
    root_mc_failures[0]=root_mc_failures[1]=0;root_mc_poll_active=0;
    changed_card=1;ScanJob job;memset(&job,0,sizeof(job));
    FILEINFO entries[MAX_ENTRY];DashApp fresh[DASH_MAX_APPS];memset(fresh,0,sizeof(fresh));
    job.sc.files=entries;job.sc.fresh=fresh;job.ndirs=2;
    strcpy(job.dirs[0],"mc0:/APPS/");strcpy(job.dirs[1],"usb0:/APPS/");
    assert(filerRootMcPresent(0,NULL,NULL)==-1);scanRun(&job);
    assert(job.ok && job.sc.nfresh==1 && dir_reads==1 && prepared[0]==2);
    assert(!strcmp(fresh[0].path,"mc0:/APPS/BOOT.ELF"));
    assert(filerRootMcPresent(0,NULL,NULL)==1 && root_mc_known_type[0]==2);
    assert(!root_mc_failures[0] && !changed_card && retry_delays==1);

    /* Draining an in-flight status request precedes an ordinary browser read. */
    root_mc_poll_active=1;root_mc_poll_port=0;root_mc_poll_type=2;root_mc_poll_free=4096;
    pending_port=0;pending_result=0;
    assert(readMC("mc0:/APPS/",entries,MAX_ENTRY)==1 && !root_mc_poll_active);
    assert(root_mc_known_free[0]==4096); /* browsing keeps valid free-space data */

    /* A stale absence snapshot must not suppress a fresh scan. */
    int before=dir_reads;root_mc_polled[0]=1;root_mc_present[0]=0;
    job.sc.nfresh=0;scanRun(&job);
    assert(job.sc.nfresh==1 && dir_reads==before+1 && filerRootMcPresent(0,NULL,NULL)==1);
    /* Missing cards keep their cached apps; cold slot 2 must not reset an
     * active MX4SIO session from the directory worker. */
    DashApp old=fresh[0];job.sc.old=&old;job.sc.nold=1;
    card_result=sceMcResFailDetect;job.sc.nfresh=0;before=dir_reads;
    scanRun(&job);assert(job.sc.nfresh==1 && dir_reads==before);
    assert(!strcmp(fresh[0].path,old.path));
    job.sc.nold=0;job.sc.nfresh=0;card_result=0;
    mx4sio_loaded=1;strcpy(job.dirs[0],"mc1:/APPS/");
    scanRun(&job);assert(!job.sc.nfresh && dir_reads==before && !prepared[1]);
    mx4sio_loaded=0;card_result=sceMcResFailDetect;
    scanRun(&job);assert(!job.sc.nfresh && filerRootMcPresent(1,NULL,NULL)<0);
    /* The viewer must keep showing a scan in progress between worker
     * completion and main-loop publication of the new application index. */
    card_result=0;ScanJob *pending=calloc(1,sizeof(*pending));assert(pending);
    pending->ndirs=1;strcpy(pending->dirs[0],"mc0:/APPS/");
    pending->sc.fresh=calloc(DASH_MAX_APPS,sizeof(DashApp));
    pending->sc.files=calloc(MAX_ENTRY,sizeof(FILEINFO));
    assert(pending->sc.fresh && pending->sc.files);
    scan_job=pending;assert(dashLibScanRunning());scanRun(pending);scanDone(pending);
    assert(dashLibScanRunning() && !dashAppCount && !cache_saves);
    int interactive=-1;assert(dashLibApplyScan(&interactive)==1 && !interactive);
    assert(!dashLibScanRunning() && dashAppCount==1 && cache_saves==1);
    assert(!strcmp(dashApps[0].path,"mc0:/APPS/BOOT.ELF"));
    assert(dashLibApplyScan(NULL)==-2);
    puts("PASS: cold/stale MC readiness, retry/cache preservation, pending scan publication, browser drain, lazy USB and MX4SIO ownership");
    puts("PASS: an unresponsive memory-card slot cannot starve the other or stay Checking forever");
    return 0;
}
'''

compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="wle-mc-poll-") as tmp:
    harness = Path(tmp) / "poll.c"
    exe = Path(tmp) / "poll.exe"
    harness.write_text(code, encoding="utf-8")
    subprocess.run([compiler, "-std=gnu11", str(harness), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

# The dashboard must let the user open an unresolved slot: browsing runs
# ensureMemoryCardPortAccessible(), which switches the IOP away from MX4SIO.
selectable = function(files, "static int devSelectable(")
assert "DASH_DEV_BUSY" in selectable and "DI_MC" in selectable
assert "present == -2" in devices
print("PASS: unresolved memory-card slots stay selectable from Devices")
