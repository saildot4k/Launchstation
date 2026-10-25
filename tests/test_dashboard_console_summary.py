"""Read console identity once at startup; render cached model/region/ROM/DVD text."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
info = (root / "src/dash_info.c").read_text()
main = (root / "src/dash_main.c").read_text()
console = (root / "src/main_console_info.c").read_text()


def function(source, signature):
    start = source.index(signature)
    pos = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos] + "\n"


summary = function(info, "void dashConsoleSummaryText(")
for forbidden in ("GetConsoleModelName(", "GetConsoleDvdVersion(", "getROMVersion(",
                  "Sif", "fileXio", "load", "DelayThread", "uLE_InitializeRegion(", "rough_region"):
    assert forbidden not in summary, forbidden
startup = function(main, "static void firstInit(")
assert startup.index("dashConsoleIdentityInit();") < startup.index("dashWorkerInit();")
sheet = function(info, "void dashShowSystemInfo(")
assert "dashWorkerAwaitAll(" in sheet and "job = cached_console_info;" in sheet
for forbidden in ("GetConsoleModelName(", "GetConsoleDvdVersion(", "getROMVersion("):
    assert forbidden not in sheet
for source in ("src/dash_home.c", "src/dash_files.c"):
    assert "dashConsoleSummaryText(console, sizeof(console));" in (root / source).read_text()

code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define CONSOLE_MODEL_NAME_MAX_LEN 24
#define FIO_O_RDONLY 1
static char ROMVER_data[16];
static const char *rom_data="0220EC20060210", *model_data="SCPH-37301", *dvd_data="0120E";
static int model_queries,dvd_queries,rom_queries,region_queries,dvd_missing;
static void GetConsoleModelName(const char *rom,char *out,size_t size) {
    assert(!strcmp(rom,rom_data));model_queries++;snprintf(out,size,"%s",model_data);
}
static void initialize_console_rom1_driver(void) { dvd_queries++; }
static int get_console_dvd_player_region(char *out) { (void)out;return 0; }
static int genOpen(const char *path,int flags) { assert(!strcmp(path,"rom1:DVDVER") && flags==FIO_O_RDONLY);return dvd_missing?-1:0; }
static int genRead(int fd,char *out,int size) { assert(fd==0 && size>(int)strlen(dvd_data));memcpy(out,dvd_data,strlen(dvd_data));return strlen(dvd_data); }
static void genClose(int fd) { assert(fd==0); }
static unsigned short getROMVersion(void) { rom_queries++;return 0x220; }
static void uLE_InitializeRegion(void) { region_queries++;snprintf(ROMVER_data,sizeof(ROMVER_data),"%s",rom_data); }
'''
code += function(console, "void GetConsoleDvdVersion(")
code += function(info, "static const char *consoleRegionName(")
end = info.index("} SysInfo;") + len("} SysInfo;")
code += info[info.rfind("typedef struct", 0, end):end] + "\n"
start = info.index("static SysInfo cached_console_info;")
code += info[start:info.index("void dashConsoleIdentityInit(", start)]
code += function(info, "void dashConsoleIdentityInit(")
code += summary
code += r'''
int main(void) {
    char text[160],tiny[5];
    dashConsoleSummaryText(text,sizeof(text));
    assert(!model_queries && !dvd_queries && !rom_queries && !region_queries);
    assert(strstr(text,"Unknown model") && strstr(text,"ROM: unavailable") && strstr(text,"DVD: unavailable"));
    dashConsoleIdentityInit();dashConsoleIdentityInit();
    assert(model_queries==1 && dvd_queries==1 && rom_queries==1 && region_queries==1);
    for(int frame=0;frame<1000;frame++) {
        dashConsoleSummaryText(text,sizeof(text));
        assert(!strcmp(text,"SCPH-37301 | Europe / Oceania (PAL) | ROM: 2.20E | DVD: 1.20E"));
    }
    assert(model_queries==1 && dvd_queries==1 && rom_queries==1 && region_queries==1);
    memset(tiny,'!',sizeof(tiny));dashConsoleSummaryText(tiny,sizeof(tiny));assert(tiny[4]==0);
    dashConsoleSummaryText(NULL,0);dashConsoleSummaryText(tiny,0);
    /* Reading cached labels must keep ROM and region independent of model strings. */
    strcpy(ROMVER_data,"0220JC20060210");dashConsoleSummaryText(text,sizeof(text));
    assert(strstr(text,"Japan (NTSC-J) | ROM: 2.20J"));
    strcpy(ROMVER_data,"0200HC20040614");dashConsoleSummaryText(text,sizeof(text));
    assert(strstr(text,"Asia (NTSC-J) | ROM: 2.00H"));
    const char *inputs[]={"0120E","1.20E","0304J\r\n","3.04J\n","custom"};
    const char *expected[]={"DVD: 1.20E","DVD: 1.20E","DVD: 3.04J","DVD: 3.04J","DVD: custom"};
    for(unsigned i=0;i<sizeof(inputs)/sizeof(inputs[0]);i++) {
        dvd_data=inputs[i];GetConsoleDvdVersion(text,sizeof(text));assert(!strcmp(text,expected[i]));
    }
    dvd_missing=1;GetConsoleDvdVersion(text,sizeof(text));assert(!strcmp(text,"DVD: <unavailable>"));
    puts("PASS: startup-only hardware identity reads, cached Home subtitle, real regions, compact ROM/DVD versions and missing-data handling");
}
'''
with tempfile.TemporaryDirectory(prefix="launchstation-console-summary-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    cc = shutil.which("gcc") or shutil.which("clang")
    assert cc, "Host compiler required"
    subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], check=True, timeout=10)
