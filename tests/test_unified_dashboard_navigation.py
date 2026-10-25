"""Exercise production section routing with Files as a first-class tab."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root / "src/dash_main.c").read_text()
home = (root / "src/dash_home.c").read_text()
tools = (root / "src/dash_tools.c").read_text()
apps = (root / "src/dash_apps.c").read_text()
settings = (root / "src/dash_settings.c").read_text()

assert "DASH_SEC_APPS" not in main[main.index("static const int visible_sections[]"):main.index("#define DASH_VISIBLE_SEC_COUNT")]
assert 'showMiscCommands();' in tools
assert 'TA_MISC_MENU' in tools
assert 'CHIP_LAST_FOLDER' in home and 'CHIP_LIBRARY' in home
assert 'dashNavigateFilesTab(dir);' in home
assert 'dashNavigateFilesTab(dir);' in (root / "src/dash_apps.c").read_text()
assert 'dashAppsScreen.input(in)' in home and 'dashAppsScreen.draw()' in home
assert 'dashAppsScreen.update(dt)' in home and 'dashAppsScreen.hints()' in home
assert 'library_open = 0;' in home and 'if (in->pressed & DASH_IN_BACK)' in home
assert 'DASH_VIEW_COUNT' in apps and 'FILTER_COUNT' in apps
assert '"Home", "Files", "Tools", "Settings"' in settings
assert 'S_FILES_MODE, "Files / Devices view"' not in settings

def function(source,signature):
    start=source.index(signature)
    pos=source.index("{",start)+1
    depth=1
    while depth:
        depth += (source[pos]=="{") - (source[pos]=="}")
        pos+=1
    return source[start:pos]+"\n"

defs=main[main.index("static const int visible_sections[]"):main.index("const char *dashSectionName")]
code=String = r'''
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
#include <strings.h>
#define stricmp strcasecmp
typedef struct { void (*enter)(void); } DashScreen;
enum { DASH_SEC_HOME=0, DASH_SEC_APPS, DASH_SEC_FILES, DASH_SEC_DEVICES,
       DASH_SEC_TOOLS, DASH_SEC_SETTINGS, DASH_SEC_COUNT };
enum { DASH_SND_TRANSITION=1 };
static int section = DASH_SEC_HOME,prev_section=DASH_SEC_HOME;
static float section_anim=1.0f;
static int section_dir=1, leave_ok=1, enter_count, sound_count, focus_count, tab_closes;
static int dashConfirmLeave(void) { return leave_ok; }
static void dashFileBrowserTabClose(void) { assert(section==DASH_SEC_FILES); tab_closes++; }
static void dashUiFocusPoke(void) { focus_count++; }
static void dashSoundPlay(int sound) { assert(sound==DASH_SND_TRANSITION); sound_count++; }
static void entered(void) { enter_count++; }
static const DashScreen item = {entered};
static const DashScreen *const screens[DASH_SEC_COUNT] = {
    &item,&item,&item,&item,&item,&item
};
'''
code+=defs
for fn in ("int dashVisibleSectionCount(void)","int dashVisibleSectionAt(int index)",
           "int dashVisibleSectionIndex(int s)","int dashAdjacentSection(int s, int direction)",
           "void dashSwitchSection(int s)"):
    code+=function(main,fn)
code += r'''
typedef struct { char Misc[64],Misc_PS2Disc[64],Misc_FileBrowser[64],Misc_PS2Browser[64],Misc_PS2Net[64],Misc_PS2PowerOff[64],Misc_HddManager[64],Misc_TextEditor[64],Misc_Configure[64],Misc_ShowFont[64],Misc_Debug_Info[64],Misc_About_uLE[64],Misc_Show_Build_Info[64],Misc_OSDSYS[64],Misc_Exploit_Installer[64],Misc_Reboot_IOP[64]; } SETTING;
static SETTING config,*setting=&config;
static int dash_active=1,modal_opens,tab_opens;
static int menu_opens,popup_open,menu_choice=-1,expected_count=15,skipped=-1;
static int native_called=-1,misc_runs;
static char last_misc[64];
static const char *command_paths[15];
typedef struct { int icon;const char *label,*detail;int disabled; } DashMenuItem;
enum { DI_DISC,DI_FOLDER,DI_APP,DI_NETWORK,DI_POWER,DI_HDD,DI_TEXT,
       DI_SETTINGS,DI_INFO,DI_CHIP,DI_MC,DI_REFRESH };
static void nativeTool(int id) { assert(!popup_open);native_called=id; }
static void dashFileBrowserTabOpen(const char *path) {assert(path && *path);tab_opens++;}
void dashOpenBrowser(const char *path) {(void)path;modal_opens++;}
static int dashOpenTextEditor(const char *path) {(void)path;nativeTool(6);return 0;}
static void dashHddManager(void) { nativeTool(5); }
static void dashShowFontViewer(void) { nativeTool(8); }
static void dashShowSystemInfo(void) { nativeTool(9); }
static void dashShowAbout(void) { nativeTool(10); }
static void dashShowBuildInfo(void) { nativeTool(11); }
static void dashExploitInstaller(void) { nativeTool(13); }
static void runMiscCommand(const char *path) {
    assert(!popup_open);misc_runs++;snprintf(last_misc,sizeof(last_misc),"%s",path);
}
static void initMisc(const char *prefix) {
    char *paths[]={setting->Misc_PS2Disc,setting->Misc_FileBrowser,setting->Misc_PS2Browser,setting->Misc_PS2Net,setting->Misc_PS2PowerOff,setting->Misc_HddManager,setting->Misc_TextEditor,setting->Misc_Configure,setting->Misc_ShowFont,setting->Misc_Debug_Info,setting->Misc_About_uLE,setting->Misc_Show_Build_Info,setting->Misc_OSDSYS,setting->Misc_Exploit_Installer,setting->Misc_Reboot_IOP};
    snprintf(setting->Misc,sizeof(setting->Misc),"%s",prefix);
    for(int i=0;i<15;i++) {
        snprintf(paths[i],64,"%sCommand%d",prefix,i);command_paths[i]=paths[i];
    }
    skipped=-1;expected_count=15;
}
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    assert(!popup_open && !strcmp(title,"MISC commands") && !subtitle && !initial && n==expected_count);
    menu_opens++;popup_open=1;
    const int icons[]={DI_DISC,DI_FOLDER,DI_APP,DI_NETWORK,DI_POWER,DI_HDD,DI_TEXT,
                       DI_SETTINGS,DI_TEXT,DI_INFO,DI_INFO,DI_CHIP,DI_APP,DI_MC,DI_REFRESH};
    for(int row=0,index=0;row<n;row++,index++) {
        if(index==skipped)index++;
        const char *label=index==3?"FTP Server":command_paths[index]+strlen(setting->Misc);
        assert(items[row].icon==icons[index] && !strcmp(items[row].label,label));
        assert(!items[row].detail && !items[row].disabled);
    }
    popup_open=0;return menu_choice;
}
static int dashModalConfirm(const char *t,const char *b,const char *a,int d) {
 (void)t;(void)b;(void)a;(void)d;return 1;
}
static void dashToolsUsbUnitDiagnostics(void) {}
'''
code += tools[tools.index("enum ToolAction {"):tools.index("static const Tool tools[]")]
code += function(main,"int DashOpenSettings(")
code += function(main,"void dashNavigateFilesTab(")
code += function(main,"void dashRunMisc(")
code += function((root / "src/lang.c").read_text(),"const char *getMiscEntryDisplayName(")
code += function(tools,"static void showMiscCommands(")
code += function(tools,"static void runTool(")
code+=r'''
int main(void) {
    assert(dashVisibleSectionCount()==4);
    assert(dashVisibleSectionAt(0)==DASH_SEC_HOME);
    assert(dashVisibleSectionAt(1)==DASH_SEC_FILES);
    assert(dashVisibleSectionAt(2)==DASH_SEC_TOOLS);
    assert(dashVisibleSectionAt(3)==DASH_SEC_SETTINGS);
    assert(dashVisibleSectionIndex(DASH_SEC_APPS)==0);
    assert(dashVisibleSectionIndex(DASH_SEC_DEVICES)==1);
    assert(dashAdjacentSection(section,+1)==DASH_SEC_FILES);
    dashSwitchSection(DASH_SEC_FILES);
    assert(section==DASH_SEC_FILES && tab_closes==0);
    assert(enter_count==1 && sound_count==1);
    assert(dashAdjacentSection(section,+1)==DASH_SEC_TOOLS);
    assert(dashAdjacentSection(section,-1)==DASH_SEC_HOME);
    /* Returning to the same tab doesn't open a second browser. */
    dashSwitchSection(DASH_SEC_FILES);
    assert(enter_count==1 && tab_closes==0);
    dashSwitchSection(DASH_SEC_TOOLS);
    assert(section==DASH_SEC_TOOLS && enter_count==2 && tab_closes==1);
    assert(dashAdjacentSection(section,-1)==DASH_SEC_FILES);
    /* Unsaved changes prevent the target tab from being initialized. */
    leave_ok=0;
    dashSwitchSection(DASH_SEC_FILES);
    assert(section==DASH_SEC_TOOLS && tab_closes==1 && enter_count==2);
    leave_ok=1;
    dashSwitchSection(DASH_SEC_FILES);
    assert(section==DASH_SEC_FILES && enter_count==3 && tab_closes==1);
    assert(dashAdjacentSection(section,+1)==DASH_SEC_TOOLS);
    dashSwitchSection(DASH_SEC_APPS);
    assert(section==DASH_SEC_HOME && tab_closes==2);
    assert(enter_count==4);
    assert(dashAdjacentSection(section,-1)==DASH_SEC_SETTINGS);
    dashSwitchSection(DASH_SEC_SETTINGS);
    assert(section==DASH_SEC_SETTINGS && enter_count==5);
    dashSwitchSection(DASH_SEC_SETTINGS);
    assert(enter_count==5);
    /* File Browser and the PS1/PS2 image shortcuts enter the Files tab. */
    int before;
    for(int action=TA_BROWSER;action<=TA_BROWSER_AT;action++) {
        dashSwitchSection(DASH_SEC_TOOLS);before=enter_count;
        int opened=tab_opens;
        Tool browser={.action=action,.path=""};
        runTool(&browser);
        assert(section==DASH_SEC_FILES && enter_count==before+1);
        assert(!modal_opens && tab_opens==opened); /* resume the Files tab */
        dashNavigateFilesTab("usb0:/APPS/");assert(tab_opens==opened+1);
        dashSwitchSection(DASH_SEC_TOOLS);before=enter_count;leave_ok=0;
        runTool(&browser);
        assert(section==DASH_SEC_TOOLS && enter_count==before && !modal_opens);
        leave_ok=1;
    }
    Tool misc={.action=TA_MISC_MENU};
    initMisc("MISC/");
    /* All fifteen commands remain available. Configure enters Settings
     * after the popup closes; File Browser enters the existing Files tab. */
    for(int choice=0;choice<15;choice++) {
        dashSwitchSection(DASH_SEC_TOOLS);before=enter_count;
        native_called=-1;misc_runs=0;last_misc[0]=0;menu_choice=choice;
        int old_menus=menu_opens,old_modals=modal_opens,old_tabs=tab_opens;
        runTool(&misc);
        assert(menu_opens==old_menus+1 && !popup_open && modal_opens==old_modals && tab_opens==old_tabs);
        if(choice==1 || choice==7) {
            assert(section==(choice==1?DASH_SEC_FILES:DASH_SEC_SETTINGS));
            assert(enter_count==before+1 && native_called==-1 && !misc_runs);
        } else {
            assert(section==DASH_SEC_TOOLS && enter_count==before);
            if(choice==5 || choice==6 || choice==8 || choice==9 || choice==10 || choice==11 || choice==13)
                assert(native_called==choice && !misc_runs);
            else assert(native_called==-1 && misc_runs==1 && !strcmp(last_misc,command_paths[choice]));
        }
    }
    /* Cancel stays in Tools and runs no command. A refused tab switch also
     * leaves Tools active with no browser dialog remaining over the screen. */
    dashSwitchSection(DASH_SEC_TOOLS);before=enter_count;
    native_called=-1;misc_runs=0;menu_choice=-1;runTool(&misc);
    assert(section==DASH_SEC_TOOLS && enter_count==before && !misc_runs && native_called==-1);
    leave_ok=0;menu_choice=7;runTool(&misc);
    assert(section==DASH_SEC_TOOLS && enter_count==before && !popup_open);
    leave_ok=1;
    /* Configured/localized path prefixes still label and dispatch correctly. */
    initMisc("Divers/");menu_choice=7;runTool(&misc);assert(section==DASH_SEC_SETTINGS);
    dashSwitchSection(DASH_SEC_TOOLS);menu_choice=-1;
    strcpy(setting->Misc_PS2Net,"usb0:/custom.elf");skipped=3;expected_count=14;runTool(&misc);
    int old_menus=menu_opens;
    initMisc("MISC/");
    for(int i=0;i<15;i++)((char *)command_paths[i])[0]=0;
    runTool(&misc);assert(menu_opens==old_menus && section==DASH_SEC_TOOLS);
    puts("PASS: unified tabs, MISC popup command labels/dispatch/cancel, Configure to Settings, File Browser to Files and leave guards");
}
'''
compiler=shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-unified-nav-") as tmp:
    source=Path(tmp)/"nav.c";exe=Path(tmp)/"nav"
    source.write_text(code)
    subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                    str(source),"-o",str(exe)],check=True)
    subprocess.run([str(exe)],timeout=5,check=True)
