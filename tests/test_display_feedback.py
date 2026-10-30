"""Exercise live video switches, graphics fences, scaling and texture recovery."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
gfx = (root / "src/dash_gfx.c").read_text()
gs = (root / "src/draw_gs.c").read_text()
art = (root / "src/dash_art.c").read_text()


def function(source, signature):
    start = source.index(signature)
    pos = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos] + "\n"


# Import saved IDs from the real header so the harness cannot hide a mismatch.
classic = (root / "include/launchelf.h").read_text()
video_start = classic.index("enum TV_mode {")
video_modes = classic[video_start:classic.index("};", video_start) + 2] + "\n"
video_modes += next(line for line in classic.splitlines()
                    if line.startswith("#define TV_MODE_LEGACY_576I ")) + "\n"

harness = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define GS_INTERLACED 1
#define GS_NONINTERLACED 0
#define GS_FIELD 0
#define GS_FRAME 1
#define GS_MODE_NTSC 2
#define GS_MODE_PAL 3
#define GS_MODE_VGA_640_60 4
#define GS_MODE_DTV_480P 5
#define GS_MODE_DTV_576P 0x53
#define FONT_HEIGHT 16
#define LINE_THICKNESS 2
#define DASH_VH 448
#define GS_SETTING_ON 1
#define GS_SETTING_OFF 0
#define ETM_INLINE 1
''' + video_modes + r'''
static struct {
    int Mode, Interlace, Field, Width, Height, StartX, StartY, DoubleBuffering, FirstFrame;
    unsigned CurrentPointer;
} g, *gsGlobal = &g;
static struct { int TV_mode,screen_x,screen_y; } config, *setting=&config;
static int TV_mode,region=TV_mode_NTSC,gsScreenGeneration,gfx_screen_gen=-1;
static char ROMVER_data[16]="0220E";
static unsigned char console_is_PSX;
static int fades,drains,finishes,inits,offsets,dma_busy,gs_busy,tex_resets,tex_modes;
static int uLE_InitializeRegion(void) { return region; }
static void fadeScreenToBlack(void) {
    /* The final drawScr submits a GIF DMA packet and a GS FINISH marker;
     * returning from the fade does not mean either has completed. */
    fades++;dma_busy=gs_busy=1;g.FirstFrame=GS_SETTING_OFF;
}
void dmaKit_wait_fast(void) { drains++;dma_busy=0; }
void gsKit_finish(void) { assert(!dma_busy);finishes++;gs_busy=0; }
static void gsKit_init_screen(__typeof__(g) *screen) {
    assert(screen==&g && screen->DoubleBuffering==GS_SETTING_ON);
    assert(!dma_busy && !gs_busy); /* Resetting GS with pending work can hang. */
    inits++;screen->StartX=100;screen->StartY=20;
    screen->CurrentPointer=2*screen->Width*screen->Height*4;
    screen->FirstFrame=GS_SETTING_OFF;
}
static void gsKit_set_display_offset(__typeof__(g) *screen,int x,int y) {
    assert(screen==&g && x==setting->screen_x && y==setting->screen_y);offsets++;
}
static void gsKit_TexManager_init(__typeof__(g) *screen) {
    assert(screen==&g && screen->CurrentPointer==2u*screen->Width*screen->Height*4);
    assert(screen->CurrentPointer<4*1024*1024);tex_resets++;
}
static void gsKit_TexManager_setmode(__typeof__(g) *screen,int mode) {
    assert(screen==&g && mode==ETM_INLINE);tex_modes++;
}
static int SCREEN_WIDTH, SCREEN_HEIGHT, Menu_end_y, Menu_start_y = 20;
static int Frame_end_y, Menu_tooltip_y;
static float g_sy = 1.0f, g_ox, g_oy;
typedef struct { int x0,x1,y0,y1; } DashClipRect;
typedef unsigned int u32;
enum { GS_PSM_CT32,GS_PSM_T8,GS_PSM_T4 };
typedef struct { int Width,Height,PSM,ClutPSM;void *Mem,*Clut; } GSTEXTURE;
static int texture_binds;
static unsigned gsKit_texture_size(int width,int height,int psm) {
    /* GS block/page padding for the sizes exercised below; include palette
     * blocks separately. The real wrapper must use the SDK size, not raw
     * pixel bytes. gsKit's allocator cannot return an oversize failure. */
    if(psm==GS_PSM_CT32 && width==16 && height==16)return 1024;
    if(psm==GS_PSM_CT32 && width==8 && height==2)return 256;
    if(psm==GS_PSM_CT32)return ((width+63u)/64)*64*((height+31u)/32)*32*4;
    if(psm==GS_PSM_T8)return ((width+127u)/128)*128*((height+63u)/64)*64;
    if(psm==GS_PSM_T4)return ((width+127u)/128)*128*((height+127u)/128)*128/2;
    return ~0u;
}
static unsigned gsKit_TexManager_bind(__typeof__(g) *screen,GSTEXTURE *tex) {
    assert(screen==&g);
    unsigned size=gsKit_texture_size(tex->Width,tex->Height,tex->PSM);
    if(tex->Clut)size+=gsKit_texture_size(tex->PSM==GS_PSM_T8?16:8,tex->PSM==GS_PSM_T8?16:2,tex->ClutPSM);
    assert(size<=4u*1024*1024-g.CurrentPointer);texture_binds++;return 1;
}
#define DASH_PATH_MAX 512
#define THEME_SLOTS 8
#define DASH_JOB_THEME 1
#define DASH_JOB_VISIBLE 2
enum { TS_EMPTY, TS_LOADED, TS_MISSING, TS_LOADING };
typedef struct {
    char path[DASH_PATH_MAX]; GSTEXTURE tex;
    int max_w, max_h, state; unsigned short gen;
} ThemeSlot;
typedef struct {
    int slot; unsigned short gen; char path[DASH_PATH_MAX];
    int max_w, max_h; u32 *pixels; int w, h, ok;
} ThemeTexJob;
static ThemeSlot theme_slots[THEME_SLOTS];
static int jobs, inactive, loading;
static void dashStrCopy(char *out, const char *in, int size) { snprintf(out, size, "%s", in); }
static int dashLoadingActive(void) { return loading; }
static int isPathDeviceStackLoaded(const char *path) { (void)path; return !inactive; }
static void themeTexRun(void *arg) { (void)arg; }
static void themeTexDone(void *arg) { (void)arg; }
static int dashWorkerSubmit(const char *name, int flags, void (*run)(void *), void (*done)(void *), void *arg) {
    (void)name; (void)flags; (void)run; (void)done;
    ++jobs; free(arg); return 0;
}
'''
harness += function(gfx, "static inline float SX(") + function(gfx, "static inline float SY(")
harness += function(gfx, "static DashClipRect clipFromLogical(")
harness += function(gfx, "float dashGfxTextY(")
harness += function(gfx, "int dashTexBind(")
harness += function(gfx, "int dashGfxCheckScreenChange(")
harness += function(gs, "int is576pSupported(") + function(gs, "static int requestedTVMode(")
harness += function(gs, "static void applyGSParams(")
harness += function(gs, "static void initScreenParams(") + function(gs, "void updateScreenMode(")
harness += function(art, "GSTEXTURE *dashThemeTextureFile(")
harness += r'''
static int expected_native576=1;
static int resolveMode(int choice) {
    if(choice==TV_mode_576P && !expected_native576)return region;
    return choice==TV_mode_AUTO?region:choice;
}
static int gsMode(int mode) {
    switch(mode) {
        case TV_mode_PAL:return GS_MODE_PAL;
        case TV_mode_VGA:return GS_MODE_VGA_640_60;
        case TV_mode_480P:return GS_MODE_DTV_480P;
        case TV_mode_576P:return GS_MODE_DTV_576P;
        default:return GS_MODE_NTSC;
    }
}
static void checkSwitches(void) {
    const struct { const char *rom;int psx,native; } consoles[]={
        {"0200E",0,0},{"0220E",0,1},{"0180J",1,1},{"0210J",1,1}
    };
    for(unsigned model=0;model<sizeof(consoles)/sizeof(consoles[0]);model++) {
        expected_native576=consoles[model].native;console_is_PSX=consoles[model].psx;
        strcpy(ROMVER_data,consoles[model].rom);
    for(region=TV_mode_NTSC;region<=TV_mode_PAL;region++)
        for(int from=0;from<TV_mode_COUNT;from++)
            for(int to=0;to<TV_mode_COUNT;to++) {
                setting->TV_mode=from;TV_mode=resolveMode(from);
                g.Mode=gsMode(TV_mode);applyGSParams();
                g.DoubleBuffering=GS_SETTING_ON;g.FirstFrame=GS_SETTING_OFF;
                g.StartX=100;g.StartY=20;setting->screen_x=12;setting->screen_y=-8;
                g.CurrentPointer=2*g.Width*g.Height*4;
                gfx_screen_gen=-1;assert(dashGfxCheckScreenChange());
                int generation=gsScreenGeneration,changed=TV_mode!=resolveMode(to);
                fades=drains=finishes=inits=offsets=tex_resets=tex_modes=0;
                setting->TV_mode=to;updateScreenMode();
                assert(fades==changed && drains==changed && finishes==changed && inits==changed);
                assert(gsScreenGeneration==generation+changed && offsets==1);
                assert(TV_mode==resolveMode(to) && g.Mode==gsMode(TV_mode));
                assert(setting->TV_mode==((to==TV_mode_576P && !expected_native576)?TV_mode_AUTO:to));
                int tall=TV_mode==TV_mode_PAL || TV_mode==TV_mode_576P;
                assert(SCREEN_WIDTH==640 && g.Width==640);
                assert(SCREEN_HEIGHT==(tall?512:448) && g.Height==SCREEN_HEIGHT);
                int interlace=TV_mode==TV_mode_NTSC || TV_mode==TV_mode_PAL;
                assert(g.Interlace==(interlace?GS_INTERLACED:GS_NONINTERLACED));
                assert(g.Field==(interlace?GS_FIELD:GS_FRAME));
                assert(setting->screen_x==12 && setting->screen_y==-8);
                assert(dashGfxCheckScreenChange()==changed);
                assert(tex_resets==changed && tex_modes==changed);
                assert(!dashGfxCheckScreenChange() && tex_resets==changed);
                assert(fabsf(g_sy-(float)SCREEN_HEIGHT/DASH_VH)<0.00001f);
                /* Every mode maps the same logical canvas and list spacing;
                 * scissor edges cover the entire new framebuffer. */
                g_ox=g_oy=0;
                DashClipRect full=clipFromLogical(0,0,640,448);
                assert(full.x0==0 && full.x1==639 && full.y0==0 && full.y1==g.Height-1);
                DashClipRect panel=clipFromLogical(34,96,572,296);
                assert(panel.x0==34 && panel.x1==605);
                assert(panel.y0==(int)(96*g_sy) && panel.y1==(int)(392*g_sy)-1);
                assert(fabsf((SY(102+29)-SY(102))-29*g_sy)<0.0001f);
            }
    }
    console_is_PSX=0;strcpy(ROMVER_data,"0220E");
    puts("PASS: 288 live video transitions across PS2 2.00/2.20 and PSX 1.80J/2.10J, NTSC/PAL regions, DMA/GS completion, "
         "double buffering, calibration, texture recovery, PAL/576p and Auto fallback scaling");
}
static void checkVramBudget(void) {
    unsigned pixel=0;GSTEXTURE t={640,512,GS_PSM_CT32,GS_PSM_CT32,&pixel,NULL};
    g.CurrentPointer=2u*640*512*4;assert(g.CurrentPointer==0x280000);
    assert(4u*1024*1024-g.CurrentPointer==0x180000);
    assert(dashTexBind(&t) && texture_binds==1); /* full-size wallpaper fits */
    t.Width=1024;assert(!dashTexBind(&t) && texture_binds==1);
    t.Width=511;t.Height=769;
    assert(511u*769*4<0x180000 && gsKit_texture_size(511,769,GS_PSM_CT32)>0x180000);
    assert(!dashTexBind(&t) && texture_binds==1); /* padded allocation does not fit */
    t.Width=768;t.Height=512;assert(dashTexBind(&t) && texture_binds==2); /* exact fit */
    t.Clut=&pixel;assert(!dashTexBind(&t) && texture_binds==2); /* plus palette exceeds pool */
    t.Width=512;t.Height=544;t.PSM=GS_PSM_T8;assert(dashTexBind(&t) && texture_binds==3);
    unsigned size=gsKit_texture_size(t.Width,t.Height,t.PSM);
    g.CurrentPointer=4u*1024*1024-size-1023;
    assert(!dashTexBind(&t) && texture_binds==3);
    g.CurrentPointer--;assert(dashTexBind(&t) && texture_binds==4); /* exact fit including CLUT */
    g.CurrentPointer=4u*1024*1024;assert(!dashTexBind(&t));
    g.CurrentPointer++;assert(!dashTexBind(&t)); /* no unsigned underflow */
    g.CurrentPointer=0x280000;t.PSM=99;assert(!dashTexBind(&t));
    t.PSM=GS_PSM_T8;t.Width=0;assert(!dashTexBind(&t));
    t.Width=512;t.Height=0;assert(!dashTexBind(&t));t.Height=-1;assert(!dashTexBind(&t));
    t.Height=544;t.Mem=NULL;assert(!dashTexBind(&t) && !dashTexBind(NULL));
    t=(GSTEXTURE){1024,448,GS_PSM_CT32,GS_PSM_CT32,&pixel,NULL};
    g.CurrentPointer=2u*640*448*4;assert(dashTexBind(&t));
    g.CurrentPointer=2u*640*512*4;int before=texture_binds;assert(!dashTexBind(&t) && texture_binds==before);
    g.CurrentPointer=2u*640*448*4;assert(dashTexBind(&t));
    puts("PASS: 2.5 MiB framebuffers / 1.5 MiB texture pool; oversized/padded/CLUT allocations "
         "are rejected before the non-returning allocator; valid textures survive mode changes");
}
static void checkRomSupport(void) {
    const struct { const char *rom;int psx,supported; } cases[]={
        {"0100J",0,0},{"0160E",0,0},{"0200E",0,0},{"0210J",0,0},{"0219E",0,0},
        {"0220E",0,1},{"0230E",0,1},{"0250E",0,1},{"",0,0},{"02x0E",0,0},
        {"0180J",0,0},{"0180J",1,1},{"0210J",1,1},{"0180E",1,0},{"0210E",1,0},
        {"0200J",1,0},{"0180",1,0},{"",1,0},{"01x0J",1,0}
    };
    for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++) {
        strcpy(ROMVER_data,cases[i].rom);console_is_PSX=cases[i].psx;
        int supported=cases[i].supported;
        assert(is576pSupported()==supported);
        for(region=TV_mode_NTSC;region<=TV_mode_PAL;region++) {
            setting->TV_mode=TV_mode_576P;
            int mode=requestedTVMode();
            assert(mode==(supported?TV_mode_576P:region));
            assert(setting->TV_mode==(supported?TV_mode_576P:TV_mode_AUTO));
            if(!supported) {
                TV_mode=region;g.Mode=gsMode(region);applyGSParams();
                g.DoubleBuffering=GS_SETTING_ON;
                setting->TV_mode=TV_mode_576P;
                fades=drains=finishes=inits=0;
                updateScreenMode();
                assert(!fades && !drains && !finishes && !inits);
                assert(setting->TV_mode==TV_mode_AUTO && TV_mode==region);
                assert(g.Mode==gsMode(region) && g.Interlace==GS_INTERLACED && g.Field==GS_FIELD);
                assert(g.Height==(region==TV_mode_PAL?512:448));
            }
            /* Old saved value 6 remains PAL on every supported console,
             * including NTSC machines and consoles without native 576p. */
            setting->TV_mode=TV_MODE_LEGACY_576I;
            assert(requestedTVMode()==TV_mode_PAL && setting->TV_mode==TV_mode_PAL);
            assert(requestedTVMode()==TV_mode_PAL && setting->TV_mode==TV_mode_PAL);
            const int invalid[]={-1,TV_mode_COUNT+1,9999};
            for(unsigned j=0;j<sizeof(invalid)/sizeof(invalid[0]);j++) {
                setting->TV_mode=invalid[j];
                assert(requestedTVMode()==region && setting->TV_mode==TV_mode_AUTO);
            }
        }
    }
    console_is_PSX=0;strcpy(ROMVER_data,"0220E");
    puts("PASS: 576p supports PS2 2.20+ and detected PSX 1.80J/2.10J; "
         "unsupported/invalid saved modes become Auto before GS initialization; legacy 576i settings become PAL");
}
int main(void) {
    assert(TV_mode_AUTO==0 && TV_mode_NTSC==1 && TV_mode_PAL==2 && TV_mode_VGA==3);
    assert(TV_mode_480P==4 && TV_mode_576P==5 && TV_mode_COUNT==6);
    assert(TV_MODE_LEGACY_576I==6); /* existing saved IDs retain their meaning */
    checkRomSupport();checkSwitches();checkVramBudget();
    int scale, offset, step;
    g.Interlace = GS_INTERLACED; g.Field = GS_FIELD;
    for (scale = 0; scale < 2; ++scale) {
        g_sy = scale ? 512.0f / 448.0f : 1.0f;
        for (offset = -16; offset <= 16; ++offset) {
            g_oy = offset * 0.17f;
            for (step = -30; step <= 300; ++step) {
                float y = step * 0.13f;
                float physical = (dashGfxTextY(y) + g_oy) * g_sy;
                assert(fabsf(physical / 2 - roundf(physical / 2)) < 0.00001f);
                assert(fabsf(physical - (y + g_oy) * g_sy) <= 1.00001f);
            }
        }
    }
    g.Interlace = GS_NONINTERLACED;
    assert(dashGfxTextY(13.37f) == 13.37f);
    g.Interlace = GS_INTERLACED; g.Field = GS_FRAME;
    assert(dashGfxTextY(13.37f) == 13.37f);
    g.Mode = GS_MODE_DTV_576P; applyGSParams();
    assert(g.Width == 640 && g.Height == 512);
    assert(g.Interlace == GS_NONINTERLACED && g.Field == GS_FRAME);
    g.Mode = GS_MODE_PAL; applyGSParams();
    assert(g.Width == 640 && g.Height == 512 && g.Interlace == GS_INTERLACED);
    g.Mode = GS_MODE_NTSC; applyGSParams();
    assert(g.Width == 640 && g.Height == 448 && g.Field == GS_FIELD);
    g.Mode = GS_MODE_DTV_480P; applyGSParams();
    assert(g.Width == 640 && g.Height == 448 && g.Interlace == GS_NONINTERLACED);
    /* One image used as both app icon and wallpaper must not reuse its thumbnail. */
    assert(!dashThemeTextureFile("usb0:/same.png", 128, 128) && jobs == 1);
    theme_slots[0].state = TS_LOADED;
    assert(dashThemeTextureFile("usb0:/same.png", 128, 128) == &theme_slots[0].tex);
    assert(!dashThemeTextureFile("usb0:/same.png", 640, 512) && jobs == 2);
    theme_slots[1].state = TS_LOADED;
    assert(dashThemeTextureFile("usb0:/same.png", 640, 512) == &theme_slots[1].tex);
    inactive = 1;
    assert(!dashThemeTextureFile("usb1:/missing.png", 640, 512) && jobs == 2);
    inactive = 0; loading = 1;
    assert(!dashThemeTextureFile("usb1:/missing.png", 640, 512) && jobs == 2);
    puts("PASS: NTSC/PAL physical field alignment, progressive animation, 576p geometry, resolution-aware wallpaper cache");
    return 0;
}
'''
cc = shutil.which("gcc") or shutil.which("clang")
if not cc:
    raise SystemExit("Host C compiler required")
build = root / "build"
build.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="display-", dir=build) as tmp:
    source, exe = Path(tmp) / "h.c", Path(tmp) / "h.exe"
    source.write_text(harness)
    subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", str(source), "-lm", "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)

font = (root / "src/dash_font.c").read_text()
assert "top = dashGfxTextY(y + sel.yshift);" in function(font, "static float drawRun(")
assert "TV_mode_480P,\n\tTV_mode_576P," in (root / "include/launchelf.h").read_text()
assert gs.count("case TV_mode_576P:") == 2  # initial setup and live changes
settings = (root / "src/dash_settings.c").read_text()
assert '"Auto", "NTSC", "PAL", "VGA", "480p", "576p"}' in settings
assert '"576i"' not in settings and '"576i"' not in (root / "src/config_screen.c").read_text()
