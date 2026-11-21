"""Execute first-frame RetroGem signaling and audio readiness before library IO."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from dash_sound_harness import run

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


# Run the actual boot graphics entry, decode every colored pixel pair, and
# distinguish screen setup from signaling on an already configured context.
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint64_t u64;
typedef struct { int Width,Height,Mode,DoubleBuffering,PrimAlphaEnable,PrimAAEnable; } GSGLOBAL;
#define GS_SETTING_ON 1
#define GS_SETTING_OFF 0
#define GS_ONESHOT 1
#define D_CTRL_RELE_OFF 0
#define D_CTRL_MFD_OFF 0
#define D_CTRL_STS_UNSPEC 0
#define D_CTRL_STD_OFF 0
#define D_CTRL_RCYC_8 0
#define DMA_CHANNEL_GIF 2
#define GS_SETREG_RGBA(r,g,b,a) ((u64)(r)|((u64)(g)<<8)|((u64)(b)<<16)|((u64)(a)<<24))
#define GS_SETREG_RGBAQ(r,g,b,a,q) GS_SETREG_RGBA(r,g,b,a)
#define DPRINTF(...) ((void)0)
static GSGLOBAL screen,*gsGlobal=&screen;
static int allocations,screen_inits,dma_inits,released,display_buffers,mode_switches;
static int no_context,bad_dma,queued,finished,flipped,sprites,clear_calls,fonts,init_complete;
static int width=640,height=448,mode=1;
static u8 bytes[64];
static const char *expected_id="LAUNCHSTATI";
static int expected_frames=2;
static GSGLOBAL *gsKit_init_global(void) {allocations++;return no_context?NULL:&screen;}
static void gsKit_deinit_global(GSGLOBAL *gs) {assert(gs==&screen);released++;}
static void dmaKit_init(int a,int b,int c,int d,int e,int f) {
 assert(!a&&!b&&!c&&!d&&!e&&f==(1<<DMA_CHANNEL_GIF));dma_inits++;
}
static int dmaKit_chan_init(int ch) {assert(ch==DMA_CHANNEL_GIF);return bad_dma;}
static void gsKit_init_screen(GSGLOBAL *gs) {assert(gs==&screen);screen_inits++;}
static void gsKit_display_buffer(GSGLOBAL *gs) {assert(gs==&screen);display_buffers++;}
static void gsKit_mode_switch(GSGLOBAL *gs,int m) {assert(gs==&screen&&m==GS_ONESHOT);mode_switches++;}
static void gsKit_clear(GSGLOBAL *gs,u64 color) {
 assert(gs==&screen&&!color);clear_calls++;sprites=0;memset(bytes,0,sizeof(bytes));
}
static void gsKit_prim_sprite(GSGLOBAL *gs,int x,int y,int x1,int y1,int z,u64 color) {
 assert(gs==&screen&&!gs->PrimAlphaEnable&&!gs->PrimAAEnable);
 int length=strnlen(expected_id,11)+7,bit=sprites/2,byte=bit/8;
 assert(x==gs->Width/2-length*8+bit*2+(sprites&1));
 assert(y==gs->Height-((gs->Height/8)*2+20)&&x1==x+1&&y1==y+2&&!z);
 assert(x>=0&&x1<=gs->Width&&y>=0&&y1<=gs->Height);
 if(!(sprites&1))assert(color==GS_SETREG_RGBA(255,0,255,0));
 else {
  assert(color==GS_SETREG_RGBA(0,255,255,0)||color==GS_SETREG_RGBA(255,255,0,0));
  if(color==GS_SETREG_RGBA(0,255,255,0))bytes[byte]|=1<<(7-bit%8);
 }
 sprites++;
}
static void gsKit_queue_exec(GSGLOBAL *gs) {
 assert(gs==&screen&&queued==finished&&finished==flipped);
 if(queued<expected_frames) {
  int n=strnlen(expected_id,11),length=n+7;
  assert(sprites==length*16&&bytes[0]==0xA5&&!bytes[1]&&bytes[3]==n);
  assert(!memcmp(bytes+4,expected_id,n));
  assert(!bytes[4+n]&&bytes[5+n]==0xD5&&!bytes[6+n]);
  u8 checksum=bytes[2];for(int i=3;i<length;i++)checksum+=bytes[i];assert(!checksum);
 } else assert(!sprites);
 queued++;
}
static void gsKit_finish(void) {assert(queued==finished+1);finished++;}
static void gsKit_sync_flip(GSGLOBAL *gs) {assert(gs==&screen&&finished==flipped+1);flipped++;}
static void setupGS(void) {
 screen=(GSGLOBAL){width,height,mode,1,1,1};gsGlobal=&screen;
}
static void loadFont(const char *name) {
 assert(!name[0]&&flipped==4&&!allocations&&!screen_inits&&!dma_inits);
 assert(screen.PrimAlphaEnable&&screen.PrimAAEnable);fonts++;
}
static void setInitPhaseComplete(void) {assert(fonts);init_complete++;}
'''
source = (ROOT/'src/main_gameid.c').read_text()
for signature in ('static u8 calculateRetroGemCRC(', 'static void displayRetroGemGameIDOnScreen(',
                  'void displayStartupGameID(', 'void displayRetroGemGameID('):
    code += function(source, signature)
code += function((ROOT/'src/main_startup.c').read_text(), 'void initializeBootGraphics(')
code += r'''
static void reset(void) {
 allocations=screen_inits=dma_inits=released=display_buffers=mode_switches=0;
 no_context=bad_dma=queued=finished=flipped=sprites=clear_calls=fonts=init_complete=0;
 expected_id="LAUNCHSTATI";expected_frames=2;setupGS();
}
int main(void) {
 int heights[]={448,512,480,576,480};
 for(int i=0;i<5;i++) {
  height=heights[i];mode=i;reset();initializeBootGraphics();
  assert(flipped==4&&fonts==1&&init_complete==1&&clear_calls==5);
  assert(!screen_inits&&!dma_inits&&!allocations&&!released&&!mode_switches);
  assert(screen.Mode==mode&&screen.Width==width&&screen.Height==height&&screen.DoubleBuffering==1);
 }
 for(int frames=-1;frames<=5;frames++) {
  reset();expected_id="SLUS_123.45EXCESS";expected_frames=frames<1?1:frames>3?3:frames;
  displayRetroGemGameID(expected_id,frames);
  assert(queued==expected_frames+2&&allocations==1&&screen_inits==1&&dma_inits==1);
  assert(released==1&&display_buffers==1&&mode_switches==1);
  assert(screen.PrimAlphaEnable&&screen.PrimAAEnable);
 }
 reset();displayRetroGemGameID(NULL,2);displayRetroGemGameID("",2);assert(!allocations&&!queued);
 no_context=1;displayRetroGemGameID("TEST",2);assert(allocations==1&&!released&&!queued);
 reset();bad_dma=1;displayRetroGemGameID("TEST",2);assert(allocations==1&&released==1&&!screen_inits&&!queued);
 reset();gsGlobal=NULL;displayStartupGameID();assert(!queued);
 puts("PASS: first-frame Launchstation barcode, exact ID/checksum/pixels, two-frame duration, existing video context and launch handoff cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix='startup-gameid-') as directory:
    path = Path(directory)
    (path/'test.c').write_text(code)
    compiler = shutil.which('gcc') or shutil.which('clang')
    subprocess.run([compiler, '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(path/'test.c'),
                    '-o', str(path/'test')], check=True)
    subprocess.run([str(path/'test')], check=True, timeout=10)

# Execute the full firstInit with the real audio code and a deliberately slow
# worker. Cache reads and scan submission must see published, usable effects.
main = r'''
enum {DASH_SEC_HOME,DASH_SEC_APPS,DASH_SEC_FILES,DASH_SEC_DEVICES,DASH_SEC_TOOLS,DASH_SEC_SETTINGS,DASH_SEC_COUNT};
static int section,dash_inited,boot_safe_mode,dashAppCount,cache_result,scans,config_loaded,worker_initialized;
static void dashStoreInit(void) {assert(!submitted);config_loaded=1;dashCfg.sound_vol=37;}
static void dashLibInit(void) {assert(config_loaded&&!submitted);}
#define dashArtInit() ((void)0)
#define dashUiInit() ((void)0)
#define dashBgInit() ((void)0)
#define dashDevicesInit() ((void)0)
#define dashGfxInit() ((void)0)
#define clearScreenToBlack() ((void)0)
#define dashFontInit() ((void)0)
#define dashIconsInit() ((void)0)
#define dashConsoleIdentityInit() ((void)0)
static void dashWorkerInit(void) {assert(config_loaded&&!submitted);worker_initialized=1;}
static int dashLibLoadCache(void) {
 assert(worker_initialized&&submitted==1&&!q_count&&!sound_job_id&&!sound_startup_preparing);
 assert(!plays[23]);
 if(module_failure)assert(!soundAlive()&&warnings==1);
 else {
  assert(soundAlive()&&sample_uploads==DASH_SND_COUNT);
  assert(bgm_loaded==exists);
  int before=0,after=0;for(int i=8;i<14;i++)before+=plays[i];
  dashSoundPlay(DASH_SND_CURSOR);
  for(int i=8;i<14;i++)after+=plays[i];assert(after==before+dashCfg.sound);
 }
 return cache_result;
}
static void dashRescanLibrary(int interactive) {assert(!interactive&&!sound_job_id);scans++;}
'''
main += function((ROOT/'src/dash_main.c').read_text(), 'static void firstInit(')
main += r'''
int main(void) {
 for(int failure=0;failure<2;failure++)for(int music=0;music<2;music++)
 for(int effects=0;effects<2;effects++)for(int cache=0;cache<2;cache++)
 for(int target=0;target<DASH_SEC_COUNT;target++) {
  reset();config_loaded=worker_initialized=scans=dash_inited=0;
  dashCfg.start_section=target;dashCfg.bgm=music;dashCfg.sound=effects;
  cache_result=cache?0:-1;module_failure=failure;exists=target!=DASH_SEC_FILES;
  firstInit();assert(dash_inited&&scans==!cache);
  assert(section==(target==DASH_SEC_APPS?DASH_SEC_HOME:target==DASH_SEC_DEVICES?DASH_SEC_FILES:target));
  assert(!plays[23]);
  dashSoundMaintain();settle();
  if(!failure)assert(plays[23]==exists&&volumes[23]==(exists?(music?80:10):0));
 }
 reset();reject_submit=1;dashSoundPrepareStartup();assert(!sound_ready&&!sound_job_id);
 reject_submit=0;dashSoundMaintain();settle();assert(soundAlive());
 /* A stale queued result returns without hanging startup or touching dead RPC. */
 reset();dashSoundMaintain();generation++;dashSoundPrepareStartup();
 assert(!sound_ready&&!sound_job_id&&!module_calls);
 dashSoundMaintain();settle();assert(soundAlive());
 reset();
 puts("PASS: audio ready before real startup cache/scan/input; no startup cue or early music; missing sidecar, disabled settings, failed drivers/queue and reset recovery");
}
'''
run(main, 'startup')
