"""Navigation wrap-around contracts for dashboard list controllers (#189)."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]


def src(name):
    return (root / "src" / name).read_text(encoding="utf-8")


browser = src("dash_browser.c")
apps = src("dash_apps.c")
files = src("dash_files.c")
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
assert "move(sel == 0 ? norder - 1" in apps
assert "move(sel == norder - 1 ? -sel" in apps

# Files list and Devices grid: movement wraps and keeps skipping non-selectable rows.
assert "if (s < 0)\n\t\t\ts = nfentries - 1;" in files
assert "else if (s >= nfentries)\n\t\t\ts = 0;" in files
assert "while (s < 0)\n\t\t\ts += ndevs;" in files
assert "while (s >= ndevs)\n\t\t\ts -= ndevs;" in files

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
#define FB_ROWS 10
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
 int sel,top,n,ndevs,nmarked,loading,gen,free_valid;
 char dir[MAX_PATH],want_sel[MAX_NAME];float sel_anim;
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
static float sel_anim, grid_cam;
static void dashUiFocusPoke(void) {}
"""
code = re.sub(r"^#define FB_ROWS \d+$", re.search(r"^#define FB_ROWS \d+$", browser, re.M).group(0), code, flags=re.M)
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
pick_start = widgets.index("\t\tif ((in.pressed & DASH_IN_UP)", widgets.index("int dashPickPath("))
pick_end = widgets.index("\n\t\tif (in.pressed & DASH_IN_MENU)", pick_start)
code += "#define DASH_SND_CURSOR 0\nstatic void dashSoundPlay(int s) { (void)s; }\n"
code += "static int pickerMove(int sel, int n_rows, DashInput in) { const int rows=10;\n" + widgets[pick_start:pick_end] + "\nreturn sel; }\n"
code += "static void gridMove(const DashInput *in) {\n" + grid_move + "\n}\n"
code += r"""
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
  assert(file_sort==1 && file_show==fb_show && !fb.nmarked);
  assert(!browser_usb_jobs && browser_usb_input_rearm==(storage==1));
 }
 /* A late result from a previous folder must not move the current view. */
 for(int abandoned=0;abandoned<=1;abandoned++) {
  FbListJob *j=calloc(1,sizeof(*j));assert(j);j->files=calloc(1,sizeof(*j->files));assert(j->files);
  j->gen=fb.gen-!abandoned;j->abandoned=abandoned;j->n=1;
  int sel=fb.sel,top=fb.top;float anim=fb.sel_anim;
  listDone(j);assert(fb.sel==sel && fb.top==top && fb.sel_anim==anim);
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
  assert(fb.sel>=fb.top && fb.sel<fb.top+FB_ROWS);
  assert(fb.sel_anim>=fb.top && fb.sel_anim<fb.top+FB_ROWS);
  fb.sel_anim=(float)fb.sel;
  browserMove(&down,n); assert(fb.sel==0 && fb.top==0);
  assert(fb.sel_anim>=fb.top && fb.sel_anim<fb.top+FB_ROWS);
 }
 for(int n=0;n<=127;n++) {
  DashInput left={DASH_IN_LEFT}, right={DASH_IN_RIGHT};
  for(int i=0;i<n;i++) {
   /* The separate path picker still pages ten rows; Files now pages eleven. */
   assert(pickerMove(i,n,left)==(i==0?n-1:(i<10?0:i-10)));
   assert(pickerMove(i,n,right)==(i==n-1?0:(i+10>=n?n-1:i+10)));
   assert(pickerMove(i,n,up)==(i?i-1:n-1));
   assert(pickerMove(i,n,down)==(i<n-1?i+1:0));
  }
  for(int i=0;i<n;i++) {
   int left=pageIndex(i,n,-1), right=pageIndex(i,n,1);
   assert(left==(i==0?n-1:(i<FB_ROWS?0:i-FB_ROWS)));
   assert(right==(i==n-1?0:(i+FB_ROWS>=n?n-1:i+FB_ROWS)));
  }
  fb.dir[0]=0;fb.n=127;fb.ndevs=n;fb.sel=n?n-1:0;fb.sel_anim=fb.sel;
  revealSelection();assert(fb.top==(n>FB_ROWS?n-FB_ROWS:0));
 }
 fb.dir[0]=1;fb.n=127;fb.sel=5;fb.top=0;fb.sel_anim=5;
 browserMove(&down,127);assert(fb.sel==6 && fb.sel_anim==5); /* retain adjacent easing */
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
print("PASS: production browser endpoint/viewport transitions and incomplete application grids")
