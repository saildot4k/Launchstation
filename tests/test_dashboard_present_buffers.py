"""Exercise real dashboard frame setup and vsync flip code using host GS mocks.

Initial GS setup must allocate both buffers in the configured video mode.
Entering/re-entering the dashboard must preserve calibration, framebuffer
addresses and screen generation without initializing the output again.
When IO worker is busy, yielding at VBLANK must still swap/display the
completed front buffer (not the drawing one).
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
gfx=(root/"src/dash_gfx.c").read_text()
classic=(root/"src/draw_gs.c").read_text()

def fn(signature, source=gfx):
    start=source.index(signature)
    pos=source.index("{",start)+1
    depth=1
    while depth:
        depth+=(source[pos]=="{")-(source[pos]=="}")
        pos+=1
    return source[start:pos]+"\n"

header=(root/"include/launchelf.h").read_text()
start=header.index("enum TV_mode {")
video_modes=header[start:header.index("};",start)+2]

code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
typedef struct {
    int Mode,PrimAAEnable,ZBuffering,DoubleBuffering,FirstFrame,ActiveBuffer,Width,PSM;
    uint32_t ScreenBuffer[2];
} GSGLOBAL;
typedef struct { int screen_x,screen_y; } Setting;
#define GS_SETTING_OFF 0
#define GS_SETTING_ON 1
static GSGLOBAL g;
static GSGLOBAL *gsGlobal=&g;
static Setting config={3,-2};
static Setting *setting=&config;
static volatile uint32_t csr=8;
static volatile uint32_t *GS_CSR=&csr;
static int gsScreenGeneration, gfx_screen_gen, gfx_ready, bound_generation, frame_active;
static int foreground_wait,frame_popup,presented_popup;
static int dashIoBusy(void) {return foreground_wait;}
static int begin_count,glow_count,check_count,init_count,offset_count;
static int shown_count,shown_base,shown_width,shown_psm,active_count;
static int queue_count,tex_frames,pump_count,sprite_count,park_count;
static int sync_count,worker_busy,wait_calls;
static void buildCornerTextures(void) { begin_count++; }
static void buildGlowTextures(void) { glow_count++; }
static int dashGfxCheckScreenChange(void) {
    check_count++;
    bound_generation=gsScreenGeneration;
    gfx_screen_gen=gsScreenGeneration;
    return 1;
}
static void gsKit_init_screen(GSGLOBAL *ptr) {
    assert(ptr==gsGlobal && ptr->DoubleBuffering==GS_SETTING_ON);
    init_count++;
    ptr->ScreenBuffer[0]=0;
    ptr->ScreenBuffer[1]=0x120000;
    ptr->Width=640;
    ptr->PSM=1;
    ptr->ActiveBuffer=1;
}
static void gsKit_set_display_offset(GSGLOBAL *ptr,int x,int y) {
    assert(ptr==gsGlobal && x==3 && y==-2); offset_count++;
}
#define GS_MODE_NTSC 2
#define GS_MODE_PAL 3
#define GS_MODE_VGA_640_60 4
#define GS_MODE_DTV_480P 5
#define GS_MODE_DTV_576P 0x53
#define GS_ONESHOT 0
#define D_CTRL_RELE_OFF 0
#define D_CTRL_MFD_OFF 0
#define D_CTRL_STS_UNSPEC 0
#define D_CTRL_STD_OFF 0
#define D_CTRL_RCYC_8 0
#define DMA_CHANNEL_GIF 2
static int configured_mode,TV_mode,global_inits,applied_params,screen_params,mode_switches;
static int requestedTVMode(void) { return configured_mode; }
static GSGLOBAL *gsKit_init_global(void) { global_inits++;return &g; }
static void applyGSParams(void) { applied_params++; }
static void initScreenParams(void) { screen_params++; }
static void dmaKit_init(int rele,int mfd,int sts,int std,int cycle,int channels) {
    assert(!rele && !mfd && !sts && !std && !cycle && channels==(1<<DMA_CHANNEL_GIF));
}
static void dmaKit_chan_init(int channel) { assert(channel==DMA_CHANNEL_GIF); }
static void gsKit_mode_switch(GSGLOBAL *ptr,int mode) {
    assert(ptr==gsGlobal && mode==GS_ONESHOT);mode_switches++;
}
static void dashSpriteBatchEnd(void) { sprite_count++; }
static void dashWorkerParkPoint(void) { park_count++; }
static int dashWorkerIoBusy(void) { return worker_busy; }
static void DelayThread(int duration) { assert(duration==250); wait_calls++; }
static void mockDisplay(int base,int width,int psm,int x,int y) {
    assert(x==0 && y==0);
    shown_base=base;shown_width=width;shown_psm=psm;
    shown_count++;
}
#define GS_SET_DISPFB2(base,width,psm,x,y) mockDisplay(base,width,psm,x,y)
static void gsKit_setactive(GSGLOBAL *ptr) { assert(ptr==gsGlobal);active_count++; }
static void gsKit_sync_flip(GSGLOBAL *ptr) { assert(ptr==gsGlobal);sync_count++; }
static void gsKit_queue_exec(GSGLOBAL *ptr) { assert(ptr==gsGlobal);queue_count++; }
static void gsKit_TexManager_nextFrame(GSGLOBAL *ptr) { assert(ptr==gsGlobal);tex_frames++; }
static void dashWorkerPump(void) { pump_count++; }
static void dashStartupAudioAfterPresent(void) { assert(!frame_active); }
'''
code+=video_modes+"\n"
code+=fn("void setupGS(void)",classic)
code+=fn("void dashGfxInit(void)")
code+=fn("int dashGfxCanYield(void)")
code+=fn("void dashGfxSetPopup(int popup)")
code+=fn("int dashGfxPopupActive(void)")
code+=fn("static void waitVsyncSharing(void)")
code+=fn("static void flipVsyncSharing(void)")
code+=fn("void dashGfxPresent(void)")
code+=r'''
int main(void) {
    assert(!dashGfxCanYield());
    gfx_ready=1;assert(dashGfxCanYield());
    assert(!dashGfxPopupActive());
    foreground_wait=1;frame_active=1;dashGfxSetPopup(1);
    assert(!dashGfxPopupActive() && !dashGfxCanYield());dashGfxPresent();
    assert(dashGfxPopupActive());
    dashGfxSetPopup(0);assert(!dashGfxPopupActive());
    assert(dashGfxCanYield());gfx_ready=0;
    assert(!frame_active && !pump_count);
    foreground_wait=0;
    queue_count=tex_frames=sprite_count=park_count=sync_count=0;
    /* Cold boots select each supported configured mode once. The dashboard
     * keeps the existing screen and both framebuffer addresses on entry. */
    const int modes[]={TV_mode_NTSC,TV_mode_PAL,TV_mode_VGA,TV_mode_480P,TV_mode_576P};
    const int gs_modes[]={GS_MODE_NTSC,GS_MODE_PAL,GS_MODE_VGA_640_60,GS_MODE_DTV_480P,GS_MODE_DTV_576P};
    for(unsigned i=0;i<sizeof(modes)/sizeof(modes[0]);i++) {
        configured_mode=modes[i];gfx_ready=0;
        setupGS();
        int expected=i+1;
        assert(TV_mode==configured_mode && g.Mode==gs_modes[i]);
        assert(g.DoubleBuffering==GS_SETTING_ON);
        assert(init_count==expected && gsScreenGeneration==expected && offset_count==expected);
        assert(global_inits==expected && applied_params==expected && screen_params==expected && mode_switches==expected);
        uint32_t front=g.ScreenBuffer[0],back=g.ScreenBuffer[1];
        dashGfxInit();dashGfxInit();
        assert(g.DoubleBuffering==GS_SETTING_ON && g.ScreenBuffer[0]==front && g.ScreenBuffer[1]==back);
        assert(init_count==expected && gsScreenGeneration==expected && bound_generation==expected && offset_count==expected);
        assert(begin_count==expected && glow_count==expected);
    }

    /* Worker-active path: completed buffer 1 becomes visible and back
     * buffer 0 receives the next frame, exactly matching gsKit. */
    g.FirstFrame=GS_SETTING_OFF;
    worker_busy=1;
    csr=8;
    dashGfxPresent();
    assert(shown_count==1 && shown_base==0x120000/8192);
    assert(shown_width==10 && shown_psm==1);
    assert(g.ActiveBuffer==0 && active_count==1 && sync_count==0);
    assert(queue_count==1 && tex_frames==1 && pump_count==1);
    assert(park_count==1 && sprite_count==1);

    g.ScreenBuffer[0]=0;
    dashGfxPresent();
    assert(shown_count==2 && shown_base==0 && g.ActiveBuffer==1);
    assert(active_count==2 && sync_count==0);

    /* Unbusy path uses gsKit's own flip; this stub intentionally does not
     * change ActiveBuffer because gsKit internals are outside our scope. */
    worker_busy=0;
    dashGfxPresent();
    assert(sync_count==1 && shown_count==2 && queue_count==3);

    /* On the very first frame, keep gsKit's FirstFrame semantics. */
    g.FirstFrame=GS_SETTING_ON;worker_busy=1;
    dashGfxPresent();
    assert(sync_count==2 && shown_count==2);
    puts("PASS: one screen initialization per boot, configured modes/calibration retained on dashboard entry, double buffering and VBLANK front/back swaps");
}
'''
cc=shutil.which("gcc") or shutil.which("clang")
assert cc,"Host compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-anti-tear-") as tmp:
    src=Path(tmp)/"test.c"
    exe=Path(tmp)/"test"
    src.write_text(code)
    subprocess.run([cc,"-std=c11","-Wall","-Wextra","-Werror",str(src),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],check=True,timeout=5)
