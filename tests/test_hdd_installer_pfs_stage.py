"""PFS cache preparation/capacity, including resumes and >4 GiB totals."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "src/hdd_install_ps2.c").read_text()
ui = (root / "src/dash_hdd_install.c").read_text()


def function(source, signature):
    a = source.index(signature)
    b = source.index("{", a) + 1
    depth = 1
    while depth:
        depth += (source[b] == "{") - (source[b] == "}")
        b += 1
    return source[a:b] + "\n"


code = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hdd_install.h"
#define ETH
#define WLE_NATIVE_HTTPS
#define PDIOC_ZONEFREE 1
#define PDIOC_ZONESZ 2
static int network=1,hdd=1,free_zones=131072,zone_size=8192;
static int cached,checks,stats;
static char last_log[256];
static int ensureDashboardIpNetworkReady(void){return network;}
static const char *dashboardIpNetworkError(void){return "network failed";}
static int loadHddModules(void){return hdd;}
void hddInstallLog(const char *fmt,...){va_list args;va_start(args,fmt);vsnprintf(last_log,sizeof(last_log),fmt,args);va_end(args);}
static int fileXioDevctl(const char *dev,int cmd,void *a,int n,void *b,int m){
 assert(!strcmp(dev,"pfs2:")&&!a&&!b&&!n&&!m);stats++;
 assert(cmd==PDIOC_ZONEFREE||cmd==PDIOC_ZONESZ);return cmd==PDIOC_ZONEFREE?free_zones:zone_size;
}
static int checkFileSize(HddInstall *in,const char *name,uint32_t size){
 assert(!strcmp(in->stage,"pfs2:/tmp")&&name&&size);checks++;
 return cached?0:-EIO;
}
'''
code += function(native, "static int launcherLicense(")
code += function(native, "static int launcherStageName(")
code += function(native, "static int stageSpace(")
code += function(ui, "int dashHddInstallPrepareStorage(")
code += r'''
int main(void){
 char name[192];
 assert(!launcherStageName("scripts/assets/neutrino/modules/ata_bd.irx",name)&&!strcmp(name,"Neutrino/modules/ata_bd.irx"));
 assert(!launcherStageName("scripts/assets/OPL/LNG/lang_French.lng",name)&&!strcmp(name,"OPL/LNG/lang_French.lng"));
 assert(!launcherStageName("icons/art/APP_NHDDL.png",name)&&!strcmp(name,"Icons/art/APP_NHDDL.png"));
 const char *bad[]={"scripts/assets/OPL/../escape","scripts/assets/OPL//escape","scripts/assets/OPL/./escape",
                    "scripts/assets/OPL/trailing/","scripts/assets/OPL/","scripts/assets/OPL/x:bad","other/root/file"};
 for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(launcherStageName(bad[i],name)==-EINVAL);
 char longpath[256];memset(longpath,'a',sizeof(longpath));memcpy(longpath,"scripts/assets/neutrino/",24);longpath[255]=0;
 assert(launcherStageName(longpath,name)==-ENAMETOOLONG);
 HddInstall in={.flags=7,.jail=1};
 assert(!dashHddInstallPrepareStorage(&in)&&!strcmp(in.stage,"pfs2:/tmp"));
 assert(strstr(last_log,"hdd0:__common:pfs:/tmp"));
 in.jail=0;assert(!dashHddInstallPrepareStorage(&in)&&!strcmp(in.stage,"pfs2:/PSBBN_DP_TEMP"));
 in.jail=1;assert(!dashHddInstallPrepareStorage(&in));
 network=0;assert(dashHddInstallPrepareStorage(&in)==-EIO&&strstr(in.error,"network failed"));network=1;
 hdd=0;assert(dashHddInstallPrepareStorage(&in)==-ENODEV);hdd=1;
 in.sizes[HI_SYSTEM]=300u*1024*1024;
 in.launcher_files=calloc(2,sizeof(*in.launcher_files));assert(in.launcher_files);
 in.launcher_count=1;in.launcher_files[0].size=1;
 strcpy(in.launcher_files[0].path,"scripts/assets/OPL/version.txt");
 assert(!stageSpace(&in)&&!checks&&stats==2);
 /* Zone rounding plus diagnostic/journal headroom, not raw byte counts. */
 free_zones=(304u*1024*1024)/8192;
 assert(stageSpace(&in)==-ENOSPC&&strstr(in.error,"__common has 304 MiB free"));
 free_zones++;assert(!stageSpace(&in));
 /* Completed downloads consume existing space and need no second copy. */
 in.downloaded_assets=1u<<HI_SYSTEM;in.downloaded_launchers=1;cached=1;
 free_zones=(4u*1024*1024)/8192;
 assert(!stageSpace(&in)&&checks==2);
 /* Old manifest licenses need neither cached files nor additional space. */
 in.launcher_count=2;in.launcher_files[1].size=4u*1024*1024;
 strcpy(in.launcher_files[1].path,"scripts/licenses/neutrino.txt");
 assert(!stageSpace(&in)&&checks==4);in.launcher_count=1;
 cached=0;assert(stageSpace(&in)==-ENOSPC); /* corrupt/truncated cache cannot count as complete */
 free_zones=-EIO;assert(stageSpace(&in)==-EIO);free_zones=131072;
 zone_size=0;assert(stageSpace(&in)==-EIO);zone_size=-ENODEV;assert(stageSpace(&in)==-ENODEV);
 zone_size=8192;
 hddInstallRecoveryBegin();hddInstallRecoveryObserve(-502);
 assert(stageSpace(&in)==-502);hddInstallRecoveryEnd();
 /* 64-bit accounting must reject >4 GiB instead of wrapping to a small value. */
 in.downloaded_assets=in.downloaded_launchers=0;
 for(unsigned i=0;i<HDD_INSTALL_ASSETS;i++)in.sizes[i]=1024u*1024*1024;
 free_zones=5*131072;assert(stageSpace(&in)==-ENOSPC);
 free(in.launcher_files);
 puts("PASS: PFS-only preparation, bounded free-space checks, cached-download reuse, zone rounding, I/O faults and 64-bit totals");
}
'''
with tempfile.TemporaryDirectory(prefix="hdd-pfs-stage-") as directory:
    d = Path(directory)
    (d / "test.c").write_text(code)
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined",
                    "-I", str(root / "include"), str(d / "test.c"), str(root / "src/hdd_install_plan.c"),
                    str(root / "src/hdd_install_recovery.c"), "-o", str(d / "test")], check=True)
    subprocess.run([str(d / "test")], check=True, timeout=10)
