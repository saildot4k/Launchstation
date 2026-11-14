"""Exercise committed launch cleanup with late controller/keyboard RPC waits.

New Neutrino status messages leave the loading view redrawable. Those waits
must stop rendering before settings/fonts are freed, regardless of the last
popup type. A cancelled preflight must keep the dashboard usable.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

def function(path, signature):
    source = (root/path).read_text()
    start = source.index(signature)
    end = source.index('{', start)+1
    depth = 1
    while depth:
        depth += (source[end] == '{')-(source[end] == '}')
        end += 1
    return source[start:end]+'\n'

code = r'''
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
typedef unsigned long long u64;
typedef int s32;
static int dash_active, startup_audio_pending, startup_audio_ready;
static int valid_settings,valid_font,loading_active=1,popup,redraws,status_draws;
static int io_owner=1,io_waiting,closing_rpcs,freed,prepare_ok=1;
static const char *last_title;
static int quiet_status;
static int isStartupDriverStatusQuiet(void){return quiet_status;}
static u64 io_next_frame,now;
static void *setting=(void*)1,*elisaFnt=(void*)2,*External_Lang_Buffer=(void*)3;
static int GetThreadId(void){return 1;}
static int DashIsActive(void){return dash_active;}
static int dashGfxCanYield(void){return 1;}
static int dashGfxPopupActive(void){return popup;}
static u64 Timer(void){return now;}
static s32 __real_DelayThread(s32 usec){now+=(usec+999)/1000;return 0;}
static void loadingDraw(void){assert(valid_settings && valid_font);redraws++;}
static void dashVisualUpdate(void){}
static void dashRenderScene(void){loadingDraw();}
static void dashGfxPresent(void){}
static void dashLoadingStatus(const char *text,int done,int total){
    assert(text && !done && !total && valid_settings && valid_font);status_draws++;
}
'''
code += function('src/dash_io.c', 'static int canCooperate(')
code += function('src/dash_ui.c', 'void dashLoadingRedraw(')
code += function('src/dash_io.c', 'static s32 waitFrame(')
code += function('src/dash_main.c', 'void DashStopUiForExec(')
code += function('src/dash_main.c', 'static void dashMsgHook(')
code += r'''
static void waitingRpc(void){
    if(canCooperate()){io_waiting++;waitFrame();io_waiting--;}
    now+=25;
}
static void fadeScreenToBlack(void){assert(valid_settings && valid_font);waitingRpc();}
static void dashSoundShutdown(void){assert(valid_settings && valid_font);waitingRpc();}
static void DashThemeSetLegacyEnabled(int on){assert(!on);}
static void clearScreenToBlack(void){assert(valid_settings && valid_font);}
static void trackedFree(void *p){
    assert(!dash_active && !startup_audio_pending && !startup_audio_ready);
    if(p==setting)valid_settings=0;
    if(p==elisaFnt)valid_font=0;
    freed++;
}
#define free trackedFree
static void teardownRpc(void){
    assert(!valid_settings && !valid_font && !canCooperate());
    int before=redraws;waitingRpc();assert(redraws==before);closing_rpcs++;
    int previous=status_draws;dashMsgHook("Late shutdown status");assert(status_draws==previous);
}
static void padPortClose(int p,int s){(void)p;(void)s;teardownRpc();}
static void padEnd(void){teardownRpc();}
static void closeKeyboardIfOpened(void){teardownRpc();}
#ifdef DS34
static int semRunning,semFinish,isRunning=1;
static void WaitSema(int sem){(void)sem;teardownRpc();}
static void SignalSema(int sem){(void)sem;}
static void ds34usb_reset(void){teardownRpc();}
static void ds34bt_reset(void){teardownRpc();}
#endif
static int DashPrepareKeepIopHandoff(const char *title){
    assert(dash_active && valid_settings && valid_font);last_title=title;return prepare_ok;
}
'''
code += function('src/main_actions.c', 'static void cleanUpForExecInternal(')
code += function('src/main_actions.c', 'int CleanUpForKeepIopExec(')
code += r'''
static void reset(int active,int modal){
    quiet_status=0;dash_active=active;popup=modal;valid_settings=valid_font=1;
    startup_audio_pending=startup_audio_ready=1;
    redraws=status_draws=freed=closing_rpcs=0;now=io_next_frame=0;
}
int main(void){
    for(int active=0;active<2;active++)for(int modal=0;modal<2;modal++)for(int keep=0;keep<2;keep++){
        reset(active,modal);cleanUpForExecInternal(keep);
        assert(freed==3 && !dash_active && !valid_settings && !valid_font);
        assert(closing_rpcs>=3+keep);
        if(active && !modal)assert(redraws>0); /* Valid waits still render before cleanup commits. */
    }
    reset(1,0);prepare_ok=0;
    assert(!CleanUpForKeepIopExec("Preparing Neutrino"));
    assert(dash_active && valid_settings && valid_font && !freed && !closing_rpcs);
    dashMsgHook("Cancelled launch");assert(status_draws==1);
    quiet_status=1;dashMsgHook("Silent launch status");assert(status_draws==1);
    quiet_status=0;
    prepare_ok=1;assert(CleanUpForKeepIopExec(NULL));assert(last_title==NULL);
    assert(freed==3 && !dash_active && !startup_audio_pending && !startup_audio_ready);
    puts("PASS: normal/keep-IOP cleanup stops wait redraws and late status callbacks before freeing UI; cancelled preflight stays usable");
}
'''
compiler = shutil.which('cc') or shutil.which('gcc')
assert compiler, 'Host C compiler required'
with tempfile.TemporaryDirectory(prefix='exec-ui-lifetime-') as folder:
    path = Path(folder)
    (path/'test.c').write_text(code)
    for ds34 in (False, True):
        exe = path/('ds34' if ds34 else 'wired')
        subprocess.run([compiler,'-std=c99','-Wall','-Wextra','-Werror',
                        *(['-DDS34'] if ds34 else []),str(path/'test.c'),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=10)
