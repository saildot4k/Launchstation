"""Run the native editor's Save/Discard/Cancel leave checks on the host."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
editor = (root / "src/dash_editor.c").read_text()


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
typedef struct { int dirty;char path[64]; } EdDoc;
static EdDoc docs[8];
static int ndocs=1,active,saves,save_ok=1,save_choice[8],next_save;
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    assert(!strcmp(title,"Save changes?") && n==3 && subtitle && !initial);
    assert(!strcmp(items[0].label,"Save") && !strcmp(items[1].label,"Don't save"));
    assert(!strcmp(items[2].label,"Cancel") && next_save<ndocs);
    return save_choice[next_save++];
}
static const char *docName(EdDoc *d) { (void)d;return "document"; }
static int docSave(EdDoc *d) { saves++;if(save_ok)d->dirty=0;return save_ok; }
'''
icons = sorted(set(re.findall(r"\bDI_\w+", leave)))
code += "enum { " + ",".join(icons) + " };\n" + leave
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
