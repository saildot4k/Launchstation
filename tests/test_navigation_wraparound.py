"""Navigation wrap-around contracts for dashboard list controllers (#189)."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]


def src(name):
    return (root / "src" / name).read_text(encoding="utf-8")


browser = src("dash_browser.c")
apps = src("dash_apps.c")
tools = src("dash_tools.c")
settings = src("dash_settings.c")
widgets = src("dash_widgets.c")
hdd = src("dash_hdd.c")
home = src("dash_home.c")

# File Browser: single steps wrap; pages stop at endpoints before wrapping.
assert "static int wrapIndex(int index, int total)" in browser
for expr in (
    "fb.sel = wrapIndex(fb.sel - 1, total);",
    "fb.sel = wrapIndex(fb.sel + 1, total);",
    "fb.sel = pageIndex(fb.sel, total, -1);",
    "fb.sel = pageIndex(fb.sel, total, 1);",
):
    assert expr in browser

# Applications: list/grid/carousel moves now cycle through all entries.
assert "next = (sel + delta) % norder;" in apps
assert "if (next < 0)" in apps and "next += norder;" in apps
assert "move(sel == 0 ? -1" in apps
assert "move(sel == norder - 1 ? 1" in apps

# Tools and Settings lists wrap at top/bottom.
assert "if (s < 0)\n\t\t\ts = NTOOLS - 1;" in tools
assert "else if (s >= NTOOLS)\n\t\t\ts = 0;" in tools
assert "int next = item > 0 ? item - 1 : total - 1;" in settings
assert "int next = item < total - 1 ? item + 1 : 0;" in settings

# Picker and HDD manager now cycle through rows.
assert "sel = sel > 0 ? sel - 1 : n_rows - 1;" in widgets
assert "sel = sel < n_rows - 1 ? sel + 1 : 0;" in widgets
assert "sel = sel > 0 ? sel - 1 : hm.n - 1;" in hdd
assert "sel = (sel + 1) % hm.n;" in hdd

# Home row/chip strips now use wrapped movement.
assert "static int wrapCol(int value, int n)" in home
assert "int next = wrapCol(col[row] - 1, n);" in home
assert "int next = wrapCol(col[row] + 1, n);" in home

print("PASS: dashboard list navigation wraps across file, menu and browser views")


# Execute the production directional-input block and viewport helper on the host.
# SDK actions after navigation are excluded; selection arithmetic is unchanged.
import shutil
import subprocess
import tempfile


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


start = browser.index("\t\tif (total > 0) {", browser.index("static void browserProcessInput"))
end = browser.index("\n\t\tif (fb.sel != prev", start)
browser_move = browser[start:end]
start = apps.index("\t\tif (in->pressed & DASH_IN_UP)", apps.index("static void appsInput"))
end = apps.index("\n\t\tif (in->pressed & DASH_IN_L2)", start)
grid_move = apps[start:end]
code = r"""
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define GRID_COLS 5
#define GRID_PITCH_Y 100
#define DASH_IN_UP 1
#define DASH_IN_DOWN 2
#define DASH_IN_LEFT 4
#define DASH_IN_RIGHT 8
#define DASH_IN_L2 16
#define DASH_IN_R2 32
typedef struct { unsigned pressed; } DashInput;
#define MAX_PATH 256
#define MAX_NAME 64
#define MAX_ENTRY 256
typedef unsigned long long u64;
typedef struct { char name[MAX_NAME]; } FILEINFO;
static struct {
 int sel,top,n,ndevs,nmarked,loading,gen,free_valid,ps1_free,card_type;
 char dir[MAX_PATH],want_sel[MAX_NAME];float sel_anim,top_anim;
 FILEINFO *files;unsigned char *mark;u64 free_bytes;
} fb;
enum { FB_SORT_STORED,FB_SORT_NAME,FB_SORT_TITLE,FB_SORT_SIZE,FB_SORT_DATE };
static int file_show,file_sort,fb_show=1,fb_sort=FB_SORT_NAME;
static int browser_usb_jobs,browser_usb_input_rearm;
static struct { char Misc[MAX_NAME]; } config={"MISC/"}, *setting=&config;
static int isMisc(const char *dir) { return !strcmp(dir,"MISC/"); }
static void dashStrCopy(char *out,const char *in,int n) { snprintf(out,n,"%s",in); }
static int compareName(const void *a,const void *b) { return strcmp(((const FILEINFO *)a)->name,((const FILEINFO *)b)->name); }
static void fbSortFiles(FILEINFO *files,int n) { qsort(files,n,sizeof(*files),compareName); }
static int sel, norder;
static float sel_anim, grid_cam,list_top_anim=-1,top_anim=-1;
static void dashUiFocusPoke(void) {}
#define DASH_TOAST_WARN 1
static int failed_card_roots,failed_card_warnings;
static char failed_card_selection[16],failed_card_message[96];
static void openDir(const char *path,const char *selected) {
 assert(!path[0]);failed_card_roots++;snprintf(failed_card_selection,sizeof(failed_card_selection),"%s",selected);
}
static void dashToast(int kind,const char *message) {assert(kind==DASH_TOAST_WARN&&message);snprintf(failed_card_message,sizeof(failed_card_message),"%s",message);failed_card_warnings++;}
"""
code += "static float dashGfxViewportHeight(void) { return 448.0f; }\n"
for macro in ("DASH_FOOTER_INSET", "DASH_FOOTER_Y", "DASH_PANE_B", "DASH_PANE_STATUS_H", "DASH_LIST_ROW_H"):
    code += re.search(r"^#define " + macro + r" .+$", (root / "include/dash_internal.h").read_text(), re.M).group() + "\n"
code += re.search(r"^#define FB_ROWS .+$", browser, re.M).group() + "\n"
code += (root / "include/list_scroll.h").read_text() + "\n"
job_start = browser.index("typedef struct", browser.index("// Listing"))
code += browser[job_start:browser.index("} FbListJob;", job_start) + len("} FbListJob;")] + "\n"
code += function(browser, "static int fbShowsTitles(") + "\n"
code += function(browser, "static int isPartitionList(") + "\n"
code += function(browser, "static int wrapIndex(") + "\n"
code += function(browser, "static int pageIndex(") + "\n"
code += function(browser, "static void revealSelection(") + "\n"
code += function(browser, "static void selectName(") + "\n"
code += function(browser, "static void listDone(") + "\n"
code += function(browser, "static void parentOf(") + "\n"
code += function(apps, "static void move(") + "\n"
code += r"""
#define DASH_FS_SMALL 12
#define DASH_SAFE_L 40
#define DASH_SAFE_R 600
static int row, nhome, nchips;
static float col_anim[2], cam[2], chip_cam;
static struct { char label[48]; } chips[24];
static float dashTextWidth(const char *label, int size) {(void)label;(void)size;return 140;}
"""
code += function(home, "static float homeChipScrollTarget(") + "\n"
code += function(home, "static void snapHomeColumn(") + "\n"

code += "static void browserMove(const DashInput *in, int total) {\n" + browser_move + "\nrevealSelection();}\n"
pick_start = widgets.index("\t\tif ((in.pressed & DASH_IN_UP)", widgets.index("static int pickPath("))
pick_end = widgets.index("\n\t\tif (in.pressed & DASH_IN_MENU)", pick_start)
code += "#define DASH_SND_CURSOR 0\nstatic void dashSoundPlay(int s) { (void)s; }\n"
code += "static float picker_anim;\n"
code += "static int pickerMove(int sel, int n_rows, DashInput in) { const int rows=10; int wrapped=0; float sel_anim=picker_anim,top_anim=-1; (void)top_anim;\n" + widgets[pick_start:pick_end] + "\npicker_anim=sel_anim; return sel; }\n"
code += "static void gridMove(const DashInput *in) {\n" + grid_move + "\n}\n"
code += r"""
#define DASH_IN_OK 64
#define TA_HEADER 0
static const struct { int action; } tools[]={{0},{1},{0},{1},{1},{0},{1}};
#define NTOOLS 7
static int tsel=1;
static float tsel_anim=1,ttop_anim=-1;
"""
code += function(tools, "static int tMove(") + "\n"
code += function(tools, "static void tPage(") + "\n"
for source, name in ((tools, "tools"),):
    body = function(source, f"static void {name}Input(")
    code += f"static void {name}Navigate(const DashInput *in) {{\n"
    code += body[body.index("int wrapped"):body.index("\tif (in->pressed & DASH_IN_OK)")] + "}\n"
ip_start = widgets.index("\t\tif (in.pressed & DASH_IN_LEFT)", widgets.index("int dashModalIp("))
ip_end = widgets.index("\t\tif (in.pressed & DASH_IN_UP)", ip_start)
code += "static void ipMove(int *selected, float *animated, DashInput in) { int sel=*selected; float sel_anim=*animated;\n"
code += widgets[ip_start:ip_end] + "*selected=sel; *animated=sel_anim; }\n"
for macro in ("LIST_Y", "ROW_H", "ROWS"):
    code += re.search(r"^#define " + macro + r" .+$", hdd, re.M).group() + "\n"
code += "static struct { int n; } hm;\n"
hdd_start = hdd.index("\t\tif (hm.n > 0)", hdd.index("void dashHddManager("))
hdd_end = hdd.index("\t\tif (sel != prev)", hdd_start)
code += "static void hddNavigate(DashInput in) { int wrapped=0;\n" + hdd[hdd_start:hdd_end] + "}\n"
code += r"""
/* Independent viewport expectation: move the window by its capacity, then
 * focus its middle row, using an endpoint for the clipped final page. */
static int expectedPage(int selected,int count,int rows,int direction) {
 if(!count)return 0;
 if(direction<0 && selected==0)return count-1;
 if(direction>0 && selected==count-1)return 0;
 int maximum=count>rows?count-rows:0;
 int top=selected-(rows-1)/2;
 if(top<0)top=0;
 if(top>maximum)top=maximum;
 top+=direction*rows;
 if(top<=0)return 0;
 if(top>=maximum)return count-1;
 return top+(rows-1)/2;
}
static void checkParentCompletion(void) {
 static FILEINFO files[MAX_ENTRY];static unsigned char marks[MAX_ENTRY];
 const int counts[]={0,1,2,6,11,12,13,127};
 const char *roots[]={"mc0:/","usb0:/"};
 for(unsigned storage=0;storage<sizeof(roots)/sizeof(roots[0]);storage++)
 for(unsigned c=0;c<sizeof(counts)/sizeof(counts[0]);c++)
 for(int target=0;target<(counts[c]?counts[c]:1);target++) {
  char child[MAX_PATH],parent[MAX_PATH],name[MAX_NAME];int n=counts[c];
  snprintf(child,sizeof(child),"%sAPPS/Folder%03d/",roots[storage],target);
  parentOf(child,parent,sizeof(parent),name,sizeof(name));
  memset(&fb,0,sizeof(fb));fb.files=files;fb.mark=marks;fb.gen=17;fb.loading=1;
  strcpy(fb.dir,parent);strcpy(fb.want_sel,name);
  /* Back has returned to the parent, but its delayed read is not done yet.
   * No browser input runs between submission and this completion. */
  assert(fb.sel==0 && fb.top==0 && fb.sel_anim==0 && fb.n==0);
  FbListJob *j=calloc(1,sizeof(*j));assert(j);
  j->files=calloc(MAX_ENTRY,sizeof(*j->files));assert(j->files);
  j->gen=fb.gen;j->n=n+3;j->quiet_input=storage==1;
  j->free_valid=1;j->free_bytes=123456;strcpy(j->path,parent);
  j->card_type=storage?0:(c%2?1:2);j->ps1_free=j->card_type==1?7:-1;
  int card_type=j->card_type,ps1_free=j->ps1_free;
  fb.card_type=1;fb.ps1_free=13; /* A completed listing replaces old media metadata. */
  strcpy(j->files[0].name,".");strcpy(j->files[1].name,"..");
  for(int i=0;i<n;i++)snprintf(j->files[i+3].name,MAX_NAME,"Folder%03d",n-i-1);
  browser_usb_jobs=j->quiet_input;browser_usb_input_rearm=0;
  listDone(j);
  int expected=n?target:0,top=expected-(FB_ROWS-1)/2,max_top=n>FB_ROWS?n-FB_ROWS:0;
  if(top<0)top=0;
  if(top>max_top)top=max_top;
  assert(!fb.loading && fb.n==n && fb.sel==expected && fb.top==top);
  assert(fb.sel_anim==(float)expected && !fb.want_sel[0]);
  assert(fb.sel>=fb.top && fb.sel<fb.top+FB_ROWS);
  if(n)assert(!strcmp(fb.files[fb.sel].name,name));
  assert(fb.free_valid && fb.free_bytes==123456);
  assert(fb.card_type==card_type && fb.ps1_free==ps1_free);
  assert(file_sort==1 && file_show==fb_show && !fb.nmarked);
  assert(!browser_usb_jobs && browser_usb_input_rearm==(storage==1));
 }
 /* A late result from a previous folder must not move the current view. */
 for(int abandoned=0;abandoned<=1;abandoned++) {
  FbListJob *j=calloc(1,sizeof(*j));assert(j);j->files=calloc(1,sizeof(*j->files));assert(j->files);
  j->gen=fb.gen-!abandoned;j->abandoned=abandoned;j->n=1;
  int sel=fb.sel,top=fb.top,card_type=fb.card_type,ps1_free=fb.ps1_free;float anim=fb.sel_anim;
  listDone(j);assert(fb.sel==sel && fb.top==top && fb.sel_anim==anim);
  const char *card_roots[]={"mc0:/","mc1:/","mmce0:/","mmce1:/"};
  for(int port=0;port<4;port++) {
   FbListJob *failed=calloc(1,sizeof(*failed));assert(failed);
   failed->files=calloc(1,sizeof(*failed->files));assert(failed->files);
   failed->gen=fb.gen;failed->n=-12;snprintf(failed->path,sizeof(failed->path),"%s",card_roots[port]);
   int before=failed_card_roots;listDone(failed);
   assert(failed_card_roots==before+1&&failed_card_warnings==failed_card_roots);
   assert(!strcmp(failed_card_selection,card_roots[port]));
   assert(strstr(failed_card_message,"error -12"));
  }
  assert(fb.card_type==card_type && fb.ps1_free==ps1_free);
 }
 memset(&fb,0,sizeof(fb));
 puts("PASS: delayed MC/USB Back completions restore folder, centered viewport and highlight without another input; stale results stay ignored");
}
int main(void) {
 checkParentCompletion();
 DashInput up={DASH_IN_UP}, down={DASH_IN_DOWN};
 const int counts[]={0,1,2,5,7,12,13,127};
 for(unsigned i=0;i<sizeof(counts)/sizeof(counts[0]);i++) {
  int n=counts[i]; fb.dir[0]=1; fb.n=n; fb.sel=fb.top=0; fb.sel_anim=0;
  browserMove(&up,n); assert(fb.sel==(n?n-1:0));
  assert(fb.sel_anim==fb.sel); /* wrap must snap even in short lists */
  assert(fb.sel>=fb.top && fb.sel<fb.top+FB_ROWS);
  assert(fb.sel_anim>=fb.top && fb.sel_anim<fb.top+FB_ROWS);
  fb.sel_anim=(float)fb.sel;
  browserMove(&down,n); assert(fb.sel==0 && fb.top==0);
  assert(fb.sel_anim==0);
  assert(fb.sel_anim>=fb.top && fb.sel_anim<fb.top+FB_ROWS);
 }
 for(int n=0;n<=127;n++) {
  DashInput left={DASH_IN_LEFT}, right={DASH_IN_RIGHT};
  for(int i=0;i<n;i++) {
   /* Each controller uses its rendered row capacity. */
   picker_anim=i;
   assert(pickerMove(i,n,left)==expectedPage(i,n,10,-1));
   if(i==0)assert(picker_anim==n-1);
   picker_anim=i;
   assert(pickerMove(i,n,right)==expectedPage(i,n,10,1));
   if(i==n-1)assert(picker_anim==0);
   picker_anim=i;
   assert(pickerMove(i,n,up)==(i?i-1:n-1));
   assert(picker_anim==(i?i:n-1));
   picker_anim=i;
   assert(pickerMove(i,n,down)==(i<n-1?i+1:0));
   assert(picker_anim==(i<n-1?i:0));
  }
  if(n>0) {
   fb.dir[0]=1;fb.n=n;fb.sel=0;fb.sel_anim=0;
   browserMove(&left,n);assert(fb.sel==n-1 && fb.sel_anim==n-1);
   browserMove(&right,n);assert(fb.sel==0 && fb.sel_anim==0);
  }
  for(int i=0;i<n;i++) {
   int left=pageIndex(i,n,-1), right=pageIndex(i,n,1);
   assert(left==expectedPage(i,n,FB_ROWS,-1));
   assert(right==expectedPage(i,n,FB_ROWS,1));
  }
  fb.dir[0]=0;fb.n=127;fb.ndevs=n;fb.sel=n?n-1:0;fb.sel_anim=fb.sel;
  revealSelection();assert(fb.top==(n>FB_ROWS?n-FB_ROWS:0));
 }
 fb.dir[0]=1;fb.n=127;fb.sel=5;fb.top=0;fb.sel_anim=5;
 browserMove(&down,127);assert(fb.sel==6 && fb.sel_anim==5); /* retain adjacent easing */
 /* Header-skipping lists snap in both directions; ordinary steps keep easing. */
 tsel=1;tsel_anim=1;assert(tMove(-1) && tsel==6 && tsel_anim==6);
 assert(tMove(1) && tsel==1 && tsel_anim==1);
 assert(!tMove(1) && tsel==3 && tsel_anim==1);
 /* A page wraps to the first actionable row, skipping headers. */
 DashInput page={DASH_IN_R2};
 tsel=6;tsel_anim=6;toolsNavigate(&page);assert(tsel==1 && tsel_anim==1 && ttop_anim<0);
 int octet=0;float octet_anim=0;
 DashInput left={DASH_IN_LEFT},right={DASH_IN_RIGHT};
 ipMove(&octet,&octet_anim,left);assert(octet==3 && octet_anim==3);
 ipMove(&octet,&octet_anim,right);assert(octet==0 && octet_anim==0);
 ipMove(&octet,&octet_anim,right);assert(octet==1 && octet_anim==0);
 for(int n=1;n<=31;n++) {
  hm.n=n;sel=0;sel_anim=0;hddNavigate(up);assert(sel==n-1 && sel_anim==sel);
  hddNavigate(down);assert(sel==0 && sel_anim==0);
  if(n>1) {hddNavigate(down);assert(sel==1 && sel_anim==0);}
 }
 /* HDD Manager pages its visible partitions with D-pad Left/Right only. */
 for(int n=0;n<=31;n++) {
  hm.n=n;
  for(int i=0;i<(n?n:1);i++) {
   sel=i;sel_anim=i;hddNavigate(left);
   assert(sel==expectedPage(i,n,ROWS,-1));
   assert(sel_anim==(n && i==0?sel:i));
   sel=i;sel_anim=i;hddNavigate(right);
   assert(sel==expectedPage(i,n,ROWS,1));
   assert(sel_anim==(n && i==n-1?sel:i));
   sel=i;sel_anim=i;page.pressed=DASH_IN_L2|DASH_IN_R2;
   hddNavigate(page);assert(sel==i && sel_anim==i);
  }
 }
 hm.n=31;sel=3;sel_anim=3;
 hddNavigate(left);assert(sel==0);
 hddNavigate(left);assert(sel==30 && sel_anim==30);
 sel=28;sel_anim=28;
 hddNavigate(right);assert(sel==30);
 hddNavigate(right);assert(sel==0 && sel_anim==0);
 for(norder=1;norder<=17;norder++) {
  sel=0;sel_anim=grid_cam=0;gridMove(&up);assert(sel==norder-1 && sel_anim==sel);
  gridMove(&down);assert(sel==0 && sel_anim==0 && grid_cam==0);
  for(int old=0;old<norder;old++) {
   sel=old;gridMove(&up);assert(sel>=0 && sel<norder);
   if(old>=GRID_COLS)assert(sel==old-GRID_COLS);
   sel=old;gridMove(&down);assert(sel>=0 && sel<norder);
   if(old+GRID_COLS<norder)assert(sel==old+GRID_COLS);
  }
 }
 /* Two applications have an ordinary adjacent move as well as a wrap. */
 norder=2;sel=0;sel_anim=0;move(1);assert(sel==1 && sel_anim==0);
 sel_anim=1;move(-1);assert(sel==0 && sel_anim==1);
 move(-1);assert(sel==1 && sel_anim==1);
 move(1);assert(sel==0 && sel_anim==0);
 /* Page wrapping may cross the boundary from the middle of a grid. */
 norder=40;sel=3;sel_anim=3;move(-15);assert(sel==28 && sel_anim==28 && grid_cam>0);
 sel=37;sel_anim=37;move(15);assert(sel==12 && sel_anim==12 && grid_cam>0);
 row=1;nchips=12;chip_cam=0;snapHomeColumn(11);
 assert(chip_cam==homeChipScrollTarget(11) && chip_cam>0 && col_anim[1]==11);
 snapHomeColumn(0);assert(chip_cam==0 && col_anim[1]==0);
 row=0;nhome=12;cam[0]=0;snapHomeColumn(11);assert(cam[0]>0 && col_anim[0]==11);
 snapHomeColumn(0);assert(cam[0]==0 && col_anim[0]==0);
 return 0;
}
"""
cc = shutil.which("gcc") or shutil.which("cc")
assert cc, "A host C compiler is required"
with tempfile.TemporaryDirectory(prefix="navigation-wrap-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    binary = path / "test.exe"
    subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", str(path / "test.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: immediate wrap highlights in browsers, header/device lists, picker, IP editor and application views; adjacent easing retained")
