"""Exercise real settings serialization and file readback, including removed keys."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = Path(os.environ.get("DASH_STORE_SOURCE", root / "src/dash_store.c")).read_text()
header = (root / "include/dash_internal.h").read_text()


def function(signature):
    start = source.index(signature)
    if source.find(";", start, source.index("{", start)) >= 0:
        start = source.index(signature, start + len(signature))
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
#define DASH_MAX_FAV 48
#define DASH_MAX_APPS 512
#define DASH_VIEW_COUNT 4
#define DASH_VIEW_GRID 0
'''
code += header[header.index("enum DashSection"):header.index("enum DashView")]
end = header.index("} DashSettings;") + len("} DashSettings;")
code += header[header.rfind("typedef struct", 0, end):end]
end = header.index("} DashUserLists;") + len("} DashUserLists;")
code += header[header.rfind("typedef struct", 0, end):end]
code += r'''
static DashSettings dashCfg, persisted;
static DashUserLists dashLists;
static char *hidden_apps[DASH_MAX_APPS];
static int nhidden;
enum { SAVE_SETTINGS, SAVE_LISTS };
static int save_dirty[2];
static char LoadedConfigPath[MAX_PATH],LaunchElfDir[MAX_PATH],LaunchElfBootDir[MAX_PATH],store_dir[MAX_PATH];
static int store_initialized,store_loaded,boot_safe_mode;
static struct {char CNF_Path[MAX_PATH];} location_setting,*setting=&location_setting;
static struct {char path[MAX_PATH],text[256];} location_files[16];
static int location_count,location_reads;
static char location_requests[16][MAX_PATH];
static void dashThemeStoreBegin(void) {}
static void dashThemeStoreEnd(void) {}
static char *dashLoadTextFile(const char *path,int max_size,int *length){
    assert(location_reads<16);snprintf(location_requests[location_reads++],MAX_PATH,"%s",path);
    for(int i=0;i<location_count;i++)if(!strcmp(path,location_files[i].path)) {
        *length=(int)strlen(location_files[i].text);assert(*length<max_size);
        char *text=malloc((size_t)*length+1);assert(text);memcpy(text,location_files[i].text,(size_t)*length+1);return text;
    }
    return NULL;
}

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
fileops = (root / "src/filer_fileops.c").read_text()
start = fileops.index("int genCmpFileExt(")
end = fileops.index("\n}\n", start) + 3
code += fileops[start:end]
for signature in ("static int listFind(", "int dashStoreSaveLists(", "void dashStorePushRecent(",
                  "int dashStoreIsHidden(", "static int setHidden(", "int dashStoreSetHidden(",
                  "static int listsKv(", "static char *buildLists("):
    code += function(signature)

# Execute production folder selection and startup parsing, including conflicting locations.
for line in source.splitlines():
    if line.startswith("#define DASH_STORE_MAX_DIRS "):
        code += line + "\n"
start = source.index("static const char *const default_scan[]")
code += source[start:source.index("};", start)+2] + "\n"
for signature in ("static int isWritableDevice(", "static void dirOf(", "static void selectStoreDir(",
                  "static void addCandidateDir(", "static int candidateMcPort(",
                  "static int candidateDirs(", "const char *dashStoreDir(",
                  "int dashStoreBuildPath(", "void dashStoreDefaults(",
                  "void dashStoreInit(", "int dashStoreLoaded("):
    if signature in source:
        code += function(signature)
code += r'''
static void resetLocations(const char *loaded,const char *active,const char *boot){
    strcpy(LoadedConfigPath,loaded);strcpy(LaunchElfDir,active);strcpy(LaunchElfBootDir,boot);
    store_initialized=store_loaded=boot_safe_mode=location_count=location_reads=0;setting->CNF_Path[0]=0;
}
static void addLocationFile(const char *dir,const char *name,const char *text){
    assert(location_count<16);int i=location_count++;
    assert(snprintf(location_files[i].path,MAX_PATH,"%s%s",dir,name)<MAX_PATH);
    assert(strlen(text)<sizeof(location_files[i].text));strcpy(location_files[i].text,text);
}
static void addBundle(const char *dir,int volume){
    char text[128];snprintf(text,sizeof(text),"Dash_SoundVolume = %d\n",volume);
    addLocationFile(dir,"DASHBOARD.CNF",text);
    snprintf(text,sizeof(text),"Favorite = usb0:/APPS/V%d.ELF\n",volume);addLocationFile(dir,"DASHAPPS.CNF",text);
}
static void expectLocation(const char *dir,int volume,int loaded){
    dashStoreInit();assert(!strcmp(dashStoreDir(),dir)&&dashCfg.sound_vol==volume&&persisted.sound_vol==volume&&dashStoreLoaded()==loaded);
    /* Only one attempt for each startup dashboard file, always in the selected folder. */
    assert(location_reads==2);
    char requested[MAX_PATH];assert(snprintf(requested,sizeof(requested),"%sDASHBOARD.CNF",dir)<(int)sizeof(requested));
    assert(!strcmp(location_requests[0],requested));
    assert(snprintf(requested,sizeof(requested),"%sDASHAPPS.CNF",dir)<(int)sizeof(requested));
    assert(!strcmp(location_requests[1],requested));
    const char *files[]={"DASHBOARD.CNF","DASHAPPS.CNF","DASHLIB.CNF","NEUT-SLUS_123.45-A.CNF"};
    for(unsigned i=0;i<sizeof(files)/sizeof(files[0]);i++) {
        char path[MAX_PATH],expected[MAX_PATH];assert(!dashStoreBuildPath(path,sizeof(path),files[i]));
        assert(snprintf(expected,sizeof(expected),"%s%s",dir,files[i])<(int)sizeof(expected));assert(!strcmp(path,expected));
    }
}
'''
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
        dashCfg.start_section=mask%DASH_SEC_COUNT;
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
        assert(dashCfg.start_section==mask%DASH_SEC_COUNT);
        free(text);
    }
    for(int units=-2;units<4;units++) {
        char text[80];int scan_reset=0;
        snprintf(text,sizeof(text),"Dash_TemperatureFahrenheit = %d\n",units);
        dashCfg.temp_fahrenheit=1;
        assert(dashKvParse(text,settingsKv,&scan_reset)==1);
        assert(dashCfg.temp_fahrenheit==(units==1));
    }
    /* Launching a game must not mutate lists or schedule the shared save,
     * including an image manually favorited before this launch. */
    dashCfg.recent_count=8;
    dashLists.nfav=1;strcpy(dashLists.fav[0],"ata0:/DVD/Manhunt.iso");
    dashStorePushRecent("mc0:/BOOT/BOOT.ELF");
    assert(dashLists.nrecent==1 && save_dirty[SAVE_LISTS]);
    save_dirty[SAVE_LISTS]=0;
    DashUserLists before=dashLists;
    const char *games[]={
        "ata0:/DVD/Manhunt.iso", "ata1:/DVD/game.ISO", "usb0:/PS1/disc.bin",
        "mass1:/PS1/game.BiN", "mmce0:/Ember/games/Game/disc.cue",
        "mx4sio:/PS1/game.CUE", "udpfs:/POPS/Game.vcd", "mmce1:/POPS/Game.VCD"
    };
    for(unsigned i=0;i<sizeof(games)/sizeof(games[0]);i++) {
        dashStorePushRecent(games[i]);
        assert(!save_dirty[SAVE_LISTS] && !memcmp(&before,&dashLists,sizeof(before)));
    }
    dashCfg.recent_count=0;dashStorePushRecent("usb0:/APPS/APP.ELF");
    assert(!save_dirty[SAVE_LISTS] && !memcmp(&before,&dashLists,sizeof(before)));
    dashLists.nrecent=0;dashStorePushRecent("usb0:/APPS/APP.ELF");
    assert(!save_dirty[SAVE_LISTS] && !dashLists.nrecent);
    dashCfg.recent_count=8;dashStorePushRecent("usb0:/APPS/APP.ELF");
    assert(save_dirty[SAVE_LISTS] && dashLists.nrecent==1);
    assert(!strcmp(dashLists.recent[0],"usb0:/APPS/APP.ELF") && dashLists.nfav==1);
    /* Hidden state belongs to app preferences, so cache refreshes and
     * library replacement cannot erase it or change favorites/history. */
    save_dirty[SAVE_LISTS]=0;before=dashLists;
    assert(dashStoreSetHidden("mc0:/APPS/Hidden.ELF",1)==1 && save_dirty[SAVE_LISTS]);
    assert(dashStoreIsHidden("MC0:/APPS/HIDDEN.ELF"));
    save_dirty[SAVE_LISTS]=0;
    assert(!dashStoreSetHidden("mc0:/APPS/hidden.elf",1) && !save_dirty[SAVE_LISTS]);
    assert(!memcmp(&before,&dashLists,sizeof(before)));
    assert(dashStoreSetHidden(NULL,1)<0 && dashStoreSetHidden("",1)<0);
    int list_len;char *saved=buildLists(&list_len);
    assert(saved && list_len==(int)strlen(saved) && strstr(saved,"Hidden = mc0:/APPS/Hidden.ELF\r\n"));
    assert(dashStoreSetHidden("MC0:/APPS/HIDDEN.ELF",0)==1 && !nhidden);
    save_dirty[SAVE_LISTS]=0;memset(&dashLists,0,sizeof(dashLists));
    assert(dashKvParse(saved,listsKv,NULL)>0);free(saved);
    assert(dashStoreIsHidden("mc0:/APPS/hidden.elf") && !save_dirty[SAVE_LISTS]);
    assert(dashLists.nfav==before.nfav && dashLists.nrecent==before.nrecent);
    assert(!strcmp(dashLists.fav[0],before.fav[0]) && !strcmp(dashLists.recent[0],before.recent[0]));
    while(nhidden)assert(dashStoreSetHidden(hidden_apps[0],0)==1);
    /* Full capacity and maximum legal paths still serialize/read back under
     * the actual DASHAPPS.CNF load limit (the former 64 KiB was too small). */
    char path[DASH_PATH_MAX];
    for(int i=0;i<DASH_MAX_APPS;i++) {
        memset(path,'x',sizeof(path));memcpy(path,"mc0:/",5);
        snprintf(path+sizeof(path)-10,10,"%05d.ELF",i);
        assert(dashStoreSetHidden(path,1)==1);
    }
    assert(nhidden==DASH_MAX_APPS && dashStoreSetHidden("mc1:/ONE-TOO-MANY.ELF",1)<0);
    saved=buildLists(&list_len);assert(saved && list_len>64*1024 && list_len<256*1024);
    while(nhidden)assert(dashStoreSetHidden(hidden_apps[0],0)==1);
    memset(&dashLists,0,sizeof(dashLists));save_dirty[SAVE_LISTS]=0;
    assert(dashKvParse(saved,listsKv,NULL)>0 && nhidden==DASH_MAX_APPS && !save_dirty[SAVE_LISTS]);
    free(saved);assert(dashStoreIsHidden(path));
    assert(dashStoreSetHidden(path,0)==1 && !dashStoreIsHidden(path));
    assert(dashStoreSetHidden("mc1:/Replacement.ELF",1)==1);
    while(nhidden)assert(dashStoreSetHidden(hidden_apps[0],0)==1);
    for(int f=0;f<=6;f++) {
        char text[64];int reset=0,length;
        snprintf(text,sizeof(text),"Dash_AppFilter = %d\n",f);
        dashKvParse(text,settingsKv,&reset);assert(dashCfg.app_filter==f);
        char *settings=dashStoreSettingsText(&dashCfg,&length);
        dashCfg.app_filter=-1;dashKvParse(settings,settingsKv,&reset);free(settings);
        assert(dashCfg.app_filter==f);
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
    /* Every dashboard file uses the loaded LAUNCHELF.CNF folder, even with other copies nearby. */
    resetLocations("usb0:/Launchstation/LAUNCHELF.CNF","mmce0:/Other/","usb0:/Launchstation/");
    addBundle("usb0:/Launchstation/",11);addBundle("mmce0:/Other/",22);addBundle("mc0:/SYS-CONF/",33);
    expectLocation("usb0:/Launchstation/",11,1);assert(dashLists.nfav==1&&!strcmp(dashLists.fav[0],"usb0:/APPS/V11.ELF"));
    int first_reads=location_reads;strcpy(LoadedConfigPath,"mc1:/Elsewhere/LAUNCHELF.CNF");dashStoreInit();
    assert(location_reads==first_reads&&!strcmp(dashStoreDir(),"usb0:/Launchstation/"));
    /* The explicit override wins over the folder that supplied the startup main config. */
    resetLocations("usb0:/Launchstation/LAUNCHELF.CNF","mmce0:/Override/","usb0:/Launchstation/");
    strcpy(setting->CNF_Path,"mmce0:/Override");
    addBundle("usb0:/Launchstation/",11);addBundle("mmce0:/Override/",22);addBundle("mc0:/SYS-CONF/",33);
    expectLocation("mmce0:/Override/",22,1);assert(dashLists.nfav==1&&!strcmp(dashLists.fav[0],"usb0:/APPS/V22.ELF"));
    /* Missing settings use defaults in the same folder; app lists there still load independently. */
    resetLocations("mc1:/SYS-CONF/LAUNCHELF.CNF","mc1:/SYS-CONF/","usb1:/APPS/Launchstation/");
    addBundle("usb1:/APPS/Launchstation/",44);addBundle("mc0:/SYS-CONF/",55);
    addLocationFile("mc1:/SYS-CONF/","DASHAPPS.CNF","Favorite = mc1:/APPS/LOCAL.ELF\n");
    expectLocation("mc1:/SYS-CONF/",80,0);assert(dashLists.nfav==1&&!strcmp(dashLists.fav[0],"mc1:/APPS/LOCAL.ELF"));
    /* An unavailable override must not search the loaded, startup or other card folders. */
    resetLocations("usb0:/Launchstation/LAUNCHELF.CNF","usb0:/Launchstation/","usb0:/Launchstation/");
    strcpy(setting->CNF_Path,"mmce1:/Unavailable/");addBundle("usb0:/Launchstation/",11);addBundle("mc0:/SYS-CONF/",33);
    expectLocation("mmce1:/Unavailable/",80,0);assert(!dashLists.nfav);
    /* Even missing files on a loaded MC config do not cause a search farther down. */
    resetLocations("mc1:/BOOT/LAUNCHELF.CNF","mc1:/BOOT/","usb0:/Launchstation/");
    addBundle("mc0:/SYS-CONF/",10);addBundle("mc1:/SYS-CONF/",20);expectLocation("mc1:/BOOT/",80,0);
    /* Read-only and network folders remain the selected source, without silent relocation. */
    resetLocations("cdfs:/APPS/LAUNCHELF.CNF","mc0:/SYS-CONF/","cdfs:/APPS/");
    addBundle("cdfs:/APPS/",99);addBundle("mc1:/SYS-CONF/",88);expectLocation("cdfs:/APPS/",99,1);
    resetLocations("host:/Config/LAUNCHELF.CNF","host:/Config/","host:/APPS/");
    addBundle("host:/Config/",42);addBundle("mc0:/SYS-CONF/",66);expectLocation("host:/Config/",42,1);

    resetLocations("host:APPS\\LAUNCHELF.CNF","host:/","host:/");
    addBundle("host:APPS\\",42);expectLocation("host:APPS\\",42,1);
    /* A missing app-list file never loads a list from a different dashboard copy. */
    resetLocations("usb0:/Launchstation/LAUNCHELF.CNF","mc1:/Other/","usb0:/Launchstation/");
    addLocationFile("usb0:/Launchstation/","DASHBOARD.CNF","Dash_SoundVolume = 12\n");addBundle("mc1:/Other/",66);
    expectLocation("usb0:/Launchstation/",12,1);assert(!dashLists.nfav);
    /* With no main config, reuse the startup config directory without doing a location search. */
    resetLocations("","usb0:/Launchstation/","usb0:/Launchstation/");addBundle("mc1:/SYS-CONF/",77);
    expectLocation("usb0:/Launchstation/",80,0);
    resetLocations("","mc0:/SYS-CONF/","cdfs:/APPS/");addBundle("mc1:/SYS-CONF/",77);
    expectLocation("mc0:/SYS-CONF/",80,0);
    resetLocations("","","usb1:/APPS/");expectLocation("usb1:/APPS/",80,0);
    resetLocations("","","");expectLocation("mc0:/SYS-CONF/",80,0);
    /* APA paths are used only when explicitly selected, never as an automatic fallback. */
    resetLocations("usb0:/Config/LAUNCHELF.CNF","hdd1:/__sysconf/FMCB/","mmce1:/APPS/");
    expectLocation("usb0:/Config/",80,0);
    strcpy(setting->CNF_Path,"hdd1:/__sysconf/FMCB/");store_initialized=0;location_reads=0;
    addBundle("hdd1:/__sysconf/FMCB/",42);expectLocation("hdd1:/__sysconf/FMCB/",42,1);
    /* Folder selection depends on the main-config path, not a writable-device whitelist. */
    const char *devices[]={"mc0:/BOOT/","mc1:/BOOT/","mass2:/APPS/","usb1:/APPS/","mmce0:/APPS/","mmce1:/APPS/","mx4sio:/APPS/","ata0:/APPS/","hdd0:/__sysconf/FMCB/","hdd1:/+Launchstation/","cf0:/APPS/","vmc0:/Config/"};
    for(unsigned i=0;i<sizeof(devices)/sizeof(devices[0]);i++) {
        char main_config[MAX_PATH];snprintf(main_config,sizeof(main_config),"%sLAUNCHELF.CNF",devices[i]);
        resetLocations(main_config,devices[i],devices[i]);addBundle(devices[i],42);expectLocation(devices[i],42,1);
    }
    resetLocations("mass2:LAUNCHELF.CNF","mass2:/","mass2:/");addBundle("mass2:/",42);expectLocation("mass2:/",42,1);
    /* SELECT recovery keeps the chosen folder, skips settings and does not migrate files. */
    resetLocations("mc1:/SYS-CONF/LAUNCHELF.CNF","mc1:/SYS-CONF/","usb0:/Launchstation/");
    addBundle("mc1:/SYS-CONF/",11);boot_safe_mode=1;expectLocation("mc1:/SYS-CONF/",80,0);
    puts("PASS: one dashboard folder, explicit override priority, no fallback probes on missing files, independent app-list loading, stable save/cache/profile paths, startup defaults and recovery mode");
    puts("PASS: removed settings ignored/omitted, MMCE backup/IGR keys discarded, settings round trips, game images skip history saves, disabled recents, hidden app reload/capacity, stable filter IDs and file failures");
}
'''
with tempfile.TemporaryDirectory(prefix="settings-persistence-") as folder:
    path = Path(folder)
    (path / "settings.c").write_text(code)
    exe = path / "settings"
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.environ.get("SANITIZE") else []
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    *flags, str(path / "settings.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], cwd=path, check=True, timeout=10)
