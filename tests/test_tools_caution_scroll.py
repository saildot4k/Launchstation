"""Run wrapped Tools cautions through their full upward-scroll/pause cycle."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
font = (root / "src/dash_font.c").read_text()
tools = (root / "src/dash_tools.c").read_text()
ui = (root / "src/dash_ui.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


draw = function(tools, "static void toolsDraw(")
assert "dashTextWrapScrollTimed(dx + 42, dy + dh - 58, dw - 62, 36, t->note," in draw
assert "18, dashUiFocusAge()" in draw
literal = r'"(?:\\.|[^"\\])*"'
table = tools[tools.index("static const Tool tools[]"):tools.index("#define NTOOLS")]
notes = re.findall(r"\{TA_\w+,\s*\w+,\s*(" + literal + r"),\s*" + literal +
                   r",\s*(" + literal + r"),", table)
assert len(notes) >= 8 and any(name == '"FTP Server"' for name, note in notes)

code = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int DashColor;
typedef struct { float x,y,w,h; } Clip;
typedef struct { float x,y;char text[256]; } Line;
static Line rendered[512];
static int rendered_count,fits,pushes,pops,depth,require_clip;
static int font_scale=100,font_face;
static float viewport_w,viewport_h;
static Clip clip={400,320,200,58},saved_clip;
static float dashTextWidthN(const char *s,int n,float scale) {
    float width=0;
    for(int i=0;s[i] && (n<0 || i<n);i++) {
        float units=10;
        if(!font_face)units=s[i]==' '?5:(s[i]=='i' || s[i]=='.')?5:s[i]=='W'?14:9;
        width+=units*scale*font_scale/100;
    }
    return width;
}
static float dashTextLineH(float scale) { return 26*scale*font_scale/100; }
static float dashTextS(float x,float y,const char *s,float scale,DashColor color) {
    (void)color;
    assert(rendered_count<512 && (!require_clip || depth==1));
    if(require_clip)assert(clip.x==414 && clip.y==330 && clip.w==viewport_w && clip.h==viewport_h+4);
    Line *line=&rendered[rendered_count++];line->x=x;line->y=y;
    snprintf(line->text,sizeof(line->text),"%s",s);
    return x+dashTextWidthN(s,-1,scale);
}
static float dashTextFit(float x,float y,float w,const char *s,float scale,DashColor color) {
    (void)w;(void)s;fits++;
    return dashTextS(x,y,"...",scale,color);
}
static void dashGfxScissorPush(float x,float y,float w,float h) {
    assert(!depth);saved_clip=clip;clip=(Clip){x,y,w,h};depth++;pushes++;
}
static void dashGfxScissorPop(void) { assert(depth==1);depth--;clip=saved_clip;pops++; }
'''
for signature in ("static int textWrap(", "int dashTextWrap(", "void dashTextWrapScrollTimed("):
    code += function(font, signature)
code += "static const char *const notes[]={\n" + ",\n".join(note for _, note in notes) + "\n};\n"
code += r'''
static float ui_time,focus_since,focus_pop;
static struct { int anim; } dashCfg={100};
static float dashTime(void) { return ui_time; }
'''
code += function(ui, "void dashUiFocusPoke(") + function(ui, "float dashUiFocusAge(")
code += r'''
#define TA_HEADER 0
static const struct { int action; } tools[]={{TA_HEADER},{1},{1}};
#define NTOOLS 3
static int tsel=1;
'''
code += function(tools, "static void tMove(") + function(tools, "static void toolsEnter(")
code += r'''
static void clear(void) { rendered_count=fits=pushes=pops=0;assert(!depth); }
static void compact(char *out,const char *in) {
    while(*in) { if(*in!=' ' && *in!='\n')*out++=*in;in++; }*out=0;
}
static void drawAt(const char *text,float age,float w,float h) {
    Clip before=clip;clear();require_clip=1;viewport_w=w;viewport_h=h;
    dashTextWrapScrollTimed(414,332,w,h,text,0.57f,1,18,age);
    require_clip=0;
    assert(!depth && pushes==1 && pops==1 && !fits);
    assert(!memcmp(&clip,&before,sizeof(clip)));
    assert(saved_clip.x==400 && saved_clip.y==320);
    /* All source text is wrapped and rendered, even beyond the visible box. */
    char joined[8192]={0},expected[8192],actual[8192];
    for(int i=0;i<rendered_count;i++) {
        assert(rendered[i].x==414);
        assert(dashTextWidthN(rendered[i].text,-1,0.57f)<=w+0.001f);
        strcat(joined,rendered[i].text);
    }
    compact(expected,text);compact(actual,joined);assert(!strcmp(actual,expected));
}
static void checkCycle(const char *text,float w,float h) {
    drawAt(text,0,w,h);
    int lines=rendered_count;assert(lines>0);
    assert(rendered[0].y==332);
    float last_bottom=rendered[lines-1].y+dashTextLineH(0.57f);
    float travel=last_bottom-(332+h);
    if(travel<=0) {
        drawAt(text,120,w,h);assert(rendered_count==lines && rendered[0].y==332);
        return;
    }
    float duration=travel/8;
    drawAt(text,duration*0.25f,w,h);
    assert(fabsf(rendered[0].y-(332-travel*0.25f))<0.001f);
    /* At the end, the entire final line is visible for a full two seconds. */
    drawAt(text,duration+0.001f,w,h);
    float at_end=rendered[0].y;
    assert(fabsf(rendered[lines-1].y+dashTextLineH(0.57f)-(332+h))<0.001f);
    drawAt(text,duration+1.999f,w,h);assert(rendered[0].y==at_end);
    /* Restart from the top, rather than scrolling back down. */
    drawAt(text,duration+2+0.001f,w,h);
    assert(fabsf(rendered[0].y-(332-0.008f))<0.002f);
    drawAt(text,2*(duration+2)+0.125f,w,h);
    assert(fabsf(rendered[0].y-331)<0.002f);
    drawAt(text,-5,w,h);assert(rendered[0].y==332);
}
int main(void) {
    for(font_face=0;font_face<2;font_face++)for(font_scale=90;font_scale<=115;font_scale+=5) {
        for(unsigned i=0;i<sizeof(notes)/sizeof(notes[0]);i++)checkCycle(notes[i],166,36);
        checkCycle("Short warning",166,36);
        checkCycle("First line\nSecond line\nThird line\nFinal line",166,36);
        char word[401];memset(word,'W',400);word[400]=0;checkCycle(word,40,36);
    }
    font_face=0;font_scale=100;clear();
    dashTextWrapScrollTimed(414,332,166,36,NULL,0.57f,1,18,0);
    dashTextWrapScrollTimed(414,332,166,36,"",0.57f,1,18,0);
    dashTextWrapScrollTimed(414,332,0,36,notes[0],0.57f,1,18,0);
    dashTextWrapScrollTimed(414,332,166,0,notes[0],0.57f,1,18,0);
    dashTextWrapScrollTimed(414,332,166,36,notes[0],0.57f,1,0,0);
    assert(!rendered_count && !pushes && !pops);
    /* Existing static wrapped labels retain their last-line ellipsis. */
    assert(dashTextWrap(414,332,50,2,"A fairly long static label that needs more lines",0.57f,1,18)==2);
    assert(fits==1 && rendered_count==2);
    clear();
    assert(textWrap(414,332,50,100,"Measure without drawing any text",0.57f,1,18,0)>2);
    assert(!rendered_count && !fits);
    /* Actual Tools focus changes restart the caution's elapsed-time clock. */
    ui_time=5;dashUiFocusPoke();ui_time=15;assert(dashUiFocusAge()==10);
    tMove(1);assert(tsel==2 && dashUiFocusAge()==0);
    drawAt(notes[0],dashUiFocusAge(),166,36);assert(rendered[0].y==332);
    ui_time=30;tMove(1);assert(tsel==1 && dashUiFocusAge()==0);
    tsel=0;ui_time=50;toolsEnter();assert(tsel==1 && dashUiFocusAge()==0);
    puts("PASS: every Tools caution, all font scales, full text/no ellipsis, slow upward motion, exact two-second end hold, restart and short-text stability");
    puts("PASS: focus reset, clip restore, newlines/long words, empty bounds, measurement and unchanged static wrapping");
}
'''
compiler = shutil.which("gcc") or shutil.which("cc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="tools-caution-scroll-") as folder:
    path = Path(folder)
    (path / "scroll.c").write_text(code)
    executable = path / "scroll"
    subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "scroll.c"), "-lm", "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True, timeout=10)
