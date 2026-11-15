"""Run the native editor's Save/Discard/Cancel leave checks on the host."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
editor = (root / "src/dash_editor.c").read_text()
classic = (root / "src/editor_menu.c").read_text()
private = (root / "include/editor_private.h").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


leave = function(editor, "static int confirmDiscard(") + function(editor, "static int leaveEditor(")
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct { int icon;const char *label,*detail;int disabled; } DashMenuItem;
typedef struct { int dirty,len,mark,eol;char path[64]; } EdDoc;
static EdDoc docs[8];
static int ndocs=1,active,saves,save_ok=1,save_choice[8],next_save;
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    if(!strcmp(title,"Text Editor")) {
        int row=-1;
        for(int i=0;i<n;i++)if(!strcmp(items[i].label,"Use as launch arguments")) {
            assert(row<0&&!items[i].disabled);row=i;
        }
        assert(row>=0);return row;
    }
    assert(!strcmp(title,"Save changes?") && n==3 && subtitle && !initial);
    assert(!strcmp(items[0].label,"Save") && !strcmp(items[1].label,"Don't save"));
    assert(!strcmp(items[2].label,"Cancel") && next_save<ndocs);
    return save_choice[next_save++];
}
static const char *docName(EdDoc *d) { (void)d;return "document"; }
static int docSave(EdDoc *d) { saves++;if(save_ok)d->dirty=0;return save_ok; }
'''
menu = function(editor, "static int editorMenu(")
icons = sorted(set(re.findall(r"\bDI_\w+", leave + menu)))
code += "enum { " + ",".join(icons) + " };\n" + leave
menu_enum_start = editor.rfind("enum {", 0, editor.index("\tM_NEW = 0,"))
code += editor[menu_enum_start:editor.index("};", menu_enum_start)+2] + "\n"
code += r'''
#define ED_MAX_DOCS 8
#define TRUE 1
#define FALSE 0
static char *clip;
static const char *const eol_names[]={"LF","CRLF","CR"};
static int selRange(EdDoc *d,int *a,int *b){(void)d;*a=*b=0;return 0;}
''' + menu
for first in ("NEW,", "CREATED,"):
    start=private.rfind("enum {",0,private.index("\t"+first))
    code += private[start:private.index("};",start)+2]+"\n"
code += r'''
static int Window[10][NUM_STATE],Active_Window,Num_Window=1;
static char Path[10][64];
static int classicArgsEnabled(void){char enable[NUM_MENU];
'''
start=classic.index("\tmemset(enable, TRUE, NUM_MENU);")
end=classic.index("\tfor (Menu_Sel = 0;",start)
code += classic[start:end]+"return enable[LAUNCH_WITH_ARGS];}\n"
code += r'''
int main(void) {
    /* Clean documents need no prompt. */
    assert(leaveEditor() && !next_save && !saves);

    /* Cancel, Back and a failed Save keep the dirty document open. */
    docs[0].dirty=1;save_choice[0]=2;
    assert(!leaveEditor() && docs[0].dirty && next_save==1);
    next_save=0;save_choice[0]=-1;
    assert(!leaveEditor() && docs[0].dirty && next_save==1);
    next_save=0;save_choice[0]=0;save_ok=0;
    assert(!leaveEditor() && saves==1 && docs[0].dirty);
    next_save=0;save_ok=1;
    assert(leaveEditor() && saves==2 && !docs[0].dirty);

    /* Cancellation in a later document stops exit and focuses that document. */
    ndocs=3;docs[0].dirty=docs[1].dirty=docs[2].dirty=1;
    save_choice[0]=1;save_choice[1]=2;next_save=0;
    assert(!leaveEditor() && next_save==2 && active==1);
    assert(docs[0].dirty && docs[1].dirty && docs[2].dirty);
    save_choice[1]=save_choice[2]=1;next_save=0;
    assert(leaveEditor() && next_save==3 && saves==2);

    /* Saving an earlier document stays committed if a later save fails. */
    save_choice[0]=0;save_choice[1]=2;next_save=0;
    assert(!leaveEditor() && next_save==2 && !docs[0].dirty && docs[1].dirty);
    next_save=0;save_ok=0;save_choice[0]=0;
    assert(!leaveEditor() && next_save==1 && active==1 && docs[1].dirty);
    next_save=0;save_ok=1;save_choice[0]=save_choice[1]=0;
    assert(leaveEditor() && next_save==2 && !docs[1].dirty && !docs[2].dirty);
    /* Launch arguments are available from every active buffer, including an
     * empty draft, an unsaved document, and nonexistent/arbitrary file paths. */
    const char *paths[]={"","usb0:/missing.bin","mc0:/new.anything","usb0:/settings.TXT"};
    active=Active_Window=0;ndocs=Num_Window=1;
    for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);i++)for(int dirty=0;dirty<2;dirty++)for(int empty=0;empty<2;empty++) {
        strcpy(docs[0].path,paths[i]);docs[0].dirty=dirty;docs[0].len=empty?0:7;
        assert(editorMenu(&docs[0])==M_LAUNCH);
        strcpy(Path[0],paths[i]);Window[0][OPENED]=1;Window[0][CREATED]=dirty;Window[0][SAVED]=!dirty;
        assert(classicArgsEnabled());
    }
    Window[0][OPENED]=0;assert(!classicArgsEnabled());
    puts("PASS: both editors offer launch arguments for new/unsaved/empty buffers and arbitrary or nonexistent paths");
    puts("PASS: editor exit Save/Discard/Cancel/Back, failed saves, clean documents and multiple unsaved documents");
}
'''
with tempfile.TemporaryDirectory(prefix="launchstation-editor-leave-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    cc = shutil.which("gcc") or shutil.which("clang")
    assert cc, "Host compiler required"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True, timeout=10)
