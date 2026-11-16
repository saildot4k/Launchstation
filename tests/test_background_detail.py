"""Exercise production background timing/detail and draw submissions on the host.

Checks density at every motion speed, including frozen scenes and sustained slow
frames. Mock drawing counts prove scene content, not PS2 rendering/performance.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
header = (root / 'include/dash_internal.h').read_text()
bg = (root / 'src/dash_bg.c').read_text()
geo = (root / 'src/dash_bg_geo.c').read_text()
ps2 = (root / 'src/dash_bg_ps2.c').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


code = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef struct { u8 r,g,b,a; } DashColor;
typedef struct { int unused; } DashApp;
typedef struct { int Width,Height; } GSTEXTURE;
#define DC(r,g,b,a) ((DashColor){r,g,b,a})
#define DASH_VW 640
#define DASH_VH 448
#define DASH_FX_OFF 0
#define DASH_FX_SUBTLE 1
#define DASH_FX_FULL 2
#define DASH_WALL_FOCUS 1
#define DASH_BLEND_ADD 1
#define DASH_BLEND_NORMAL 0
#define GS_CMODE_REPEAT 1
#define GS_CMODE_CLAMP 0
#define CUBES 8
#define WAVE_SEGS 32
static struct { int effects,bg_detail; } dashCfg;
static struct { int bg,wallpaper; DashColor bg1,bg2; } dashTheme;
static int draws,lines,quads,sparkles,texture_draws,last_glow_alpha;
static float frame_dt=0.033f;
static float dashFrameDelta(void) { return frame_dt; }
static float dashAnimSpeed(void) { return 1; }
static DashApp *dashThemeFocusApp(void) { return NULL; }
static void dashThemeSetFocusApp(DashApp *app) { (void)app; }
#define dashSinf sinf
#define dashCosf cosf
static float dashClampf(float x,float lo,float hi) { return x<lo?lo:x>hi?hi:x; }
static DashColor dashColorScale(DashColor c,float f) { (void)f;return c; }
static DashColor dashColorLighten(DashColor c,float f) { (void)f;return c; }
static DashColor dashColorLerp(DashColor a,DashColor b,float f) { (void)b;(void)f;return a; }
static DashColor dashColorHue(int h,int s,int v,int a) { (void)h;(void)s;(void)v;return DC(255,255,255,a); }
#define dashRect(...) (++draws)
#define dashRectGradV(...) (++draws)
#define dashRectGradH(...) (++draws)
#define dashTri(...) (++draws)
#define dashLine(...) (++draws,++lines)
#define dashQuadG(...) (++draws,++quads)
#define dashSparkle(...) (++draws,++sparkles)
static void dashGlow(float x,float y,float rx,float ry,DashColor c) {
    (void)x;(void)y;(void)rx;(void)ry;draws++;last_glow_alpha=c.a;
}
#define dashGfxBlend(...) ((void)0)
#define gsKit_set_clamp(...) ((void)0)
#define dashTexDraw(...) (++draws,++texture_draws)
#define dashTexDrawUV(...) (++draws,++texture_draws)
static GSTEXTURE *dashThemeTexture(const char *name,int w,int h) {
    static GSTEXTURE texture={256,128};(void)name;(void)w;(void)h;return &texture;
}
'''
a = header.index('enum DashBgKind')
code += header[a:header.index('};', a) + 2] + '\n'
code += bg[bg.index('#define BG_STARS'):bg.index('static float frand(')]
code += function((root / 'src/dash_gfx.c').read_text(), 'float dashApproach(')
for name in ('static float frand(', 'float dashBgHash(', 'void dashBgVignette(',
             'static void spawnSpark(', 'void dashBgInit(', 'static int bgAnimated(',
             'void dashBgUpdate(', 'static void crystalBase(', 'static void drawThemeLayers(',
             'static void drawOrbs(', 'static void drawStars(', 'static void drawTower(',
             'static void sceneCrystal(', 'int dashBgSupportsDetail(', 'static int effectiveFx('):
    code += function(bg, name)
for name in ('static DashColor colA(', 'static float fracf(', 'static void trace(',
             'void dashBgSceneGradient(', 'void dashBgSceneLines(',
             'void dashBgSceneCubes(', 'void dashBgSceneStream(', 'void dashBgSceneWave('):
    code += function(geo, name)
for name in ('static void streak(', 'void dashBgSceneMist(',
             'void dashBgSceneStreaks(', 'void dashBgSceneClouds('):
    code += function(ps2, name)
code += r'''
static void crystal(float t,int fx) { (void)t;sceneCrystal(fx); }
int main(void) {
    void (*scenes[])(float,int)={dashBgSceneLines,dashBgSceneCubes,
        dashBgSceneStream,dashBgSceneWave,crystal,dashBgSceneMist,
        dashBgSceneStreaks,dashBgSceneClouds};
    int low[8]={0};
    const int supported[]={DASH_BG_GRADIENT,DASH_BG_TUNNEL,DASH_BG_MIST,
        DASH_BG_TOWERS,DASH_BG_DISC,DASH_BG_ORBIT,DASH_BG_CLOCKRING,
        DASH_BG_LINES,DASH_BG_CUBES,DASH_BG_STREAM,DASH_BG_WAVE,
        DASH_BG_CRYSTAL,DASH_BG_STREAKS,DASH_BG_CLOUDS};
    for(int kind=0;kind<DASH_BG_COUNT;kind++) {
        int expected=0;
        for(unsigned i=0;i<sizeof(supported)/sizeof(supported[0]);i++)
            expected|=kind==supported[i];
        assert(dashBgSupportsDetail(kind)==expected);
    }
    dashTheme.bg=DASH_BG_CRYSTAL;
    dashBgInit();
    for(int detail=0;detail<=1;detail++) {
        dashCfg.bg_detail=detail;
        for(int s=0;s<8;s++) {
            int baseline=0;
            for(int speed=0;speed<=200;speed+=10) {
                dashCfg.effects=speed;
                /* This must also hold after the old six-frame downgrade. */
                for(int frame=0;frame<620;frame++)
                    assert(effectiveFx()==(detail?DASH_FX_FULL:DASH_FX_SUBTLE));
                draws=lines=quads=sparkles=texture_draws=0;
                scenes[s](1.25f,effectiveFx());
                if(speed==0)baseline=draws;
                assert(draws==baseline);
                if(s==1)assert(lines==(detail?8:4)*12);
                if(s==3)assert(quads==(detail?3:2)*WAVE_SEGS*2);
                if(s==4) {
                    assert(sparkles==(detail?BG_SPARKS:BG_SPARKS/2));
                    assert(texture_draws==3); /* frozen Crystal keeps texture layers */
                }
            }
            if(!detail)low[s]=baseline;
            else assert(baseline>low[s]);
        }
        /* Detail may change the gradient's glow without adding primitives. */
        dashBgSceneGradient(1.25f,effectiveFx());
        assert(last_glow_alpha==(detail?17:10));
        for(int speed=0;speed<=200;speed+=10) {
            dashCfg.effects=speed;
            float before=bg_time;
            dashBgUpdate(0.1f);
            assert(fabsf(bg_time-before-speed*0.001f)<0.00001f);
        }
    }
    /* High-detail Crystal streaks must run below 100% motion as well. */
    dashCfg.effects=50;dashCfg.bg_detail=1;streak_t=-1;streak_next=0.01f;
    dashBgUpdate(0.1f);assert(streak_t==0);
    dashBgUpdate(0.1f);assert(fabsf(streak_t-0.05f)<0.00001f);
    dashCfg.effects=0;
    float time=bg_time,star=stars[0].x,life=sparks[0].life,rotation=towers[0].rot;
    dashBgUpdate(2);
    assert(time==bg_time && star==stars[0].x && life==sparks[0].life && rotation==towers[0].rot);
    assert(streak_t==0.05f);
    puts("PASS: Low/High density independent of 0-200% motion and slow frames; frozen Crystal layers, timing and slow streaks");
    return 0;
}
'''
compiler = shutil.which('gcc') or shutil.which('clang')
if not compiler:
    raise SystemExit('Host gcc or clang required')
with tempfile.TemporaryDirectory(prefix='launchstation-detail-') as tmp:
    source = Path(tmp) / 'detail.c'
    exe = Path(tmp) / 'detail'
    source.write_text(code)
    subprocess.run([compiler, '-std=c11', str(source), '-lm', '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
