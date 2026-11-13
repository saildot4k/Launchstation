"""Execute startup routing with slow audio, nested modal frames and handoffs."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
shell = (root / 'src/dash_main.c').read_text()


def function(signature):
    start = shell.index(signature)
    end = shell.index('{', start) + 1
    depth = 1
    while depth:
        depth += (shell[end] == '{') - (shell[end] == '}')
        end += 1
    return shell[start:end] + '\n'


code = r'''
#include <assert.h>
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 256
#define DASH_TITLE_MAX 64
#define SETTING_LK_AUTO 0
#define SETTING_LK_BTN_COUNT 2
#define DASH_SND_BOOT 5
#define stricmp strcmp
typedef uint64_t u64;
typedef struct { char *main_msg; } MainExecuteContext;
typedef struct { int any; } DashInput;
typedef struct { char title[DASH_TITLE_MAX]; } DashApp;
enum { DASH_SEC_HOME, DASH_SEC_APPS, DASH_SEC_FILES, DASH_SEC_TOOLS, DASH_SEC_SETTINGS };
static struct {
 int Init_Delay,timeout;
 char LK_Path[2][MAX_PATH],LK_Title[2][DASH_TITLE_MAX];
 const char *Misc_PS2Net,*Misc_PS2Disc,*Misc_OSDSYS,*Misc_PS2Browser,
            *Misc_PS2PowerOff,*Misc_Reboot_IOP,*Misc_Configure,*Misc_Exploit_Installer;
} config,*setting=&config;
static struct { int start_section; } dashCfg;
static MainExecuteContext exec_ctx;
static int dash_active,dash_inited,background_only,section,boot_phase;
static int startup_audio_pending,startup_audio_ready,startup_boot_sound;
static int io_busy,worker_busy,parked,frame_active;
static int screen_entered,library_open,displayed_tool,frames,audio_calls,boot_sounds;
static int held_key,external_success,misc_success,settle_ok,launches;
static int audio_tool;
static float fade_in,section_anim;
static u64 now_ms,last_frame_ms,boot_phase_end;
static char boot_auto_title[DASH_TITLE_MAX];
static char main_msg[MAX_PATH];
static jmp_buf handed_off;
static u64 Timer(void) { return now_ms; }
static int DashIoBusy(void) { return io_busy||worker_busy||parked||frame_active; }
void dashStartupAudioAfterPresent(void);
static void present(void) {
 assert(screen_entered);frame_active=1;frames++;now_ms+=16;
 if(fade_in<1)fade_in+=0.25f;
 if(fade_in>1)fade_in=1;
 frame_active=0;dashStartupAudioAfterPresent();
}
static void dashSoundMaintain(void) {
 assert(screen_entered&&frames>0&&fade_in>=0.95f&&!DashIoBusy());
 assert(!boot_phase&&startup_audio_ready&&!startup_audio_pending);
 audio_calls++;audio_tool=displayed_tool;
 /* Slow module/sidecar IO keeps rendering without re-entering startup. */
 io_busy=1;for(int i=0;i<20;i++)present();io_busy=0;
}
static void dashSoundPlay(int id) { assert(id==DASH_SND_BOOT&&audio_calls==1);boot_sounds++; }
'''
code += function('void dashStartupAudioAfterPresent(')
code += r'''
static void enter(void) {
 assert(!audio_calls);screen_entered=1;
 io_busy=1;present();io_busy=0;
}
static struct {void (*enter)(void);} screen={enter};
static const __typeof__(screen) *screens[]={&screen,&screen,&screen,&screen,&screen};
static void firstInit(void) {section=dashCfg.start_section==DASH_SEC_APPS?DASH_SEC_HOME:dashCfg.start_section;dash_inited=1;}
static void dashAppsRebuildView(void) { assert(screen_entered&&!audio_calls); }
static void dashHomeOpenApplications(void) { library_open=1; }
#define dashAppsShowAll() ((void)0)
#define dashGfxCheckScreenChange() ((void)0)
#define dashClassicUiInstall(x) ((void)(x))
#define dashGfxInit() ((void)0)
#define clearScreenToBlack() ((void)0)
#define dashFontInit() ((void)0)
#define dashIoInit() ((void)0)
#define DashThemeSetLegacyEnabled(x) ((void)(x))
#define dashInputFlush() ((void)0)
#define setStartupDriverStatusQuiet(x) ((void)(x))
static void (*drawMsgOverride)(const char *);
static void (*mainActionLaunchHook)(const char *);
static void dashMsgHook(const char *s) {(void)s;}
static void dashLaunchHook(const char *s) {(void)s;}
static void dashStrCopy(char *out,const char *in,int size) {snprintf(out,size,"%s",in);}
static void dashLibPrettyName(const char *p,char *out,int n) {dashStrCopy(out,p,n);}
static int genCmpFileExt(const char *p,const char *ext) {const char *dot=strrchr(p,'.');return dot&&!strcmp(dot+1,ext);}
static DashApp *dashLibResolve(const char *p,DashApp *a) {(void)p;strcpy(a->title,"Target");return a;}
static void dashLaunchApp(DashApp *a,int args) {
 (void)a;(void)args;assert(!startup_audio_ready&&!audio_calls);launches++;
 for(int i=0;i<8;i++)present();
 assert(!audio_calls);if(external_success)longjmp(handed_off,1);
}
static void dashRunMisc(const char *);
'''
code += function('static void runLaunchKey(')
code += r'''
static int bootHeldLaunchKey(void) {return held_key;}
static void dashToast(int type,const char *text) {(void)type;(void)text;}
#define DASH_TOAST_INFO 1
'''
code += function('static void bootBegin(') + function('static void bootUpdate(')

# Run the production entry sequence, ending just before its never-ending loop.
entry = function('void DashRun(')
entry = entry[:entry.index('\t/* the dashboard is the only shell: it never returns */')]
code += entry + '(void)in;(void)next_device_poll;(void)next_disc_poll;(void)next_remote_poll;\n}\n'
code += r'''
static int settleBackgroundWork(const char *title) {
 assert(title&&!startup_audio_ready);present();return settle_ok;
}
static void dashLoadingBegin(const char *title) {assert(title);present();}
#define filerRootMcPollIdle() ((void)0)
#define dashSoundShutdown() ((void)0)
#define dashSoundSuspend() ((void)0)
#define dashGfxRestoreLegacyState() ((void)0)
#define afterMiscCommand() ((void)0)
#define dashLoadingEnd() ((void)0)
#define showActionMessage() ((void)0)
static void ExecuteMainAction(char *path,MainExecuteContext *ctx) {
 assert(path&&ctx&&!startup_audio_ready);
 for(int i=0;i<8;i++)present();
 assert(!audio_calls);if(misc_success)longjmp(handed_off,1);
}
'''
code += function('static void runMiscCommand(')
code += r'''
static void dashRunMisc(const char *path) {
 launches++;
 if(!strcmp(path,"MISC/OSDSYS")) {
  runMiscCommand(path);
 } else {
  displayed_tool=1;for(int i=0;i<8;i++)present();
  assert(audio_calls==1&&audio_tool==1); /* first modal frame, before it closes */
 }
}
static void reset(int start,int delay,int timeout,const char *target) {
 memset(&config,0,sizeof(config));config.Init_Delay=delay;config.timeout=timeout;
 config.Misc_PS2Net="MISC/FTP";strcpy(config.LK_Path[0],target);
 config.Misc_PS2Disc="MISC/Disc";config.Misc_OSDSYS="MISC/OSDSYS";
 config.Misc_PS2Browser="MISC/Browser";config.Misc_PS2PowerOff="MISC/PowerOff";
 config.Misc_Reboot_IOP="MISC/Reboot";config.Misc_Configure="MISC/Configure";
 config.Misc_Exploit_Installer="MISC/Exploit";settle_ok=1;
 dashCfg.start_section=start;now_ms=1000;held_key=-1;dash_active=dash_inited=0;
 screen_entered=library_open=displayed_tool=frames=audio_calls=boot_sounds=audio_tool=0;
 boot_phase=io_busy=worker_busy=parked=frame_active=launches=external_success=misc_success=0;
 startup_audio_pending=startup_audio_ready=startup_boot_sound=0;fade_in=1;
}
static void show(void) { for(int i=0;i<8;i++)present(); }
int main(void) {
 MainExecuteContext ctx={main_msg};DashInput no_input={0},cancel={1};
 for(int start=0;start<=DASH_SEC_SETTINGS;start++)for(int boot=0;boot<2;boot++) {
  reset(start,0,0,"");DashRun(&ctx,boot);
  assert(!audio_calls&&startup_audio_pending&&fade_in==0.25f);
  assert(section==(start==DASH_SEC_APPS?DASH_SEC_HOME:start));
  assert(library_open==(start==DASH_SEC_APPS));
  show();assert(audio_calls==1&&boot_sounds==boot&&fade_in==1);
  show();assert(audio_calls==1&&boot_sounds==boot);
 }
 /* A configured target at zero seconds remains disabled. */
 reset(DASH_SEC_FILES,0,0,"mc0:/BOOT.ELF");DashRun(&ctx,1);show();assert(audio_calls==1&&!launches);
 /* Both delay and countdown remain responsive and take precedence over audio. */
 reset(DASH_SEC_FILES,2,3,"mc0:/BOOT.ELF");DashRun(&ctx,1);show();
 assert(boot_phase==1&&!audio_calls);now_ms=boot_phase_end;bootUpdate(&no_input);show();
 assert(boot_phase==2&&!audio_calls);bootUpdate(&cancel);show();assert(!launches&&audio_calls==1);
 /* A successful external automatic launch never loads dashboard audio. */
 reset(DASH_SEC_HOME,0,1,"mc0:/BOOT.ELF");external_success=1;
 if(!setjmp(handed_off)) {DashRun(&ctx,1);show();now_ms=boot_phase_end;bootUpdate(&no_input);assert(0);}
 assert(launches==1&&!audio_calls&&startup_audio_pending);
 /* Failed launches resume sound after the destination is displayed again. */
 reset(DASH_SEC_HOME,0,1,"mc0:/MISSING.ELF");DashRun(&ctx,1);show();
 now_ms=boot_phase_end;bootUpdate(&no_input);assert(!audio_calls);show();assert(audio_calls==1&&launches==1);
 /* Held shortcuts have priority, including modal tools and leaving MISC targets. */
 for(int target=0;target<3;target++) {
  reset(DASH_SEC_HOME,0,0,target==0?"mc0:/BOOT.ELF":target==1?"MISC/TextEditor":"MISC/OSDSYS");
  held_key=0;external_success=misc_success=1;
  if(!setjmp(handed_off)) {DashRun(&ctx,1);assert(target==1&&audio_calls==1);}
  assert(launches==1&&audio_calls==(target==1));
 }
 reset(DASH_SEC_FILES,0,0,"MISC/OSDSYS");held_key=0;settle_ok=0;
 DashRun(&ctx,1);show();assert(audio_calls==1&&startup_audio_ready);
 /* Modal automatic targets also start sound while their screen remains open. */
 reset(DASH_SEC_FILES,0,1,"MISC/TextEditor");DashRun(&ctx,1);show();
 assert(!audio_calls);now_ms=boot_phase_end;bootUpdate(&no_input);
 assert(audio_calls==1&&audio_tool==1&&launches==1);
 reset(DASH_SEC_FILES,2,0,"MISC/TextEditor");held_key=0;DashRun(&ctx,1);show();
 assert(!audio_calls);now_ms=boot_phase_end;bootUpdate(&no_input);
 assert(audio_calls==1&&audio_tool==1&&launches==1);
 /* Startup audio waits for foreground IO, worker reads and parked IOPs. */
 for(int busy=0;busy<3;busy++) {
  reset(DASH_SEC_FILES,0,0,"");DashRun(&ctx,1);
  if(!busy)io_busy=1;else if(busy==1)worker_busy=1;else parked=1;
  show();assert(!audio_calls&&startup_audio_pending);
  io_busy=worker_busy=parked=0;present();assert(audio_calls==1&&boot_sounds==1);
 }
 puts("PASS: selected screens and modal targets precede audio; one fade, launch delays/cancel/disabled targets, external handoffs, failure recovery and IO/reentrant-frame guards");
}
'''

with tempfile.TemporaryDirectory(prefix='startup-audio-') as folder:
    folder = Path(folder)
    (folder / 'test.c').write_text(code)
    cc = os.environ.get('CC') or shutil.which('gcc') or shutil.which('clang')
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', *flags, str(folder / 'test.c'), '-o', str(folder / 'test')], check=True)
    subprocess.run([str(folder / 'test')], check=True, timeout=10)
