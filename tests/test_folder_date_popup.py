"""Exercise the inline folder-date popup's layout, controls and reorder model."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_browser.c").read_text()
actions = (root / "src/filer_actions.c").read_text()
title = (root / "src/main_title.c").read_text()
header = (root / "include/filer_actions.h").read_text()
ui_header = (root / "include/dash_internal.h").read_text()


def function(text, signature):
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


editor = function(source, "static int tsEdit(")
placement = "tsDrawHints(x + 24, y + h - 36, w - 48);"
assert editor.index("dashGfxPushAlpha(oe);") < editor.index(placement) < editor.index("dashGfxPopAlpha();")
assert "dashDrawHints(" not in editor and "filerDateEditorField(" not in editor

code = r'''
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
typedef unsigned int u32;
typedef int DashColor;
#define stricmp strcasecmp
#define MAX_NAME 64
#define DASH_FS_SMALL 0.66f
#define DASH_FS_LABEL 0.86f
#define DASH_FS_CAPTION 0.60f
#define DASH_C_TEXT 0
#define DASH_C_ACCENT 1
#define DASH_C_TEXT2 2
#define DASH_C_TEXT3 3
#define DASH_C_OK 4
#define DASH_SND_CURSOR 1
#define DASH_SND_CONFIRM 2
#define DASH_SND_CANCEL 3
#define DASH_VW 640
#define DASH_VH 448
typedef struct { unsigned char Resv2,Sec,Min,Hour,Day,Month; unsigned short Year; } sceMcStDateTime;
typedef struct { char name[MAX_NAME]; struct { sceMcStDateTime _Modify; } stats; } FILEINFO;
typedef struct { int button; const char *key, *label; } DashHint;
typedef struct { u32 pressed, raw_new, text_repeat; int any; } DashInput;
static struct { char dir[32]; } fb={"mc0:/"};
static int mapping, use12, date_format, geometry, hint_geometry;
static float font_width=10, row_y, field_x, field_w;
static char formatted[40];
static int expected_position, expected_selected, expected_changed, names, dates, selections, panels;
static int buttons, labels, group_buttons;
static float group_x[5], group_right[5], last_button_right, hint_y;
static DashInput events[32];
static int next_event, event_count, adjustment, frames;
static int dashOkIcon(void) { return mapping ? DI_BTN_CROSS : DI_BTN_CIRCLE; }
static int dashBackIcon(void) { return mapping ? DI_BTN_CIRCLE : DI_BTN_CROSS; }
'''
# Put icon declarations before functions referring to them.
icons = (root / "include/dash_icons.h").read_text()
code = code.replace("static int dashOkIcon", icons + "\nstatic int dashOkIcon", 1)
start = header.index("typedef struct")
code += header[start:header.index("} FilerDateEditor;") + len("} FilerDateEditor;")] + "\n"
start = ui_header.rfind("enum {", 0, ui_header.index("DASH_IN_UP"))
code += ui_header[start:ui_header.index("};", start) + 2] + "\n"
start = actions.index("enum {\n\tCUSTOM_DATE_HOUR")
code += actions[start:actions.index("};", start) + 2] + "\n"
code += r'''
static void menuTitleGetClockFormat(int *use, int *format) {
    if(use) *use=use12;
    if(format) *format=date_format;
}
static int convertCustomTimestampToLocalTime(sceMcStDateTime *ts) { (void)ts; return 1; }
'''
for signature in ("void menuTitleFormatClockTime(", "void menuTitleFormatClockDate("):
    code += function(title, signature)
for signature in (
    "static int isCustomDateLeapYear(", "static int getCustomDateDaysInMonth(",
    "static void normalizeCustomFolderTimestamp(", "static void stepCustomFolderTimestamp(",
    "static int getCustomDateFieldForDisplayPosition(", "static int getCustomDateFieldOffset(",
    "static int compareCustomDateEditorFolders(", "static int customDateEditorTimestampEqual(",
    "static void sortCustomDateEditorFolders(",
    "static int updateCustomDateEditorFolders(", "static int moveCustomDateEditorNextToFolder(",
    "static int selectCustomDateEditorFolder(", "static void formatCustomDateEditorTimestamp(",
    "int filerDateEditorSync(", "int filerDateEditorChanged(", "int filerDateEditorSelect(", "int filerDateEditorMoveNextTo(",
    "int filerDateEditorFieldCount(", "void filerDateEditorFieldRange(", "void filerDateEditorFormat(",
):
    code += function(actions, signature)
for macro in ("TS_ROWS", "TS_ROW_H", "TS_LIST_H"):
    code += re.search(r"^#define " + macro + r" .+$", source, re.M).group() + "\n"
code += r'''
static float dashTextWidthN(const char *text, int n, float scale) {
    float width=0;
    /* Unequal digit/separator widths catch character-count positioning errors. */
    for(int i=0;i<n && text[i];i++) width+=(font_width+(text[i]%3))*scale;
    return width;
}
static float dashTextWidth(const char *text, float scale) { return dashTextWidthN(text,strlen(text),scale); }
static float dashButtonWidth(int icon, const char *key) { assert(!key); return icon==DI_BTN_SELECT?26:22; }
static float dashDrawButton(float x, float y, int icon, const char *key) {
    float w=dashButtonWidth(icon,key);
    if(hint_geometry) {
        const int expected[]={DI_BTN_L1,DI_BTN_R1,dashOkIcon(),dashBackIcon(),DI_BTN_SELECT,DI_BTN_START};
        assert(buttons<6 && icon==expected[buttons++]);
        assert(x>=54 && x+w<=586.001f);
        assert(y==374 && y+22<=410);
        if(!group_buttons) group_x[labels]=x;
        group_buttons++; last_button_right=x+w; hint_y=y;
    }
    return w;
}
static float dashTextS(float x,float y,const char *text,float scale,DashColor col) {
    (void)col;
    if(hint_geometry) {
        const char *expected[]={"Up/Down","Add","Subtract","Cancel","Save"};
        assert(labels<5 && !strcmp(text,expected[labels]));
        assert(group_buttons==(labels==0?2:1));
        assert(fabsf(x-last_button_right-4)<0.001f);
        assert(fabsf(y+16*scale-hint_y-11)<0.001f);
        group_right[labels]=x+dashTextWidth(text,scale);
        assert(group_right[labels]<=586.001f);
        if(labels) assert(group_x[labels]>=group_right[labels-1]);
        labels++; group_buttons=0;
    }
    return x+dashTextWidth(text,scale);
}
static void dashDrawSelection(float x,float y,float w,float h,float radius,float strength) {
    (void)radius; (void)strength;
    if(geometry) {
        assert(expected_selected && x==46 && w==548);
        assert(y==row_y+1 && h==20); selections++;
    }
}
static DashColor dashColorA(DashColor color,float alpha) { (void)alpha; return color; }
static void dashPanel(float x,float y,float w,float h,float radius,DashColor color) {
    (void)radius; (void)color;
    if(geometry) {
        assert(expected_selected && fabsf(x-(field_x-2))<0.001f);
        assert(fabsf(w-field_w-4)<0.001f && y==row_y+1 && h==20); panels++;
    }
}
static void dashPanelBorder(float x,float y,float w,float h,float r,DashColor c) { dashPanel(x,y,w,h,r,c); }
static void dashIcon(int icon,float x,float y,float size,DashColor color) {
    (void)color;
    if(geometry) {
        assert(icon==(expected_changed?DI_CLOCK:DI_FOLDER) && x==54 && size==14 && y+size/2==row_y+11);
        assert(color==(expected_changed?DASH_C_OK:expected_selected?DASH_C_TEXT:DASH_C_TEXT2));
    }
}
static void dashTextFit(float x,float y,float w,const char *text,float scale,DashColor color) {
    (void)color;
    if(geometry) {
        float date_x=582-dashTextWidth(formatted,scale);
        assert(color==(expected_selected?DASH_C_TEXT:DASH_C_TEXT2));
        assert(x==76 && fabsf(y+16*scale-row_y-11)<0.001f);
        assert(w>0 && fabsf(x+w+16-date_x)<0.001f && text[0]); names++;
    }
}
static void dashTextRight(float x,float y,const char *text,float scale,DashColor color) {
    (void)color;
    if(geometry) {
        assert(color==(expected_selected?DASH_C_TEXT:DASH_C_TEXT2));
        assert(x==582 && !strcmp(text,formatted));
        assert(fabsf(y+16*scale-row_y-11)<0.001f); dates++;
    }
}
static void dashInputFlush(void) {}
static void dashInputPoll(DashInput *in) { assert(next_event<event_count); *in=events[next_event++]; }
static void dashSoundPlay(int sound) { (void)sound; }
/* Field arithmetic has its own production/Gregorian comparison test. */
static void filerDateEditorAdjust(FilerDateEditor *e,int delta) { adjustment+=delta; e->timestamp->Sec+=delta; }
static int listCenteredTop(int selected,int count,int rows) {
    int top=selected-(rows-1)/2, max=count-rows;
    return max<=0 || top<0?0:top>max?max:top;
}
static float dashAnimSpeed(void) { return 1; }
static float dashVisualUpdate(void) { return 0.016f; }
static float dashApproach(float a,float b,float speed,float dt) { (void)a;(void)speed;(void)dt;return b; }
static float dashEaseOutCubic(float value) { return value; }
static void dashRenderScene(void) {}
static void dashModalBackdrop(float value) { (void)value; }
static void dashGfxPushAlpha(float value) { (void)value; }
static void dashGfxPopAlpha(void) {}
static void dashModalPanel(float x,float y,float w,float h,float a) { (void)x;(void)y;(void)w;(void)h;(void)a; }
static void dashGfxScissor(float x,float y,float w,float h) { (void)x;(void)y;(void)w;assert(h==TS_LIST_H); }
static void dashGfxScissorReset(void) {}
static void dashDrawScrollbar(float x,float y,float h,int top,int rows,int count) { (void)x;(void)y;(void)h;(void)top;(void)rows;(void)count; }
static void dashGfxPresent(void) { frames++; }
'''
for signature in ("static float tsRowY(", "static void tsDrawHints(", "static void tsDrawFolderRow(", "static int tsEdit("):
    code += function(source, signature)
code += r'''
static void queue(u32 pressed,u32 repeat) { events[event_count++]=(DashInput){pressed,0,repeat,1}; }
static int run(FilerDateEditor *e,u32 key,u32 repeat,u32 exit_key) {
    next_event=event_count=frames=0;
    queue(key,repeat); queue(exit_key,0);
    int result=tsEdit(e);
    assert(next_event==2 && frames==1);
    return result;
}
int main(void) {
    FILEINFO folders[40]={0}; sceMcStDateTime original[40],timestamp;
    FilerDateEditor e={folders,original,40,&timestamp,0,"Folder 20",0};
    for(int i=0;i<40;i++) {
        snprintf(folders[i].name,sizeof(folders[i].name),"Folder %02d",i);
        folders[i].stats._Modify=(sceMcStDateTime){0,20,7,13,1,3,2024};
        folders[i].stats._Modify.Min=59-i;
        original[i]=folders[i].stats._Modify;
    }
    timestamp=folders[20].stats._Modify;
    /* Check both key mappings and font metrics larger than bundled fonts. */
    hint_geometry=1;
    for(mapping=0;mapping<2;mapping++) for(int width=8;width<=16;width+=4)
        for(int percent=90;percent<=115;percent+=5) {
            font_width=width*percent/100.0f;
            buttons=labels=group_buttons=0;
            tsDrawHints(54,374,532);
            assert(buttons==6 && labels==5 && !group_buttons);
            assert(group_x[0]==54 && fabsf(group_right[4]-586)<0.001f);
            float gap=group_x[1]-group_right[0];
            for(int i=2;i<5;i++) assert(fabsf(group_x[i]-group_right[i-1]-gap)<0.001f);
        }
    hint_geometry=0; geometry=1;
    for(int count=1;count<=40;count++) for(int selected=0;selected<count;selected++) {
        int top=listCenteredTop(selected,count,TS_ROWS), end=top+TS_ROWS;
        if(end>count) end=count;
        float first=tsRowY(108,top,top,selected), last=tsRowY(108,end-1,top,selected);
        assert(first>=108 && last+TS_ROW_H<=108+TS_LIST_H);
        float selected_y=tsRowY(108,selected,top,selected);
        float before=selected==top?108:tsRowY(108,selected-1,top,selected)+TS_ROW_H;
        float after=selected==end-1?108+TS_LIST_H:tsRowY(108,selected+1,top,selected);
        assert(selected_y-before==TS_ROW_H/2 && after-selected_y-TS_ROW_H>=TS_ROW_H/2);
        for(int i=top;i<end;i++) {
            row_y=tsRowY(108,i,top,selected); expected_selected=i==selected;
            if(i>top) assert(row_y>=tsRowY(108,i-1,top,selected)+TS_ROW_H);
            for(use12=0;use12<2;use12++) for(date_format=0;date_format<3;date_format++)
                for(expected_position=0;expected_position<6;expected_position++) {
                    e.position=expected_position;
                    filerDateEditorFormat(&folders[i].stats._Modify,formatted,sizeof(formatted));
                    const int starts[2][3][6]={
                        {{0,3,6,9,14,17},{0,3,6,9,12,15},{0,3,6,9,12,15}},
                        {{0,3,6,12,17,20},{0,3,6,12,15,18},{0,3,6,12,15,18}}};
                    int offset,length,expected_length=(expected_position==(date_format?5:3))?4:2;
                    filerDateEditorFieldRange(e.position,&offset,&length);
                    assert(offset==starts[use12][date_format][e.position] && length==expected_length);
                    field_x=582-dashTextWidth(formatted,DASH_FS_SMALL)+dashTextWidthN(formatted,offset,DASH_FS_SMALL);
                    field_w=dashTextWidthN(formatted+offset,length,DASH_FS_SMALL);
                    selections=panels=names=dates=0;
                    tsDrawFolderRow(&e,i,expected_selected,30,row_y,580);
                    assert(selections==expected_selected && panels==2*expected_selected && names==1 && dates==1);
                }
        }
    }
    /* Unsaved edits change only the icon. Reverting any date/time component
     * restores the folder, even when reserved timestamp metadata differs. */
    for(expected_selected=0;expected_selected<2;expected_selected++) {
        row_y=119; e.position=0;
        for(int field=0;field<6;field++) for(int state=0;state<4;state++) {
            sceMcStDateTime *value=&folders[20].stats._Modify;
            *value=original[20]; expected_changed=state==1;
            if(state==1) switch(field) {
                case 0: value->Year++; break;
                case 1: value->Month++; break;
                case 2: value->Day++; break;
                case 3: value->Hour++; break;
                case 4: value->Min++; break;
                case 5: value->Sec++; break;
            }
            if(state==3) value->Resv2^=0xA5;
            assert(filerDateEditorChanged(&e,20)==expected_changed);
            filerDateEditorFormat(value,formatted,sizeof(formatted));
            field_x=582-dashTextWidth(formatted,DASH_FS_SMALL);
            field_w=dashTextWidthN(formatted,2,DASH_FS_SMALL);
            tsDrawFolderRow(&e,20,expected_selected,30,row_y,580);
        }
    }
    folders[20].stats._Modify=original[20];
    geometry=0;
    /* Run the whole production popup loop against the real select/reorder model. */
    assert(run(&e,DASH_IN_UP,0,DASH_IN_START)==1 && !strcmp(e.selected,"Folder 19"));
    assert(run(&e,DASH_IN_DOWN,0,DASH_IN_START)==1 && !strcmp(e.selected,"Folder 20"));
    e.position=0;
    run(&e,DASH_IN_LEFT,0,DASH_IN_START); assert(e.position==5);
    run(&e,DASH_IN_RIGHT,0,DASH_IN_START); assert(e.position==0);
    run(&e,DASH_IN_OK,DASH_IN_OK,DASH_IN_START); assert(adjustment==1);
    run(&e,DASH_IN_BACK,0,DASH_IN_START); assert(adjustment==0);
    run(&e,0,DASH_IN_OK,DASH_IN_START); assert(adjustment==1);
    run(&e,0,DASH_IN_BACK,DASH_IN_START); assert(adjustment==0);
    sceMcStDateTime neighbor=e.folders[19].stats._Modify;
    run(&e,DASH_IN_L1,0,DASH_IN_START);
    assert(filerDateEditorSync(&e)==19 && !strcmp(e.selected,"Folder 20"));
    stepCustomFolderTimestamp(&neighbor,1,0); assert(!memcmp(&timestamp,&neighbor,sizeof(timestamp)));
    neighbor=e.folders[20].stats._Modify;
    run(&e,DASH_IN_R1,0,DASH_IN_START);
    assert(filerDateEditorSync(&e)==20 && !strcmp(e.selected,"Folder 20"));
    stepCustomFolderTimestamp(&neighbor,-1,0); assert(!memcmp(&timestamp,&neighbor,sizeof(timestamp)));
    sceMcStDateTime unchanged=timestamp;
    run(&e,DASH_IN_L2|DASH_IN_R2,0,DASH_IN_START); assert(!memcmp(&timestamp,&unchanged,sizeof(timestamp)));
    assert(run(&e,0,0,DASH_IN_SELECT)==0);
    /* Exit buttons take precedence over edits, and boundary moves do nothing. */
    next_event=event_count=0; queue(DASH_IN_START|DASH_IN_OK,0);
    assert(tsEdit(&e)==1 && adjustment==0);
    next_event=event_count=0; queue(DASH_IN_SELECT|DASH_IN_BACK,0);
    assert(tsEdit(&e)==0 && adjustment==0);
    strcpy(e.selected,e.folders[0].name); timestamp=e.folders[0].stats._Modify;
    run(&e,DASH_IN_L1|DASH_IN_UP,0,DASH_IN_START); assert(filerDateEditorSync(&e)==0);
    strcpy(e.selected,e.folders[39].name); timestamp=e.folders[39].stats._Modify;
    run(&e,DASH_IN_R1|DASH_IN_DOWN,0,DASH_IN_START); assert(filerDateEditorSync(&e)==39);
    puts("PASS: inline date fields in all clock/date formats; centered row content and half-row gaps at every list position; ordered hints in one aligned row, both confirm mappings; navigation, add/subtract repeat, one-second reorder, START save and SELECT cancel; changed clock icons and original folder icons on revert, with stable text colors");
}
'''
compiler = shutil.which("gcc") or shutil.which("cc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="folder-date-popup-") as folder:
    c = Path(folder) / "check.c"
    executable = Path(folder) / "check"
    c.write_text(code)
    subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                    str(c), "-o", str(executable), "-lm"], check=True)
    subprocess.run([str(executable)], check=True)
