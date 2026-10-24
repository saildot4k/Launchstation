"""Execute R3Z 4.80 ELF target/argv handling in exFAT and classic builds."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/elf.c").read_text()


def function(signature, source=source):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r"""
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define MAX_PATH 1025
#define ELFLOAD_MAX_ARGC 15
#define ELFLOAD_BASE_ARGC 3
#define FIO_MT_RDONLY 1
#define FIO_MT_RDWR 2
#define WLE_PFS_WRITETHROUGH 4
#define DPRINTF(...) ((void)0)
static char target[MAX_PATH], child_arg0[MAX_PATH], mode[32];
static int loader_calls;
static int isPcCardCfPath(const char *p) { return p && !strncmp(p,"cf",2); }
static int shutdownPcCardCf(void) { return 0; }
static int fileXioMount(const char *a,const char *b,int flags) {
 (void)a;(void)b;(void)flags;return 0;
}
static void unmountParty(int p) {(void)p;}
static int LaunchArgsPending(void) {return 0;}
static int LaunchArgsCopyToArgv(char **args,int n) {(void)args;(void)n;return 0;}
static void LaunchArgsClear(void) {}
static void RunEmbeddedLoader(int argc,char **argv) {
 assert(argc==3);loader_calls++;
 snprintf(target,sizeof(target),"%s",argv[0]);
 snprintf(child_arg0,sizeof(child_arg0),"%s",argv[1]);
 snprintf(mode,sizeof(mode),"%s",argv[2]);
}
"""
for sig in ("static int parseUsbMassPathUnit(", "static int isHddPartyPath(",
            "static int isHddBrowserPath(", "static int isExplicitHddHandoffPath(",
            "static const char *normalizeExecArg0Path(", "static void RunLoaderElfInternal(",
            "void RunLoaderElf(", "void RunLoaderElfKeepIOPWithArgv0("):
    code += function(sig)
browser = (root / "src/filer_browser.c").read_text()
code += function("int filerFormatUsbPathForDisplay(", browser)
code += function("static void formatBrowserPathForDisplay(", browser)
native = (root / "src/dash_browser.c").read_text()
start = native.index("\tif (!filerFormatUsbPathForDisplay(", native.index("static void browserDrawBody("))
end = native.index("\n\n", start)
code += "static void dashStrCopy(char *out,const char *in,int cap) { snprintf(out,cap,\"%s\",in); }\n"
code += "static void nativeDisplay(const char *path,char *out) { struct { const char *dir; } fb={path};char display_path[MAX_PATH+2];\n"
code += native[start:end] + "\ndashStrCopy(out,display_path,MAX_PATH); }\n"
code += r"""
static void expect(const char *selected,const char *wanted) {
 char load_path[MAX_PATH];snprintf(load_path,sizeof(load_path),"%s",selected);
 for(int reboot=0;reboot<2;reboot++) {
  int calls=loader_calls;
  RunLoaderElf(load_path,"",selected,1,reboot);
  assert(loader_calls==calls+1 && !strcmp(child_arg0,wanted));
  assert(!strcmp(target,!strncmp(wanted,"mass",4)?wanted:selected));
  assert(!strcmp(mode,reboot?"-la=AR":"-la=A"));
 }
}
int main(void) {
 char display[MAX_PATH];
 const char *aliases[]={"mass:","mass:/", "usb:","usb:/"};
 for(unsigned i=0;i<sizeof(aliases)/sizeof(aliases[0]);i++) {
  char original[MAX_PATH];snprintf(original,sizeof(original),"%s",aliases[i]);
  nativeDisplay(original,display);assert(!strcmp(display,"usb0:/") && !strcmp(original,aliases[i]));
  formatBrowserPathForDisplay(original,display);assert(!strcmp(display,"usb0:/"));
 }
 for(int unit=0;unit<10;unit++) for(int slash=0;slash<2;slash++) {
  char expected[MAX_PATH],path[MAX_PATH],original[MAX_PATH];
  snprintf(expected,sizeof(expected),"usb%d:/Folder name/APP.ELF",unit);
  for(int mass=0;mass<2;mass++) {
   snprintf(path,sizeof(path),"%s%d:%sFolder name/APP.ELF",mass?"mass":"usb",unit,slash?"/":"");
   strcpy(original,path);nativeDisplay(path,display);
   assert(!strcmp(display,expected) && !strcmp(path,original));
   formatBrowserPathForDisplay(path,display);assert(!strcmp(display,expected));
  }
 }
 const char *others[]={"", "ata0:/GAMES/", "ata1:/", "mx4sio:/APPS/", "mmce0:/", "mc1:/BOOT/", "massBackup:/", "usb10:/"};
 for(unsigned i=0;i<sizeof(others)/sizeof(others[0]);i++) {
  nativeDisplay(others[i],display);assert(!strcmp(display,others[i]));
 }
 char short_display[4];
 assert(filerFormatUsbPathForDisplay("mass9:/APPS/",short_display,sizeof(short_display)) && !strcmp(short_display,"usb"));
 formatBrowserPathForDisplay("usb1:/APPS/APP.ELF",display);assert(!strcmp(display,"usb1:/APPS/APP.ELF"));
 formatBrowserPathForDisplay("mass:/APPS/APP.ELF",display);assert(!strcmp(display,"usb0:/APPS/APP.ELF"));
 formatBrowserPathForDisplay("mass3:/APPS/APP.ELF",display);assert(!strcmp(display,"usb3:/APPS/APP.ELF"));
 formatBrowserPathForDisplay("ata1:/APP.ELF",display);assert(!strcmp(display,"ata1:/APP.ELF"));
 expect("usb:/APP.ELF","mass0:/APP.ELF");
 expect("usb0:APP.ELF","mass0:/APP.ELF");
 expect("usb1:/APP.ELF","mass1:/APP.ELF");
 expect("mass:/APP.ELF","mass0:/APP.ELF");
 expect("mass0:APP.ELF","mass0:/APP.ELF");
 expect("mass9:/APP.ELF","mass9:/APP.ELF");
 expect("ata0:/APP.ELF","ata0:/APP.ELF");
 expect("ata1:/APP.ELF","ata1:/APP.ELF");
 expect("mx4sio:/APP.ELF","mx4sio:/APP.ELF");
 expect("mx4sio0:/APP.ELF","mx4sio0:/APP.ELF");
 expect("mc0:/BOOT/APP.ELF","mc0:/BOOT/APP.ELF");
 expect("mmce1:/APP.ELF","mmce1:/APP.ELF");
 RunLoaderElf("pfs0:/APP.ELF","hdd1:+APPS","hdd1:/+APPS/APP.ELF",1,1);
 assert(!strcmp(target,"pfs0:/APP.ELF"));
 assert(!strcmp(child_arg0,"hdd1:+APPS:pfs:/APP.ELF") && !strcmp(mode,"-la=ARH"));
 RunLoaderElf("usb0:/APP.KELF","","usb:/APP.KELF",2,0);
 assert(!strcmp(target,"usb0:/APP.KELF") && !strcmp(child_arg0,"mass0:/APP.KELF"));
 RunLoaderElfKeepIOPWithArgv0("usb1:/ember.elf","","usb1:/ember.elf",1);
 assert(!strcmp(child_arg0,"usb1:/ember.elf") && !strcmp(mode,"-la=A"));
 return 0;
}
"""
config = (root / "src/config.c").read_text()
settings = (root / "src/dash_settings.c").read_text()
assert "Modern_Device_Handoff" not in config
assert "modern_device_handoff" not in config + settings
assert "S_MODERN_HANDOFF" not in settings
assert "ElfBdmIdentity" not in source and "PrepareElfHandoffPath" not in source
assert "RunLoaderElf(fullpath, party, path, t, x);" in (root / "src/main_actions.c").read_text()
cc = shutil.which("gcc") or shutil.which("cc")
assert cc, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="device-handoff-") as folder:
    path = Path(folder)
    c = path / "test.c"
    c.write_text(code)
    for exfat in (False, True):
        exe = path / ("exfat.exe" if exfat else "classic.exe")
        subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror", *(["-DEXFAT"] if exfat else []), str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
print("PASS: fixed R3Z 4.80 loader targets, child argv[0], USB display and preserved Ember override")
