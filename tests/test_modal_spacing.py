"""Production word wrapping, confirmation footers and one-line HDD size controls."""
from pathlib import Path
import json
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
ui = (root / 'src/dash_ui.c').read_text()
font = (root / 'src/dash_font.c').read_text()
hdd = (root / 'src/dash_hdd.c').read_text()
app = (root / 'src/dash_hdd_app.c').read_text()


def function(source, signature):
    start = source.index(signature)
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[start:], re.S):
        depth += (token.group() == '{') - (token.group() == '}')
        if not depth and token.group() == '}':
            return source[start:start + token.end()] + '\n'
    raise AssertionError(signature)


body = re.search(r'dashModalConfirm\("Install apps to HDD", "([^"\n]+)"', app)[1]
code = r'''
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "dash_icons.h"
typedef uint64_t u64;
typedef unsigned DashColor;
typedef struct {unsigned pressed;} DashInput;
typedef struct {const char *label,*value;} DashTableRow;
#define DASH_VW 640
static float DASH_VH;
#define DASH_LIST_ROW_H 24.0f
enum {DASH_FS_SMALL=1,DASH_FS_LABEL,DASH_FS_CAPTION,DASH_FS_TITLE,DASH_C_TEXT,DASH_C_TEXT2,DASH_C_TEXT3,DASH_C_ACCENT,DASH_C_WARM,
      DASH_SND_CURSOR,DASH_SND_CONFIRM,DASH_SND_CANCEL,DASH_BLEND_ADD,DASH_BLEND_NORMAL,
      DASH_IN_OK=1<<8,DASH_IN_BACK=1<<9,DASH_IN_UP=1<<10,DASH_IN_DOWN=1<<11,DASH_IN_LEFT=1<<12,DASH_IN_RIGHT=1<<13,
      DASH_IN_MENU=1<<14,DASH_IN_L1=1<<15,DASH_IN_R1=1<<16,DASH_IN_L2=1<<17,DASH_IN_R2=1<<18};
#define DC(a,b,c,d) 0
static struct {int glow;} dashTheme;
static struct {int icon_backing;} dashCfg;
static float glyph_w,panel_x,panel_y,panel_w,panel_h,body_bottom,detail_bottom,footer_y,hint_y,hint_end;
static int frame,reserve_mode,cancelled,body_rows,buttons,rendered;
static u64 Timer(void){return 0;}
static void dashInputFlush(void){}
static void dashInputPoll(DashInput*in){in->pressed=frame++?cancelled?DASH_IN_BACK:DASH_IN_OK:0;}
static void dashSoundPlay(int n){(void)n;}
static float dashVisualUpdate(void){return 1;}
static float dashAnimSpeed(void){return 1;}
static float dashApproach(float a,float b,float speed,float dt){(void)a;(void)speed;(void)dt;return b;}
static float dashEaseOutCubic(float v){return v;}
static float dashClampf(float v,float a,float b){return v<a?a:v>b?b:v;}
static void dashRenderScene(void){}
static void modalBackdrop(float n){assert(n==1);}
static void dashModalBackdrop(float n){assert(n==1);}
static void dashGfxPushAlpha(float n){assert(n==1);}
static void dashGfxPushOffset(float x,float y){assert(!x&&!y);}
static void dashGfxPopOffset(void){}
static void dashGfxPopAlpha(void){}
static void modalPanel(float x,float y,float w,float h,float alpha){
    assert(alpha==1&&x>=20&&y>=20&&x+w<=620&&y+h<=DASH_VH-20);
    panel_x=x;panel_y=y;panel_w=w;panel_h=h;
}
static void dashModalPanel(float x,float y,float w,float h,float a){modalPanel(x,y,w,h,a);}
static float dashTextWidthN(const char*s,int n,float scale){(void)s;(void)scale;return n*glyph_w;}
static float dashTextS(float x,float y,const char*s,float scale,DashColor c){
    (void)scale;(void)c;
    float end=x+strlen(s)*glyph_w;
    if(reserve_mode){assert(end<=panel_x+panel_w-24);if(end>hint_end)hint_end=end;}
    else {assert(x>=panel_x+30);body_rows++;if(y+20>body_bottom)body_bottom=y+20;}
    return end;
}
static void dashTextFit(float x,float y,float w,const char*s,float scale,DashColor c){
    (void)x;(void)w;(void)s;(void)scale;(void)c;
    if(!reserve_mode){body_rows++;if(y+20>body_bottom)body_bottom=y+20;}
}
static void dashTextScrollTimed(float x,float y,float w,const char*s,float scale,DashColor c,float age){
    (void)x;(void)w;(void)s;(void)scale;(void)c;(void)age;
    if(y>panel_y+60)detail_bottom=y+20;
}
static void dashText(float x,float y,const char*s,float scale,DashColor c){(void)x;(void)y;(void)s;(void)scale;(void)c;}
static void dashTextRight(float x,float y,const char*s,float scale,DashColor c){(void)x;(void)y;(void)s;(void)scale;(void)c;}
static void dashTextCenter(float x,float y,const char*s,float scale,DashColor c){(void)x;(void)y;(void)s;(void)scale;(void)c;}
static float dashButtonTextY(float y,float scale){(void)scale;return y+2;}
static void dashGfxBlend(int n){(void)n;}
static DashColor dashColorA(DashColor c,float a){(void)a;return c;}
static void dashGlow(float x,float y,float w,float h,DashColor c){(void)x;(void)y;(void)w;(void)h;(void)c;}
static void dashIcon(int icon,float x,float y,float size,DashColor c){(void)icon;(void)x;(void)y;(void)size;(void)c;}
static void dashPanel(float x,float y,float w,float h,int radius,DashColor c){
    (void)radius;(void)c;assert(x>=panel_x&&x+w<=panel_x+panel_w&&y>=panel_y&&y+h<=panel_y+panel_h);
    if(!reserve_mode){assert(y>=body_bottom+16&&y>=detail_bottom+16);footer_y=y;}
}
static float drawButton(float x,float y,int icon,const char*key){
    (void)icon;(void)key;assert(x>=panel_x+24&&x+22<=panel_x+panel_w-24);
    if(reserve_mode){if(buttons)assert(y==hint_y);hint_y=y;buttons++;}
    return 22;
}
static float dashDrawButton(float x,float y,int icon,const char*key){return drawButton(x,y,icon,key);}
static int dashOkIcon(void){return DI_BTN_CROSS;}
static int dashBackIcon(void){return DI_BTN_CIRCLE;}
static void dashGfxScissor(float x,float y,float w,float h){(void)x;(void)y;(void)w;(void)h;assert(0);}
static void dashGfxScissorReset(void){assert(0);}
static void dashDrawScrollbar(float x,float y,float h,float offset,int visible,int total){(void)x;(void)y;(void)h;(void)offset;(void)visible;(void)total;assert(0);}
static int hddPartitionSizeStep(int value,int step,int minimum,int maximum){(void)step;(void)minimum;(void)maximum;assert(0);return value;}
static void dashGfxPresent(void){
    rendered++;
    if(reserve_mode)assert(buttons==8&&hint_end<=panel_x+panel_w-24&&hint_y+22<panel_y+panel_h);
    else assert(body_rows>0&&footer_y>body_bottom&&footer_y>detail_bottom);
}
'''
code += function(font, 'static int textWrap(') + function(font, 'int dashTextWrapLines(') + function(font, 'int dashTextWrap(')
code += function(ui, 'static void modalHintRow(') + function(ui, 'void dashModalHintRow(')
code += function(ui, 'static int modalButtons(') + function(ui, 'int dashModalConfirm(')
code += function(hdd, 'static int pickSizeMenu(')
code += '\nstatic const char install_body[] = ' + json.dumps(body) + ';\n'
code += r'''
static void reset(void){frame=body_rows=buttons=rendered=0;body_bottom=detail_bottom=footer_y=hint_y=hint_end=0;}
int main(void){
    int underestimate=0;
    for(int height=384;height<=576;height+=32)for(int font=5;font<=12;font++)for(cancelled=0;cancelled<2;cancelled++){
        DASH_VH=height;glyph_w=font;reserve_mode=0;reset();
        int actual=dashTextWrapLines(380,6,install_body,DASH_FS_SMALL);
        if(actual>(int)(strlen(install_body)*glyph_w/380)+1)underestimate++;
        assert(dashModalConfirm("Install apps to HDD",install_body,"Continue",0)==!cancelled);
        assert(rendered==1&&body_rows==actual&&panel_h>=184);
        reset();assert(modalButtons("Details",install_body,"Selected PSU",DI_INFO,DASH_C_ACCENT,"Continue","Cancel",0,NULL,0)==!cancelled);
        assert(rendered==1&&detail_bottom>body_bottom);
        for(int backing=0;backing<2;backing++){
            reserve_mode=1;dashCfg.icon_backing=backing;reset();
            assert(pickSizeMenu("Choice 5 of 6: Reserved APA space for future use",0,65536,8192,0)==(cancelled?-1:8192));
            assert(rendered==1&&buttons==8);
        }
    }
    assert(underestimate>0);
    puts("PASS: real app-install wording uses measured word wrapping; body/detail/footer stay separated across font widths and video heights; all eight HDD size controls fit one row with either backing style");
}
'''
with tempfile.TemporaryDirectory(prefix='modal-spacing-') as tmp:
    p = Path(tmp)
    (p / 'test.c').write_text(code)
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=undefined', '-I', str(root / 'include'), str(p / 'test.c'), '-lm', '-o', str(p / 'test')], check=True)
    subprocess.run([str(p / 'test')], check=True, timeout=10)
