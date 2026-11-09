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
ui = (root / "src/dash_ui.c").read_text()
title = (root / "src/main_title.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


clock_header = (root / "include/main_title.h").read_text()
code = clock_header[clock_header.index("typedef struct MenuClockSettings"):clock_header.index("} MenuClockSettings;")+len("} MenuClockSettings;")]
code += r'''
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
code += function(title, "void menuTitleFormatClockDate(") + function(title, "void menuTitleFormatClockTime(")
code += r'''
static int inputs[512], input_count, input_index, shoulder_input;
static float footer_y, footer_left, footer_right, font_width=7, shoulder_width=24;
static int flushes, ticks, renders, presents, digits, plus, minus, selected, sounds[3];
static float selected_x, plus_x, minus_x;
static int shown[6], choice=-1, rtc_valid=1, manual_ok=1;
static MenuClockSettings preferences,expected_preferences;
static int box_values,meridiem,shown_12h,dynamic_limits,limits_calls;
static char shown_zone[20],shown_dst[20];
static int current[6], expected[6], minimum[6], maximum[6], menus, field_reads, manual_writes, messages, last_icon;
static int allow_wait=1,waits;
static int dashWorkerAwaitAll(const char *title) { assert(title);waits++;return allow_wait; }
static void filerRootMcPollIdle(void) {}
static int menuTitleLoadSavedClockSettings(void) { return 1; }
static void menuTitleGetClockSettings(MenuClockSettings *out) {*out=preferences;}
static void dashClockManualLimitsForSettings(int lo[6],int hi[6],const MenuClockSettings *settings) {
 assert(settings->timezone_minutes>=-720 && settings->timezone_minutes<=840);limits_calls++;
 if(dynamic_limits) {
     /* Script independently supplied endpoint changes, to check the UI reclamps immediately. */
     assert(settings->timezone_minutes==-480 || settings->timezone_minutes==-465);
     int lo_case[]={1999,12,31,7+settings->daylight_saving,settings->timezone_minutes==-465?15:0,0};
     int hi_case[]={2099,12,31,(settings->timezone_minutes==-465?7:6)+settings->daylight_saving,
                    settings->timezone_minutes==-465?14:59,59};
     memcpy(minimum,lo_case,sizeof(minimum));memcpy(maximum,hi_case,sizeof(maximum));
 }
 memcpy(lo,minimum,sizeof(minimum));memcpy(hi,maximum,sizeof(maximum));
}
static float panel_open;
static char last_title[80], last_body[200], last_detail[32];
static void press(int input) { assert(input_count<NITEMS(inputs));inputs[input_count++]=input; }
static void selectField(int field) { for(int i=0;i<field;i++)press(DASH_IN_RIGHT); }
static void selectControl(int control) {selectField(control-(control>=7&&!preferences.use_12h?1:0));}
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
static void dashRenderScene(void) {
 renders++;digits=plus=minus=box_values=meridiem=shown_12h=0;selected=-1;footer_y=-1;
}
static void dashModalPanel(float x,float y,float w,float h,float open) {
    assert(x>=40 && x+w<=600 && y>=26 && y+h<=424);
    assert(open>=panel_open);panel_open=open; /* Edits keep the same open panel. */
}
static void dashDrawSelection(float x,float y,float w,float h,float r,float a) {
    (void)r;(void)a;assert(x>=40 && x+w<=600 && y>=26 && y+h<=424);
}
static void dashTextCenter(float x,float y,const char *text,float size,DashColor color) {
    assert(x>=40 && x<=600 && y>=26 && y<=424);
    if(size==DASH_FS_LABEL && (color==100 || color==101)) {
        int logical=box_values;
        if(box_values<6) {
            assert(isdigit((unsigned char)text[0]));shown[digits]=atoi(text);
            assert(strlen(text)==(digits==0?4:2));digits++;
        } else if(!strcmp(text,"AM") || !strcmp(text,"PM")) {
            meridiem=!strcmp(text,"PM")?2:1;
        } else {
            logical+=!meridiem;
            if(logical==7)snprintf(shown_zone,sizeof(shown_zone),"%s",text);
            if(logical==8)snprintf(shown_dst,sizeof(shown_dst),"%s",text);
            if(logical==9)shown_12h=!strcmp(text,"12-hour");
        }
        if(color==101) {assert(selected==-1);selected=logical;selected_x=x;}
        box_values++;
    }
    if(size==DASH_FS_BODY && !strcmp(text,"+")) { plus++;plus_x=x; }
    if(size==DASH_FS_BODY && !strcmp(text,"-")) { minus++;minus_x=x; }
}
static float dashTextWidth(const char *text,float size) { (void)size;return strlen(text)*font_width; }
static float dashTextS(float x,float y,const char *text,float size,DashColor color) {
    (void)color;float right=x+dashTextWidth(text,size);
    if(y==footer_y+4.5f)footer_right=right;
    return right;
}
static void dashTextFit(float x,float y,float w,const char *text,float size,DashColor color) {
    (void)x;(void)y;(void)w;(void)text;(void)size;(void)color;
}
static float dashButtonWidth(int icon,const char *key) { (void)key;return icon==-1?shoulder_width:22; }
static float dashDrawButton(float x,float y,int icon,const char *key) {
    assert(x>=40 && x+22<=600 && y>=26 && y+22<=424);
    if(footer_y<0){footer_y=y;footer_left=x;}else assert(footer_y==y);
    if(icon==-1) { assert(key && (!strcmp(key,"L1") || !strcmp(key,"R1")));return shoulder_width; }
    assert(icon==DI_BTN_LEFT || icon==DI_BTN_RIGHT || icon==DI_BTN_UP || icon==DI_BTN_DOWN || icon==1 || icon==2);return 22;
}
'''
code += "#define drawButton dashDrawButton\n" + function(ui, "static void modalHintRow(")
code += r'''
static void dashModalHintRow(float x,float y,int ok,const char *apply,int back,const char *cancel) {
    assert(footer_y==y);assert(ok==1 && back==2 && !strcmp(apply,"Apply") && !strcmp(cancel,"Cancel"));
    modalHintRow(x,y,ok,apply,back,cancel);
}
static int dashOkIcon(void) { return 1; }
static int dashBackIcon(void) { return 2; }
static void dashGfxPresent(void) {
    assert(digits==6 && plus==1 && minus==1 && selected>=0 && selected<10);
    assert(box_values==(shown_12h?10:9) && (!!meridiem)==shown_12h);
    assert(!shown_12h || (shown[3]>=1 && shown[3]<=12));
    assert(selected_x==plus_x && selected_x==minus_x);
    assert(shown[0]>=minimum[0] && shown[0]<=maximum[0]);
    assert(shown[1]>=1 && shown[1]<=12 && shown[2]>=1);
    assert(shown[2]<=dashClockDaysInMonth(shown[0],shown[1]));
    assert(shown[3]<=23 && shown[4]<=59 && shown[5]<=59);
    assert(footer_left>=56 && footer_right<=584);
    assert(fabsf((footer_left+footer_right)*0.5f-DASH_VW*0.5f)<0.5f);
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
    *u=preferences.use_12h;*f=preferences.date_format;return rtc_valid;
}
static int dashClockSetManualWithSettings(const int got[6],const MenuClockSettings *settings,char *result,int cap) {
    assert(!memcmp(got,expected,sizeof(expected)));
    assert(!memcmp(settings,&expected_preferences,sizeof(*settings)));
    manual_writes++;snprintf(result,cap,"%s",manual_ok?"Clock verified":"RTC write failed");return manual_ok;
}
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail) {
    messages++;last_icon=icon;
    snprintf(last_title,sizeof(last_title),"%s",title);snprintf(last_body,sizeof(last_body),"%s",body);
    snprintf(last_detail,sizeof(last_detail),"%s",detail?detail:"");
}
#ifdef ETH
static int loading, begins, ends, syncs, sync_ok=1, empty_error;
static void dashLoadingBegin(const char *title) { assert(title && waits && !loading);loading=1;begins++; }
static void dashLoadingEnd(void) { assert(loading);loading=0;ends++; }
static int dashClockSyncInternet(char *result,int cap) {
    assert(loading && waits);syncs++;
    snprintf(result,cap,"%s",empty_error?"":sync_ok?"Clock verified":"Server timeout");return sync_ok;
}
'''
code += function(settings, "static void syncClockFromInternet(") + "#endif\n"
code += (function(settings, "static void clockFieldLimits(")
         + function(settings, "static int editClockDateTime(")
         + function(settings, "static void setClockManually(")
         + function(settings, "static void setPs2Clock("))
code += r'''
static void reset(void) {
    const int initial[]={2026,11,8,8,30,15},lo[]={2000,1,1,0,0,0},hi[]={2099,12,31,23,59,59};
    memcpy(minimum,lo,sizeof(lo));memcpy(maximum,hi,sizeof(hi));allow_wait=1;waits=0;
    memcpy(current,initial,sizeof(current));memcpy(expected,initial,sizeof(expected));
    preferences=expected_preferences=(MenuClockSettings){-480,0,0,2};dynamic_limits=limits_calls=0;
    choice=-1;rtc_valid=manual_ok=1;font_width=7;shoulder_width=24;
    menus=field_reads=manual_writes=messages=0;
    flushes=ticks=renders=presents=input_count=input_index=0;
    memset(sounds,0,sizeof(sounds));panel_open=0;
    last_title[0]=last_body[0]=last_detail[0]=0;
#ifdef ETH
    allow_wait=sync_ok=1;waits=loading=begins=ends=syncs=empty_error=0;
#endif
}
static void acceptAndCheck(int fields[6]) {
    press(DASH_IN_OK);assert(editClockDateTime(fields,&preferences));
    assert(!memcmp(&preferences,&expected_preferences,sizeof(preferences)));
    assert(!memcmp(fields,expected,sizeof(expected)) && input_index==input_count);
    assert(flushes==2 && sounds[0]==1 && !sounds[1] && renders==input_count-1);
}
int main(void) {
    /* The complete rendered row stays centered with different font/badge widths. */
    for(int wide=0;wide<2;wide++) {
        reset();font_width=wide?8.5f:5.0f;shoulder_width=wide?30.0f:22.0f;
        press(0);acceptAndCheck(current);
    }
    /* Local endpoints may lie in 1999 or 2100, with a partial boundary day. */
    const int west_min[]={1999,12,31,7,0,0},west_max[]={2099,12,31,6,59,59};
    reset();memcpy(minimum,west_min,sizeof(minimum));memcpy(maximum,west_max,sizeof(maximum));
    memset(current,0,sizeof(current));memcpy(expected,west_min,sizeof(expected));press(0);acceptAndCheck(current);
    reset();memcpy(minimum,west_min,sizeof(minimum));memcpy(maximum,west_max,sizeof(maximum));
    memcpy(current,west_min,sizeof(current));memcpy(expected,west_min,sizeof(expected));
    selectField(2);press(DASH_IN_L1);acceptAndCheck(current); /* One possible day, even with a -10 step. */
    const int east_min[]={2000,1,1,5,0,0},east_max[]={2100,1,1,4,59,59};
    reset();memcpy(minimum,east_min,sizeof(minimum));memcpy(maximum,east_max,sizeof(maximum));
    memcpy(current,east_max,sizeof(current));memcpy(expected,east_max,sizeof(expected));
    selectField(3);press(DASH_IN_R1);acceptAndCheck(current); /* Hour range 0..4 wraps safely. */
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
    reset();press(DASH_IN_LEFT);press(DASH_IN_LEFT);press(DASH_IN_LEFT);press(DASH_IN_LEFT);
    press(DASH_IN_UP);expected[5]++;acceptAndCheck(current);assert(selected==5);
    reset();selectField(9);press(DASH_IN_UP);expected[0]++;acceptAndCheck(current);assert(selected==0);
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
        press(cancel?DASH_IN_MENU:DASH_IN_BACK);assert(!editClockDateTime(current,&preferences));
        assert(!memcmp(current,expected,sizeof(current)) && sounds[1]==1 && !sounds[0] && flushes==2);
    }
    /* Saved 12-hour format renders midnight/noon correctly and keeps canonical 24-hour values. */
    for(int hour=0;hour<24;hour+=12) {
        reset();preferences.use_12h=expected_preferences.use_12h=1;
        current[3]=expected[3]=hour;press(0);acceptAndCheck(current);
        assert(shown[3]==12 && meridiem==(hour?2:1));
    }
    reset();preferences.use_12h=expected_preferences.use_12h=1;
    selectControl(6);press(DASH_IN_UP);expected[3]=20;acceptAndCheck(current);
    assert(selected==6 && meridiem==2);
    reset();preferences.use_12h=expected_preferences.use_12h=1;
    current[3]=expected[3]=12;selectControl(3);press(DASH_IN_UP);expected[3]=13;acceptAndCheck(current);
    assert(shown[3]==1 && meridiem==2);
    reset();preferences.use_12h=expected_preferences.use_12h=1;
    current[3]=expected[3]=0;selectControl(3);press(DASH_IN_DOWN);expected[3]=11;acceptAndCheck(current);
    assert(shown[3]==11 && meridiem==1);
    /* Preferences can be staged and cancelled, including toggles from repeated shoulders. */
    for(int control=7;control<=9;control++) {
        reset();selectControl(control);press(DASH_IN_UP);
        if(control==7)expected_preferences.timezone_minutes=-465;
        if(control==8)expected_preferences.daylight_saving=1;
        if(control==9)expected_preferences.use_12h=1;
        acceptAndCheck(current);assert(selected==control);
        if(control==7)assert(!strcmp(shown_zone,"-07:45"));
        if(control==8)assert(!strcmp(shown_dst,"On (+1h)"));
        reset();selectControl(control);repeatShoulder(DASH_IN_R1);press(DASH_IN_BACK);
        assert(!editClockDateTime(current,&preferences));
        assert(!memcmp(&preferences,&expected_preferences,sizeof(preferences)) && !manual_writes);
    }
    /* The boundary date is reclamped in the same frame as a preference change. */
    for(int control=7;control<=8;control++) {
        reset();dynamic_limits=1;memcpy(current,west_min,sizeof(current));memcpy(expected,west_min,sizeof(expected));
        selectControl(control);press(DASH_IN_UP);
        if(control==7){expected_preferences.timezone_minutes=-465;expected[4]=15;}
        else {expected_preferences.daylight_saving=1;expected[3]=8;}
        acceptAndCheck(current);assert(limits_calls==2);
    }
    /* Time-zone endpoints wrap; quarter-hour regions and 24-hour mode are selectable. */
    reset();preferences.timezone_minutes=840;expected_preferences.timezone_minutes=-720;
    selectControl(7);press(DASH_IN_UP);acceptAndCheck(current);
    reset();preferences.timezone_minutes=-720;expected_preferences.timezone_minutes=840;
    selectControl(7);press(DASH_IN_DOWN);acceptAndCheck(current);
    reset();preferences.use_12h=1;expected_preferences.use_12h=0;
    current[3]=expected[3]=23;selectControl(9);press(DASH_IN_UP);acceptAndCheck(current);
    assert(shown[3]==23 && !meridiem);
    /* Integration: chooser cancellation does no RTC work; editor cancellation never writes. */
    reset();setPs2Clock();assert(menus==1 && !field_reads && !manual_writes && !messages);
    reset();choice=0;allow_wait=0;setPs2Clock();assert(!field_reads && !manual_writes && !flushes);
    reset();choice=0;press(DASH_IN_UP);press(DASH_IN_BACK);setPs2Clock();
    assert(field_reads==1 && !manual_writes && !messages && flushes==2);
    reset();choice=0;selectField(3);press(DASH_IN_UP);expected[3]++;press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_CHECK && !strcmp(last_title,"PS2 clock updated"));
    assert(!strcmp(last_detail,"08/11/2026 09:30:15"));
#ifdef ETH
    assert(waits==2 && !syncs); /* Storage settles; manual entry never starts the network. */
#endif
    reset();choice=0;preferences.use_12h=expected_preferences.use_12h=1;
    current[3]=expected[3]=0;selectControl(6);press(DASH_IN_UP);expected[3]=12;
    press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && !strcmp(last_detail,"08/11/2026 12:30:15 PM"));
    reset();choice=0;manual_ok=0;press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_WARNING && !strcmp(last_body,"RTC write failed"));
    reset();choice=0;rtc_valid=0;memcpy(expected,lower,sizeof(expected));press(0);press(DASH_IN_OK);setPs2Clock();
    assert(manual_writes==1 && messages==1 && !strcmp(last_detail,"01/01/2000 00:00:00"));
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
    puts("PASS: centered single-row clock controls, 12/24-hour and AM/PM editing, staged time-zone/DST preferences, accelerating shoulders, whole-year field, valid-date wrapping, leap years, stable animation, safe cancellation and RTC/Internet dispatch");
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
