"""Exercise production Settings pages/input with host mocks; no PS2/GS proof.

Checks reachability, unique controls, restored selection/scroll, global Changes
access, dependent settings, and page IDs that overlap setting IDs.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
settings = (root / "src/dash_settings.c").read_text()
header = (root / "include/dash_internal.h").read_text()
classic = (root / "include/launchelf.h").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


declarations = settings[settings.index("enum SetType"):settings.index("/* Unsaved-changes session:")]
icons = sorted(set(re.findall(r"\bDI_\w+", settings)))
code = "#include <assert.h>\n#include <stdio.h>\n#include <string.h>\n"
code += "#define ETH 1\n#define WLE_NATIVE_HTTPS 1\n#define UDPFS 1\n#define MAX_PATH 1024\n#define DASH_FONT_SYSTEM 1\n"
code += "enum { " + ", ".join(icons) + " };\n"
code += classic[classic.index("enum SETTING_LK {"):classic.index("};", classic.index("enum SETTING_LK {")) + 2]
code += classic[classic.index("enum TV_mode {"):classic.index("};", classic.index("enum TV_mode {")) + 2]
code += re.search(r"static const char \*const tv_names\[\] = [^;]+;", settings).group() + "\n"
code += declarations
input_start = header.rfind("enum {", 0, header.index("DASH_IN_UP"))
code += header[input_start:header.index("void dashInputPoll(")]
code = "#include <stdint.h>\ntypedef uint32_t u32;\n" + code
code += r"""
enum { DASH_TOAST_INFO, DASH_TOAST_OK, DASH_SEC_HOME };
enum { DASH_SND_CANCEL };
static void dashSoundPlay(int s) { assert(s == DASH_SND_CANCEL); }
static void dashUiFocusPoke(void) {}
static struct { int sound, bgm, artwork; } dashCfg;
static struct { int font, wallpaper, clock; } dashTheme;
static struct { int usbkbd_used,screen_x,screen_y,Init_Delay,timeout,TV_mode; char LK_Path[SETTING_LK_COUNT][MAX_PATH]; } config;
static struct { int StartX,StartY; } gs_state={32,32}, *gsGlobal=&gs_state;
static __typeof__(config) *setting = &config;
static int session, begins, home, saves, reverts, changes, resets, edits, toast;
static int dash_dirty, classic_dirty, net_dirty, session_saves, cfg_failed[2];
static int leave_prompts, commits, discards;
enum { SESSION_SAVE_CNF=1, SESSION_SAVE_NET=2, SESSION_SAVE_DASH=4,
       CFG_SAVE_CNF=0, CFG_SAVE_NET=1 };
static int dashStoreSettingsFailed(void) { return 0; }
static int modal_result = -1, dirty = 1, failed,can576=1,video_menus;
static int is576pSupported(void) { return can576; }
static int auto_mode=TV_mode_NTSC;
static int uLE_InitializeRegion(void) { return auto_mode; }
typedef struct { int icon; const char *label, *detail; int disabled; } DashMenuItem;
static void sessionBegin(void) { if (!session) { session = 1; begins++; } }
static int anyDirty(void) { return dirty; }
static void settingsCommit(void) { commits++; dirty=0; }
static void settingsRevert(void) { discards++; dirty=0; }
static int failedSaves(void) { return failed; }
static int dashModalMenu(const char *t,const char *d,DashMenuItem *m,int n,int s) {
    (void)d; (void)s;
    if(n==TV_mode_COUNT) {
        assert(!strcmp(t,"Video mode"));video_menus++;
        const char *expected[]={NULL,"720x480i 60Hz","720x576i 50Hz",
                                "640x480p 60Hz","720x480p 60Hz",
                                "720x576p 50Hz"};
        expected[TV_mode_AUTO]=auto_mode==TV_mode_PAL ? "720x576i 50Hz" : "720x480i 60Hz";
        if(!can576)expected[TV_mode_576P]="720x576p 50Hz (unsupported)";
        for(int i=0;i<n;i++) {
            assert(m[i].disabled==(i==TV_mode_576P && !can576));
            assert(m[i].icon==(i==s ? DI_CHECK : -1));
            assert(!strcmp(m[i].label,tv_names[i]));
            assert(m[i].detail && !strcmp(m[i].detail,expected[i]));
        }
        return modal_result;
    }
    assert(n == 3);
    if (!strcmp(t,"Save your changes?")) { leave_prompts++; return modal_result; }
    changes++;
    assert(m[0].disabled == !(dirty || failed) && m[1].disabled == !dirty);
    return modal_result;
}
static void runAction(int id) { if(id==S_SAVE_CLASSIC) saves++; else if(id==S_REVERT) reverts++; }
static void dashSwitchSection(int s) { assert(s == DASH_SEC_HOME); home++; }
static void dashToast(int kind,const char *msg) { (void)kind; assert(msg); toast++; }
static void colorEditor(const char *name,int id) { (void)name; (void)id; edits++; }
static void choosePreset(void) { edits++; }
static void editPathMenu(const SetItem *it) { (void)it; edits++; }
static void editIp(const SetItem *it) { (void)it; edits++; }
static void editLaunchMenu(const SetItem *it) { (void)it; edits++; }
static void editLaunchKey(const SetItem *it,int what) { (void)it; (void)what; edits++; }
static void setNumber(int id,int v) { (void)id; (void)v; edits++; }
static int choiceInfo(int id,int *v,const char *const **names,const char **single) {
    static const char *const options[]={"Off","On"};
    *single=NULL;
    if(id==S_TVMODE) { *v=setting->TV_mode;*names=tv_names;return TV_mode_COUNT; }
    *v=0; *names=options; return 2;
}
static int dashModalChoice(const char *l,const char *const *o,int n,int c) {
    (void)l; (void)o; (void)n; return c;
}
static void setChoice(int id,int v) { if(id==S_TVMODE)setting->TV_mode=v;edits++; }
static int resetThemeSetting(int id) { (void)id; resets++; return 1; }
"""
for signature in (
    "static int numberInfo(",
    "static const char *videoModeDetail(",
    "static int chooseVideoMode(",
    "static int themeSettingResettable(",
    "static const SetItem *curItem(",
    "static int settingsLeave(",
    "static void settingsEnter(",
    "static int itemDisabled(",
    "static const char *disabledHelp(",
    "static void settingsMenu(",
    "static void settingsInput(",
):
    code += function(settings, signature)

# Baseline visible controls, excluding page links, scoped resets and the
# separate panel-opacity alias (Panels already edits that same alpha).
expected = """
S_TVMODE S_SCREEN_X S_SCREEN_Y S_EFFECTS S_ANIM S_SCREEN_RESET
S_DISPLAY_THEME_RESET S_SOUND S_SVOL S_BGM S_BGMVOL S_START S_VIEW
S_ARTWORK S_RECENT S_AUTOSCAN S_SCANPATHS S_RESCAN S_CLEAR_RECENT S_INTRO
S_CONFIRM S_VKEY S_USBKBD S_USBKBD_FILE S_KBDMAP_FILE S_PATHPAD_LOCK
S_INIT_DELAY S_TIMEOUT S_CNF_PATH S_LANG_FILE S_FONT_FILE S_ESR_PATH
S_OSDSYS_PATH S_POPS_PATH S_EMBER_PATH S_NEUTRINO_PATH S_HIDE_HDD S_HIDE_MC S_REBOOT_ELF
S_ABOUT_PROJECT S_NET_IP
S_NET_NM S_NET_GW S_HOSTWRITE S_LANGUAGE S_GAMEID S_GAMEID_DISC
S_PSU_HUGE S_PSU_DATE S_PSU_NOOVER S_SAVE_AS S_T_PRESET S_T_LOAD S_T_SAVE
S_T_DEFAULT S_T_BG S_T_BG1 S_T_BG2 S_T_BRIGHT S_T_SCAN S_T_IMAGE
S_T_TEXT S_T_TEXT2 S_T_TEXT3 S_T_SELTEXT S_T_ACCENT S_T_SELECT S_T_PANEL
S_T_BORDER S_T_WARN S_T_HL S_T_CORNER S_T_TILE S_T_GLOW S_T_FONT
S_T_FSCALE S_T_BOLD S_T_SHADOW S_T_ICONTINT S_T_APPICON S_T_APPICON_IMG
S_T_CLOCK S_T_CLOCKPOS S_T_HOURS S_T_SECONDS S_T_DATE S_T_WALL S_T_WALLDIM
S_T_RENAME S_T_RESTORE_PRESET S_CLOCK_MANUAL S_TEMP_UNITS S_CLOCK_SYNC
""".split()
code += "static const int expected[] = {" + ",".join(expected) + "};\n"
code += r"""
static int seen[P_COUNT], occurrences[S_T_RESETCAT+1];
static void visit(int p,int depth) {
    assert(p>=0 && p<P_COUNT && depth<=PAGE_DEPTH && !seen[p]);
    seen[p]=1; assert(pages[p].n>0);
    for(int i=0;i<pages[p].n;i++) {
        const SetItem *it=&pages[p].items[i];
        if(it->type==ST_PAGE) visit(it->id,depth+1);
        else { assert(it->id>=0 && it->id<=S_T_RESETCAT); occurrences[it->id]++; }
    }
}
static void press(int key) { DashInput in={.pressed=key}; settingsInput(&in); }
static void select_id(int p,int id) {
    page=p;
    for(item=0;item<pages[p].n;item++) if(pages[p].items[item].id==id) return;
    assert(0);
}
int main(void) {
    visit(P_ROOT,0);
    for(int p=0;p<P_COUNT;p++) assert(seen[p]);
    for(int i=0;i<NITEMS(expected);i++) assert(occurrences[expected[i]]==1);
    for(int k=SETTING_LK_AUTO;k<SETTING_LK_START;k++) assert(occurrences[S_LK_0+k]==1);
    assert(!occurrences[S_LK_0+SETTING_LK_START]); /* START is reserved for contextual actions. */
    for(int s=0;s<S_T_RESETCAT;s++) assert(occurrences[s]<=1);
    settingsEnter(); assert(page==P_ROOT && !item && !item_top && !page_depth && begins==1);
    /* Wrap snaps regardless of page length, including a still-moving bar.
     * An ordinary adjacent move must leave the animation to settingsUpdate. */
    for(int p=0;p<P_COUNT;p++) {
        page=p;item=0;item_anim=0.25f;
        press(DASH_IN_UP);assert(item==pages[p].n-1 && item_anim==item);
        item_anim=item-0.25f;
        press(DASH_IN_DOWN);assert(item==0 && item_anim==0);
        if(pages[p].n>1) {
            press(DASH_IN_DOWN);assert(item==1 && item_anim==0);
            item_anim=1;press(DASH_IN_UP);assert(item==0 && item_anim==1);
        }
    }
    page=P_ROOT;item=0;
    /* Root shortcuts never interpret a page ID as an overlapping SetId. */
    for(item=0;item<pages[P_ROOT].n;item++) press(DASH_IN_FAV);
    assert(!resets && !edits);
    item=0; press(DASH_IN_OK); assert(page==P_APPEARANCE && page_depth==1);
    item=1; press(DASH_IN_RIGHT); assert(page==P_THEME);
    item=1; press(DASH_IN_OK); assert(page==P_THEME_COLORS && page_depth==3);
    press(DASH_IN_R2); assert(item==pages[page].n-1);
    item_top=item-ITEM_ROWS+1;
    int selected=item, top=item_top;
    settingsEnter(); assert(page==P_THEME_COLORS && item==selected && begins==1);
    /* Tab visits end the editing session, but must keep the full navigation
     * state. Cover clean exit, Save, Discard, and cancel/Keep editing. */
    __typeof__(page_stack) parents;
    memcpy(parents,page_stack,sizeof(parents));
    int depth=page_depth;
    for(int outcome=0;outcome<4;outcome++) {
        dirty=outcome!=0; dash_dirty=dirty;
        modal_result=outcome==1 ? 0 : outcome==2 ? 1 : 2;
        int previous_begins=begins, prompts=leave_prompts;
        item_anim=(float)selected-0.5f;
        int allowed=settingsLeave();
        assert(allowed==(outcome!=3));
        assert(session==(outcome==3));
        assert(leave_prompts==prompts+(outcome!=0));
        if(allowed) settingsEnter();
        assert(begins==previous_begins+allowed);
        assert(page==P_THEME_COLORS && item==selected && item_top==top);
        assert(page_depth==depth && !memcmp(parents,page_stack,sizeof(parents)));
        if(allowed) assert(item_anim==(float)selected);
    }
    assert(commits==1 && discards==1);
    dirty=1; dash_dirty=0;
    press(DASH_IN_BACK); assert(page==P_THEME && item==1);
    press(DASH_IN_BACK); assert(page==P_APPEARANCE && item==1);
    press(DASH_IN_BACK); assert(page==P_ROOT && item==0);
    /* Stack restores scroll as well as selection. */
    page=P_THEME_COLORS; item=selected; item_top=top;
    openPage(P_THEME_TEXT); backPage();
    assert(page==P_THEME_COLORS && item==selected && item_top==top);
    /* The session menu works everywhere and does not reset navigation. */
    for(int p=0;p<P_COUNT;p++) {
        page=p; item=0; modal_result=0; press(DASH_IN_MENU); assert(page==p && item==0);
    }
    assert(saves==P_COUNT);
    modal_result=1; press(DASH_IN_MENU); assert(reverts==1);
    modal_result=-1; dirty=0; press(DASH_IN_MENU); assert(saves==P_COUNT && reverts==1);
    failed=1; modal_result=0; press(DASH_IN_MENU); assert(saves==P_COUNT+1 && reverts==1);
    failed=0; modal_result=-1;
    select_id(P_SOUND,S_SVOL); edits=0; press(DASH_IN_RIGHT); assert(!edits && toast);
    dashCfg.sound=1; press(DASH_IN_RIGHT); assert(edits==1);
    /* The zero-timeout caption must tell users that automatic start is off. */
    int value,lo,hi;char value_text[32];
    assert(numberInfo(S_TIMEOUT,&value,&lo,&hi,value_text,sizeof(value_text)));
    assert(value==0 && lo==0 && hi==99 && !strcmp(value_text,"0 s (Off)"));
    setting->timeout=3;
    assert(numberInfo(S_TIMEOUT,&value,&lo,&hi,value_text,sizeof(value_text)));
    assert(value==3 && !strcmp(value_text,"3 s"));setting->timeout=0;
    select_id(P_BOOT,S_TIMEOUT); press(DASH_IN_RIGHT); assert(edits==1);
    strcpy(setting->LK_Path[SETTING_LK_AUTO],"mc0:/BOOT/BOOT.ELF");
    press(DASH_IN_RIGHT); assert(edits==2);
    select_id(P_KEYBOARD,S_USBKBD_FILE); press(DASH_IN_OK); assert(edits==2);
    setting->usbkbd_used=1; press(DASH_IN_OK); assert(edits==3);
    select_id(P_THEME_TEXT,S_FONT_FILE); press(DASH_IN_OK); assert(edits==3);
    dashTheme.font=DASH_FONT_SYSTEM; press(DASH_IN_OK); assert(edits==4);
    select_id(P_THEME_WALL,S_T_WALLDIM); press(DASH_IN_RIGHT); assert(edits==4);
    dashCfg.artwork=1; dashTheme.wallpaper=1; press(DASH_IN_RIGHT); assert(edits==5);
    select_id(P_THEME_CLOCK,S_T_SECONDS); press(DASH_IN_OK); assert(edits==5);
    dashTheme.clock=1; press(DASH_IN_OK); assert(edits==6);
    /* Six unique choices, with PAL covering 576i. Unsupported 576p is
     * disabled in the popup and skipped by Left/Right in both directions. */
    assert(TV_mode_COUNT==6 && sizeof(tv_names)/sizeof(tv_names[0])==TV_mode_COUNT);
    const char *labels[]={"Auto","NTSC","PAL","VGA","480p","576p"};
    for(int i=0;i<TV_mode_COUNT;i++)assert(!strcmp(tv_names[i],labels[i]));
    select_id(P_SCREEN,S_TVMODE);can576=0;setting->TV_mode=TV_mode_AUTO;
    press(DASH_IN_LEFT);assert(setting->TV_mode==TV_mode_480P);
    press(DASH_IN_RIGHT);assert(setting->TV_mode==TV_mode_AUTO);
    press(DASH_IN_RIGHT);assert(setting->TV_mode==TV_mode_NTSC);
    press(DASH_IN_RIGHT);assert(setting->TV_mode==TV_mode_PAL);
    modal_result=TV_mode_PAL;press(DASH_IN_OK);assert(video_menus==1 && setting->TV_mode==TV_mode_PAL);
    can576=1;setting->TV_mode=TV_mode_AUTO;
    press(DASH_IN_LEFT);assert(setting->TV_mode==TV_mode_576P);
    press(DASH_IN_LEFT);assert(setting->TV_mode==TV_mode_480P);
    press(DASH_IN_RIGHT);assert(setting->TV_mode==TV_mode_576P);
    press(DASH_IN_RIGHT);assert(setting->TV_mode==TV_mode_AUTO);
    modal_result=TV_mode_576P;press(DASH_IN_OK);assert(video_menus==2 && setting->TV_mode==TV_mode_576P);
    /* Details cover all choices. Auto follows the console even while a
     * different mode is selected; opening/canceling a chooser changes nothing. */
    for(auto_mode=TV_mode_NTSC;auto_mode<=TV_mode_PAL;auto_mode++)
    for(can576=0;can576<=1;can576++)
    for(int current=0;current<TV_mode_COUNT;current++) {
        setting->TV_mode=current;
        for(modal_result=-1;modal_result<TV_mode_COUNT;modal_result++) {
            assert(chooseVideoMode(tv_names,TV_mode_COUNT,current)==modal_result);
            assert(setting->TV_mode==current);
        }
    }
    assert(!videoModeDetail(-1) && !videoModeDetail(TV_mode_COUNT));
    puts("PASS: resolution/scan/refresh details for every video mode, console-dependent Auto, unsupported 576p and unchanged choices");
    page=P_ROOT; page_depth=0; item=0; press(DASH_IN_BACK); assert(home==0);
    /* The overview itself also remembers a lower, scrolled selection. */
    press(DASH_IN_R2); selected=item; item_top=item-ITEM_ROWS+1; top=item_top;
    dirty=0; assert(settingsLeave()==1); settingsEnter();
    assert(page==P_ROOT && item==selected && item_top==top && !page_depth);
    puts("PASS: all pages reachable, baseline controls unique, tab memory/Back stack, session menu and dependencies");
}
"""
compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="wle-settings-") as tmp:
    source = Path(tmp) / "settings.c"
    exe = Path(tmp) / "settings.exe"
    source.write_text(code)
    subprocess.run([compiler, "-std=gnu11", str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
