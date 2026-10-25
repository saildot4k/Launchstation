"""Sample production selection primitives for continuous, uniformly tinted borders.

This host raster model checks geometry and alpha composition, not GS scanout.
An optional source path runs the same assertions against an older dash_gfx.c.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
gfx = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else (root / "src/dash_gfx.c").read_text()
ui = (root / "src/dash_ui.c").read_text()
theme = (root / "src/dash_themes.c").read_text()
header = (root / "include/dash_internal.h").read_text()


def function(source, signature):
    start = source.index(signature)
    pos = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos] + "\n"


code = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef struct { u8 r,g,b,a; } DashColor;
typedef struct { int Width,Height; u32 *Mem; } GSTEXTURE;
static GSTEXTURE tex_corner,tex_ring;
static float g_alpha=1;
static struct { int corner,highlight; } dashTheme;
enum { DASH_CORNER_SQUARE,DASH_CORNER_SOFT,DASH_CORNER_ROUND };
enum { DASH_HL_FILL,DASH_HL_BAR,DASH_HL_OUTLINE,DASH_HL_TEXT };
static DashColor DASH_C_SELECT={23,61,117,111},DASH_C_SELEDGE={149,227,93,181};
static DashColor DASH_C_ACCENT={219,83,167,213};
static float dashClampf(float v,float lo,float hi) { return v<lo?lo:v>hi?hi:v; }
static u32 *allocTexMem(int w,int h) { return calloc(w*h,sizeof(u32)); }
static void setupTex(GSTEXTURE *t,int w,int h,u32 *mem) { t->Width=w;t->Height=h;t->Mem=mem; }
static u64 gsColor(DashColor c) { return (u64)c.r|((u64)c.g<<8)|((u64)c.b<<16)|((u64)c.a<<24); }
static int dashTexBind(GSTEXTURE *t) { return t->Mem!=NULL; }
static void dashSpriteBatchEnd(void) {}
typedef struct {
    double x[4],y[4];
    float u1,v1,u2,v2;
    DashColor c;
    GSTEXTURE *tex;
} Primitive;
static Primitive primitives[256];
static int count;
static void dashQuadG(float x1,float y1,float x2,float y2,float x3,float y3,float x4,float y4,
                     DashColor c1,DashColor c2,DashColor c3,DashColor c4) {
    assert(count<256 && !memcmp(&c1,&c2,sizeof(c1)) && !memcmp(&c1,&c3,sizeof(c1)) && !memcmp(&c1,&c4,sizeof(c1)));
    Primitive *p=&primitives[count++];memset(p,0,sizeof(*p));p->c=c1;
    /* Convert the renderer's triangle-strip order to perimeter order. */
    p->x[0]=x1;p->y[0]=y1;p->x[1]=x2;p->y[1]=y2;
    p->x[2]=x4;p->y[2]=y4;p->x[3]=x3;p->y[3]=y3;
}
static void dashRect(float x,float y,float w,float h,DashColor c) {
    if(w<=0 || h<=0 || !c.a || g_alpha<=0)return;
    dashQuadG(x,y,x+w,y,x,y+h,x+w,y+h,c,c,c,c);
}
static void dashRectGradV(float x,float y,float w,float h,DashColor top,DashColor bottom) {
    assert(!memcmp(&top,&bottom,sizeof(top)));dashRect(x,y,w,h,top);
}
static void texQuad(GSTEXTURE *t,float x1,float y1,float x2,float y2,
                    float u1,float v1,float u2,float v2,u64 tint) {
    DashColor c={tint&255,(tint>>8)&255,(tint>>16)&255,(tint>>24)&255};
    dashRect(x1,y1,x2-x1,y2-y1,c);
    Primitive *p=&primitives[count-1];p->tex=t;p->u1=u1;p->v1=v1;p->u2=u2;p->v2=v2;
}
static int contains(const Primitive *p,float x,float y) {
    int inside=0;
    for(int i=0,j=3;i<4;j=i++)
        if((p->y[i]>y)!=(p->y[j]>y) && x<(p->x[j]-p->x[i])*(y-p->y[i])/(p->y[j]-p->y[i])+p->x[i])
            inside=!inside;
    return inside;
}
static float texAlpha(const GSTEXTURE *t,int x,int y) {
    if(x<0)x=0;
    if(y<0)y=0;
    if(x>=t->Width)x=t->Width-1;
    if(y>=t->Height)y=t->Height-1;
    return (t->Mem[y*t->Width+x]>>24)/128.0f;
}
static void sample(float x,float y,float rgb[3]) {
    rgb[0]=11;rgb[1]=17;rgb[2]=23;
    for(int i=0;i<count;i++) {
        Primitive *p=&primitives[i];
        if(!contains(p,x,y))continue;
        float alpha=p->c.a/255.0f*g_alpha;
        if(p->tex) {
            float u=p->u1+(p->u2-p->u1)*(x-p->x[0])/(p->x[1]-p->x[0])-0.5f;
            float v=p->v1+(p->v2-p->v1)*(y-p->y[0])/(p->y[3]-p->y[0])-0.5f;
            int tx=(int)floorf(u),ty=(int)floorf(v);float fx=u-tx,fy=v-ty;
            alpha*=texAlpha(p->tex,tx,ty)*(1-fx)*(1-fy)+texAlpha(p->tex,tx+1,ty)*fx*(1-fy)
                  +texAlpha(p->tex,tx,ty+1)*(1-fx)*fy+texAlpha(p->tex,tx+1,ty+1)*fx*fy;
        }
        rgb[0]=p->c.r*alpha+rgb[0]*(1-alpha);
        rgb[1]=p->c.g*alpha+rgb[1]*(1-alpha);
        rgb[2]=p->c.b*alpha+rgb[2]*(1-alpha);
    }
}
'''
code += function(header, "static inline DashColor dashColorA(")
code += function(gfx, "DashColor dashColorLerp(")
code += function(gfx, "static inline u32 whiteA(")
code += function(gfx, "static void buildCornerTextures(")
code += function(theme, "float dashThemeRadius(")
code += function(gfx, "static void panelCorners(")
if "static void borderCorner(" in gfx:
    code += function(gfx, "static void borderCorner(")
code += "void dashRoundedGradV(float,float,float,float,float,DashColor,DashColor);\n"
code += "void dashRoundedBorder(float,float,float,float,float,DashColor);\n"
for signature in ("void dashPanelGradV(", "void dashRoundedGradV(", "void dashPanel(",
                  "void dashPanelBorder(", "void dashRoundedBorder("):
    code += function(gfx, signature)
code += function(ui, "void dashDrawSelection(")
code += r'''
static void samePixel(float x,float y,const float expected[3]) {
    float actual[3];sample(x,y,actual);
    for(int channel=0;channel<3;channel++) {
        if(fabsf(actual[channel]-expected[channel])>0.5f) {
            fprintf(stderr,"border mismatch at %.3f,%.3f: %.2f versus %.2f (corner=%d style=%d)\n",
                    x,y,actual[channel],expected[channel],dashTheme.corner,dashTheme.highlight);
            abort();
        }
    }
}
int main(void) {
    buildCornerTextures();
    const float radii[]={4,6,9,14,16};
    const float strengths[]={0.35f,0.7f,1.0f};
    for(int corner=0;corner<3;corner++) for(int mode=0;mode<2;mode++)
    for(unsigned radius=0;radius<sizeof(radii)/sizeof(radii[0]);radius++)
    for(unsigned strength=0;strength<sizeof(strengths)/sizeof(strengths[0]);strength++) {
        dashTheme.corner=corner;dashTheme.highlight=mode?DASH_HL_OUTLINE:DASH_HL_FILL;
        float r=dashThemeRadius(radii[radius]),w=120,h=40;
        float x=13.25f,y=7.125f,reference[3],background[3]={11,17,23};
        count=0;dashDrawSelection(x,y,w,h,radii[radius],strengths[strength]);
        sample(x+w/2,y+1,reference);
        samePixel(x+w/2,y+h-1,reference);
        samePixel(x+1,y+h/2,reference);samePixel(x+w-1,y+h/2,reference);
        if(r>=2) {
            for(int quadrant=0;quadrant<4;quadrant++) for(int angle=1;angle<18;angle++) {
                float a=angle*1.57079632679f/18,depth=r-1;
                float sx=(quadrant&1)?1:-1,sy=(quadrant&2)?1:-1;
                float cx=(quadrant&1)?x+w-r:x+r,cy=(quadrant&2)?y+h-r:y+r;
                samePixel(cx+sx*depth*cosf(a),cy+sy*depth*sinf(a),reference);
            }
            samePixel(x+0.05f,y+0.05f,background); /* keep the rounded cutout */
            samePixel(x+w-0.05f,y+h-0.05f,background);
        } else {
            samePixel(x+1,y+1,reference);samePixel(x+w-1,y+h-1,reference);
        }
        if(mode)samePixel(x+w/2,y+h/2,background); /* outline stays hollow */
    }
    count=0;dashRoundedBorder(0,0,120,40,9,(DashColor){1,2,3,0});assert(!count);
    g_alpha=0;dashRoundedBorder(0,0,120,40,9,DASH_C_ACCENT);assert(!count);g_alpha=1;
    free(tex_corner.Mem);free(tex_ring.Mem);
    puts("PASS: equal border tint/opacity on all four corners and straight edges, square/soft/round, solid/outline, translucent strength and rounded cutouts");
}
'''
cc = shutil.which("gcc") or shutil.which("clang")
assert cc, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-rounded-borders-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "test.c"), "-lm", "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True, timeout=10)
