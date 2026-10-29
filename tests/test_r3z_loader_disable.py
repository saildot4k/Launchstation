"""Exercise loader path menus, CNF persistence wiring and launch opt-out guards."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]

def source(path):
    return (root / path).read_text(encoding="utf-8")

def function(text, signature):
    start = text.index(signature)
    end = text.index("\n}", start) + 2
    return text[start:end]

header = source("include/launchelf.h")
config = source("src/config.c")
settings = source("src/dash_settings.c")
actions = source("src/main_actions.c")
docs = source("docs/LAUNCHELF.CNF")

# Default NO means enabled on older CNFs, and each bit is independently stored.
for feature, field in (
    ("EMBER", "disable_ember"),
    ("POPSTARTER", "disable_popstarter"),
    ("NEUTRINO", "disable_neutrino"),
):
    assert f"int {field};" in header
    assert f"setting->{field} = 0;" in config
    assert f"Disable_{feature} = %d" in config
    assert f'strcmp(name, "Disable_{feature}")' in config
    assert f"setting->{field} = (atoi(value) != 0);" in config
    assert f"Disable_{feature} = 0" in docs
    assert f"p->disabled = &setting->{field};" in settings

# Dashboard choices participate in the existing classic CNF Save/Discard session.
assert "S_DISABLE_" not in settings
assert 'v = "Disabled";' in settings
assert "memcpy(setting, &snap_classic, sizeof(snap_classic));" in settings
assert "cfgSave(CFG_SAVE_CNF" in settings

# The image handler remains selected by the existing file format, with no
# unrelated ELF fallback when the chosen core is disabled.
for token in ("IsPopstarterVcdPath(path)", 'genCmpFileExt(path, "CUE") || IsEmberGamePath(path)', "IsNeutrinoIsoPath(path)"):
    assert token in actions
for path, symbol, field, first_io in (
    ("src/ember.c", "LaunchEmberGame", "disable_ember", "parseEmberGamePath(path,"),
    ("src/popstarter.c", "LaunchPopstarterVcd", "disable_popstarter", "prepareLaunch(path,"),
    ("src/neutrino_iso.c", "LaunchNeutrinoIso", "disable_neutrino", "validateIso(path,"),
):
    body = function(source(path), "int " + symbol + "(")
    guard = "if (setting != NULL && setting->" + field + ")"
    assert body.index(guard) < body.index(first_io), (symbol, "gate must precede image access")
    assert body.index(guard) < body.index("CleanUpFor"), (symbol, "gate must precede IOP shutdown")


# Execute the real path menu, picker and apply/clear functions. In particular,
# canceled file selection must preserve a disabled loader's remembered path.
code = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 128
#define NITEMS(a) ((int)(sizeof(a)/sizeof((a)[0])))
enum { S_USBKBD_FILE, S_KBDMAP_FILE, S_CNF_PATH, S_LANG_FILE, S_FONT_FILE,
       S_ESR_PATH, S_OSDSYS_PATH, S_POPS_PATH, S_EMBER_PATH, S_NEUTRINO_PATH };
enum { DASH_PICK_FILE, DASH_PICK_FOLDER, DI_FOLDER, DI_CLOSE, DI_WARNING,
       DASH_TOAST_INFO, SETTING_LK_ESR=0, SETTING_LK_OSDSYS=1 };
typedef struct {
    char usbkbd_file[MAX_PATH], kbdmap_file[MAX_PATH], CNF_Path[MAX_PATH];
    char lang_file[MAX_PATH], font_file[MAX_PATH], LK_Path[2][MAX_PATH];
    char popstarter_file[MAX_PATH], ember_dir[MAX_PATH], neutrino_file[MAX_PATH];
    int LK_Flag[2], disable_popstarter, disable_ember, disable_neutrino;
} Setting;
static Setting config, *setting=&config;
typedef struct { int id; const char *label; } SetItem;
typedef struct { int icon; const char *label, *detail; int disabled; } DashMenuItem;
static int classic_dirty, selection=-1, picker_ok, picker_calls, messages;
static int expected_count, expected_clear, expected_disabled;
static const char *picked_path="usb1:/Loaders/selected.ELF";
static void dashStrCopy(char *dst, const char *src, int n) { snprintf(dst,n,"%s",src); }
static int dashWorkerAwaitAll(const char *text) { (void)text; return 1; }
static void Load_External_Language(void) { }
static int loadFont(const char *path) { (void)path; return 1; }
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail)
{ (void)icon;(void)title;(void)body;(void)detail; messages++; }
static void dashToast(int icon,const char *text) { (void)icon;(void)text; }
static int dashPickPath(const char *title,const char *start,int mode,const char *ext,char *out,int n)
{
    (void)title;(void)start;picker_calls++;
    assert(mode==DASH_PICK_FILE && !strcmp(ext,"ELF"));
    if (picker_ok) dashStrCopy(out,picked_path,n);
    return picker_ok;
}
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial)
{
    (void)title; assert(n==expected_count && initial==0);
    assert(!strcmp(items[0].label,"Choose a location..."));
    assert(!strcmp(items[1].label,"Clear location"));
    assert(items[1].disabled==!expected_clear);
    if (n==3) {
        assert(!strcmp(items[2].label,"Disabled") && !items[2].disabled);
        assert((!strcmp(subtitle,"Disabled"))==expected_disabled);
    }
    return selection;
}
"""
start = settings.index("typedef struct\n{\n\tchar *field;")
end = settings.index("} PathSpec;", start) + len("} PathSpec;")
code += settings[start:end] + "\n"
for signature in (
    "static int pathInfo(", "static void mcAlias(", "static void pathApplied(",
    "static void startDirOf(", "static void editPath(", "static void clearPath(",
    "static void editPathMenu(",
):
    code += function(settings, signature) + "\n"
code += r"""
int main(void)
{
    const SetItem loaders[]={
        {S_POPS_PATH,"POPStarter path"}, {S_EMBER_PATH,"Ember path"},
        {S_NEUTRINO_PATH,"Neutrino path"}
    };
    int *flags[]={&config.disable_popstarter,&config.disable_ember,&config.disable_neutrino};
    for (int i=0;i<3;i++) {
        memset(&config,0,sizeof(config));
        PathSpec ps; assert(pathInfo(loaders[i].id,&ps));
        assert(ps.disabled==flags[i]);
        strcpy(ps.field,"usb0:/Loaders/original.ELF");
        for (int j=0;j<3;j++) *flags[j]=j!=i;
        expected_count=3; expected_clear=1; expected_disabled=0;
        selection=2; classic_dirty=0; editPathMenu(&loaders[i]);
        assert(*flags[i]==1 && classic_dirty);
        assert(!strcmp(ps.field,"usb0:/Loaders/original.ELF"));
        for (int j=0;j<3;j++) assert(*flags[j]==1);

        /* Neither cancel path mutates settings or creates a Save prompt. */
        Setting saved=config; expected_disabled=1;
        selection=-1; classic_dirty=0; editPathMenu(&loaders[i]);
        assert(!memcmp(&saved,&config,sizeof(config)) && !classic_dirty);
        selection=0; picker_ok=0; picker_calls=0; editPathMenu(&loaders[i]);
        assert(picker_calls==1);
        assert(!memcmp(&saved,&config,sizeof(config)) && !classic_dirty);
        selection=2; editPathMenu(&loaders[i]);
        assert(!memcmp(&saved,&config,sizeof(config)) && !classic_dirty);

        /* Successful file selection re-enables just this loader. */
        selection=0; picker_ok=1; editPathMenu(&loaders[i]);
        assert(!strcmp(ps.field,picked_path) && !*flags[i] && classic_dirty);
        for (int j=0;j<3;j++) if (j!=i) assert(*flags[j]==1);

        /* Clearing a configured or disabled path restores discovery. */
        expected_disabled=0; selection=1; classic_dirty=0; editPathMenu(&loaders[i]);
        assert(!ps.field[0] && !*flags[i] && classic_dirty);
        expected_clear=0; selection=-1; classic_dirty=0; editPathMenu(&loaders[i]);
        assert(!classic_dirty);
        selection=2; editPathMenu(&loaders[i]);
        assert(*flags[i] && !ps.field[0]);
        expected_disabled=1; expected_clear=1;
        selection=1; classic_dirty=0; editPathMenu(&loaders[i]);
        assert(!*flags[i] && !ps.field[0] && classic_dirty);
        for (int j=0;j<3;j++) if (j!=i) assert(*flags[j]==1);

        /* Clearing a disabled loader with a stored path clears both. */
        strcpy(ps.field,"usb0:/Loaders/remembered.ELF"); *flags[i]=1;
        classic_dirty=0; editPathMenu(&loaders[i]);
        assert(!*flags[i] && !ps.field[0] && classic_dirty);
    }
    /* Other path settings retain their existing two-choice menu. */
    const SetItem generic={S_ESR_PATH,"ESR loader"};
    expected_count=2; expected_clear=0; selection=-1; classic_dirty=0;
    editPathMenu(&generic); assert(!classic_dirty);
    strcpy(config.LK_Path[SETTING_LK_ESR],"usb0:/ESR.ELF");
    config.LK_Flag[SETTING_LK_ESR]=1;
    expected_clear=1; selection=1; editPathMenu(&generic);
    assert(!config.LK_Path[SETTING_LK_ESR][0] && !config.LK_Flag[SETTING_LK_ESR]);
    assert(classic_dirty && !messages);
    puts("Loader path menus: choose, clear, disable, cancel and independent state OK");
    return 0;
}
"""
compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="loader-path-menus-") as tmp:
    cfile = Path(tmp) / "loader_path_menus.c"
    executable = Path(tmp) / "loader_path_menus"
    cfile.write_text(code, encoding="utf-8")
    subprocess.run([compiler, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(cfile), "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
print("R3Z loader availability: defaults, persistence and route guards OK")
