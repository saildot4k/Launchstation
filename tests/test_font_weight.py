"""Exercise the bundled font palettes and real Bold/shadow drawing paths."""
from pathlib import Path
import ast
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
font = (root / "src/dash_font.c").read_text()
data_header = (root / "include/dash_font_data.h").read_text()
data = (root / "src/dash_font_data.c").read_text()
generator = ast.parse((root / "scripts/gen_dash_font.py").read_text())
sizes = next(ast.literal_eval(node.value) for node in generator.body
             if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "SIZES"
                                                    for target in node.targets))


def function(signature):
    start = font.index(signature)
    end = font.index("{", start) + 1
    depth = 1
    while depth:
        depth += (font[end] == "{") - (font[end] == "}")
        end += 1
    return font[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct { int r,g,b,a; } DashColor;
#define DC(r,g,b,a) ((DashColor){r,g,b,a})
typedef struct {
    int Width,Height,PSM,ClutPSM,ClutStorageMode,Filter,Delayed;
    u32 *Clut,*Mem;
} GSTEXTURE;
enum { GS_PSM_T8, GS_PSM_CT32, GS_CLUT_STORAGE_CSM1, GS_FILTER_LINEAR, DASH_FONT_ROBOTO, DASH_FONT_SYSTEM };
static struct { int font,font_scale,bold,text_shadow; } dashTheme;
static int cache_flushes,texture_setups,foreground,shadow;
static DashColor batch_color;
static void SyncDCache(void *start,void *end) {
    assert((u8 *)end-(u8 *)start==1024);cache_flushes++;
}
static void gsKit_setup_tbw(GSTEXTURE *t) { assert(t->Clut && t->Mem);texture_setups++; }
static float dashGfxTextY(float y) { return y; }
static void dashSpriteBatchBegin(GSTEXTURE *tex,DashColor color) { assert(tex);batch_color=color; }
static void dashSpriteBatchEnd(void) {}
static void dashSpriteBatchAdd(float x1,float y1,float u1,float v1,float x2,float y2,float u2,float v2) {
    assert(x2>x1 && y2>y1 && u2>u1 && v2>v1);
    if(batch_color.a==255) foreground++;
    else { assert(batch_color.a==89);shadow++; }
}
'''
code += data_header.replace("#include <tamtypes.h>", "")
code += data.replace('#include "dash_font_data.h"', "")
for name in ("FONT_CELL_W", "FONT_CELL_H", "FONT_SLOT_W", "FONT_SLOT_H", "FONT_COLS", "FONT_FIRST", "FONT_LAST",
             "FONT_GLYPHS", "DASH_FONT_UNIT", "CLASSIC_CELL_EM", "CLASSIC_XMID_ROW"):
    code += re.search(rf"^#define {name} .+$", font, re.M).group() + "\n"
for name in ("GlyphMetric", "FaceSel"):
    end = font.index("} " + name + ";") + len("} " + name + ";")
    code += font[font.rfind("typedef struct", 0, end):end] + "\n"
code += r'''
static GlyphMetric metrics[FONT_GLYPHS];
static GSTEXTURE font_tex,face_tex[DASH_FONT_FACES];
static u32 face_clut[DASH_FONT_FACES][256];
static int font_ready=1,faces_ready;
'''
for signature in ("static inline int clutSwizzle(", "static int nextGlyphs(", "static void facesInit(void)\n{",
                  "static float fontScale(", "static void pickFace(", "static float glyphAdv(",
                  "float dashTextWidthN(", "static float drawRun(", "float dashTextS("):
    code += function(signature)
code += "static const int expected_gamma[] = {" + ",".join(str(round(gamma * 100)) for _, gamma in sizes) + "};\n"
code += r'''
int main(void) {
    facesInit();assert(cache_flushes==DASH_FONT_FACES && texture_setups==DASH_FONT_FACES);
    /* Atlas alpha is decoded to regular coverage independently of text size. */
    for(int face=0;face<DASH_FONT_FACES;face++) {
        const DashFaceData *f=&dash_font_faces[face];
        assert(f->alpha_gamma100==expected_gamma[face] && face_tex[face].Clut==face_clut[face]);
        assert(face_tex[face].Width==f->tex_w && face_tex[face].Height==f->tex_h);
        for(int coverage=0;coverage<=255;coverage++) {
            int encoded=(int)(255*powf(coverage/255.0f,f->alpha_gamma100/100.0f)+0.5f);
            int actual=face_clut[face][clutSwizzle(encoded)]>>24;
            int expected=(coverage*128+127)/255;
            assert(abs(actual-expected)<=1);
            assert((face_clut[face][clutSwizzle(encoded)]&0xffffff)==0x808080);
        }
        for(int alpha=0;alpha<256;alpha++) {
            int actual=face_clut[face][clutSwizzle(alpha)]>>24;
            int linear=(alpha*128+127)/255;
            assert(actual<=linear);
            if(f->alpha_gamma100==100) assert(actual==linear);
        }
        if(f->alpha_gamma100<100) assert((face_clut[face][clutSwizzle(128)]>>24)<64);
    }
    for(int i=0;i<FONT_GLYPHS;i++) metrics[i]=(GlyphMetric){0,6,9};
    const int scales[]={90,100,115};
    const float sizes[]={0.60f,0.66f,0.82f,1.0f,1.1f,1.4f};
    const DashColor colors[]={DC(236,238,244,255),DC(118,214,255,255)};
    int used_faces[DASH_FONT_FACES]={0};
    for(int face=0;face<2;face++) for(int fs=0;fs<3;fs++) for(int size=0;size<6;size++) {
        dashTheme.font=face?DASH_FONT_SYSTEM:DASH_FONT_ROBOTO;dashTheme.font_scale=scales[fs];
        FaceSel chosen;pickFace(sizes[size],&chosen);
        if(!chosen.classic) used_faces[chosen.f-dash_font_faces]=1;
        float width=dashTextWidthN("Ag",-1,sizes[size]);
        for(int col=0;col<2;col++) for(int sh=0;sh<2;sh++) for(int bold=0;bold<2;bold++) {
            dashTheme.bold=bold;dashTheme.text_shadow=sh;foreground=shadow=0;
            float end=dashTextS(10,20,"Ag",sizes[size],colors[col]);
            assert(fabsf(end-(10+width))<0.001f);
            assert(foreground==(bold?4:2));
            assert(shadow==(sh?(bold?4:2):0));
        }
    }
    for(int face=0;face<DASH_FONT_FACES;face++) assert(used_faces[face]);
    assert(cache_flushes==DASH_FONT_FACES && texture_setups==DASH_FONT_FACES);
    puts("PASS: regular alpha at all atlas sizes, Bold-only extra strokes, selected/normal text, Roboto/System, stable metrics and independent shadow");
}
'''
with tempfile.TemporaryDirectory(prefix="font-weight-") as folder:
    path = Path(folder)
    (path / "font.c").write_text(code)
    exe = path / "font"
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "font.c"), "-lm", "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
