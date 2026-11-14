"""Compile and execute the upstream Neutrino option argument builder on a host.

Unlike a textual-only check, this exercises the actual C builder used by the
PS2 executable, without needing a PS2 graphics/pad stack on the host.
"""
from pathlib import Path
import subprocess
import shutil
import tempfile

root = Path(__file__).resolve().parents[1]
gui = (root / "src/gui_neutrino.c").read_text(encoding="utf-8")
neutrino = (root / "src/neutrino_iso.c").read_text(encoding="utf-8")
makefile = (root / "Makefile").read_text(encoding="utf-8")
ps2build = (root / "ps2.yaml").read_text(encoding="utf-8")

assert '"gui_neutrino.h"' in neutrino
assert "gui_neutrino.o" in makefile
assert "src/gui_neutrino.c" in ps2build
assert "showNeutrinoLaunchOptions(&options)" in neutrino
assert "buildNeutrinoOptionArgs(options, &option_args)" in neutrino
assert "RunLoaderElfKeepIOP" in neutrino
assert neutrino.index("setting->disable_neutrino") < neutrino.index("showNeutrinoLaunchOptions(&options)")
assert neutrino.index("showNeutrinoLaunchOptions(&options)") < neutrino.index("CleanUpForKeepIopExec")
assert "if (message != NULL && message_size > 0)" in neutrino

# Extract the actual data and pure argument builder without pulling in PS2 UI.
start = gui.index("static const struct {")
end = gui.index("/* Versioned two-slot Neutrino profiles.", start)
pure_c = (
    '#include <stdio.h>\n#include <string.h>\n'
    '#include "gui_neutrino.h"\n'
    + gui[start:end]
)
# Execute the dashboard menu with scripted user choices, including cancel.
native_start = gui.index("typedef struct {\n\tNEUTRINO_LAUNCH_OPTIONS *options;")
native_end = gui.index("static void drawNeutrinoHeading", native_start)
pure_c += r"""
#define TRUE 1
#define FALSE 0
#define DI_INFO 0
#define DI_SETTINGS 1
#define DI_PLAY 2
#define DI_BACK 3
#define DI_SAVE 4
#define DI_UNDO 5
#define DASH_TOAST_OK 1
#define DASH_TOAST_WARN 2
static char active_profile_gameid[12];
int profileSave(const char *id, const NEUTRINO_LAUNCH_OPTIONS *o);
void dashToast(int kind, const char *text);
typedef struct { int icon; const char *label; const char *detail; int disabled; } DashMenuItem;
typedef int (*DashMenuEdit)(int, int, void *);
int dashModalMenuEdit(const char *, const char *, DashMenuItem *, int, int, DashMenuEdit, void *);
int dashModalChoice(const char *, const char *const *, int, int);
void dashSoundMaintain(void);
"""
pure_c += gui[native_start:native_end]
pure_c += "int testDashboard(NEUTRINO_LAUNCH_OPTIONS *o) { return showDashboardNeutrinoOptions(o); }\n"
pure_c += 'void testProfile(int enabled) { strcpy(active_profile_gameid, enabled ? "SLUS_123.45" : ""); }\n'

harness = r"""
#include <assert.h>
#include <string.h>
#include "gui_neutrino.h"
typedef struct { int row, direction; } Edit;
static const Edit *script;
static int step, choice, audio_ready, audio_recoveries, menus, choices, saves, save_ok=1, toast_kind;
static NEUTRINO_LAUNCH_OPTIONS saved_options;
static NEUTRINO_LAUNCH_OPTIONS *current_options;
void dashSoundMaintain(void) { audio_ready=1; audio_recoveries++; }
int testDashboard(NEUTRINO_LAUNCH_OPTIONS *);
void testProfile(int);
int profileSave(const char *id, const NEUTRINO_LAUNCH_OPTIONS *o) {
    assert(!strcmp(id,"SLUS_123.45"));saves++;saved_options=*o;return save_ok;
}
void dashToast(int kind, const char *text) { assert(text);toast_kind=kind; }
typedef struct { int icon; const char *label; const char *detail; int disabled; } DashMenuItem;
typedef int (*DashMenuEdit)(int, int, void *);
int dashModalMenuEdit(const char *title, const char *subtitle, DashMenuItem *items, int count, int selected,
                     DashMenuEdit edit, void *arg) {
    assert(audio_ready); /* ISO preparation can replace the IOP before entry. */
    assert(title && subtitle && selected == 0 && (count == 11 || count == 13));
    assert(edit && arg && !step);menus++;
    for (int i = 0; i < count; i++) assert(items[i].label && !items[i].disabled);
    assert(!strcmp(items[0].label, "Run game") && items[0].detail == NULL);
    assert(!strcmp(items[1].label, "Fast disc reads"));
    while(step < 100) {
        Edit action=script[step++];
        if(action.row < 0) return -1;
        assert(action.row < count);
        int handled=edit(action.row,action.direction,arg);
        /* Values refresh immediately, without starting another modal. */
        const int compatibility_bits[]={0,2,3,5,7};
        for(int i=0;i<5;i++)
            assert(!strcmp(items[i+1].detail,(current_options->game_compatibility & (1u<<compatibility_bits[i]))?"On":"Off"));
        assert(!strcmp(items[8].detail,current_options->debug_colors?"On":"Off"));
        assert(!strcmp(items[9].detail,current_options->logo?"On":"Off"));
        if(current_options->video_mode==0) assert(!strcmp(items[6].detail,"Original (480i / 576i)"));
        if(current_options->video_mode==5) assert(!strcmp(items[6].detail,"1080i (Width x3)"));
        if(current_options->video_compatibility==0) assert(!strcmp(items[7].detail,"Off"));
        if(current_options->video_compatibility==3) assert(!strcmp(items[7].detail,"Field flipping 3"));
        if(!handled && !action.direction) return action.row;
    }
    assert(!"script did not close the menu");return -1;
}
int dashModalChoice(const char *title, const char *const *labels, int count, int selected) {
    assert(audio_ready);
    assert(title && labels && count > selected);
    choices++;return choice;
}
static int runScript(NEUTRINO_LAUNCH_OPTIONS *o,const Edit *actions,int profile) {
    script=actions;current_options=o;step=menus=audio_ready=0;testProfile(profile);
    int result=testDashboard(o);
    assert(menus==1 && audio_ready);return result;
}
int main(void) {
    NEUTRINO_LAUNCH_OPTIONS o = {0};
    NEUTRINO_OPTION_ARGS a;
    int n;
    n = buildNeutrinoOptionArgs(&o, &a);
    assert(n == 0); /* defaults are unmodified, never saved */

    o.game_compatibility = (1u<<0) | (1u<<2) | (1u<<3) | (1u<<5) | (1u<<7);
    n = buildNeutrinoOptionArgs(&o, &a);
    assert(n == 1 && strcmp(a.argv[0], "-gc=02357") == 0);

    o.video_mode = 5;
    o.video_compatibility = 3;
    o.debug_colors = 1;
    o.logo = 1;
    n = buildNeutrinoOptionArgs(&o, &a);
    assert(n == 4);
    assert(strcmp(a.argv[0], "-gc=02357") == 0);
    assert(strcmp(a.argv[1], "-gsm=1080ix3:3") == 0);
    assert(strcmp(a.argv[2], "-dbc") == 0);
    assert(strcmp(a.argv[3], "-logo") == 0);

    o.game_compatibility = 1u << 1; /* Neutrino dummy mode is not selectable */
    assert(buildNeutrinoOptionArgs(&o, &a) == -1);
    o.game_compatibility = 0;
    o.video_mode = 99;
    assert(buildNeutrinoOptionArgs(&o, &a) == -1);
    o.video_mode = 0;
    o.video_compatibility = -1;
    assert(buildNeutrinoOptionArgs(&o, &a) == -1);
    assert(buildNeutrinoOptionArgs(0, &a) == -1);
    assert(buildNeutrinoOptionArgs(&o, 0) == -1);
    const Edit run[] = {{1,0},{5,1},{6,1},{6,1},{6,1},{7,-1},{8,-1},{9,0},{0,0}};
    memset(&o, 0, sizeof(o));
    assert(runScript(&o,run,0) == 1 && step == 9 && audio_recoveries == 1 && !choices);
    assert(o.game_compatibility == ((1u << 0) | (1u << 7)));
    assert(o.video_mode == 3 && o.video_compatibility == 3 && o.debug_colors && o.logo);
    const Edit cancel[] = {{-1,0}};
    assert(runScript(&o,cancel,0) == 0 && audio_recoveries == 2);
    const Edit submenu_cancel[] = {{6,0},{10,0}};choice=-1;
    assert(runScript(&o,submenu_cancel,0) == 0 && o.video_mode == 3 && audio_recoveries == 3 && choices==1);
    const Edit submenu_choose[] = {{6,0},{7,0},{0,0}};choice=2;
    assert(runScript(&o,submenu_choose,0) == 1 && o.video_mode==2 && o.video_compatibility==2 && choices==3);
    /* Both cyclic selectors wrap in either direction. */
    const Edit wrap[] = {{6,-1},{7,-1},{6,1},{7,1},{0,0}};
    memset(&o,0,sizeof(o));assert(runScript(&o,wrap,0)==1 && !o.video_mode && !o.video_compatibility);
    const Edit previous[] = {{6,-1},{7,-1},{0,0}};
    assert(runScript(&o,previous,0)==1 && o.video_mode==5 && o.video_compatibility==3);
    assert(runScript(&o,wrap,0)==1 && o.video_mode==5 && o.video_compatibility==3);
    /* Every compatibility switch and both toggles accept either direction. */
    for(int row=1;row<=9;row++) {
        if(row==6 || row==7) continue;
        const Edit toggle[]={{row,-1},{row,1},{0,0}};
        memset(&o,0,sizeof(o));assert(runScript(&o,toggle,0)==1);
        assert(!o.game_compatibility && !o.debug_colors && !o.logo);
    }
    /* Action rows never execute on Left/Right. Save/reset stay in one session. */
    const Edit actions[]={{0,-1},{0,1},{1,1},{10,-1},{10,1},{11,-1},{11,1},{12,-1},{12,1},{10,0},{11,0},{0,0}};
    memset(&o,0,sizeof(o));assert(runScript(&o,actions,1)==1 && saves==1 && toast_kind==1);
    assert(saved_options.game_compatibility==1 && !o.game_compatibility && !o.video_mode && !o.logo);
    const Edit failed_save[]={{5,1},{10,0},{12,0}};save_ok=0;
    assert(runScript(&o,failed_save,1)==0 && saves==2 && toast_kind==2 && o.game_compatibility==(1u<<7));
    const Edit cancel_no_profile[]={{10,-1},{10,1},{10,0}};
    assert(runScript(&o,cancel_no_profile,0)==0 && saves==2);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="r3z-neutrino-") as folder:
    temp = Path(folder)
    (temp / "builder.c").write_text(pure_c, encoding="utf-8")
    (temp / "main.c").write_text(harness, encoding="utf-8")
    binary = temp / "test_neutrino_args"
    subprocess.run(
        [shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-I", str(root / "include"), str(temp / "builder.c"),
         str(temp / "main.c"), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)

print("R3Z Neutrino option parser: executable host C checks passed")
