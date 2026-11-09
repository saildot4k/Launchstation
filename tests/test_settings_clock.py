"""Run the real clock editor and chooser with scripted pad input and RTC spies."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
settings = (root / "src/dash_settings.c").read_text()
clock = (root / "src/dash_clock_sync.c").read_text()
header = (root / "include/dash_internal.h").read_text()
gfx = (root / "src/dash_gfx.c").read_text()


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
#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef int DashColor;
typedef struct { int pressed; } DashInput;
typedef struct { int icon; const char *label, *detail; int disabled; } DashMenuItem;
#define NITEMS(a) ((int)(sizeof(a)/sizeof((a)[0])))
#define DASH_VW 640
#define DASH_VH 448
#define DC(r,g,b,a) 0
'''
symbols = sorted(set(re.findall(r"\b(?:DI_|DASH_FS_|DASH_SND_|DASH_C_)\w+",
                               function(settings, "static int editClockDateTime("))))
code += "enum { " + ",".join(symbols + ["DI_CHECK", "DI_WARNING"]) + " };\n"
input_start = header.rfind("enum {", 0, header.index("DASH_IN_UP"))
code += header[input_start:header.index("};", input_start) + 2] + "\n"
code += function(clock, "static int manualLeap(") + function(clock, "int dashClockDaysInMonth(")
code += function(gfx, "float dashApproach(")
code += r'''
static int inputs[512], input_count, input_index, shoulder_input;
static float footer_y;
static int flushes, ticks, renders, presents, digits, plus, minus, selected, sounds[3];
static float selected_x, plus_x, minus_x;
static int shown[6], choice=-1, rtc_valid=1, manual_ok=1;
static int current[6], expected[6], menus, field_reads, manual_writes, messages, last_icon;
static float panel_open;
static char last_title[80], last_body[200], last_detail[32];
static void press(int input) { assert(input_count<NITEMS(inputs));inputs[input_count++]=input; }
static void selectField(int field) { for(int i=0;i<field;i++)press(DASH_IN_RIGHT); }
static void dashInputPoll(DashInput *in) {
    assert(input_index<input_count);int event=inputs[input_index++];in->pressed=event&0xffff;shoulder_input=(unsigned)event>>16;
}
static unsigned dashInputShoulderRepeat(void) { return shoulder_input; }
static void repeatShoulder(int button) { press(button<<16); }
static void dashInputFlush(void) { if(!(flushes%2))panel_open=0;flushes++; }
static void dashSoundPlay(int sound) {
    if(sound==DASH_SND_CONFIRM)sounds[0]++;
    else if(sound==DASH_SND_CANCEL)sounds[1]++;
    else { assert(sound==DASH_SND_CURSOR);sounds[2]++; }
}
static float dashVisualUpdate(void) { ticks++;return 0.02f; }
static float dashAnimSpeed(void) { return 1; }
static float dashEaseOutCubic(float t) { return 1-(1-t)*(1-t)*(1-t); }
static DashColor dashItemColor(int selected) { return 100+selected; }
static void dashRenderScene(void) { renders++;digits=plus=minus=0;selected=-1;footer_y=-1; }
static void dashModalPanel(float x,float y,float w,float h,float open) {
    assert(x>=40 && x+w<=600 && y>=26 && y+h<=424);
    assert(open>=panel_open);panel_open=open; /* Edits keep the same open panel. */
}
static void dashDrawSelection(float x,float y,float w,float h,float r,float a) {
    (void)r;(void)a;assert(x>=40 && x+w<=600 && y>=26 && y+h<=424);
}
static void dashTextCenter(float x,float y,const char *text,float size,DashColor color) {
    assert(x>=40 && x<=600 && y>=26 && y<=424);
    if(size==DASH_FS_LABEL && isdigit((unsigned char)text[0])) {
        assert(digits<6 && (color==100 || color==101));shown[digits]=atoi(text);
        assert(strlen(text)==(digits==0?4:2)); /* The full year shares one box. */
        if(color==101) { assert(selected==-1);selected=digits;selected_x=x; }
        digits++;
    }
    if(size==DASH_FS_BODY && !strcmp(text,"+")) { plus++;plus_x=x; }
    if(size==DASH_FS_BODY && !strcmp(text,"-")) { minus++;minus_x=x; }
}
static float dashTextS(float x,float y,const char *text,float size,DashColor color) {
    (void)y;(void)size;(void)color;return x+strlen(text)*7;
}
static void dashTextFit(float x,float y,float w,const char *text,float size,DashColor color) {
    (void)x;(void)y;(void)w;(void)text;(void)size;(void)color;
}
static float dashDrawButton(float x,float y,int icon,const char *key) {
    assert(x>=40 && x+22<=600 && y>=26 && y+22<=424);
    if(footer_y<0)footer_y=y;else assert(footer_y==y);
    if(icon==-1) { assert(key && (!strcmp(key,"L1") || !strcmp(key,"R1")));return 24; }
    assert(icon==DI_BTN_LEFT || icon==DI_BTN_RIGHT || icon==DI_BTN_UP || icon==DI_BTN_DOWN);return 22;
}
static void dashModalHintRow(float x,float y,int ok,const char *apply,int back,const char *cancel) {
    assert(footer_y==y && x+44+16+24+11*7<=600);assert(ok==1 && back==2 && !strcmp(apply,"Apply") && !strcmp(cancel,"Cancel"));
}
static int dashOkIcon(void) { return 1; }
static int dashBackIcon(void) { return 2; }
static void dashGfxPresent(void) {
    assert(digits==6 && plus==1 && minus==1 && selected>=0 && selected<6);
    assert(selected_x==plus_x && selected_x==minus_x);
    assert(shown[0]>=2000 && shown[0]<=2099);
    assert(shown[1]>=1 && shown[1]<=12 && shown[2]>=1);
    assert(shown[2]<=dashClockDaysInMonth(shown[0],shown[1]));
    assert(shown[3]<=23 && shown[4]<=59 && shown[5]<=59);
    presents++;assert(ticks==renders && renders==presents);
}
#define dashModalBackdrop(...) ((void)0)
#define dashGfxPushAlpha(...) ((void)0)
#define dashGfxPushOffset(...) ((void)0)
#define dashGfxPopOffset(...) ((void)0)
#define dashGfxPopAlpha(...) ((void)0)
#define dashIcon(...) ((void)0)
#define dashPanel(...) ((void)0)
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    assert(!strcmp(title,"Set PS2 Clock") && !subtitle && !initial);
#ifdef ETH
    assert(n==2 && !strcmp(items[1].label,"Sync from Internet"));
#else
    assert(n==1);
#endif
    assert(!strcmp(items[0].label,"Set manually..."));
    for(int i=0;i<n;i++)assert(items[i].icon==DI_CLOCK && !items[i].disabled);
    menus++;return choice;
}
static int menuTitleGetClockFields(int *y,int *m,int *d,int *h,int *mi,int *s,int *u,int *f) {
    field_reads++;*y=current[0];*m=current[1];*d=current[2];*h=current[3];*mi=current[4];*s=current[5];
    *u=1;*f=2;return rtc_valid; /* Editor still uses 24-hour values. */
}
static int dashClockSetManual(int y,int m,int d,int h,int mi,int s,char *result,int cap) {
    int got[]={y,m,d,h,mi,s};assert(!memcmp(got,expected,sizeof(got)));
    manual_writes++;snprintf(result,cap,"%s",manual_ok?"Clock verified":"RTC write failed");return manual_ok;
}
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail) {
    messages++;last_icon=icon;
    snprintf(last_title,sizeof(last_title),"%s",title);snprintf(last_body,sizeof(last_body),"%s",body);
    snprintf(last_detail,sizeof(last_detail),"%s",detail?detail:"");
}
#ifdef ETH
static int allow_wait=1, waits, loading, begins, ends, syncs, sync_ok=1, empty_error;
static int dashWorkerAwaitAll(const char *title) { assert(title);waits++;return allow_wait; }
static void dashLoadingBegin(const char *title) { assert(title && waits && !loading);loading=1;begins++; }
static void dashLoadingEnd(void) { assert(loading);loading=0;ends++; }
static int dashClockSyncInternet(char *result,int cap) {
    assert(loading && waits);syncs++;
    snprintf(result,cap,"%s",empty_error?"":sync_ok?"Clock verified":"Server timeout");return sync_ok;
}
'''
code += function(settings, "static void syncClockFromInternet(") + "#endif\n"
code += (function(settings, "static int editClockDateTime(")
         + function(settings, "static void setClockManually(")
         + function(settings, "static void setPs2Clock("))
code += r'''
static void reset(void) {
    const int initial[]={2026,11,8,8,30,15};
    memcpy(current,initial,sizeof(current));memcpy(expected,initial,sizeof(expected));
    choice=-1;rtc_valid=manual_ok=1;
    menus=field_reads=manual_writes=messages=0;
    flushes=ticks=renders=presents=input_count=input_index=0;
    memset(sounds,0,sizeof(sounds));panel_open=0;
    last_title[0]=last_body[0]=last_detail[0]=0;
#ifdef ETH
    allow_wait=sync_ok=1;waits=loading=begins=ends=syncs=empty_error=0;
#endif
}
static void acceptAndCheck(int fields[6]) {
    press(DASH_IN_OK);assert(editClockDateTime(fields));
    assert(!memcmp(fields,expected,sizeof(expected)) && input_index==input_count);
    assert(flushes==2 && sounds[0]==1 && !sounds[1] && renders==input_count-1);
}
int main(void) {
    /* Every whole field increments/decrements independently; no keyboard symbol is linked. */
    for(int field=0;field<6;field++)for(int direction=-1;direction<=1;direction+=2) {
        reset();selectField(field);press(direction==1?DASH_IN_UP:DASH_IN_DOWN);
        expected[field]+=direction;acceptAndCheck(current);
        assert(shown[field]==expected[field] && selected==field);
    }
    /* The IP editor's shoulder shortcuts change the selected field by ten. */
    const int buttons[]={DASH_IN_L1,DASH_IN_L2,DASH_IN_R1,DASH_IN_R2};
    const int less10[]={2016,1,28,22,20,5},more10[]={2036,9,18,18,40,25};
    for(int field=0;field<6;field++)for(int button=0;button<4;button++) {
        reset();selectField(field);press(buttons[button]);
        expected[field]=(button<2?less10:more10)[field];acceptAndCheck(current);
        assert(shown[field]==expected[field] && selected==field);
    }
    /* Bounds wrap without carrying into other fields. */
    const int lower[]={2000,1,1,0,0,0},upper[]={2099,12,31,23,59,59};
    for(int field=0;field<6;field++)for(int up=0;up<=1;up++) {
        reset();current[0]=2028;current[1]=1;current[2]=15;
        current[field]=up?upper[field]:lower[field];memcpy(expected,current,sizeof(expected));
        expected[field]=up?lower[field]:upper[field];selectField(field);
        press(up?DASH_IN_UP:DASH_IN_DOWN);acceptAndCheck(current);
    }
    /* Repeated shoulders change the field each time, even without a fresh press. */
    for(int direction=0;direction<2;direction++) {
        reset();int button=direction?DASH_IN_R1:DASH_IN_L1;
        press(button);repeatShoulder(button);repeatShoulder(button);
        expected[0]=direction?2056:2096;acceptAndCheck(current);
    }
    /* Selection wraps in both directions, including the full four-digit year. */
    reset();press(DASH_IN_LEFT);press(DASH_IN_UP);expected[5]++;acceptAndCheck(current);assert(selected==5);
    reset();selectField(6);press(DASH_IN_UP);expected[0]++;acceptAndCheck(current);assert(selected==0);
    /* Month/year changes clamp the day, including leap-day loss. */
    reset();current[0]=expected[0]=2028;current[1]=1;current[2]=31;
    expected[1]=2;expected[2]=29;selectField(1);press(DASH_IN_UP);acceptAndCheck(current);
    reset();current[0]=2028;current[1]=expected[1]=2;current[2]=29;
    expected[0]=2029;expected[2]=28;press(DASH_IN_UP);acceptAndCheck(current);
    reset();current[0]=2028;current[1]=expected[1]=2;current[2]=29;
    expected[0]=2038;expected[2]=28;press(DASH_IN_R1);acceptAndCheck(current);
    reset();current[1]=3;current[2]=31;expected[1]=2;expected[2]=28;
    selectField(1);press(DASH_IN_DOWN);acceptAndCheck(current);
    reset();current[1]=3;current[2]=31;expected[1]=4;expected[2]=30;
    selectField(1);press(DASH_IN_UP);acceptAndCheck(current);
    /* Day bounds follow the currently selected month after it is changed. */
    reset();current[0]=expected[0]=2028;current[1]=1;current[2]=31;
    expected[1]=2;expected[2]=1;selectField(1);press(DASH_IN_UP);press(DASH_IN_RIGHT);
    press(DASH_IN_UP);acceptAndCheck(current);
    /* Invalid RTC fields are made safe before the first render. */
    reset();memcpy(current,(int[]){1999,13,99,-1,60,60},sizeof(current));
    memcpy(expected,(int[]){2000,12,31,0,59,59},sizeof(expected));press(0);acceptAndCheck(current);
    /* Cancel leaves caller data intact after edits, including menu-button cancellation. */
    for(int cancel=0;cancel<2;cancel++) {
        reset();press(DASH_IN_UP);press(DASH_IN_RIGHT);press(DASH_IN_DOWN);
        press(cancel?DASH_IN_MENU:DASH_IN_BACK);assert(!editClockDateTime(current));
        assert(!memcmp(current,expected,sizeof(current)) && sounds[1]==1 && !sounds[0] && flushes==2);
    }
    /* Integration: chooser cancellation does no RTC work; editor cancellation never writes. */
    reset();setPs2Clock();assert(menus==1 && !field_reads && !manual_writes && !messages);
    reset();choice=0;press(DASH_IN_UP);press(DASH_IN_BACK);setPs2Clock();
    assert(field_reads==1 && !manual_writes && !messages && flushes==2);
    reset();choice=0;selectField(3);press(DASH_IN_UP);expected[3]++;press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_CHECK && !strcmp(last_title,"PS2 clock updated"));
    assert(!strcmp(last_detail,"2026-11-08 09:30:15"));
#ifdef ETH
    assert(!waits && !syncs); /* Manual entry never starts the network. */
#endif
    reset();choice=0;manual_ok=0;press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_WARNING && !strcmp(last_body,"RTC write failed"));
    reset();choice=0;rtc_valid=0;memcpy(expected,lower,sizeof(expected));press(0);press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && !strcmp(last_detail,"2000-01-01 00:00:00"));
#ifdef ETH
    reset();choice=1;allow_wait=0;setPs2Clock();assert(waits==1 && !begins && !syncs && !messages);
    reset();choice=1;setPs2Clock();
    assert(syncs==1 && begins==1 && ends==1 && !loading && !field_reads && !manual_writes);
    assert(messages==1 && last_icon==DI_CHECK && !strcmp(last_title,"PS2 clock synchronized"));
    reset();choice=1;sync_ok=0;setPs2Clock();
    assert(syncs==1 && ends==1 && !loading && last_icon==DI_WARNING && !strcmp(last_body,"Server timeout"));
    reset();choice=1;sync_ok=0;empty_error=1;setPs2Clock();
    assert(!strcmp(last_body,"No reliable Internet time was available."));
#endif
    puts("PASS: single-row clock controls, accelerating shoulder adjustments, whole-year field, valid-date wrapping, leap years, stable animation, safe cancellation and RTC/Internet dispatch");
}
'''

compiler = shutil.which("cc") or shutil.which("gcc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-settings-clock-") as tmp:
    src, binary = Path(tmp) / "clock.c", Path(tmp) / "clock"
    src.write_text(code)
    for flags in ([], ["-DETH"]):
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        *flags, str(src), "-lm", "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=5)
