"""Run shared editor/naming keyboards, input decisions and drawing geometry."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_editor.c").read_text()
widgets = (root / "src/dash_widgets.c").read_text()
classic = (root / "src/editor_input.c").read_text()
header = (root / "include/launchelf.h").read_text()
dash_header = (root / "include/dash_internal.h").read_text()


def function(signature, body=source):
    start = body.index(signature)
    end = body.index("{", start) + 1
    depth = 1
    while depth:
        depth += (body[end] == "{") - (body[end] == "}")
        end += 1
    return body[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <math.h>
typedef uint64_t u64;
typedef int DashColor;
#define stricmp strcasecmp
#define MAX_PATH 1024
#define DASH_VW 640.0f
#define DASH_VH 448.0f
#define DASH_FS_SMALL 0.66f
#define DASH_TOAST_WARN 0
#define DC(r,g,b,a) (a)
static struct { int virtual_keyboard_layout, usbkbd_used, color[4]; } config, *setting=&config;
static void dashToast(int kind,const char *s) { (void)kind; (void)s; assert(0); }
'''
api_start = dash_header.index("typedef struct", dash_header.index("/* Shared native keyboard"))
api_end = dash_header.index("/* Native text entry", api_start)
code += dash_header[api_start:api_end]
code += re.search(r"^#define DASH_SELECT_EXTRA_W .+$", dash_header, re.M).group() + "\n"
layout_start = header.rfind("enum ", 0, header.index("VKEY_LAYOUT_ABC"))
code += header[layout_start:header.index("};", layout_start) + 2] + "\n"
for name in ("VKEY_LAYOUT_COLS", "VKEY_LAYOUT_ROWS", "VKEY_LAYOUT_SIZE", "VKEY_EDITOR_COLS", "VKEY_EDITOR_SIZE"):
    code += re.search(rf"^#define {name} .+$", header, re.M).group() + "\n"
code += (root / "src/virtual_keyboard.c").read_text().replace('#include "launchelf.h"', "")
table_start = classic.index("const unsigned char EditorSpecialChars[]")
table_end = classic.index(";", classic.index("const int EditorSpecialCharCount")) + 1
code += classic[table_start:table_end] + "\n"
doc_end = source.index("} EdDoc;") + len("} EdDoc;")
code += source[source.rfind("typedef struct", 0, doc_end):doc_end] + "\n"
for name in ("ED_MAX_SIZE", "ED_TAB", "ED_X", "ED_Y", "ED_W", "ED_ROW", "KB_H"):
    code += re.search(rf"^#define {name} .+$", source, re.M).group() + "\n"
code += "static int kb_shown;\nstatic DashKeyboard editor_keyboard;\n"
code += "#define kb_sel editor_keyboard.selected\n#define kb_act editor_keyboard.action\n#define kb_caps editor_keyboard.caps\n#define kb_page editor_keyboard.page\n"
code += "static void kbMove(int dx,int dy) { dashKeyboardMove(&editor_keyboard,dx,dy); }\n"
for signature in (
    "static void docRelines(", "static int docLineOf(", "static int docLineEnd(",
    "static int docColOf(", "static int docOffAtCol(", "static int docReserve(",
    "static int selRange(", "static void docDelete(", "static int docInsert(",
    "static void docBackspace(",
):
    code += function(signature)
code += function("static void kbTypeKey(")
code += function("static void moveCursor(") + function("static void moveLines(")
code += function("static int visibleRows(") + function("static void scrollToCursor(")
input_start = dash_header.rfind("enum {", 0, dash_header.index("DASH_IN_UP"))
code += dash_header[input_start:dash_header.index("};", input_start) + 2] + "\n"
code += "#define PAD_UP DASH_IN_UP\n#define PAD_DOWN DASH_IN_DOWN\n"
code += "#define PAD_LEFT DASH_IN_LEFT\n#define PAD_RIGHT DASH_IN_RIGHT\n"
for name in ("PAD_R3_H0", "PAD_R3_H1", "PAD_R3_V0", "PAD_R3_V1",
             "PAD_L3_H0", "PAD_L3_H1", "PAD_L3_V0", "PAD_L3_V1"):
    code += re.search(rf"^#define {name} .+$", header, re.M).group() + "\n"
input_start = source.index("else if (kb_shown) {") + len("else if (kb_shown) {")
input_end = source.index("\n\t\t} else {", input_start)
options_start = source.index("\t\tif (in.pressed & DASH_IN_MENU)\n\t\t\taction = editorMenu(d);", source.index("int dashTextEditorEx("))
options_end = source.index("\n\t\telse if (kb_shown)", options_start)
code += "static int options_opens;\nstatic int editorMenu(EdDoc *d) { (void)d;options_opens++;return 99; }\n"
code += "static int optionsInput(EdDoc *d, int pressed) { struct { int pressed; } in={pressed};int action=-1;\n"
code += source[options_start:options_end] + "\nreturn action;}\n"
code += "static void keyboardInputEvents(EdDoc *d, int pressed, int raw, int text_repeat) { struct { int pressed,raw_new,text_repeat; } in={pressed,raw,text_repeat};\n"
code += source[input_start:input_end] + "\n}\n"
code += r'''
static void keyboardInputRaw(EdDoc *d,int pressed,int raw) {
    keyboardInputEvents(d,pressed,raw,pressed&(DASH_IN_OK|DASH_IN_BACK));
}
static void keyboardInput(EdDoc *d,int pressed) {
    keyboardInputRaw(d,pressed,pressed&(DASH_IN_UP|DASH_IN_DOWN|DASH_IN_LEFT|DASH_IN_RIGHT));
}
typedef struct { float x,y,w,h; int selected; } Box;
typedef struct { float x,y; char text[40]; } Label;
static Box boxes[128];
static Label labels[128];
static int nboxes,nlabels,drawn[256],naming_mode,filename_ff,path_draws;
static float naming_title_y,naming_path_y,naming_path_w;
static char shown_directory[MAX_PATH];
static const char *naming_directory="mc0:/APPS/";
static void box(float x,float y,float w,float h,int selected) {
    assert(nboxes<128 && x>=34 && x+w<=606 && y>=(naming_mode?64:214) && y+h<394);
    boxes[nboxes++]=(Box){x,y,w,h,selected};
}
static void dashDrawPanelBox(float x,float y,float w,float h,float r) {
    (void)r; box(x,y,w,h,0);
}
static void dashDrawSelection(float x,float y,float w,float h,float r,float a) {
    (void)r; (void)a; box(x,y,w,h,1);
}
static void dashPanel(float x,float y,float w,float h,float r,DashColor color) {
    (void)r; (void)color; box(x,y,w,h,0);
}
static DashColor dashItemColor(int on) { return on; }
static void dashTextCenter(float x,float y,const char *s,float size,DashColor color) {
    (void)size; (void)color; assert(nlabels<128);
    labels[nlabels]=(Label){.x=x,.y=y};
    snprintf(labels[nlabels++].text,sizeof(labels[0].text),"%s",s);
}
static void dashFontMonoByte(unsigned char c,float x,float y,DashColor color) {
    (void)color; assert(c>=0x20 && y+16<394);
    if(!(naming_mode && y<190)) assert(x>=34 && x+8<606);
    if(naming_mode && y<190 && c==0xff) filename_ff++;
    drawn[c]++;
}
'''
keyboard_start = widgets.index("enum {", widgets.index("// Keyboard"))
code += widgets[keyboard_start:widgets.index("static void kbInsert(", keyboard_start)]
code += function("static void drawKeyboard(")
code += r'''
typedef struct { int pressed,raw_new,text_repeat; } DashInput;
typedef struct { int button;const char *key,*label; } DashHint;
#define DASH_C_ACCENT 1
#define DASH_C_TEXT 2
#define DASH_C_TEXT2 3
#define DASH_C_TEXT3 4
#define DASH_C_PANEL 5
#define DASH_FS_LABEL 0.9f
#define DASH_FS_CAPTION 0.6f
#define DASH_SND_CURSOR 1
#define DASH_SND_CANCEL 2
#define DASH_SND_CONFIRM 3
#define DI_EDIT 1
#define DI_BTN_SQUARE 2
#define DI_BTN_TRIANGLE 3
#define DI_BTN_R3 4
#define DI_BTN_SELECT 5
#define DI_BTN_START 6
#define PS2KBD_ESCAPE_KEY 0x1b
static int steps[256],raw_steps[256],text_steps[256],nsteps,next_step,frames,ticks,alpha_depth,offset_depth;
static int hint_buttons,hint_labels,hint_cursor;
static float hint_left,hint_right,hint_y,hint_scale=1.0f;
static unsigned char usb_data[64];
static int usb_length,usb_next;
static void dashStrCopy(char *out,const char *in,int cap) { snprintf(out,cap,"%s",in); }
static int dashWorkerIoBusy(void) { return 0; }
static int dashIopParked(void) { return 0; }
static int ensureUsbKeyboardReady(void) { return 1; }
static int PS2KbdRead(char *out) {
    if(usb_next>=usb_length) return 0;
    *out=(char)usb_data[usb_next++];return 1;
}
static void dashInputPollEx(DashInput *in,int usb) {
    assert(!usb && next_step<nsteps);in->pressed=steps[next_step];in->raw_new=raw_steps[next_step];in->text_repeat=text_steps[next_step++];
}
static void dashInputFlush(void) {}
static void dashSoundPlay(int sound) { (void)sound; }
static float dashVisualUpdate(void) { ticks++;return 1.0f/60.0f; }
static void dashRenderScene(void) { frames++;nboxes=nlabels=hint_buttons=hint_labels=hint_cursor=path_draws=0; }
static float dashApproach(float from,float to,float speed,float dt) { (void)from;(void)speed;(void)dt;return to; }
static float dashAnimSpeed(void) { return 1; }
static float dashEaseOutCubic(float x) { return x; }
static void dashModalBackdrop(float a) { (void)a; }
static void dashGfxPushAlpha(float a) { (void)a;alpha_depth++; }
static void dashGfxPopAlpha(void) { assert(alpha_depth==1);alpha_depth--; }
static void dashGfxPushOffset(float x,float y) { (void)x;(void)y;offset_depth++; }
static void dashGfxPopOffset(void) { assert(offset_depth==1);offset_depth--; }
static void dashModalPanel(float x,float y,float w,float h,float a) {
    (void)a;assert(w==572 && (h==276 || h==300));box(x,y,w,h,0);
}
static void dashIcon(int icon,float x,float y,float size,DashColor color) { (void)icon;(void)x;(void)y;(void)size;(void)color; }
static float dashTextWidth(const char *s,float size) { (void)size;return strlen(s)*6*hint_scale; }
static float dashTextS(float x,float y,const char *s,float size,DashColor color) {
    (void)color;float end=x+dashTextWidth(s,size);
    if(size==DASH_FS_LABEL)naming_title_y=y;
    if(hint_buttons && y==hint_y+4.5f) { hint_right=end;hint_labels++; }
    return end;
}
static void dashTextScrollTimed(float x,float y,float w,const char *s,float size,DashColor color,float age) {
    (void)size;(void)color;
    assert(x>=boxes[0].x && x+w<=boxes[0].x+boxes[0].w && w>0 && age>0);
    path_draws++;naming_path_y=y;naming_path_w=w;
    snprintf(shown_directory,sizeof(shown_directory),"%s",s);
}
static void dashTextRight(float x,float y,const char *s,float size,DashColor color) { (void)x;(void)y;(void)s;(void)size;(void)color; }
static DashColor dashColorA(DashColor color,float alpha) { (void)alpha;return color; }
static void dashPanelBorder(float x,float y,float w,float h,float r,DashColor color) { (void)x;(void)y;(void)w;(void)h;(void)r;(void)color; }
static void dashGfxScissor(float x,float y,float w,float h) { assert(x>=34 && y>=80 && x+w<=606 && y+h<394); }
static void dashGfxScissorReset(void) {}
static u64 Timer(void) { return 1000; }
static void dashRect(float x,float y,float w,float h,DashColor color) { (void)x;(void)y;(void)w;(void)h;(void)color; }
float dashButtonWidth(int icon,const char *key);
static int keyIcon(const char *key) { return key && !strcmp(key,"START")?DI_BTN_START:key && !strcmp(key,"SELECT")?DI_BTN_SELECT:-1; }
static float dashDrawButton(float x,float y,int icon,const char *key) {
    if(!hint_buttons) {hint_left=x;hint_y=y;}
    if(hint_buttons==4)assert(key && !strcmp(key,"START"));
    hint_buttons++;hint_cursor+=icon==DI_BTN_R3;
    return dashButtonWidth(icon,key);
}
static int dashOkIcon(void) { return 0; }
static int dashBackIcon(void) { return 1; }
static void dashGfxPresent(void) {}
'''
ui = (root / 'src/dash_ui.c').read_text()
code += function('static float buttonWidth(', ui) + function('float dashButtonWidth(', ui)
for signature in ('static void kbInsert(', 'static void kbDelete(', 'static int kbUsb(',
                  'static void kbDrawHints(', 'static int modalKeyboard(', 'int dashModalKeyboard(', 'int dashModalFilename(',
                  'static int classicKeyboard('):
    code += function(signature, widgets)
# Compile the classic fallback and its native-dialog dispatch as well.
gui = (root / 'src/gui.c').read_text()
code += r'''
#define FONT_WIDTH 8
#define FONT_HEIGHT 16
#define LINE_THICKNESS 1
#define SCREEN_WIDTH 640
#define SCREEN_HEIGHT 448
#define SCREEN_MARGIN 16
#define COLOR_BACKGR 0
#define COLOR_TEXT 1
#define COLOR_FRAME 2
#define COLOR_SELECT 3
#define TRUE 1
#define LNG(x) #x
#define PAD_START DASH_IN_START
#define PAD_L1 DASH_IN_L1
#define PAD_R1 DASH_IN_R1
#define PAD_CROSS DASH_IN_BACK
#define PAD_CIRCLE DASH_IN_OK
#define PAD_SQUARE DASH_IN_FAV
#define PAD_TRIANGLE DASH_IN_MENU
static int new_pad,swapKeys,Menu_tooltip_y=430,classic_drawn[256];
static int (*keyboardOverride)(char *,int,int,const char *);
static void waitPadReady(int port,int slot) { (void)port;(void)slot; }
static int readpad_no_KB(void) { assert(next_step<nsteps);new_pad=steps[next_step++];return !!new_pad; }
static void drawPopSprite(int color,int x1,int y1,int x2,int y2) { (void)color;(void)x1;(void)y1;(void)x2;(void)y2; }
#define drawFrame drawPopSprite
#define drawOpSprite drawPopSprite
#define drawSprite drawPopSprite
static int printXY(const char *text,int x,int y,int color,int draw,int limit) {
    (void)x;(void)y;(void)color;(void)draw;(void)limit;return strlen(text)*8;
}
static void drawChar(unsigned char c,int x,int y,int color) { (void)x;(void)y;(void)color;classic_drawn[c]++; }
static void drawScr(void) { frames++; }
'''
for signature in ('static int keyboardIsKey(', 'static int keyboardNextKey(', 'static int keyboardImpl(',
                  'int keyboard(', 'int filenameKeyboard('):
    # The unchanged classic loop compares its int cursor with strlen().
    if signature == 'static int keyboardImpl(':
        code += '#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wsign-compare"\n'
    code += function(signature, gui)
    if signature == 'static int keyboardImpl(':
        code += '#pragma GCC diagnostic pop\n'
code += r'''
static int font_ready,font_tex,packets;
#define GS_INTERLACED 1
#define GS_FIELD 0
static struct { int Interlace,Field; } gs_state,*gsGlobal=&gs_state;
static float g_sy=1.0f,g_oy;

#define FONT_FIRST 0x20
#define FONT_COLS 28
#define FONT_SLOT_W 18
#define FONT_SLOT_H 34
static float last_quad[8];
static void dashSpriteBatchBegin(const int *texture,DashColor color) { assert(texture==&font_tex);(void)color; }
static void dashSpriteBatchAdd(float x1,float y1,float u1,float v1,float x2,float y2,float u2,float v2) {
    float values[]={x1,y1,u1,v1,x2,y2,u2,v2};memcpy(last_quad,values,sizeof(values));packets++;
}
static void dashSpriteBatchEnd(void) {}
'''
code += function('float dashGfxTextY(', (root / 'src/dash_gfx.c').read_text())
code += function('void dashFontByte(', (root / 'src/dash_font.c').read_text()).replace('void dashFontByte(', 'void productionFontByte(')
code += r'''
static void planReset(void) { nsteps=usb_length=0;setting->usbkbd_used=0; }
static void planRaw(int pressed,int raw) {
    assert(nsteps<256);steps[nsteps]=pressed;raw_steps[nsteps]=raw;
    text_steps[nsteps++]=pressed&(DASH_IN_OK|DASH_IN_BACK);
}
static void plan(int pressed) { planRaw(pressed,pressed&(DASH_IN_UP|DASH_IN_DOWN|DASH_IN_LEFT|DASH_IN_RIGHT)); }
static void planRepeat(int action) { planRaw(0,0);text_steps[nsteps-1]=action; }
static int textDialog(char *buf,int cap,int filename,int bridge) {
    naming_mode=1;next_step=frames=ticks=usb_next=filename_ff=path_draws=0;
    int accepted=bridge ? (filename ? filenameKeyboard(buf,cap,naming_directory) : keyboard(buf,cap))>=0 :
                         (filename ? dashModalFilename("Text",buf,cap,naming_directory) : dashModalKeyboard("Text",buf,cap));
    assert(next_step==nsteps && frames==ticks && !alpha_depth && !offset_depth);
    if(frames) {
        int has_directory=filename && naming_directory && naming_directory[0];
        assert(path_draws==has_directory);
        if(has_directory) {
            assert(!strcmp(shown_directory,naming_directory));
            assert(naming_title_y<naming_path_y && naming_path_y+20<boxes[1].y);
            assert(naming_path_w==boxes[1].w && boxes[0].h==300);
            for(int i=2;i<nboxes;i++)assert(boxes[i].y>=boxes[1].y+boxes[1].h);
        } else assert(boxes[0].h==276);
    }
    naming_mode=0;return accepted;
}
static int nameDialog(char *buf,int cap) { return textDialog(buf,cap,1,0); }
static void checkNamingPaths(void) {
    char buf[256],long_directory[800];
    memset(long_directory,'a',sizeof(long_directory)-1);long_directory[sizeof(long_directory)-1]=0;
    memcpy(long_directory,"usb1:/",6);
    const char *paths[]={"mc1:/BADATA-SYSTEM/","usb0:/APPS/Utilities/",long_directory,"",NULL};
    for(int bridge=0;bridge<=1;bridge++) {
        keyboardOverride=bridge?classicKeyboard:NULL;
        for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);i++) {
            naming_directory=paths[i];strcpy(buf,"Folder");planReset();plan(0);plan(DASH_IN_START);
            assert(textDialog(buf,36,1,bridge) && !strcmp(buf,"Folder"));
            strcpy(buf,"Folder");planReset();plan(DASH_IN_OK);plan(DASH_IN_MENU);
            assert(!textDialog(buf,36,1,bridge) && !strcmp(buf,"Folder"));
        }
    }
    keyboardOverride=NULL;naming_directory="mc0:/APPS/";
    puts("PASS: naming title, actual parent path, field and keys stay ordered; long paths scroll without truncating the name buffer; native/classic routing and cancellation");
}
static void checkNamingHints(void) {
    for(int percent=90;percent<=115;percent+=5) {
        hint_scale=percent/100.0f;
        hint_buttons=hint_labels=hint_cursor=0;
        kbDrawHints(DASH_VW*0.5f,326);
        assert(hint_buttons==6 && hint_labels==6 && hint_cursor==1);
        assert(fabsf((hint_left+hint_right)*0.5f-DASH_VW*0.5f)<0.001f);
        assert(hint_left>=34+24 && hint_right<=606-24);
    }
    hint_scale=1;
    puts("PASS: naming helpers centered as a complete row at every font scale, including the right-stick cursor hint");
}
static void checkNamingDialogs(void) {
    DashKeyboard saved=editor_keyboard;
    char buf[256];setting->virtual_keyboard_layout=VKEY_LAYOUT_QWERTY;
    /* START immediately accepts a name without navigating to a Done key. */
    strcpy(buf,"name");planReset();plan(DASH_IN_START);
    assert(nameDialog(buf,255) && next_step==nsteps && !strcmp(buf,"name"));
    /* SELECT no longer accepts a name; deletion stays on the controller shortcut. */
    strcpy(buf,"name");planReset();plan(DASH_IN_SELECT);plan(DASH_IN_OK);plan(DASH_IN_START);
    assert(nameDialog(buf,255) && !strcmp(buf,"nameq"));
    strcpy(buf,"name");planReset();plan(DASH_IN_BACK);plan(DASH_IN_START);
    assert(nameDialog(buf,255) && !strcmp(buf,"nam"));
    /* Caps, cursor movement, buffer limits and cancellation use real input. */
    strcpy(buf,"ab");planReset();plan(DASH_IN_FAV);plan(DASH_IN_L1);plan(DASH_IN_OK);plan(DASH_IN_R1);plan(DASH_IN_START);
    assert(nameDialog(buf,255) && !strcmp(buf,"aQb"));
    /* Right-stick cursor movement is independent of D-pad key focus. */
    for(int filename=0;filename<=1;filename++) {
        strcpy(buf,"ab");planReset();planRaw(0,PAD_R3_H0);plan(DASH_IN_OK);
        planRaw(0,PAD_R3_H1);plan(DASH_IN_OK);plan(DASH_IN_START);
        assert(textDialog(buf,255,filename,0) && !strcmp(buf,"aqbq"));
        strcpy(buf,"ab");planReset();planRaw(DASH_IN_RIGHT,PAD_RIGHT|PAD_R3_H0);
        plan(DASH_IN_OK);plan(DASH_IN_START);
        assert(textDialog(buf,255,filename,0) && !strcmp(buf,"awb"));
        strcpy(buf,"ab");planReset();
        for(int i=0;i<5;i++)planRaw(0,PAD_R3_H0);
        plan(DASH_IN_OK);
        for(int i=0;i<5;i++)planRaw(0,PAD_R3_H1);
        plan(DASH_IN_OK);plan(DASH_IN_START);
        assert(textDialog(buf,255,filename,0) && !strcmp(buf,"qabq"));
        strcpy(buf,"ab");planReset();plan(DASH_IN_R3);
        planRaw(DASH_IN_LEFT,PAD_L3_H0);planRaw(0,PAD_R3_V0|PAD_R3_V1);
        plan(DASH_IN_OK);plan(DASH_IN_START);
        assert(textDialog(buf,255,filename,0) && !strcmp(buf,"abq"));
    }
    buf[0]=0;planReset();plan(DASH_IN_OK);plan(DASH_IN_OK);plan(DASH_IN_OK);plan(DASH_IN_START);
    assert(nameDialog(buf,2) && !strcmp(buf,"qq"));
    strcpy(buf,"original");planReset();plan(DASH_IN_OK);plan(DASH_IN_MENU);
    assert(!nameDialog(buf,255) && !strcmp(buf,"original"));
    /* General text fields retain symbols, including the last literal extended byte. */
    buf[0]=0;planReset();plan(DASH_IN_UP);plan(DASH_IN_UP);
    for(int i=0;i<kbSymbolPageCount();i++) plan(DASH_IN_OK);
    plan(DASH_IN_UP);
    int last_symbol=((int)sizeof(kb_ascii_symbols)-2+EditorSpecialCharCount)%KB_SYMBOL_PAGE_SIZE;
    for(int i=0;i<last_symbol%KB_SYMBOL_COLS;i++) plan(DASH_IN_RIGHT);
    plan(DASH_IN_OK);plan(0);plan(DASH_IN_START);
    assert(textDialog(buf,255,0,0) && (unsigned char)buf[0]==0xff && buf[1]==0 && filename_ff>0);
    /* USB input retains acceptance, cursor editing and cancel/restore behavior. */
    strcpy(buf,"ab");planReset();setting->usbkbd_used=1;
    unsigned char edit[]={0x1b,0x2a,'x',0x07,'y',0x0a};
    memcpy(usb_data,edit,sizeof(edit));usb_length=sizeof(edit);plan(0);
    assert(nameDialog(buf,255) && !strcmp(buf,"ayb"));
    strcpy(buf,"original");planReset();setting->usbkbd_used=1;
    unsigned char cancel[]={'x',0x1b,0x1b};
    memcpy(usb_data,cancel,sizeof(cancel));usb_length=sizeof(cancel);plan(0);
    assert(!nameDialog(buf,255) && !strcmp(buf,"original"));
    /* Filename input filters both key pairs; path/title prompts retain all four bytes. */
    unsigned char path[]={'a','/','?','b','\\','|','c',0x0a};
    for(int bridge=0;bridge<2;bridge++) for(int filename=0;filename<2;filename++) {
        keyboardOverride=bridge?classicKeyboard:NULL;
        buf[0]=0;planReset();setting->usbkbd_used=1;
        memcpy(usb_data,path,sizeof(path));usb_length=sizeof(path);plan(0);
        assert(textDialog(buf,255,filename,bridge));
        assert(!strcmp(buf,filename?"abc":"a/?b\\|c"));
    }
    keyboardOverride=NULL;
    /* Caps keeps the slash/question-mark key omitted and preserves focus. */
    buf[0]=0;planReset();plan(DASH_IN_FAV);plan(DASH_IN_DOWN);plan(DASH_IN_DOWN);
    for(int i=0;i<8;i++) plan(DASH_IN_RIGHT);
    plan(DASH_IN_FAV);plan(DASH_IN_OK);plan(DASH_IN_START);
    assert(nameDialog(buf,255) && !strcmp(buf,"."));
    assert(!memcmp(&saved,&editor_keyboard,sizeof(saved)));
    /* Literal font rendering uses the actual 0xFF atlas slot and the batched renderer. */
    productionFontByte(0xff,40,80,0);assert(!packets);font_ready=1;
    productionFontByte(' ',40,80,0);productionFontByte('\t',40,80,0);assert(!packets);
    productionFontByte(0xff,40,80,0);assert(packets==1);
    assert(last_quad[0]==39.5f && last_quad[1]==78.5f && last_quad[2]==486 && last_quad[3]==238);
    assert(last_quad[4]==48.5f && last_quad[5]==95.5f && last_quad[6]==504 && last_quad[7]==272);
    gs_state.Interlace=GS_INTERLACED;gs_state.Field=GS_FIELD;
    for(int scale=0;scale<2;scale++) for(int offset=-8;offset<=8;offset++) {
        g_sy=scale?512.0f/448.0f:1.0f;g_oy=offset*0.17f;
        productionFontByte(0xff,40,80.3f,0);
        float physical=(last_quad[1]+g_oy)*g_sy;
        assert(fabsf(physical/2-roundf(physical/2))<0.00001f);
    }
    puts("PASS: filename/general prompt routing, slash/question-mark/backslash/pipe filtering, Caps focus, pad/USB edits, cancellation, limits, literal 0xFF/alignment and independent editor state");
}
'''
code += r'''
static Label *label(const char *s) {
    for(int i=0;i<nlabels;i++) if(!strcmp(labels[i].text,s)) return &labels[i];
    return NULL;
}
static Box *keyBox(const char *s) {
    Label *l=label(s);assert(l);
    for(int i=1;i<nboxes;i++)
        if(fabsf(boxes[i].x+boxes[i].w/2-l->x)<0.01f && l->y>=boxes[i].y && l->y<boxes[i].y+boxes[i].h)
            return &boxes[i];
    assert(0);return NULL;
}
static void draw(void) {
    nboxes=nlabels=0; drawKeyboard();
    /* No key extends outside the panel or overlaps any other key. */
    float first_top=1000,last_bottom=0;
    for(int i=1;i<nboxes;i++) {
        Box a=boxes[i],panel=boxes[0];
        assert(a.x>=panel.x && a.x+a.w<=panel.x+panel.w && a.y>=panel.y && a.y+a.h<=panel.y+panel.h);
        /* Focus adds one pixel outside the key on each edge. */
        float top=a.y+a.selected,bottom=a.y+a.h-a.selected;
        if(top<first_top)first_top=top;
        if(bottom>last_bottom)last_bottom=bottom;
        for(int j=i+1;j<nboxes;j++) {
            Box b=boxes[j];
            assert(a.x+a.w<=b.x || b.x+b.w<=a.x || a.y+a.h<=b.y || b.y+b.h<=a.y);
        }
    }
    float top_gap=first_top-boxes[0].y;
    float bottom_gap=boxes[0].y+boxes[0].h-last_bottom;
    assert(fabsf(top_gap-6)<0.01f && fabsf(bottom_gap-top_gap)<0.01f);
}
static int state(void) { return kb_act<0?kb_sel:VKEY_LAYOUT_SIZE+kb_act; }
static void setState(int s) {
    kb_act=s>=VKEY_LAYOUT_SIZE?s-VKEY_LAYOUT_SIZE:-1;
    kb_sel=s<VKEY_LAYOUT_SIZE?s:KB_SPACE_KEY;
}
static void checkReachability(void) {
    int seen[VKEY_LAYOUT_SIZE+KA_COUNT]={0},queue[VKEY_LAYOUT_SIZE+KA_COUNT],head=0,tail=0;
    const int directions[][2]={{-1,0},{1,0},{0,-1},{0,1}};
    queue[tail++]=KB_SPACE_KEY; seen[KB_SPACE_KEY]=1;
    while(head<tail) {
        int old=queue[head++];
        for(int dir=0;dir<4;dir++) {
            setState(old); kbMove(directions[dir][0],directions[dir][1]);
            int next=state();
            assert(next>=0 && next<VKEY_LAYOUT_SIZE+KA_COUNT);
            assert(kb_act>=0 || kbIsKey(&editor_keyboard,kb_sel));
            if(!seen[next]) { seen[next]=1;queue[tail++]=next; }
        }
    }
    for(int i=0;i<VKEY_LAYOUT_SIZE;i++) assert(seen[i]==kbIsKey(&editor_keyboard,i));
    for(int a=0;a<KA_COUNT;a++) assert(seen[VKEY_LAYOUT_SIZE+a]==kbHasAction(&editor_keyboard,a));
}
static void checkFilenameLayouts(void) {
    Label filename_space[VKEY_LAYOUT_COUNT];
    for(int layout=0;layout<VKEY_LAYOUT_COUNT;layout++) for(int caps=0;caps<2;caps++) {
        setting->virtual_keyboard_layout=layout;
        dashKeyboardInit(&editor_keyboard,layout);
        editor_keyboard.single_line=editor_keyboard.filename=1;kb_caps=caps;
        checkReachability();kb_act=-1;kb_sel=KB_SPACE_KEY;draw();
        assert(label("Space") && !label("Symbols") && !label("/") && !label("\\") && !label("?") && !label("|"));
        if(!caps)filename_space[layout]=*label("Space");
        else assert(label("Space")->x==filename_space[layout].x && label("Space")->y==filename_space[layout].y);
        assert(!label("Tab") && !label("Del") && !label("Return"));
        if(layout==VKEY_LAYOUT_QWERTY && !caps) {
            kb_sel=0;draw();
            Box c=*keyBox("c"),period=*keyBox("."),space=*keyBox("Space");
            assert(space.x==c.x && space.x+space.w==period.x+period.w);
        }
        for(int i=0;i<VKEY_LAYOUT_SIZE;i++) {
            /* The entire key position stays hidden in both normal/Caps states. */
            int source=kbLayoutIndex(layout,i);
            int present=isVirtualKeyboardLayoutKey(layout,source);
            unsigned char c=getVirtualKeyboardLayoutChar(layout,source,caps);
            int allowed=present &&
                !strchr("/\\?|",getVirtualKeyboardLayoutChar(layout,source,0)) &&
                !strchr("/\\?|",getVirtualKeyboardLayoutChar(layout,source,1));
            assert(kbIsKey(&editor_keyboard,i)==allowed);
            kb_sel=i;kb_act=-1;
            assert(dashKeyboardPress(&editor_keyboard)==(allowed?c:0));
            c=getVirtualKeyboardLayoutChar(layout,i,caps);
            allowed=isVirtualKeyboardLayoutKey(layout,i) &&
                !strchr("/\\?|",getVirtualKeyboardLayoutChar(layout,i,0)) &&
                !strchr("/\\?|",getVirtualKeyboardLayoutChar(layout,i,1));
            assert(keyboardIsKey(i,caps,1)==allowed);
            assert(keyboardIsKey(i,caps,0)==isVirtualKeyboardLayoutKey(layout,i));
            const int dirs[][2]={{0,0},{-1,0},{1,0},{0,-1},{0,1}};
            for(int d=0;d<5;d++)
                assert(keyboardIsKey(keyboardNextKey(i,dirs[d][0],dirs[d][1],caps,1),caps,1));
        }
        for(int a=0;a<KA_COUNT;a++) {
            kb_act=a;
            assert(!kbHasAction(&editor_keyboard,a) && !dashKeyboardPress(&editor_keyboard));
            assert(kb_page==0);
        }
    }
    /* Run the actual classic input/drawing loop without the dashboard override. */
    setting->virtual_keyboard_layout=VKEY_LAYOUT_QWERTY;keyboardOverride=NULL;
    char buf[256];unsigned char path[]={'a','/','?','b','\\','|','c',0x0a};
    for(int filename=0;filename<2;filename++) {
        buf[0]=0;planReset();setting->usbkbd_used=1;usb_next=next_step=0;
        memcpy(usb_data,path,sizeof(path));usb_length=sizeof(path);
        memset(classic_drawn,0,sizeof(classic_drawn));
        for(unsigned i=0;i<sizeof(path);i++) plan(0);
        assert((filename?filenameKeyboard(buf,255,"mc0:/"):keyboard(buf,255))>0 && next_step==nsteps);
        assert(!strcmp(buf,filename?"abc":"a/?b\\|c"));
        assert(!!classic_drawn['/']==!filename && !!classic_drawn['\\']==!filename);
    }
    /* Native and classic pad navigation skip slash, preserving delete/cancel/accept. */
    strcpy(buf,"name");planReset();next_step=0;
    plan(DASH_IN_BACK);plan(DASH_IN_START);plan(DASH_IN_OK);
    assert(filenameKeyboard(buf,255,"mc0:/")==3 && !strcmp(buf,"nam"));
    buf[0]=0;planReset();next_step=0;
    plan(DASH_IN_DOWN);plan(DASH_IN_DOWN);plan(DASH_IN_DOWN);
    for(int i=0;i<8;i++) plan(DASH_IN_RIGHT);
    plan(DASH_IN_RIGHT);plan(DASH_IN_OK);plan(DASH_IN_START);plan(DASH_IN_OK);
    assert(filenameKeyboard(buf,255,"mc0:/")==1 && !strcmp(buf,"`"));
    puts("PASS: filename keys/actions hidden and unreachable across all six layouts and Caps states; classic USB/pad input, rendering and native override");
}
static void checkCursorStick(void) {
    const char *text="abcdef\nxy\n\t12345\nend";
    EdDoc d={.mark=-1};docRelines(&d);assert(docInsert(&d,text,strlen(text)));
    for(int page=0;page<=kbSymbolPageCount();page++) {
        dashKeyboardInit(&editor_keyboard,VKEY_LAYOUT_QWERTY);
        kb_shown=1;kb_page=page;kb_caps=1;
        DashKeyboard before=editor_keyboard;
        moveCursor(&d,4,0);
        keyboardInputRaw(&d,DASH_IN_LEFT,PAD_R3_H0);assert(d.cur==3 && d.want_col==3);
        keyboardInputRaw(&d,DASH_IN_RIGHT,PAD_R3_H1);assert(d.cur==4 && d.want_col==4);
        /* Short lines and tabs retain the requested visual column. */
        keyboardInputRaw(&d,DASH_IN_DOWN,PAD_R3_V1);assert(d.cur==9 && d.want_col==4);
        keyboardInputRaw(&d,DASH_IN_DOWN,PAD_R3_V1);assert(d.cur==11 && d.want_col==4);
        keyboardInputRaw(&d,DASH_IN_UP,PAD_R3_V0);assert(d.cur==9 && d.want_col==4);
        keyboardInputRaw(&d,DASH_IN_UP,PAD_R3_V0);assert(d.cur==4 && d.want_col==4);
        assert(kb_shown && !memcmp(&before,&editor_keyboard,sizeof(before)));
        moveCursor(&d,0,0);
        keyboardInputRaw(&d,DASH_IN_LEFT,PAD_R3_H0);
        keyboardInputRaw(&d,DASH_IN_UP,PAD_R3_V0);assert(d.cur==0);
        moveCursor(&d,d.len,0);
        keyboardInputRaw(&d,DASH_IN_RIGHT,PAD_R3_H1);
        keyboardInputRaw(&d,DASH_IN_DOWN,PAD_R3_V1);assert(d.cur==d.len);
        assert(!memcmp(&before,&editor_keyboard,sizeof(before)));
        /* D-pad only moves key focus; both controls can act in one poll. */
        keyboardInput(&d,DASH_IN_RIGHT);
        assert(d.cur==d.len && memcmp(&before,&editor_keyboard,sizeof(before)));
        before=editor_keyboard;moveCursor(&d,11,0);
        keyboardInputRaw(&d,DASH_IN_UP|DASH_IN_RIGHT,PAD_R3_V0|PAD_RIGHT);
        assert(d.cur==9 && memcmp(&before,&editor_keyboard,sizeof(before)));
        /* Left-stick motion and stick clicks do not move the cursor. */
        const int left_stick[][2]={{DASH_IN_LEFT,PAD_L3_H0},{DASH_IN_RIGHT,PAD_L3_H1},
                                   {DASH_IN_UP,PAD_L3_V0},{DASH_IN_DOWN,PAD_L3_V1}};
        for(int i=0;i<4;i++) {
            int cur=d.cur;before=editor_keyboard;
            keyboardInputRaw(&d,left_stick[i][0],left_stick[i][1]);
            assert(d.cur==cur && !memcmp(&before,&editor_keyboard,sizeof(before)));
        }
        int cur=d.cur;before=editor_keyboard;
        keyboardInputRaw(&d,DASH_IN_L3|DASH_IN_R3,0);
        assert(d.cur==cur && !memcmp(&before,&editor_keyboard,sizeof(before)));
    }
    /* Repeated stick navigation scrolls the ten-line viewport to the caret. */
    for(int i=0;i<40;i++) assert(docInsert(&d,"\nline",5));
    moveCursor(&d,0,0);
    for(int i=0;i<d.nlines+2;i++) {
        keyboardInputRaw(&d,DASH_IN_DOWN,PAD_R3_V1);
        scrollToCursor(&d,visibleRows(),60);
        int line=docLineOf(&d,d.cur);
        assert(line>=d.top && line<d.top+visibleRows() && kb_shown);
    }
    assert(docLineOf(&d,d.cur)==d.nlines-1 && d.top==d.nlines-10);
    free(d.buf);free(d.lines);
    puts("PASS: right-stick caret movement, tab/short-line columns, document bounds, independent D-pad focus, symbols pages and repeated viewport scrolling");
}
static void checkSpaceReturn(void) {
    for(int layout=0;layout<VKEY_LAYOUT_COUNT;layout++)
        for(int filename=0;filename<=1;filename++)
            for(int caps=0;caps<=1;caps++) {
                DashKeyboard kb;
                int returns=0;
                dashKeyboardInit(&kb,layout);kb.filename=kb.single_line=filename;kb.caps=caps;
                for(int page=0;page<=(filename?0:kbSymbolPageCount());page++) {
                    kb.page=page;
                    for(int row=0;row<KB_CHAR_ROWS;row+=KB_CHAR_ROWS-1)
                        for(int col=0;col<VKEY_LAYOUT_COLS;col++) {
                            int previous=row*VKEY_LAYOUT_COLS+col;
                            if(!kbIsKey(&kb,previous))continue;
                            kb.selected=previous;kb.action=-1;
                            int dy=row?1:-1;
                            dashKeyboardMove(&kb,0,dy);
                            if(kb.selected!=KB_SPACE_KEY || kb.action>=0)continue;
                            returns++;
                            assert(dashKeyboardPress(&kb)==' ');
                            assert(dashKeyboardPress(&kb)==' ');
                            dashKeyboardMove(&kb,0,-dy);
                            assert(kb.selected==previous && kb.action<0);
                        }
                }
                assert(returns>0);
            }
    puts("PASS: Space returns to the previous key in both keyboards, every layout, Caps and symbols pages");
}
static void checkTypingRepeat(void) {
    for(int layout=0;layout<VKEY_LAYOUT_COUNT;layout++)for(int caps=0;caps<=1;caps++) {
        EdDoc d={.mark=-1};docRelines(&d);
        dashKeyboardInit(&editor_keyboard,layout);kb_caps=caps;kb_shown=1;
        int expected=dashKeyboardPress(&editor_keyboard);
        keyboardInput(&d,DASH_IN_OK);
        for(int i=0;i<25;i++)keyboardInputEvents(&d,0,0,DASH_IN_OK);
        assert(d.len==26);
        for(int i=0;i<d.len;i++)assert((unsigned char)d.buf[i]==expected);
        for(int i=0;i<30;i++)keyboardInputEvents(&d,0,0,DASH_IN_BACK);
        assert(d.cur==0 && d.len==0);
        kb_sel=KB_SPACE_KEY;kb_act=-1;
        for(int i=0;i<8;i++)keyboardInputEvents(&d,0,0,DASH_IN_OK);
        assert(d.len==8 && !memcmp(d.buf,"        ",8));
        kb_act=KA_TAB;keyboardInputEvents(&d,0,0,DASH_IN_OK);assert(d.buf[d.len-1]=='\t');
        kb_act=KA_RETURN;keyboardInputEvents(&d,0,0,DASH_IN_OK);assert(d.buf[d.len-1]=='\n');
        kb_act=KA_SYMBOLS;keyboardInput(&d,DASH_IN_OK);
        int page=kb_page,len=d.len;
        for(int i=0;i<25;i++)keyboardInputEvents(&d,0,0,DASH_IN_OK);
        assert(kb_page==page && d.len==len); /* holding Type cannot cycle Symbols */
        free(d.buf);free(d.lines);
    }
    setting->virtual_keyboard_layout=VKEY_LAYOUT_QWERTY;
    for(int filename=0;filename<=1;filename++) {
        char buf[256]={0};planReset();plan(DASH_IN_OK);
        for(int i=0;i<25;i++)planRepeat(DASH_IN_OK);
        for(int i=0;i<3;i++)planRepeat(DASH_IN_BACK);
        plan(DASH_IN_START);
        assert(textDialog(buf,8,filename,0) && !strcmp(buf,"qqqqq"));
        strcpy(buf,"abc");planReset();plan(DASH_IN_BACK);
        for(int i=0;i<25;i++)planRepeat(DASH_IN_BACK);
        plan(DASH_IN_START);
        assert(textDialog(buf,8,filename,0) && !buf[0]);
    }
    puts("PASS: held Type/Delete edits both keyboards once per repeat, including Space/Tab/Return, caps, buffer limits and empty text; Symbols changes only on a new press");
}
int main(void) {
    EdDoc d={.mark=-1}; docRelines(&d);
    assert(KA_COUNT==3 && !strcmp(ka_names[KA_TAB],"Tab") && !strcmp(ka_names[KA_RETURN],"Return"));
    /* Every real key and action is reachable; blank cells on partial pages never receive focus. */
    for(int layout=0;layout<VKEY_LAYOUT_COUNT;layout++) {
        setting->virtual_keyboard_layout=layout;dashKeyboardInit(&editor_keyboard,layout);
        kb_act=-1;kb_sel=KB_SPACE_KEY;draw();
        Label fixed_space=*label("Space"),fixed_tab=*label("Tab"),fixed_return=*label("Return");
        for(kb_page=0;kb_page<=kbSymbolPageCount();kb_page++) {
            checkReachability();
            for(int i=0;i<VKEY_LAYOUT_SIZE;i++) if(!kbIsKey(&editor_keyboard,i)) {
                kb_sel=i; kb_act=-1; int len=d.len; kbTypeKey(&d); assert(d.len==len);
            }
            /* All themes/layouts fit the keyboard panel above the footer. */
            kb_act=-1;kb_sel=KB_SPACE_KEY;draw();
            assert(label("Space") && label("Tab") && !label("Del") && label("Return"));
            float left=boxes[1].x,right=boxes[1].x+boxes[1].w;
            for(int i=2;i<nboxes;i++) {
                if(boxes[i].x<left)left=boxes[i].x;
                if(boxes[i].x+boxes[i].w>right)right=boxes[i].x+boxes[i].w;
            }
            assert(fabsf((left+right)*0.5f-DASH_VW*0.5f)<0.01f);
            assert(label("Return")->x==fixed_return.x && label("Return")->y==fixed_return.y);
            assert(docInsert(&d,"!",1));int before_delete=d.len;
            keyboardInput(&d,DASH_IN_BACK);assert(d.len==before_delete-1);
            assert(label("Space")->x==fixed_space.x && label("Space")->y==fixed_space.y);
            assert(label("Tab")->x==fixed_tab.x && label("Tab")->y==fixed_tab.y);
            assert(!label("Enter") && !label("sp") && !label("Caps") && !label("Delete") && !label("Hide"));
            /* General text prompts keep every character, with no hidden actions in navigation. */
            DashKeyboard full=editor_keyboard;
            editor_keyboard.single_line=1;
            checkReachability();draw();
            assert(label("Space") && !label("Tab") && !label("Del") && !label("Return"));
            for(int a=KA_TAB;a<=KA_RETURN;a++) {
                editor_keyboard.action=a;
                assert(!dashKeyboardPress(&editor_keyboard));
            }
            editor_keyboard=full;
        }
        kb_page=0;kb_caps=0;kb_act=-1;
        /* Moving backslash preserves the full character set in every layout/shift. */
        for(int caps=0;caps<2;caps++) {
            int original[256]={0},native[256]={0};
            for(int i=0;i<VKEY_LAYOUT_SIZE;i++) {
                if(isVirtualKeyboardLayoutKey(layout,i)) original[(unsigned char)getVirtualKeyboardLayoutChar(layout,i,caps)]++;
                if(kbIsKey(&editor_keyboard,i)) native[(unsigned char)(i==KB_SPACE_KEY?' ':getVirtualKeyboardLayoutChar(layout,kbLayoutIndex(layout,i),caps))]++;
            }
            for(int i=0;i<256;i++) assert(original[i]==native[i]);
        }
        kb_sel=getVirtualKeyboardLayoutNextKey(layout,VKEY_LAYOUT_COLS,0,0);
        char expected=getVirtualKeyboardLayoutChar(layout,kb_sel,0);
        keyboardInput(&d,DASH_IN_OK); assert(d.buf[d.len-1]==expected);
        keyboardInput(&d,DASH_IN_FAV); assert(kb_caps);
        expected=getVirtualKeyboardLayoutChar(layout,kb_sel,1);
        keyboardInput(&d,DASH_IN_OK); assert(d.buf[d.len-1]==expected);
        int before=d.len;keyboardInput(&d,DASH_IN_BACK);assert(d.len==before-1);
    }
    /* Space spans C's left edge to period's right edge, including its focus bar. */
    setting->virtual_keyboard_layout=VKEY_LAYOUT_QWERTY;dashKeyboardInit(&editor_keyboard,VKEY_LAYOUT_QWERTY);
    kb_page=kb_caps=0;kb_act=KA_RETURN;draw();
    Box c=*keyBox("c"),period=*keyBox(".");Label space=*label("Space"); int found=0;
    for(int i=0;i<nboxes;i++) if(fabsf(boxes[i].x-c.x)<0.01f && fabsf(boxes[i].x+boxes[i].w-(period.x+period.w))<0.01f) {
        assert(fabsf(space.x-(boxes[i].x+boxes[i].w/2))<0.01f);found++;
    }
    assert(found==1);
    kb_act=-1;kb_sel=KB_SPACE_KEY;draw();found=0;
    for(int i=0;i<nboxes;i++) if(boxes[i].selected) {
        assert(fabsf(boxes[i].x-(c.x-1))<0.01f && fabsf(boxes[i].x+boxes[i].w-(period.x+period.w+1))<0.01f);found++;
    }
    assert(found==1);
    kbTypeKey(&d); assert(d.buf[d.len-1]==' ');
    /* Tab/Return align with Q/apostrophe; the number row has no Delete action. */
    kb_act=-1;kb_sel=0;draw();
    Box tab=*keyBox("Tab"),ret=*keyBox("Return");
    Box q=*keyBox("q"),apostrophe=*keyBox("'"),slash=*keyBox("\\"),bracket=*keyBox("]");
    assert(tab.y==q.y && fabsf(tab.x+tab.w+3-q.x)<0.01f);
    assert(ret.y==apostrophe.y && fabsf(apostrophe.x+apostrophe.w+3-ret.x)<0.01f);
    assert(slash.y==bracket.y && fabsf(bracket.x+bracket.w+3-slash.x)<0.01f);
    assert(label("Symbols")->y==label("Space")->y);
    kb_sel=VKEY_LAYOUT_COLS;kbMove(-1,0);assert(kb_act==KA_TAB);
    kbTypeKey(&d);assert(d.buf[d.len-1]=='\t');
    kbMove(1,0);assert(kb_act<0 && kb_sel==VKEY_LAYOUT_COLS);
    kb_sel=11;kbMove(1,0);assert(kb_act<0 && kb_sel==0);
    kbMove(-1,0);assert(kb_act<0 && kb_sel==11);
    assert(!label("Del") && !label("Delete"));
    kb_sel=2*VKEY_LAYOUT_COLS+10;kbMove(1,0);assert(kb_act==KA_RETURN);
    kbTypeKey(&d);assert(d.buf[d.len-1]=='\n');
    kbMove(-1,0);assert(kb_act<0 && kb_sel==2*VKEY_LAYOUT_COLS+10);
    kb_sel=KB_SPACE_KEY;kbMove(-1,0);assert(kb_act==KA_SYMBOLS);
    kbMove(1,0);assert(kb_act<0 && kb_sel==KB_SPACE_KEY);

    /* Repeated confirms on Symbols cycle every page and return to letters, without typing. */
    memset(drawn,0,sizeof(drawn));
    int expected_count[256]={0};
    for(unsigned i=0;i<sizeof(kb_ascii_symbols)-1;i++) expected_count[kb_ascii_symbols[i]]++;
    for(int i=0;i<EditorSpecialCharCount;i++) expected_count[EditorSpecialChars[i]]++;
    kb_caps=1;
    for(int round=0;round<2;round++) {
        int inserted[256]={0};
        for(int page=1;page<=kbSymbolPageCount();page++) {
            kb_act=KA_SYMBOLS; int before=d.len; keyboardInput(&d,DASH_IN_OK);
            assert(kb_page==page && kb_act==KA_SYMBOLS && d.len==before && kb_caps);
            if(!round) { draw(); char name[32];snprintf(name,sizeof(name),"Symbols %d/%d",page,kbSymbolPageCount());assert(label(name)); }
            kb_act=-1;
            for(int i=0;i<KB_CHAR_ROWS*VKEY_LAYOUT_COLS;i++) if(kbIsKey(&editor_keyboard,i)) {
                kb_sel=i;unsigned char c=kbSymbolChar(&editor_keyboard,i);kbTypeKey(&d);
                assert((unsigned char)d.buf[d.len-1]==c);inserted[c]++;
            }
        }
        for(int i=0;i<256;i++) assert(inserted[i]==expected_count[i]);
        kb_act=KA_SYMBOLS;int before=d.len;keyboardInput(&d,DASH_IN_OK);
        assert(!kb_page && kb_caps && kb_act==KA_SYMBOLS && d.len==before);
        kbMove(1,0);assert(kb_act<0 && kb_sel==KB_SPACE_KEY);
    }
    for(int i=0;i<256;i++) assert(drawn[i]==expected_count[i]);
    assert(drawn[0xff]==1);
    for(int shown=0;shown<=1;shown++) {
        kb_shown=shown;options_opens=0;
        assert(optionsInput(&d,DASH_IN_MENU)==99 && options_opens==1 && kb_shown==shown);
    }
    kb_shown=1;keyboardInput(&d,DASH_IN_MENU);assert(kb_shown); /* Options is handled before the keyboard branch. */
    /* Two extra hidden-keyboard text rows, a shorter keyboard, and resize at EOF. */
    kb_shown=0;assert(ED_Y==60 && visibleRows()==18);
    assert(ED_Y-4+visibleRows()*ED_ROW+8<394);
    kb_shown=1;assert(visibleRows()==10 && KB_H==147);
    assert(ED_Y-4+visibleRows()*ED_ROW+8<DASH_VH-58-KB_H);
    EdDoc long_doc={.mark=-1};docRelines(&long_doc);
    for(int i=0;i<40;i++) assert(docInsert(&long_doc,"line\n",5));
    scrollToCursor(&long_doc,visibleRows(),60);assert(long_doc.top==long_doc.nlines-10);
    kb_shown=0;scrollToCursor(&long_doc,visibleRows(),60);assert(long_doc.top==long_doc.nlines-18);
    free(long_doc.buf);free(long_doc.lines);
    checkCursorStick();
    checkSpaceReturn();
    checkNamingHints();
    checkFilenameLayouts();
    checkNamingDialogs();
    checkNamingPaths();
    checkTypingRepeat();
    free(d.buf);free(d.lines);
    puts("PASS: editor keyboard side-key/space geometry, viewport resize, reachable keys/actions, normal/caps input, complete symbol cycles including 0xFF, centered fixed pages, Tab/Return and controller Delete");
}
'''
with tempfile.TemporaryDirectory(prefix="editor-keyboard-") as folder:
    path = Path(folder)
    (path / "keyboard.c").write_text(code)
    exe = path / "keyboard"
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "keyboard.c"), "-lm", "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
