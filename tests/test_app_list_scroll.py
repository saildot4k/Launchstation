"""Run the production Applications list through its synchronized text cycle."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
apps = (root / "src/dash_apps.c").read_text()
font = (root / "src/dash_font.c").read_text()
header = (root / "include/dash_internal.h").read_text()


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
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int DashColor;
typedef int GSTEXTURE;
typedef struct { char title[128],path[256],desc[64],author[32],version[16]; } DashApp;
static DashApp dashApps[2];
static int order[]={0,1},sel,norder=2;
static float sel_anim,age,font_scale=1;
static int face,focus_reads,draws,depth,pushes,pops,seen[3];
static float drawn_x[3],offsets[3],clip_x,clip_w;
static float dashClampf(float v,float lo,float hi) { return v<lo?lo:v>hi?hi:v; }
static float dashTextWidth(const char *s,float scale) {
    float width=0;
    for(;*s;s++)width+=(face?10:(*s=='W'?14:*s=='i'||*s=='.'?5:9))*scale*font_scale;
    return width;
}
static float dashTextLineH(float scale) { return 26*scale*font_scale; }
static DashApp *selApp(void) { return norder?&dashApps[sel]:NULL; }
static float dashUiFocusAge(void) { focus_reads++;return age; }
static void dashGfxScissorPush(float x,float y,float w,float h) {
    (void)y;assert(w>0 && h>0 && !depth);depth++;pushes++;clip_x=x;clip_w=w;
}
static void dashGfxScissorPop(void) { assert(depth==1);depth--;pops++; }
'''
for macro in ("DASH_SAFE_L", "DASH_SAFE_R", "DASH_PANE_R", "DASH_FS_SMALL",
              "DASH_FS_LABEL", "DASH_FS_CAPTION"):
    code += re.search(r"^#define " + macro + r" .+$", header, re.M).group() + "\n"
for macro in ("LIST_ROWS", "LIST_ROW_H"):
    code += re.search(r"^#define " + macro + r" .+$", apps, re.M).group() + "\n"
code += r'''
static float dashTextS(float x,float y,const char *s,float scale,DashColor color) {
    (void)y;(void)color;assert(selApp());
    int field=s==selApp()->path?2:scale==DASH_FS_SMALL?0:1;
    float start=field?368:78,viewport=field?224:226;
    assert(s==(field==2?selApp()->path:selApp()->title));
    assert(!seen[field]++);draws++;drawn_x[field]=x;offsets[field]=start-x;
    if(dashTextWidth(s,scale)>viewport) {
        assert(depth==1 && clip_x==start && clip_w==viewport);
    } else assert(!depth && x==start);
    return x+dashTextWidth(s,scale);
}
#define listCenteredTop(...) 0
#define dashDrawPanelBox(...) ((void)0)
#define dashGfxScissor(...) ((void)0)
#define dashDrawSelection(...) ((void)0)
#define dashGfxScissorReset(...) ((void)0)
#define dashArtGet(...) NULL
#define dashGfxPushAlpha(...) ((void)0)
#define appOpacity(...) 1.0f
#define dashTexDrawFit(...) ((void)0)
#define dashIcon(...) ((void)0)
#define dashItemColor(on) (on)
#define dashTextFit(...) ((void)0)
#define dashStoreIsFavorite(...) 0
#define dashGfxPopAlpha(...) ((void)0)
#define dashDrawScrollbar(...) ((void)0)
#define dashDrawCard(...) ((void)0)
#define dashDrawAppArt(...) ((void)0)
#define dashLibDeviceLabel(...) ((void)0)
#define dashTextWrap(...) ((void)0)
#define DASH_C_TEXT 1
#define DASH_C_TEXT3 2
'''
code += function(font, "void dashTextScrollProgress(")
code += function(apps, "static float listScrollProgress(")
code += function(apps, "static void drawList(")
code += r'''
static void drawAt(float when) {
    age=when;draws=focus_reads=pushes=pops=0;memset(seen,0,sizeof(seen));
    drawList();assert(draws==3 && focus_reads==1 && !depth && pushes==pops);
}
static void travelFor(float travel[3]) {
    const DashApp *a=selApp();
    travel[0]=fmaxf(0,dashTextWidth(a->title,DASH_FS_SMALL)-226);
    travel[1]=fmaxf(0,dashTextWidth(a->title,DASH_FS_LABEL)-224);
    travel[2]=fmaxf(0,dashTextWidth(a->path,DASH_FS_CAPTION*0.9f)-224);
}
static void checkPosition(float when,float expected,const float travel[3]) {
    drawAt(when);
    for(int field=0;field<3;field++)assert(fabsf(offsets[field]-travel[field]*expected)<0.002f);
}
static void checkCycle(void) {
    float travel[3];travelFor(travel);
    float longest=fmaxf(travel[0],fmaxf(travel[1],travel[2]));
    float move=fmaxf(longest/34,0.35f),end=3+move,cycle=end+3;
    checkPosition(-1,0,travel);
    checkPosition(0,0,travel);
    checkPosition(2.99f,0,travel);
    checkPosition(3,0,travel);
    checkPosition(3+move*0.5f,0.5f,travel);
    checkPosition(end,1,travel);
    checkPosition(end+1.5f,1,travel);
    checkPosition(cycle-0.01f,1,travel);
    checkPosition(cycle+0.01f,0,travel);
    checkPosition(cycle+2.99f,0,travel);
    checkPosition(cycle+3+move*0.5f,0.5f,travel);
    /* Every frame moves toward the text end or holds, through both dwells.
     * All overflowing fields have the same progress despite different lengths. */
    float previous[3]={0};
    for(int frame=0;frame<1000;frame++) {
        drawAt((cycle-0.01f)*frame/999);
        for(int field=0;field<3;field++) {
            assert(offsets[field]>=previous[field]-0.002f);
            assert(offsets[field]>=-0.002f && offsets[field]<=travel[field]+0.002f);
            if(travel[field]>0 && travel[1]>0)
                assert(fabsf(offsets[field]/travel[field]-offsets[1]/travel[1])<0.0001f);
            previous[field]=offsets[field];
        }
    }
}
int main(void) {
    for(int f=0;f<2;f++)for(int size=0;size<3;size++) {
        face=f;font_scale=size==0?0.75f:size==1?1:1.5f;
        strcpy(dashApps[0].title,"Wide application name WWW iii with a long descriptive title that needs scrolling");
        strcpy(dashApps[0].path,"usb0:/APPS/Long folder name/Another folder/Another long folder/More directories/Really long application filename.ELF");
        strcpy(dashApps[1].title,"Short");strcpy(dashApps[1].path,"mc0:/BOOT.ELF");
        sel=0;checkCycle();
        /* Fitting names stay still while a long path follows the shared cycle. */
        strcpy(dashApps[0].title,"Short");checkCycle();
        /* Focus changes restart all three from the beginning. */
        sel=1;float travel[3];travelFor(travel);
        checkPosition(0,0,travel);checkPosition(100,0,travel);assert(!pushes);
    }
    norder=0;draws=focus_reads=0;drawList();assert(!draws && focus_reads==1 && !depth);
    assert(listScrollProgress(NULL,226,224,10)==0);
    puts("PASS: Applications list name/detail/path scroll forward together, hold each end for 3 seconds, reset instantly, leave fitting text still, and balance clipping across font sizes/faces");
}
'''
compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("A host C compiler is required")
with tempfile.TemporaryDirectory(prefix="app-list-scroll-") as directory:
    source = Path(directory) / "scroll.c"
    executable = Path(directory) / "scroll"
    source.write_text(code)
    subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-variable", "-Wno-unused-but-set-variable",
                    str(source), "-lm", "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
