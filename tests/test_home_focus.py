"""Run Home focus, automatic library entry and persisted startup routing."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (subprocess.check_output(["git", "show", f"{sys.argv[1]}:src/dash_home.c"], cwd=root, text=True)
          if len(sys.argv) > 1 else (root / "src/dash_home.c").read_text())


def function(signature, text=None):
    text = source if text is None else text
    start = text.index(signature)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


code = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char u8;
#define DASH_PATH_MAX 128
#define DASH_MAX_APPS 8
#define DI_HDD 20
#define DI_MC 21
#define DI_USB 22
#define DI_STAR 23
#define DASH_VIEW_GRID 0
#define DASH_VIEW_LIST 1
#define DASH_VIEW_CAROUSEL 2
#define DASH_TITLE_MAX 64
#define HOME_MAX_APPS 24
#define HOME_MAX_CHIPS 24
#define DASH_APP_META_PIN 1
#define SETTING_LK_BTN_COUNT 4
#define SETTING_LK_START 3
#define SETTING_LK_LEFT 1
#define SETTING_LK_RIGHT 2
#define stricmp strcmp
#define CHIP_APPS 1
#define CHIP_FILES 2
#define CHIP_LIBRARY 0
#define CHIP_LAST_FOLDER 1
#define DI_DISC 1
#define DI_KEY 2
#define CHIP_DISC 3
#define CHIP_DEVICES 4
#define CHIP_TOOLS 5
#define CHIP_SETTINGS 6
#define CHIP_LAUNCHKEY 7
#define DI_APPS 3
#define DI_CLOCK 8
#define DI_FOLDER 4
#define DI_DEVICES 5
#define DI_TOOLS 6
#define DI_SETTINGS 7
typedef struct { char path[DASH_PATH_MAX]; int flags; } DashApp;
typedef struct { char pin[8][DASH_PATH_MAX], recent[8][DASH_PATH_MAX], fav[8][DASH_PATH_MAX]; int npin, nrecent, nfav; } Lists;
typedef struct { char Misc_PS2Net[DASH_PATH_MAX]; char LK_Path[SETTING_LK_BTN_COUNT][DASH_PATH_MAX]; char LK_Title[SETTING_LK_BTN_COUNT][DASH_TITLE_MAX]; int LK_Flag[SETTING_LK_BTN_COUNT]; } Setting;
static Lists dashLists;
static struct { int recent_count; int home_shortcuts; int start_section; int app_filter; int view; } dashCfg = {8,1,0,0,0};
static Setting setting_data;
static Setting *setting = &setting_data;
static char LastDir[DASH_PATH_MAX], last_chip_label[DASH_TITLE_MAX];
static DashApp dashApps[8], home_tmp[HOME_MAX_APPS], *home_apps[HOME_MAX_APPS];
static u8 home_badge[HOME_MAX_APPS];
static int dashAppCount, nhome, nchips, row, row_forced, col[2], library_open;
static float col_anim[2], cam[2];
static const char *const lk_names[SETTING_LK_BTN_COUNT] = {"Auto", "Left", "Right", "Start"};
typedef struct { void (*enter)(void); } DashScreen;
static void homeRebuild(void);
static int apps_enters, focus_pokes;
static void appsEnter(void);
static void appsEntered(void) { apps_enters++;appsEnter(); }
static const DashScreen dashAppsScreen={appsEntered};
static void dashUiFocusPoke(void) { focus_pokes++; }
static void dashStrCopy(char *d, const char *s, int n) { snprintf(d, n, "%s", s); }
static int device_ready=1,scan_running;
static int dashDevicePathReady(const char *p) { (void)p; return device_ready; }
static int dashLibDeviceIcon(const char *p) { return !strncmp(p,"mc",2)?DI_MC:DI_USB; }
static int dashStoreIsFavorite(const char *p) {
    for(int i=0;i<dashLists.nfav;i++)if(!strcmp(p,dashLists.fav[i]))return 1;
    return 0;
}
static int dashStoreIsPinned(const char *p) {
    for(int i=0;i<dashLists.npin;i++)if(!strcmp(p,dashLists.pin[i]))return 1;
    return 0;
}
static void dashHomeRebuild(void) { homeRebuild(); }
static DashApp *dashLibResolve(const char *p, DashApp *tmp) {
    int i;
    for (i = 0; i < dashAppCount; i++) if (!strcmp(dashApps[i].path, p)) return &dashApps[i];
    dashStrCopy(tmp->path, p, sizeof(tmp->path)); return tmp;
}
static void dashLibPrettyName(const char *p, char *name, int n) { dashStrCopy(name, p, n); }
static void addChip(int kind, int lk, int icon, const char *label, const char *desc) {
    (void)kind; (void)lk; (void)icon; (void)desc; dashStrCopy(last_chip_label,label,sizeof(last_chip_label)); nchips++;
}
"""
code += function("static int homeHas(") + function("static void homeAdd(") + function("static void homeRebuild(")
code += function("void dashHomeOpenApplications(") + function("static void homeEnter(")
header = (root / "include/dash_internal.h").read_text()
settings = (root / "src/dash_settings.c").read_text()
main = (root / "src/dash_main.c").read_text()
code += header[header.index("enum DashSection"):header.index("enum DashView")]
choice_start = settings.index("\t\tcase S_START: {", settings.index("static int choiceInfo("))
choice_end = settings.index("\t\tcase S_FILES_MODE:", choice_start)
code += "enum { S_START };\nstatic int startChoice(int *cur,const char *const **names) { switch(S_START) {\n"
code += settings[choice_start:choice_end] + "}return 0;}\n"
set_start = settings.index("\t\tcase S_START:", settings.index("static void setChoice("))
set_end = settings.index("\t\tcase S_FILES_MODE:", set_start)
code += "static void setStartChoice(int v) { switch(S_START) {\n" + settings[set_start:set_end] + "}}\n"
code += "static int section,dash_inited;\nstatic const DashScreen home_screen={homeEnter};\n"
code += "static const DashScreen *const screens[DASH_SEC_COUNT]={&home_screen,&dashAppsScreen,&dashAppsScreen,&dashAppsScreen,&dashAppsScreen,&dashAppsScreen};\n"
apps = (root / "src/dash_apps.c").read_text()
code += apps[apps.index("enum AppFilter"):apps.index("#define GRID_COLS")]
for sig in ("static int matchFilter(", "void dashAppsRebuildView(",
            "void dashAppsShowAll(", "static void appsEnter("):
    code += function(sig, apps)
code += r"""
static int app_draws,empty_icon;
static char empty_title[80],empty_body[256];
static int dashLibScanRunning(void) { return scan_running; }
static void drawTitleBar(void) { (void)filter_names;empty_title[0]=empty_body[0]=0;empty_icon=-1; }
static void dashDrawEmptyState(int x,int y,int icon,const char *title,const char *body) {
    (void)x;(void)y;empty_icon=icon;
    snprintf(empty_title,sizeof(empty_title),"%s",title);snprintf(empty_body,sizeof(empty_body),"%s",body);
}
static void drawGrid(void) { (void)grid_cam;app_draws++; }
static void drawList(void) { app_draws++; }
static void drawCarousel(void) { app_draws++; }
#define dashEaseOutCubic(x) (x)
#define dashGfxPushAlpha(x) ((void)(x))
#define dashGfxPushOffset(...) ((void)0)
#define dashGfxPopAlpha(...) ((void)0)
#define dashGfxPopOffset(...) ((void)0)
"""
code += function("static void appsDraw(", apps)
code += "static void startDashboard(void) {\n"
boot_start = main.index("section = dashCfg.start_section;", main.index("static void firstInit(void)"))
boot_end = main.index("dash_inited = 1;", boot_start) + len("dash_inited = 1;")
enter_start = main.index("\tif (screens[section]->enter)", main.index("void DashRun("))
enter_end = main.index("\n\tdashInputFlush();", enter_start)
code += main[boot_start:boot_end] + "\n" + main[enter_start:enter_end] + "\n}\n"
code += r"""
int main(void) {
    dashAppCount = 3;
    dashStrCopy(dashApps[0].path, "mass0:/A.ELF", DASH_PATH_MAX);
    dashStrCopy(dashApps[1].path, "mass0:/B.ELF", DASH_PATH_MAX);
    dashStrCopy(dashApps[2].path, "mass0:/C.ELF", DASH_PATH_MAX);
    homeRebuild();
    col[0] = 1; /* User selected B before making it a favorite. */
    dashStrCopy(dashLists.fav[0], dashApps[1].path, DASH_PATH_MAX);
    dashLists.nfav = 1;
    homeRebuild();
    assert(!strcmp(home_apps[col[0]]->path, dashApps[1].path));
    assert(col[0] == 0);
    assert(col_anim[0] == 0.0f);
    /* Library is always accessible; Last folder is Home-only and conditional.
     * Disabling user-configured launch keys must not hide navigation. */
    dashCfg.home_shortcuts = 0;
    homeRebuild();
    assert(nchips == 1);
    dashStrCopy(LastDir, "mass0:/APPS/", sizeof(LastDir));
    homeRebuild();
    assert(nchips == 2);
    LastDir[0] = '\0';
    homeRebuild();
    assert(nchips == 1);
    dashCfg.home_shortcuts=1;
    strcpy(setting->Misc_PS2Net,"MISC/PS2Net");
    strcpy(setting->LK_Path[SETTING_LK_LEFT],setting->Misc_PS2Net);
    setting->LK_Flag[SETTING_LK_LEFT]=1;homeRebuild();
    assert(!strcmp(last_chip_label,"FTP Server"));
    assert(!strcmp(setting->LK_Path[SETTING_LK_LEFT],"MISC/PS2Net"));
    strcpy(setting->LK_Title[SETTING_LK_LEFT],"My FTP shortcut");homeRebuild();
    assert(!strcmp(last_chip_label,"My FTP shortcut"));
    strcpy(setting->LK_Path[SETTING_LK_START],"mc0:/OLD-START.ELF");homeRebuild();
    assert(nchips==2); /* Legacy START targets do not produce a launch shortcut. */
    /* Automatic entry requires BOTH disabled recents and empty saved history,
     * even though the Continue sample and favorites already contain apps. */
    dashCfg.recent_count=8;dashLists.nrecent=0;homeEnter();
    assert(!library_open && row==0 && !apps_enters);
    dashCfg.recent_count=0;dashLists.nrecent=1;homeEnter();
    assert(!library_open && row==0 && !apps_enters);
    dashLists.nrecent=0;homeEnter();
    assert(library_open && apps_enters==1 && nhome>0 && row==1 && col[1]==0);
    dashHomeOpenApplications();assert(apps_enters==1); /* idempotent */
    library_open=0;homeRebuild();assert(!library_open && row==1); /* Back can reach shortcuts */

    const int targets[]={DASH_SEC_HOME,DASH_SEC_APPS,DASH_SEC_FILES,DASH_SEC_TOOLS,DASH_SEC_SETTINGS};
    const char *labels[]={"Home","Applications","Files","Tools","Settings"};
    for(int i=0;i<5;i++) {
        const char *const *names;int current=-1;
        setStartChoice(i);assert(dashCfg.start_section==targets[i]);
        assert(startChoice(&current,&names)==5 && current==i && !strcmp(names[i],labels[i]));
    }
    const char *const *names;int current;
    dashCfg.start_section=DASH_SEC_DEVICES;startChoice(&current,&names);assert(current==2);
    /* Execute the actual boot normalization and screen-entry block. */
    dashCfg.recent_count=8;dashLists.nrecent=1;
    apps_enters=0;dashCfg.start_section=DASH_SEC_APPS;startDashboard();
    assert(dash_inited && section==DASH_SEC_HOME && library_open && apps_enters==1);
    dashCfg.start_section=DASH_SEC_HOME;startDashboard();
    assert(section==DASH_SEC_HOME && !library_open && row==0 && apps_enters==1);
    for(int i=2;i<5;i++) {
        setStartChoice(i);startDashboard();assert(section==targets[i]);
    }
    dashCfg.recent_count=0;dashLists.nrecent=0;
    for(int i=0;i<2;i++) {
        apps_enters=0;setStartChoice(i);startDashboard();
        assert(section==DASH_SEC_HOME && library_open && apps_enters==1);
    }
    /* Applications startup must not inherit an empty Favorites/device
     * filter. Run the real Apps enter/filter/rebuild/render functions. */
    dashCfg.recent_count=8;dashLists.nrecent=1;dashLists.npin=dashLists.nfav=0;
    dashCfg.start_section=DASH_SEC_APPS;
    for(int previous=0;previous<FILTER_COUNT;previous++) {
        dashCfg.app_filter=previous;startDashboard();
        assert(library_open && filter==FILTER_ALL && norder==3);
        assert(dashCfg.app_filter==previous); /* leave the saved preference alone */
        int drawn=app_draws;appsDraw();assert(!empty_title[0] && app_draws==drawn+1);
    }
    /* Cached apps on storage that is not ready do not masquerade as an
     * empty Favorites list, including while the startup scan is running. */
    device_ready=0;dashAppsRebuildView();assert(!norder && dashAppCount==3);
    scan_running=1;appsDraw();assert(empty_icon==DI_APPS && !strcmp(empty_title,"Looking for applications..."));
    scan_running=0;appsDraw();assert(empty_icon==DI_APPS && !strcmp(empty_title,"Application devices not ready"));
    assert(strstr(empty_body,"Files") && !strstr(empty_body,"SELECT"));
    device_ready=1;dashAppsRebuildView();appsDraw();assert(norder==3 && !empty_title[0]);
    /* Ordinary entry still honors the filter; only Favorites uses a star. */
    dashCfg.app_filter=FILTER_FAV;appsEnter();appsDraw();
    assert(!norder && empty_icon==DI_STAR && !strcmp(empty_title,"No favorites yet"));
    dashCfg.app_filter=FILTER_MC;appsEnter();appsDraw();
    assert(!norder && empty_icon==DI_APPS && !strcmp(empty_title,"Nothing to show"));
    dashCfg.recent_count=0;dashLists.nrecent=0;
    dashAppCount=0;dashLists.npin=dashLists.nfav=0;homeEnter();
    assert(library_open && nhome==0); /* empty library has its normal scan prompt */
    appsDraw();assert(empty_icon==DI_APPS && !strcmp(empty_title,"No applications found"));
    return 0;
}
"""

cc = shutil.which("gcc") or shutil.which("cc")
if not cc:
    raise SystemExit("A host C compiler is required")
with tempfile.TemporaryDirectory() as temp:
    source_path = Path(temp) / "home_focus.c"
    binary_path = Path(temp) / "home_focus.exe"
    source_path.write_text(code)
    subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", str(source_path), "-o", str(binary_path)], check=True)
    subprocess.run([str(binary_path)], check=True)
print("PASS: Home favorites keep focus; empty disabled recents open Applications; all five startup choices, real application filters, startup All and readiness/scan empty states")
