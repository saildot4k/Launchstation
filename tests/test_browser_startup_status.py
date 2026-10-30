"""Run native browser startup feedback through the production loading API.

Driver/file I/O is mocked. Verify path-bar placement, title-only feedback,
restored presenters after cancellation/failure, and unchanged operation popups.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
browser = (root / "src/dash_browser.c").read_text()
ui = (root / "src/dash_ui.c").read_text()
header = (root / "include/dash_internal.h").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
typedef struct { int r,g,b,a; } DashColor;
typedef struct { const char *name; } DashDevice;
#define DASH_VW 640
#define DASH_VH 448
#define DASH_FS_LABEL 0.9f
#define DASH_FS_SMALL 0.66f
#define DASH_FS_CAPTION 0.6f
#define DASH_BLEND_ADD 1
#define DASH_BLEND_NORMAL 0
#define FB_X 40
#define FB_W 560
#define DASH_PANE_L 34
#define DASH_PANE_W 572
static const DashColor DASH_C_ACCENT={0},DASH_C_TEXT={0},DASH_C_TEXT2={0},DASH_C_TEXT3={0};
static struct {
    char dir[256],startup_status[64];
    int free_valid,nmarked,n;
    u64 free_bytes;
} fb;
static int fb_tab_active,quiet,worker,overlays,tab_frames,modal_frames,presents,ticks,flushes,reports;
static int metadata,prepare_result,prepare_calls,start_result;
static char caption[256];
static u64 now_ms;
static u64 Timer(void) { return now_ms; }
static int isStartupDriverStatusQuiet(void) { return quiet; }
static int dashWorkerOnThread(void) { return worker; }
static void dashWorkerStatus(const char *s,int d,int t) { (void)s;(void)d;(void)t;reports++; }
static void dashStrCopy(char *dst,const char *src,int n) { snprintf(dst,n,"%s",src); }
static float dashClampf(float x,float lo,float hi) { return x<lo?lo:x>hi?hi:x; }
static float dashApproach(float v,float target,float rate,float dt) { (void)v;(void)rate;(void)dt;return target; }
static DashColor dashColorA(DashColor c,float k) { (void)k;return c; }
static float dashVisualUpdate(void) { ticks++;now_ms+=16;return 0.016f; }
static void ignore(float first,...) { (void)first; }
#define dashDrawPanelBox(...) ignore(__VA_ARGS__)
#define modalPanel(...) ignore(__VA_ARGS__)
#define dashGfxPushAlpha(...) ignore(__VA_ARGS__)
#define dashGfxBlend(...) ignore(__VA_ARGS__)
#define dashDrawSpinner(...) ignore(__VA_ARGS__)
#define dashTextFit(...) ignore(__VA_ARGS__)
#define loadingBarShape(...) ignore(__VA_ARGS__)
#define modalHintRow(...) ignore(__VA_ARGS__)
static void modalBackdrop(float k) { (void)k;overlays++; }
static int dashBackIcon(void) { return 0; }
static void dashGfxPopAlpha(void) { }
static void dashGfxPresent(void) { assert(ticks==presents+1);presents++; }
static void dashInputFlush(void) { flushes++; }
static void fmtBytes(char *out,int n,u64 b) { (void)b;snprintf(out,n,"1 MB"); }
static void dashTextScroll(float x,float y,float w,const char *text,float scale,DashColor c) {
    (void)x;(void)y;(void)scale;(void)c;
    if(fb.startup_status[0]) assert(w==FB_W-12);
    snprintf(caption,sizeof(caption),"%s",text);
}
static void dashTextRight(float x,float y,const char *text,float scale,DashColor c) {
    (void)x;(void)y;(void)text;(void)scale;(void)c;metadata++;
}
'''
# Execute the real path-panel drawing block, including its available width and
# metadata lane, without mocking the expression that chooses the caption.
body = function(browser, "static void browserDrawBody(void)\n{")
start = body.index("\tdashDrawPanelBox(")
end = body.index("\tif (LaunchArgsPending())", start)
code += r'''
static void drawPathBar(void) {
    char info[64],display_path[258];
    const float path_panel_y=68,path_center_y=80;
    snprintf(display_path,sizeof(display_path),"%s",fb.dir);
'''
code += body[start:end] + "}\n"
code += r'''
static void dashRenderScene(void) { tab_frames++;drawPathBar(); }
static void browserScene(void) { modal_frames++;drawPathBar(); }
'''
start = header.index("typedef void (*DashLoadingView)")
code += header[start:header.index(";", start)+1] + "\n"
code += ui[ui.index("static int loading_active;"):ui.index("int dashLoadingActive(void)")]
for signature in (
    "int dashLoadingActive(", "static void loadingDraw(", "void dashLoadingBegin(",
    "void dashLoadingSetCancel(", "static void loadingProgress(", "void dashLoadingStatus(",
    "void dashLoadingFrame(", "void dashLoadingEnd(",
):
    code += function(ui, signature)
code += r'''
static void driver_work(const char *title) {
    dashLoadingBegin(title);
    dashLoadingFrame("Waiting for memory card status",0,0);
    assert(!strcmp(caption,title));
    now_ms+=40;dashLoadingStatus("Loading internal driver details",0,0);
    assert(!strcmp(caption,title));
    dashLoadingEnd();
}
static void openDirInternal(const char *dir,const char *select) {
    (void)select;prepare_calls++;
    driver_work("Starting device");
    if(!prepare_result) return; /* canceled wait or preparation failure */
    snprintf(fb.dir,sizeof(fb.dir),"%s",dir);
}
static int dashDevicesStart(const DashDevice *d,void *cb,void *user) {
    assert(!cb && !user);driver_work(d->name);return start_result;
}
'''
for signature in (
    "static void browserStartupDraw(const char *title)\n{",
    "static void browserStartupEnd(", "static int browserStartDevice(",
    "static void openDir(const char *dir, const char *select)\n{",
):
    code += function(browser, signature)
code += r'''
static int parent_frames;
static void parent_view(const char *title) { assert(title);parent_frames++;dashGfxPresent(); }
int main(void) {
    drawPathBar();assert(!strcmp(caption,"Choose a device"));
    for(int tab=0;tab<2;tab++) for(int result=0;result<2;result++) {
        fb_tab_active=tab;prepare_result=result;
        tab_frames=modal_frames=metadata=0;
        int before=ticks;
        openDir("ata0:/",NULL);
        assert(ticks==before+3 && !overlays && !loading_active && !loading_view);
        assert(!fb.startup_status[0] && !strcmp(caption,"Starting device"));
        assert(tab ? tab_frames==3 && !modal_frames : modal_frames==3 && !tab_frames);
        assert(!metadata); /* no stale item/free-space summary while starting */
        drawPathBar();assert(!strcmp(caption,result?"ata0:/":"Choose a device"));
        fb.dir[0]=0;
    }
    /* An already-open folder also restores its path after a canceled wait. */
    strcpy(fb.dir,"mc0:/APPS/");prepare_result=0;openDir("ata0:/",NULL);
    drawPathBar();assert(!strcmp(caption,"mc0:/APPS/"));
    const DashDevice dev={"Starting Internal HDD"};
    for(int result=-1;result<=0;result++) {
        start_result=result;parent_frames=0;
        assert(dashLoadingSetView(parent_view)==NULL);
        assert(browserStartDevice(&dev)==result);
        assert(loading_view==parent_view && !fb.startup_status[0]);
        assert(!strcmp(caption,dev.name) && !parent_frames && !overlays);
        dashLoadingBegin("Parent operation");assert(parent_frames==1);
        dashLoadingEnd();assert(dashLoadingSetView(NULL)==parent_view);
    }
    worker=1;int before=presents;
    dashLoadingStatus("Worker result",0,0);assert(presents==before && reports==1);
    worker=0;
    dashLoadingBegin("Pasting");assert(overlays==1 && loading_active);
    dashLoadingFrame("BOOT.ELF",5,10);assert(overlays==2);
    dashLoadingEnd();assert(!loading_active && !loading_view);
    assert(presents==ticks); /* one visual tick and present per rendered frame */
    puts("PASS: inline browser startup titles; path/root restoration, canceled/failed scopes, worker isolation and normal file-operation popups");
}
'''
compiler = shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-browser-startup-") as tmp:
    source = Path(tmp) / "startup.c"
    executable = Path(tmp) / "startup"
    source.write_text(code)
    subprocess.run([compiler,"-std=c99","-Wall","-Wextra","-Werror",str(source),"-o",str(executable)],check=True)
    subprocess.run([str(executable)],check=True)
