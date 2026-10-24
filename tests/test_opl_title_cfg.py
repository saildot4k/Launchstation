"""Guard OPL title.cfg parsing semantics used by the dashboard app library."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
src = (root / "src/dash_lib.c").read_text()

# OPL distinguishes lowercase metadata keys from similarly named descriptive keys.
assert 'm->opl_style && !strcmp(key, "boot")' in src
assert 'm->opl_style && !strcmp(key, "title")' in src
assert '!m->opl_style && (!stricmp(key, "title") || !stricmp(key, "name"))' in src

opl = src[src.index("static int metaKv("):src.index("static void splitPath(", src.index("static int metaKv("))]
assert 'm->opl_style && !stricmp(key, "boot")' not in opl
assert 'm->opl_style && !stricmp(key, "title")' not in opl

print("PASS: OPL title.cfg uses exact lowercase title/boot while wLE sidecars remain case-insensitive")

# Run the real metadata path and edit action, including existing files and stale flags.
import shutil
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


apps = (root / 'src/dash_apps.c').read_text()
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 1024
#define DASH_PATH_MAX 256
#define DASH_TITLE_MAX 64
#define DASH_APP_HAS_META 1
#define FIO_O_RDONLY 1
#define DI_WARNING 1
typedef struct { char path[DASH_PATH_MAX],title[DASH_TITLE_MAX];int flags; } DashApp;
static int exists,confirm,worker_ready,in_lib,write_error;
static int reads,closes,writes,edits,refreshes,prompts,messages,polls;
static char contents[1024],expected[MAX_PATH];
static void dashStrCopy(char *out,const char *in,int size) { snprintf(out,size,"%s",in); }
static int dashWorkerAwaitAll(const char *text) { (void)text;return worker_ready; }
static void filerRootMcPollIdle(void) { polls++; }
static int genOpen(const char *path,int mode) {
    assert(worker_ready && polls && mode==FIO_O_RDONLY && !strcmp(path,expected));
    reads++;return exists?0:-2;
}
static void genClose(int fd) { assert(fd==0);closes++; }
static int dashModalConfirm(const char *title,const char *body,const char *ok,int back) {
    (void)body;(void)ok;(void)back;assert(!strcmp(title,"Create title.cfg?"));prompts++;return confirm;
}
static int dashWriteFile(const char *path,const void *text,int size) {
    assert(!exists && !strcmp(path,expected) && size==(int)strlen(text) && size<(int)sizeof(contents));
    writes++;if(write_error)return -1;memcpy(contents,text,size+1);exists=1;return 0;
}
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail) {
    (void)icon;(void)title;(void)body;assert(!strcmp(detail,expected));messages++;
}
static int dashOpenTextEditor(const char *path) { assert(exists && !strcmp(path,expected));edits++;return 1; }
static int dashLibIndexOf(const DashApp *app) { (void)app;return in_lib?0:-1; }
static void dashLibRefreshApp(DashApp *app) { (void)app;refreshes++; }
'''
code += function(src, 'static void splitPath(')
code += function(src, 'int dashLibMetadataPath(')
code += function(apps, 'static void editMetadata(')
code += r'''
static void reset(void) {
    exists=write_error=reads=closes=writes=edits=refreshes=prompts=messages=polls=0;
    confirm=worker_ready=in_lib=1;contents[0]=0;
    strcpy(expected,"usb0:/APPS/TOOL/title.cfg");
}
int main(void) {
    const struct { const char *app,*meta; } paths[]={
        {"usb0:/APPS/TOOL/TOOL.ELF","usb0:/APPS/TOOL/title.cfg"},
        {"mc1:/BOOT/BOOT.ELF","mc1:/BOOT/title.cfg"},
        {"mmce0:/Apps/A/APP.KELF","mmce0:/Apps/A/title.cfg"},
        {"ata1:/APP.ELF","ata1:/title.cfg"},
        {"hdd1:/+APPS/Tool/BOOT.ELF","hdd1:/+APPS/Tool/title.cfg"},
        {"host:APP.ELF","host:title.cfg"},
        {"APP.ELF","title.cfg"}
    };
    DashApp app={0};char out[MAX_PATH];
    for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);i++) {
        snprintf(app.path,sizeof(app.path),"%s",paths[i].app);
        assert(!dashLibMetadataPath(&app,out,sizeof(out)) && !strcmp(out,paths[i].meta));
        assert(dashLibMetadataPath(&app,out,4)<0 && out[3]==0);
    }
    strcpy(app.path,paths[0].app);strcpy(app.title,"My tool");
    /* A readable title.cfg is kept, even when the cached metadata flag is absent. */
    reset();exists=1;strcpy(contents,"title=Existing\nboot=TOOL.ELF\ncustom=keep\n");app.flags=0;
    editMetadata(&app);assert(reads==1 && closes==1 && !writes && !prompts && edits==1 && refreshes==1);
    assert(!strcmp(contents,"title=Existing\nboot=TOOL.ELF\ncustom=keep\n"));
    /* An ELF-specific sidecar must not prevent creating the missing title.cfg. */
    reset();app.flags=DASH_APP_HAS_META;editMetadata(&app);
    assert(reads==1 && !closes && writes==1 && prompts==1 && edits==1 && refreshes==1);
    assert(strstr(contents,"title = My tool\r\n") && strstr(contents,"boot = TOOL.ELF\r\n"));
    reset();confirm=0;editMetadata(&app);assert(prompts==1 && !writes && !edits && !refreshes);
    reset();worker_ready=0;editMetadata(&app);assert(!reads && !polls && !writes && !edits);
    reset();write_error=1;editMetadata(&app);assert(writes==1 && messages==1 && !edits && !refreshes);
    reset();exists=1;in_lib=0;editMetadata(&app);assert(edits==1 && !writes && !refreshes);
    puts("PASS: Home/Apps metadata opens title.cfg, preserves existing content and handles missing files, stale flags, cancellation and IO failures");
}
'''
with tempfile.TemporaryDirectory(prefix='title-cfg-editor-') as folder:
    path = Path(folder)
    (path / 'metadata.c').write_text(code)
    exe = path / 'metadata'
    cc = shutil.which('gcc') or shutil.which('cc')
    assert cc, 'Host C compiler required'
    subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Werror',
                    str(path / 'metadata.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
