"""Exercise real settings serialization and file readback, including removed keys."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_store.c").read_text()
header = (root / "include/dash_internal.h").read_text()


def function(signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <fcntl.h>
#include <unistd.h>
typedef unsigned char u8;
#define MAX_PATH 1024
#define FIO_O_CREAT O_CREAT
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_TRUNC O_TRUNC
#define FIO_O_RDONLY O_RDONLY
#define DASH_PATH_MAX 256
#define DASH_MAX_SCAN 12
#define DASH_MAX_RECENT 16
#define DASH_SEC_COUNT 5
#define DASH_SEC_HOME 0
#define DASH_VIEW_COUNT 4
#define DASH_VIEW_GRID 0
'''
end = header.index("} DashSettings;") + len("} DashSettings;")
code += header[header.rfind("typedef struct", 0, end):end]
code += r'''
static DashSettings dashCfg, persisted;
#define SAVE_SETTINGS 0
static int save_dirty[1];
typedef int (*DashKvCallback)(const char *, char *, void *);
#define stricmp case_compare
static int stricmp(const char *a, const char *b) {
    while (*a && tolower((unsigned char)*a)==tolower((unsigned char)*b)) { a++; b++; }
    return tolower((unsigned char)*a)-tolower((unsigned char)*b);
}
static int dashThemeStoreWrite(char *out,int cap) { (void)out; (void)cap; return 0; }
static int dashThemeStoreKey(const char *key,char *value) { (void)key; (void)value; return 0; }
static int corrupt,fail_write_close,fail_read_close,short_write,read_error,opens,open_error;
static int genFixPath(const char *p,char *out){strcpy(out,p);return 0;}
static void configEnsureSysconfDir(const char *p){(void)p;}
static int genOpen(const char *p,int flags){opens++;return opens==open_error?-1:open(p,flags,0600);}
static int genClose(int fd){int r=close(fd);return (opens==1&&fail_write_close)||(opens==2&&fail_read_close)?-1:r;}
static int genWrite(int fd,void *data,int n){return write(fd,data,short_write?n-1:n);}
static int genRead(int fd,void *data,int n){
    if(read_error)return -1;
    int r=read(fd,data,n>7?7:n);if(corrupt&&r>0)((char*)data)[0]^=1;return r;
}
'''
for signature in (
    "void dashStrCopy(", "char *dashTrim(", "int dashKvParse(",
    "static int clampInt(", "static int percentSetting(", "static int settingsKv(",
    "char *dashStoreSettingsText(", "int dashStoreSaveSettings(", "int dashWriteFile(",
):
    code += function(signature)
code += r'''
int main(void) {
    /* Old settings are ignored; saving removes them and keeps supported values. */
    for (int mask=0; mask<128; mask++) {
        char config_text[512]; int scan_reset=0,length;
        snprintf(config_text,sizeof(config_text),
                 "Dash_DevAuto = %d\nDash_ShowUnavailableDevices = %d\n"
                 "Dash_IGRCloudSync = 1\nDash_IGRAutoBackup = %d\n"
                 "Dash_IGRAfter = 2\nDash_IGRAfterPath = mc0:/BOOT/REMOVED.ELF\n"
                 "Dash_MMCEBackupKeep = 25\nDash_MMCEBackupFormat = 1\n"
                 "%s = usb0:/Backups\n"
                 "Dash_SoftwareClock = 2028-02-29 23:59:59\nDash_Sound = 1\nDash_SoundVolume = 67\n",
                 mask,mask & 1,mask & 1,
                 (mask & 2) ? "Dash_MMCEBackupPath" : "Dash_IGRBackupPath");
        memset(&dashCfg,0,sizeof(dashCfg));
        assert(dashKvParse(config_text,settingsKv,&scan_reset)>0 && dashCfg.sound==1 && dashCfg.sound_vol==67);
        dashCfg.temp_fahrenheit=mask&1;
        assert(!dashStoreSaveSettings() && save_dirty[SAVE_SETTINGS]);
        assert(persisted.sound==1 && persisted.sound_vol==67 && persisted.temp_fahrenheit==(mask&1));
        char *text=dashStoreSettingsText(&persisted,&length);
        assert(text && length==(int)strlen(text));
        assert(!strstr(text,"Dash_DevAuto") && !strstr(text,"Dash_ShowUnavailableDevices"));
        assert(!strstr(text,"Dash_IGR") && !strstr(text,"REMOVED.ELF"));
        assert(!strstr(text,"Dash_MMCEBackup") && !strstr(text,"usb0:/Backups"));
        assert(!strstr(text,"Dash_SoftwareClock") && !strstr(text,"2028-02-29 23:59:59"));
        memset(&dashCfg,0,sizeof(dashCfg));
        assert(dashKvParse(text,settingsKv,&scan_reset)>0 && dashCfg.sound==1 && dashCfg.sound_vol==67);
        assert(dashCfg.temp_fahrenheit==(mask&1));
        free(text);
    }
    for(int units=-2;units<4;units++) {
        char text[80];int scan_reset=0;
        snprintf(text,sizeof(text),"Dash_TemperatureFahrenheit = %d\n",units);
        dashCfg.temp_fahrenheit=1;
        assert(dashKvParse(text,settingsKv,&scan_reset)==1);
        assert(dashCfg.temp_fahrenheit==(units==1));
    }
    const char data[]="Dash_Sound = 1\r\nDash_SoundVolume = 67\r\n";
    for(int scenario=0;scenario<8;scenario++) {
        opens=corrupt=short_write=read_error=fail_write_close=fail_read_close=open_error=0;
        if(scenario==1)corrupt=1;
        if(scenario==2)short_write=1;
        if(scenario==3)read_error=1;
        if(scenario==4)fail_write_close=1;
        if(scenario==5)fail_read_close=1;
        if(scenario==6)open_error=1;
        if(scenario==7)open_error=2;
        assert((dashWriteFile("DASHBOARD.CNF",data,sizeof(data)-1)==0)==(scenario==0));
    }
    puts("PASS: removed settings ignored/omitted, MMCE backup/IGR keys discarded, settings round trips and file failures");
}
'''
with tempfile.TemporaryDirectory(prefix="settings-persistence-") as folder:
    path = Path(folder)
    (path / "settings.c").write_text(code)
    exe = path / "settings"
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "settings.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], cwd=path, check=True, timeout=10)
