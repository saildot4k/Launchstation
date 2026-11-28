"""Production installer job dispatch/retry checkpoints, without a physical disk."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'src/dash_hdd.c').read_text()


def function(signature):
    a = source.index(signature)
    depth = 0
    for t in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[a:], re.S):
        depth += (t.group() == '{') - (t.group() == '}')
        if not depth and t.group() == '}': return source[a:a + t.end()] + '\n'
    raise AssertionError(signature)


code = r'''
#include <assert.h>
#include <errno.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "hdd_install.h"
#define DASH_JOB_VISIBLE 1
#define DASH_TOAST_WARN 2
#define HDIOC_FLUSH 1
enum { HOP_DOWNLOAD_INSTALLER=1,HOP_INSTALL_SOFTWARE=2,HOP_RESUME_LOOKUP=3,HOP_RESUME_AVAILABLE=4 };
typedef struct {int op,ret,format_started,abandoned;HddInstall *installer;HddFormatPlan format_plan;} HddJob;
static int scenario,submits,applies,populates,finishes,boots,cleanups,downloads,creates,finds,physical,core,prepared,rawloads,freed;
static jmp_buf fatal;
static int loading,planned,generation,storage_loads,prep_error,disk_flushes;
static int dashWorkerAwaitAll(const char *s){assert(s&&!hddInstallRecoveryActive());return prep_error!=1;}
unsigned getIopResetGeneration(void){return generation;}
void rebootInstallerIopForExtraction(void){assert(!hddInstallRecoveryActive());planned++;if(prep_error!=2)generation++;}
static int loadHddModules(void){storage_loads++;return prep_error!=3;}
static int fileXioDevctl(const char *p,int cmd,const void *a,int n,void *b,int m){assert(!strcmp(p,"hdd0:")&&cmd==HDIOC_FLUSH&&!a&&!n&&!b&&!m);disk_flushes++;return 0;}

static int dashLoadingActive(void){return loading;}
static void dashLoadingBegin(const char *s){assert(s&&!loading);loading=1;}
static void dashLoadingEnd(void){assert(loading&&!hddInstallRecoveryFault());loading=0;}
int hddInstallResumeSave(HddInstall *in){assert(in);return 0;}
void hddInstallLog(const char *s,...){assert(s);}
void hddInstallLogFlush(HddInstall *in){assert(in);}
void hddInstallProgress(const char *s,int a,int b){assert(s&&a<=b);}
static void filerSizeCacheInvalidate(const char *s){assert(s);}
int hddInstallMountStage(HddInstall *in){assert(in);return hddInstallRecoveryFault()?-502:0;}
int hddInstallUnmountStage(HddInstall *in){assert(in);return hddInstallRecoveryFault()?-502:0;}
int hddInstallCreateStage(HddInstall *in){assert(!in->stage_ready);creates++;in->stage_ready=in->owned=1;return 0;}
int hddInstallFindStage(HddInstall *in){assert(in->stage_ready&&in->owned);finds++;return 0;}
int hddInstallDownload(HddInstall *in){assert(in);downloads++;if(scenario==2&&downloads==1){hddInstallRecoveryObserve(-502);return -502;}return 0;}
int hddInstallApply(HddInstall *in){assert(in&&!in->applied);applies++;return 0;}
int hddInstallPsbbnPayload(void *context,const HddFormatIo *io,HddInstallRestart restart){
 HddInstall *in=context;(void)io;(void)restart;populates++;
 if((scenario==1||scenario==7||scenario==8||scenario==10)&&populates==1){hddInstallRecoveryObserve(-502);return -502;}
 if(scenario==3){hddInstallRecoveryObserve(-502);return -502;}
 if(scenario==6)return -EINVAL;
 in->populated=1;return 0;
}
int hddInstallFinish(const HddFormatPlan *p,const char *mbr,int *started,HddInstallPopulate populate,void *context){
 assert(p&&mbr&&started&&context);finishes++;*started=1;
 int ret=populate?populate(context,NULL,NULL):0;
 if(ret<0)return ret;
 if(scenario==4&&finishes==1){hddInstallRecoveryObserve(-502);return -502;}
 return 0;
}
int hddInstallEnableBoot(HddInstall *in){assert(in&&!hddInstallRecoveryFault()&&!in->committed);boots++;return 0;}
void hddInstallCleanup(HddInstall *in){
 assert(in->committed);cleanups++;
 if(scenario==5&&cleanups==1){hddInstallRecoveryObserve(-502);return;}
 in->owned=0;
}
static void hddJobFree(HddJob *j){assert(j);freed++;}
static void hddJobDone(void *j){assert(j);}
static void dashToast(int icon,const char *s){assert(icon==2&&s);}
int resetInstallerIopTransport(void){physical++;return scenario!=10;}
int reloadInstallerCoreAfterReset(void){core++;return scenario!=8;}
int dashHddInstallPrepareStorage(HddInstall *in){assert(in);prepared++;return 0;}
int hddFormatLoad(void){rawloads++;return prep_error==4?-EIO:0;}
void dashHddInstallRecoveryFailed(void){longjmp(fatal,1);}
'''
ui=(root/'src/dash_hdd_install.c').read_text()
previous_source=source
source=ui
code+=function('int dashHddInstallPrepareExtraction(')
source=previous_source

a = source.index('\t\tcase HOP_DOWNLOAD_INSTALLER:', source.index('static void hddJobRun('))
b = source.index('\t\tcase HOP_UNMOUNT:', a)
code += 'static void hddJobRun(void *arg){HddJob *j=arg;switch(j->op){\n' + source[a:b] + 'default:break;}}\n'
code += r'''
static int dashWorkerSubmit(const char *s,int flags,void(*run)(void*),void(*done)(void*),void *arg){
 assert(s&&flags==1&&done);if(scenario==9)return -1;submits++;run(arg);return submits;
}
int dashHddInstallAwait(int id,const char *s){
 assert(id&&s);
 if(scenario==7&&submits==1){hddInstallRecoveryRequestReset();assert(resetInstallerIopTransport());hddInstallRecoveryResetComplete();}
 return 1;
}
static int dashWorkerAwait(int id,const char *s,int cancelable){(void)cancelable;assert(id&&s);return 1;}
'''
code += function('static int runJob(')
code += r'''
int main(void){
 for(scenario=0;scenario<=10;scenario++){
  planned=storage_loads=disk_flushes=prep_error=0;loading=0;submits=applies=populates=finishes=boots=cleanups=downloads=creates=finds=physical=core=prepared=rawloads=freed=0;
  HddInstall in={.flags=7,.jail=1,.owned=1,.stage_ready=scenario!=2};strcpy(in.stage,"pfs2:/tmp");
  HddJob j={.op=scenario==2?HOP_DOWNLOAD_INSTALLER:HOP_INSTALL_SOFTWARE,.installer=&in,.format_plan={.apa_sectors=131072u*2048}};
  if(scenario==8||scenario==10){
   if(!setjmp(fatal)){runJob(&j,"Installing",0);assert(0);}
   assert(physical==1&&core==(scenario==8?1:0)&&submits==1&&!freed&&!hddInstallRecoveryActive());
   continue;
  }
  int ok=runJob(&j,"Installer",0);assert(!hddInstallRecoveryActive());
  if(scenario==9){assert(!ok&&freed==1&&!submits);continue;}
  assert(ok&&!freed);
  if(scenario==3){assert(j.ret==-502&&submits==3&&in.recovery_attempts==2&&physical==3&&core==3&&!boots&&!cleanups);continue;}
  if(scenario==6){assert(j.ret==-EINVAL&&submits==1&&!physical&&!boots);continue;}
  assert(!j.ret);
  if(scenario==0){assert(submits==1&&!physical&&applies==1&&populates==1&&boots==1&&planned==1&&storage_loads==1);}
  else{assert(submits==2&&in.recovery_attempts==1&&physical==1&&core==1&&prepared==(scenario==2?1:0));}
  if(scenario==2){assert(creates==1&&finds==1&&downloads==2&&!applies&&!planned&&disk_flushes==1);}
  if(scenario==1||scenario==7){assert(applies==1&&populates==2&&finishes==2&&boots==1);}
  if(scenario==4){assert(applies==1&&populates==1&&finishes==2&&boots==1);}
  if(scenario==5){assert(applies==1&&populates==1&&finishes==1&&boots==1&&cleanups==2);}
 }
 /* Preparation failures stop before queueing any installation writes. */
 for(prep_error=1;prep_error<=4;prep_error++){
  HddInstall in={.flags=7,.jail=1};HddJob j={.op=HOP_INSTALL_SOFTWARE,.installer=&in};
  scenario=0;loading=planned=submits=rawloads=storage_loads=0;
  assert(runJob(&j,"Installer",0)&&j.ret<0&&!submits&&!loading&&!hddInstallRecoveryActive());
  assert(planned==(prep_error==1?0:1));
  assert(storage_loads==(prep_error>=3?1:0)&&rawloads==(prep_error==4?1:0));
  assert(strstr(in.error,"Cached downloads are retained"));
 }
 prep_error=0;
 /* A resumed population/commit must not reboot or repeat extraction. */
 for(unsigned committed=0;committed<=1;committed++){
  HddInstall in={.flags=7,.jail=1,.owned=1,.stage_ready=1,.applied=1,.populated=1,.committed=committed};
  HddJob j={.op=HOP_INSTALL_SOFTWARE,.installer=&in};
  scenario=0;loading=planned=submits=rawloads=populates=finishes=0;
  assert(runJob(&j,"Installer",0)&&!j.ret&&!planned&&!populates&&submits==1&&rawloads==!committed);
 }
 puts("PASS: planned local-only reset before fresh/resumed extraction, preparation failures, completed-stage skips, download flushes and two bounded retries, state retained; no whole-drive reformat, completed apply/population/boot checkpoints, download staging retained and non-ATA errors stop normally");
}
'''
with tempfile.TemporaryDirectory(prefix='hdd-installer-retry-') as directory:
    d = Path(directory)
    (d / 'test.c').write_text(code)
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                    '-I', str(root / 'include'), str(d / 'test.c'), str(root / 'src/hdd_install_recovery.c'),
                    '-o', str(d / 'test')], check=True)
    subprocess.run([str(d / 'test')], check=True, timeout=10)

# The planned reboot must also leave networking unloaded in UDP debug builds.
source=(root/'src/init.c').read_text()
wrapper=function('void rebootInstallerIopForExtraction(')
with tempfile.TemporaryDirectory(prefix='hdd-install-local-reset-') as directory:
    d=Path(directory)
    code=r'''
#include <assert.h>
#define FALSE 0
#ifdef UDPTTY
static int network_stack_switching;
#endif
static int resets;
static void resetRuntimeDeviceState(int show){
 assert(!show);resets++;
#ifdef UDPTTY
 assert(network_stack_switching);
#endif
}
'''+wrapper+r'''
int main(void){
 rebootInstallerIopForExtraction();assert(resets==1);
#ifdef UDPTTY
 assert(!network_stack_switching);
 network_stack_switching=1;rebootInstallerIopForExtraction();assert(network_stack_switching&&resets==2);
#endif
}
'''
    (d/'reset.c').write_text(code)
    for options in ([],['-DUDPTTY']):
        subprocess.run(['gcc','-std=c99','-Wall','-Wextra','-Werror',*options,str(d/'reset.c'),'-o',str(d/'reset')],check=True)
        subprocess.run([str(d/'reset')],check=True,timeout=10)
print('PASS: planned reset suppresses UDP debug network reload and restores its prior switch state')
