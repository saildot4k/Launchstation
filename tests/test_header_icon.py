"""Check the production header emblem's atlas packing, rotation and timing.

Host geometry checks cover both directions and the cycle boundary; this does
not substitute for PS2/GS visual validation.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
icons = (root / "src/dash_icons.c").read_text()
header = (root / "include/dash_internal.h").read_text()
ui = (root / "src/dash_ui.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint64_t u64;
typedef struct { u8 r,g,b,a; } DashColor;
typedef struct { int unused; } GSTEXTURE;
static GSTEXTURE icon_tex;
static int icons_ready=1, draws, tints, clock_reads;
static u64 now_ms;
static u64 Timer(void) { clock_reads++; return now_ms; }
static float dashClampf(float v,float lo,float hi) { return v<lo?lo:v>hi?hi:v; }
static DashColor dashIconTint(DashColor c) { tints++; c.g=17; return c; }
static struct { float x[4],y[4],u[4],v[4]; DashColor c; } quads[2];
static void dashTexDrawQuadUV(GSTEXTURE *tex,
    float x1,float y1,float u1,float v1, float x2,float y2,float u2,float v2,
    float x3,float y3,float u3,float v3, float x4,float y4,float u4,float v4,
    DashColor c)
{
    assert(tex==&icon_tex && draws<2);
    float xs[]={x1,x2,x3,x4},ys[]={y1,y2,y3,y4};
    float us[]={u1,u2,u3,u4},vs[]={v1,v2,v3,v4};
    memcpy(quads[draws].x,xs,sizeof(xs));memcpy(quads[draws].y,ys,sizeof(ys));
    memcpy(quads[draws].u,us,sizeof(us));memcpy(quads[draws].v,vs,sizeof(vs));
    quads[draws++].c=c;
}
'''
for macro in ("ICON_SIZE", "ICON_SLOT", "ICON_COLS", "ICON_TEX_W", "ICON_TEX_H",
              "SELECT_HALF_W", "APP_PART_SIZE", "APP_PART_SLOT", "APP_PART_X"):
    code += re.search(r"^#define " + macro + r" .+$", icons, re.M).group() + "\n"
start = header.index("enum DashIcon {")
code += header[start:header.index("};", start) + 2] + "\n"
code += icons[icons.index("typedef struct"):icons.index("static inline int clutSwizzle(")]
for signature in ("static void initHeaderIconParts(", "static void drawHeaderIconPart(",
                  "void dashHeaderIcon("):
    code += function(icons, signature)
code += r'''
static u8 atlas[ICON_TEX_W*ICON_TEX_H];
static void check_at(u64 ms,float degrees)
{
    const float cx=401,cy=40,size=26;
    const float width=size*(float)APP_PART_SLOT/APP_PART_SIZE;
    const float radians=degrees*3.14159265358979323846f/180;
    const float cs=cosf(radians),sn=sinf(radians);
    const DashColor color={123,234,210,211};
    now_ms=ms;draws=tints=clock_reads=0;
    dashHeaderIcon(cx,cy,size,color);
    assert(draws==2 && tints==1 && clock_reads==1);
    for(int part=0;part<2;part++) {
        float sine=part==0?-sn:sn;
        float vx=quads[part].x[1]-quads[part].x[0];
        float vy=quads[part].y[1]-quads[part].y[0];
        assert(fabsf(vx/width-cs)<0.00001f && fabsf(vy/width-sine)<0.00001f);
        float sx=0,sy=0;
        for(int k=0;k<4;k++) {sx+=quads[part].x[k];sy+=quads[part].y[k];}
        assert(fabsf(sx/4-cx)<0.0001f && fabsf(sy/4-cy)<0.0001f);
        assert(quads[part].c.r==123 && quads[part].c.g==17 &&
               quads[part].c.b==210 && quads[part].c.a==211);
        assert(quads[part].u[0]==APP_PART_X && quads[part].u[1]==APP_PART_X+APP_PART_SLOT);
        assert(quads[part].v[0]==part*APP_PART_SLOT && quads[part].v[2]==(part+1)*APP_PART_SLOT);
    }
}
int main(void)
{
    assert(APP_PART_X+APP_PART_SLOT<=ICON_TEX_W && 2*APP_PART_SLOT<=ICON_TEX_H);
    assert(((DI_COUNT+ICON_COLS-1)/ICON_COLS)*ICON_SLOT<=ICON_TEX_H);
    for(int y=0;y<ICON_TEX_H;y++) memset(atlas+y*ICON_TEX_W,0xA5,APP_PART_X);
    initHeaderIconParts(atlas);
    int ink[2]={0};
    for(int y=0;y<ICON_TEX_H;y++) for(int x=0;x<ICON_TEX_W;x++) {
        u8 a=atlas[y*ICON_TEX_W+x];
        if(x<APP_PART_X) { assert(a==0xA5); continue; }
        int part=y/APP_PART_SLOT, local_y=y%APP_PART_SLOT;
        int inside=part<2 && x>=APP_PART_X+2 && x<APP_PART_X+2+APP_PART_SIZE &&
                   local_y>=2 && local_y<2+APP_PART_SIZE;
        if(!inside) assert(!a); /* transparent gutters and unused rows */
        else ink[part]+=a!=0;
    }
    assert(ink[0]>0 && ink[1]>0);
    int middle=APP_PART_SIZE/2+2;
    assert(!atlas[middle*ICON_TEX_W+APP_PART_X+middle]);
    assert(atlas[(APP_PART_SLOT+middle)*ICON_TEX_W+APP_PART_X+middle]==255);

    check_at(0,0);check_at(1000,12);check_at(7500,90);
    check_at(15000,180);check_at(22500,270);
    check_at(29999,359.988f);check_at(30000,0);check_at(30001,0.012f);
    check_at(86400000000ULL+7500,90); /* long uptime keeps millisecond resolution */
    /* Frames between whole seconds must move, including across the wrap. */
    for(u64 ms=29960;ms<=30040;ms+=16)
        check_at(ms,(float)(ms%30000)*0.012f);

    draws=tints=clock_reads=0;icons_ready=0;
    dashHeaderIcon(0,0,26,(DashColor){255,255,255,255});
    icons_ready=1;
    dashHeaderIcon(0,0,0,(DashColor){255,255,255,255});
    dashHeaderIcon(0,0,26,(DashColor){255,255,255,0});
    assert(!draws && !tints && !clock_reads);
    puts("PASS: header atlas layers, fixed center/tint, opposite 30-second turns and smooth cycle wrap");
}
'''
assert "initHeaderIconParts(mem);" in function(icons, "void dashIconsInit(")
assert "dashHeaderIcon(" in function(ui, "void dashDrawHeader(")
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-header-icon-") as tmp:
    source = Path(tmp) / "header_icon.c"
    binary = Path(tmp) / "header_icon"
    source.write_text(code)
    subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", str(source), "-lm", "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
