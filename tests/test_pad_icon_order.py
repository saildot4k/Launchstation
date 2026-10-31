"""Controller hint glyphs: START must look like START, SELECT like SELECT,
and hints may only name real PS2 buttons.

Regressions: "Menu" (START) once drew the SELECT bar, and the Applications
screen showed a "BACK" badge, which is not a PS2 button.
"""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
icons = (root / "src/dash_icons.c").read_text(encoding="utf-8")
ui = (root / "src/dash_ui.c").read_text(encoding="utf-8")


def case(name):
    start = icons.index(f"case {name}:")
    return icons[start:icons.index("break;", start)]


# START is the right-pointing wedge, SELECT the flat rounded bar.
assert "sdTriP(" in case("DI_BTN_START") and "sdBoxOutline(" not in case("DI_BTN_START")
assert "sdBox(" in case("DI_BTN_SELECT") and "sdBoxOutline(" not in case("DI_BTN_SELECT") and "sdTriP(" not in case("DI_BTN_SELECT")
key_icon = ui[ui.index("static int keyIcon("):ui.index("static float buttonWidth(")]
assert 'if (!strcmp(key, "START"))\n\t\treturn DI_BTN_START;' in key_icon
assert 'if (!strcmp(key, "SELECT"))\n\t\treturn DI_BTN_SELECT;' in key_icon
print("PASS: START/SELECT hint keys map to their own glyphs")

# Hint key badges must name real PS2 controller buttons ("BACK" is not one;
# the back action uses dashBackIcon(), i.e. Circle or Cross).
allowed = {"START", "SELECT", "L1", "L2", "L3", "R1", "R2", "R3", "L1/R1", "L2/R2"}
for path in sorted((root / "src").glob("*.c")):
    for key in re.findall(r'\.key = "([^"]+)"', path.read_text(encoding="utf-8", errors="replace")):
        assert key in allowed, f"{path.name}: hint key {key!r} is not a PS2 button"
print("PASS: hint key badges name real PS2 buttons")


# Execute the production SDF shapes and controller drawing at actual hint sizes.
# The GS samples pixels at integer coordinates and bilinear texels at n + 0.5.
# Comparing reflected output pixels catches shifted corners after minification;
# merely checking the symmetric source SDF cannot detect this rendering bug.
import shutil
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    pos = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos] + "\n"


header = (root / "include/dash_internal.h").read_text()
gfx = (root / "src/dash_gfx.c").read_text()
code = r"""
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct { int r,g,b,a; } DashColor;
typedef struct { int unused; } GSTEXTURE;
static struct { int icon_backing; } dashCfg;
static GSTEXTURE icon_tex;
static int icons_ready=1;
static float g_sy=1,g_ox,g_oy;
static float dashClampf(float v,float lo,float hi) { return v<lo?lo:v>hi?hi:v; }
static DashColor DC(int r,int g,int b,int a) { return (DashColor){r,g,b,a}; }
static DashColor dashIconTint(DashColor c) { return c; }
static void dashRoundedBorder(float x,float y,float w,float h,float r,DashColor c) {
 (void)x;(void)y;(void)w;(void)h;(void)r;(void)c;
}
static void dashSpriteBatchBegin(GSTEXTURE *tex,DashColor c) { assert(tex==&icon_tex && c.a); }
static void dashSpriteBatchEnd(void) {}
static struct { float x1,y1,x2,y2,u1,v1,u2,v2; } quad;
static void spriteBatchAddPhysical(float x1,float y1,float u1,float v1,float x2,float y2,float u2,float v2) {
 /* Model gsKit's 12.4 vertex/UV conversion. Atlas coordinates are positive. */
 quad.x1=floorf(x1*16)/16;quad.y1=floorf(y1*16)/16;
 quad.x2=floorf(x2*16)/16;quad.y2=floorf(y2*16)/16;
 quad.u1=floorf(u1*16)/16;quad.v1=floorf(v1*16)/16;
 quad.u2=floorf(u2*16)/16;quad.v2=floorf(v2*16)/16;
}
"""
start = header.index("enum DashIcon {")
code += header[start:header.index("};", start) + 2] + "\n"
for define in ("ICON_SIZE", "ICON_SLOT", "ICON_COLS", "SELECT_HALF_W",
               "APP_PART_SIZE", "APP_PART_SLOT", "APP_PART_X", "CLIP_ICON_Y"):
    code += re.search(r"^#define " + define + r" .+$", icons, re.M).group() + "\n"
code += re.search(r"^#define DASH_SELECT_EXTRA_W .+$", header, re.M).group() + "\n"
code += icons[icons.index("typedef struct"):icons.index("static inline int clutSwizzle(")]
for signature in ("static inline float SX(", "static inline float SY(",
                  "void dashSpriteBatchAdd(", "void dashSpriteBatchAddAligned("):
    code += function(gfx, signature)
code += function(icons, "void dashIcon(")
code += r"""
static unsigned char tile[ICON_SLOT][ICON_SLOT];
static float texel(int x,int y) {
 return x>=0 && y>=0 && x<ICON_SLOT && y<ICON_SLOT?tile[y][x]/255.0f:0;
}
static float sample(int id,int x,int y) {
 float u0=id>=DI_CUT?APP_PART_X:(id%ICON_COLS)*ICON_SLOT;
 float v0=id>=DI_CUT?CLIP_ICON_Y+(id-DI_CUT)*APP_PART_SLOT:(id/ICON_COLS)*ICON_SLOT;
 float u=quad.u1+(quad.u2-quad.u1)*(x-quad.x1)/(quad.x2-quad.x1)-u0-0.5f;
 float v=quad.v1+(quad.v2-quad.v1)*(y-quad.y1)/(quad.y2-quad.y1)-v0-0.5f;
 int tx=(int)floorf(u),ty=(int)floorf(v);float fx=u-tx,fy=v-ty;
 return texel(tx,ty)*(1-fx)*(1-fy)+texel(tx+1,ty)*fx*(1-fy)
       +texel(tx,ty+1)*(1-fx)*fy+texel(tx+1,ty+1)*fx*fy;
}
int main(void) {
 const int ids[]={DI_BTN_SELECT,DI_BTN_SQUARE,DI_BTN_CIRCLE};
 const float sizes[]={16,18,22,24,32};
 assert(DASH_SELECT_EXTRA_W==4.0f);
 for(unsigned id=0;id<sizeof(ids)/sizeof(ids[0]);id++) {
  memset(tile,0,sizeof(tile));
  for(int y=0;y<ICON_SIZE;y++)for(int x=0;x<ICON_SIZE;x++) {
   V2 p={(x+0.5f)/(ICON_SIZE*0.5f)-1,(y+0.5f)/(ICON_SIZE*0.5f)-1};
   float a=dashClampf(0.5f-iconSdf(ids[id],p)*(ICON_SIZE*0.5f),0,1);
   tile[y+2][x+2]=(unsigned char)(a*255+0.5f);
  }
  for(int backing=0;backing<2;backing++)for(int mode=0;mode<2;mode++)
  for(unsigned s=0;s<sizeof(sizes)/sizeof(sizes[0]);s++)for(int phase=0;phase<8;phase++) {
   dashCfg.icon_backing=backing;g_sy=mode?512.0f/448:1;
   g_ox=phase*0.125f;g_oy=phase*0.078125f;
   dashIcon(ids[id],13.25f,400,sizes[s],DC(255,255,255,255));
   int x0=(int)ceilf(quad.x1),y0=(int)ceilf(quad.y1);
   int xlast=(int)ceilf(quad.x2)-1,ylast=(int)ceilf(quad.y2)-1;
   for(int y=y0;y<=ylast;y++)for(int x=x0;x<=xlast;x++) {
    float alpha=sample(ids[id],x,y);
    if(fabsf(alpha-sample(ids[id],x0+xlast-x,y))>1.5f/255 ||
       fabsf(alpha-sample(ids[id],x,y0+ylast-y))>1.5f/255) {
     fprintf(stderr,"asymmetric controller glyph %d, size %.0f, PAL %d, phase %d at %d,%d\n",ids[id],sizes[s],mode,phase,x,y);
     abort();
    }
   }
   float middle=sample(ids[id],(x0+xlast)/2,(y0+ylast)/2);
   assert(ids[id]==DI_BTN_SELECT?middle>0.99f:middle<0.01f);
  }
 }
 /* Tab's entire arrow and Return's point must remain mirrored above/below
  * the shaft in rendered pixels, including PAL scaling and modal offsets. */
 const int keyboard_ids[]={DI_KEY_TAB,DI_KEY_RETURN};
 for(unsigned id=0;id<sizeof(keyboard_ids)/sizeof(keyboard_ids[0]);id++) {
  memset(tile,0,sizeof(tile));
  for(int y=0;y<APP_PART_SIZE;y++)for(int x=0;x<APP_PART_SIZE;x++) {
   V2 p={(x+0.5f)/(APP_PART_SIZE*0.5f)-1,(y+0.5f)/(APP_PART_SIZE*0.5f)-1};
   float a=dashClampf(0.5f-iconSdf(keyboard_ids[id],p)*(APP_PART_SIZE*0.5f),0,1);
   tile[y+2][x+2]=(unsigned char)(a*255+0.5f);
  }
  for(int mode=0;mode<2;mode++)for(unsigned s=0;s<sizeof(sizes)/sizeof(sizes[0]);s++)
  for(int phase=0;phase<8;phase++) {
   g_sy=mode?512.0f/448:1;g_ox=phase*0.125f;g_oy=phase*0.078125f;
   dashIcon(keyboard_ids[id],13.25f,270,sizes[s],DC(255,255,255,255));
   int x0=(int)ceilf(quad.x1),y0=(int)ceilf(quad.y1);
   int xlast=(int)ceilf(quad.x2)-1,ylast=(int)ceilf(quad.y2)-1,ink=0;
   for(int y=y0;y<=ylast;y++)for(int x=x0;x<=xlast;x++) {
    /* The Return elbow on the right is intentionally above the shaft. */
    if(keyboard_ids[id]==DI_KEY_RETURN && x>(x0+xlast)*0.5f)continue;
    float a=sample(keyboard_ids[id],x,y);
    ink+=a>0.1f;
    if(fabsf(a-sample(keyboard_ids[id],x,y0+ylast-y))>1.5f/255) {
     fprintf(stderr,"asymmetric keyboard arrow %d, size %.0f, PAL %d, phase %d at %d,%d\n",keyboard_ids[id],sizes[s],mode,phase,x,y);
     abort();
    }
   }
   assert(ink>0);
  }
 }
 puts("PASS: 160 rendered Tab/Return glyphs have mirrored arrowheads at five sizes, NTSC/PAL scaling and eight animation offsets");
 /* Small clipboard tiles must address the right margin, rather than a
  * ninth grid row outside the unchanged texture allocation. */
 g_sy=1;g_ox=g_oy=0;
 for(int id=DI_CUT;id<DI_COUNT;id++) {
  dashIcon(id,40,80,16,DC(255,255,255,255));
  assert(quad.u1==APP_PART_X && quad.u2==APP_PART_X+APP_PART_SLOT);
  assert(quad.v1==CLIP_ICON_Y+(id-DI_CUT)*APP_PART_SLOT);
  assert(quad.v2==quad.v1+APP_PART_SLOT);
  if(id==DI_KEY_TAB || id==DI_KEY_RETURN)
   assert(quad.x1==38.5f && quad.x2==56.5f && quad.y1==78.5f && quad.y2==96.5f);
  else assert(quad.x1==39 && quad.x2==57 && quad.y1==79 && quad.y2==97);
 }
 puts("PASS: clipboard icon UVs use the existing margin with transparent filtering gutters");
 puts("PASS: 480 controller glyph renders have mirrored corners/edges after scaling, with both backing choices; Select stays filled and Square/Circle hollow");
}
"""
cc = shutil.which("gcc") or shutil.which("clang")
assert cc, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-pad-corners-") as temp:
    source, binary = Path(temp) / "icons.c", Path(temp) / "icons"
    source.write_text(code)
    subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", str(source), "-lm", "-o", str(binary)], check=True)
    subprocess.run([str(binary)], timeout=10, check=True)
