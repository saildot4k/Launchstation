"""Run Dashboard queuing and real editor Save/Discard guards on the host."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
main = (root / "src/dash_main.c").read_text()
editor = (root / "src/dash_editor.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


queue = "".join(function(main, name) for name in (
    "int dashDashboardPending(", "int dashDashboardConfirmLeave(",
    "void dashDashboardMenu(", "static void globalMenu(",
))
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { int icon;const char *label,*detail;int disabled; } DashMenuItem;
typedef struct { int dirty;char path[64]; } EdDoc;
static EdDoc docs[8];
static int ndocs=1,active,saves,save_ok=1;
static int dash_active=1,background_only,boot_phase,ql_down,ql_used;
static int dashboard_action=-1,dashboard_menu_open,dashboard_leave_guard;
static int menu_choice=-1,opens,save_choice[8],next_save;
static int switched=-1,switches,rescans,runs,leave_ok=1,confirm_ok=1;
static struct { const char *Misc_Reboot_IOP,*Misc_PS2PowerOff; } config={"reboot","off"},*setting=&config;
enum { DASH_SEC_HOME=0,DASH_SEC_FILES,DASH_SEC_SETTINGS };
void dashDashboardMenu(void);
int dashDashboardPending(void);
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    if(!strcmp(title,"Dashboard")) {
        assert(!subtitle && n==6 && initial==0 && dashboard_menu_open);
        assert(!strcmp(items[0].label,"Home") && !strcmp(items[2].label,"File Browser"));
        assert(!strcmp(items[3].label,"Settings") && !dashDashboardPending());
        int before=++opens;dashDashboardMenu();assert(opens==before); /* no recursion */
        return menu_choice;
    }
    assert(!strcmp(title,"Save changes?") && n==3 && subtitle && !initial);
    assert(dashboard_leave_guard && !dashDashboardPending());
    return save_choice[next_save++];
}
static const char *docName(EdDoc *d) { (void)d;return "document"; }
static int docSave(EdDoc *d) { saves++;if(save_ok)d->dirty=0;return save_ok; }
static void dashSwitchSection(int section) {
    assert(!dashDashboardPending());switches++;if(leave_ok)switched=section;
}
static int dashConfirmLeave(void) { assert(!dashDashboardPending());return leave_ok; }
static int dashModalConfirm(const char *t,const char *b,const char *a,int initial) {
    (void)t;(void)b;(void)a;(void)initial;assert(!dashDashboardPending());return confirm_ok;
}
static void dashRescanLibrary(int force) { assert(force && !dashDashboardPending());rescans++; }
static void dashRunMisc(const char *path) { assert(path && !dashDashboardPending());runs++; }
'''
icons = sorted(set(re.findall(r"\bDI_\w+", queue + function(editor, "static int confirmDiscard("))))
code += "enum { " + ",".join(icons) + " };\n"
code += function(editor, "static int confirmDiscard(") + function(editor, "static int leaveEditor(")
code += queue
code += r'''
static void choose(int choice) { menu_choice=choice;dashDashboardMenu(); }
int main(void) {
    dash_active=0;choose(0);assert(!opens && !dashDashboardPending());dash_active=1;
    background_only=1;boot_phase=2;ql_down=ql_used=1;
    choose(-1);assert(opens==1 && !dashDashboardPending());
    assert(!background_only && !boot_phase && !ql_down && !ql_used && !switches);

    /* A Dashboard choice cannot change sections underneath an open editor. */
    docs[0].dirty=1;choose(2);assert(dashDashboardPending() && !switches);
    int before=opens;dashDashboardMenu();assert(opens==before);
    save_choice[0]=2;next_save=0;
    assert(!dashDashboardConfirmLeave(leaveEditor));
    assert(!dashDashboardPending() && docs[0].dirty && !switches);
    globalMenu();assert(!switches);

    /* A failed Save also cancels navigation and keeps the document. */
    choose(3);save_choice[0]=0;next_save=0;save_ok=0;
    assert(!dashDashboardConfirmLeave(leaveEditor));
    assert(saves==1 && docs[0].dirty && !dashDashboardPending());
    choose(0);next_save=0;save_ok=1;
    assert(dashDashboardConfirmLeave(leaveEditor) && dashDashboardPending());
    assert(!docs[0].dirty && !switches);
    globalMenu();assert(switched==DASH_SEC_HOME && switches==1 && !dashDashboardPending());

    /* Check every unsaved document; cancellation in a later document wins. */
    ndocs=2;docs[0].dirty=docs[1].dirty=1;
    choose(2);save_choice[0]=1;save_choice[1]=2;next_save=0;
    assert(!dashDashboardConfirmLeave(leaveEditor) && next_save==2);
    assert(!dashDashboardPending() && docs[0].dirty && docs[1].dirty);
    choose(2);save_choice[1]=1;next_save=0;
    assert(dashDashboardConfirmLeave(leaveEditor) && next_save==2);
    globalMenu();assert(switched==DASH_SEC_FILES && switches==2);

    choose(1);assert(!rescans);globalMenu();assert(rescans==1);
    leave_ok=0;choose(4);globalMenu();assert(!runs);
    leave_ok=1;confirm_ok=0;choose(5);globalMenu();assert(!runs);
    confirm_ok=1;choose(4);globalMenu();assert(runs==1);
    puts("PASS: Dashboard popup recursion/chord isolation, deferred actions, editor Save/Discard/Cancel and failures, multiple documents and system guards");
}
'''
with tempfile.TemporaryDirectory(prefix="launchstation-dashboard-start-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    cc = shutil.which("gcc") or shutil.which("clang")
    assert cc, "Host compiler required"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True, timeout=10)
