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
enum {TV_mode_AUTO, TV_mode_NTSC, TV_mode_PAL, TV_mode_VGA, TV_mode_480P, TV_mode_576P, TV_mode_COUNT};
static struct {
    int Mode, Interlace, Field, Width, Height, StartX, StartY, DoubleBuffering, FirstFrame;
    unsigned CurrentPointer;
} g, *gsGlobal = &g;
static struct { int TV_mode,screen_x,screen_y; } config, *setting=&config;
static int TV_mode,region=TV_mode_NTSC,gsScreenGeneration,gfx_screen_gen=-1;
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
typedef struct { int unused; } GSTEXTURE;
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
harness += function(gfx, "int dashGfxCheckScreenChange(")
harness += function(gs, "static void applyGSParams(")
harness += function(gs, "static void initScreenParams(") + function(gs, "void updateScreenMode(")
harness += function(art, "GSTEXTURE *dashThemeTextureFile(")
harness += r'''
static int resolveMode(int choice) { return choice==TV_mode_AUTO?region:choice; }
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
    puts("PASS: 72 live video transitions, pending DMA/GS completion before reset, double buffering, "
         "Auto region, calibration, texture recovery and NTSC/PAL/VGA/480p/576p scaling");
}
int main(void) {
    checkSwitches();
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
assert '"VGA", "480p", "576p"' in (root / "src/dash_settings.c").read_text()
