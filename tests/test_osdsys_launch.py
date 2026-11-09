"""Run OSDSYS overrides through the real dispatcher and R3Z loader fallback."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
actions = (root / "src/main_actions.c").read_text()
loader = (root / "loader/loader.c").read_text()
fileops = (root / "src/main_fileops.c").read_text()


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
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "main_actions.h"
#define MAX_PATH 1025
#define FALSE 0
#define stricmp strcasecmp
#define FIO_O_RDONLY 1
#define SCECdDVDV 1
#define SCECdCDDA 2
#define TEXTEDITOR_RESULT_LAUNCH_ARGS 1
#define TEXTEDITOR_RESULT_BROWSE_DIR 2
#define DPRINTF(...) ((void)0)
#define LNG(x) #x
#define LCDVD_FLUSHCACHE() ((void)0)
#define LCDVD_DISKREADY(x) ((void)(x))
#define MMCE
#define MX4SIO
#define EXFAT

enum {SETTING_LK_OSDSYS, SETTING_LK_ESR};
typedef struct {
 char LK_Path[2][MAX_PATH],font_file[1];int LK_Flag[2],reboot_iop_elf_load,cdrom_disable_gameid,app_gameid;
 const char *Misc_OSDSYS,*Misc_PS2Disc,*Misc_FileBrowser,*Misc_PS2Browser,*Misc_PS2PowerOff;
 const char *Misc_HddManager,*Misc_TextEditor,*Misc_Configure,*Misc_ShowFont,*Misc_Debug_Info;
 const char *Misc_Show_Build_Info,*Misc_Exploit_Installer,*Misc_Reboot_IOP;
} Settings;
static Settings stored,*setting=&stored;
static char LaunchElfDir[MAX_PATH]="usb0:/Launchstation/",LastDir[MAX_PATH];
static int vmcMounted[2]={1,1},mx4sio_driver_running=1,BootDiscType,cdmode;
static char SystemCnf_BOOT2[MAX_PATH],SystemCnf_BOOT[MAX_PATH],SystemCnf_VER[16];
static int ordinary_result,encrypted_result,ordinary_entry,encrypted_entry,header_kind,card_slot;
static int regular_calls,encrypted_calls,exec_calls,loader_calls,legacy_calls,cleanups,keep_cleanups;
static int iop_resets,chooser_calls,sidecars,args_pending,args_clears,legacy_available;
static int prepare_ok=1,last_mode,last_kind;
static char selected[MAX_PATH],loaded[MAX_PATH],partition[MAX_PATH],sidecar[MAX_PATH],legacy_arg[MAX_PATH+3];
static char call_order[8];static int order_count;
typedef struct {uintptr_t epc,gp;} t_ExecData;
static void clearUserMem(void) {}
static void FlushCache(int which) {(void)which;}
static void SifLoadFileInit(void) {}
static void SifLoadFileExit(void) {}
static int SifLoadElf(const char *path,t_ExecData *out) {
 regular_calls++;call_order[order_count++]='R';snprintf(loaded,sizeof(loaded),"%s",path);
 out->epc=ordinary_entry;out->gp=0;return ordinary_result;
}
static int SifLoadElfEncrypted(const char *path,t_ExecData *out) {
 assert(regular_calls==1 && order_count==1);encrypted_calls++;call_order[order_count++]='E';
 assert(!strcmp(path,loaded));out->epc=encrypted_entry;return encrypted_result;
}
static void cleanupDev9ForLaunch(int mode) {assert(mode==0);}
static void resetIOP(void) {iop_resets++;}
static void SifExitRpc(void) {}
static void ExecPS2(void *entry,void *gp,int argc,char **argv) {
 (void)gp;assert((uintptr_t)entry && argc==1 && argv && !strcmp(argv[0],selected));exec_calls++;
}
'''
code += function(loader, "static int loadFilePayload(")
code += r'''
static void RunLoaderElf(char *full,char *party,const char *path,int kind,int reboot) {
 assert(cleanups+keep_cleanups==1);loader_calls++;last_mode=reboot;last_kind=kind;
 snprintf(selected,sizeof(selected),"%s",path);snprintf(partition,sizeof(partition),"%s",party);
 char *argv[]={(char *)path};loadFilePayload(full,1,argv,reboot,0);
}
static int genCmpFileExt(const char *path,const char *ext) {const char *dot=strrchr(path,'.');return dot&&!strcasecmp(dot+1,ext);}
static int isPcCardCfPath(const char *path) {return !strncmp(path,"cf",2);}
static int IsPopstarterVcdPath(const char *path) {(void)path;return 0;}
static int IsEmberGamePath(const char *path) {(void)path;return 0;}
static int IsNeutrinoIsoPath(const char *path) {(void)path;return 0;}
static int LaunchArgsPending(void) {return args_pending;}
static void LaunchArgsClear(void) {args_pending=0;args_clears++;}
static int LaunchArgsLoadSidecarForExec(const char *path,char *msg,int size) {
 (void)msg;(void)size;sidecars++;snprintf(sidecar,sizeof(sidecar),"%s",path);return 0;
}
static int checkELFheader(char *path) {
 if(!strncmp(path,"mc0:",4) && card_slot==1)return 0;
 return header_kind;
}
static int genFixPath(const char *in,char *out) {strcpy(out,in);return 0;}
static int wleExists(const char *path) {(void)path;return 1;}
static int genOpen(const char *path,int mode) {(void)path;assert(mode==FIO_O_RDONLY);return legacy_available?7:-1;}
static int genClose(int fd) {assert(fd==7);return 0;}
static void LoadExecPS2(const char *program,int argc,char **argv) {
 assert(!strcmp(program,"moduleload") && argc==4);legacy_calls++;
 assert(!strcmp(argv[0],"-m rom0:SIO2MAN") && !strcmp(argv[1],"-m rom0:MCMAN") && !strcmp(argv[2],"-m rom0:MCSERV"));
 snprintf(legacy_arg,sizeof(legacy_arg),"%s",argv[3]);
}
static void CleanUpForExec(void) {cleanups++;}
static int CleanUpForKeepIopExec(const char *title) {assert(title);if(prepare_ok)keep_cleanups++;return prepare_ok;}
static int DashChooseElfIopMode(int saved) {chooser_calls++;return saved;}
void (*mainActionLaunchHook)(const char *path);
#define LaunchPopstarterVcd(...) assert(0)
#define LaunchEmberGame(...) assert(0)
#define LaunchNeutrinoIso(...) assert(0)
#define loadHddModules() ((void)0)
#define loadMx4sioModules() 1
#define loadMmceModules() ((void)0)
#define loadAtaModules() ((void)0)
static int buildLaunchGameID(const char *path,char *out,int size) {(void)path;(void)out;(void)size;return 0;}
#define updateOSDHistoryFile(...) assert(0)
#define applyXPARAM(...) assert(0)
#define displayRetroGemGameID(...) assert(0)
#define isLikelyDiscLaunch(path) 0
#define readSystemCnf() assert(0)
#define uLE_cdDiscValid() 0
#define Check_ESR_Disc() 0
#define drawMsg(...) ((void)0)
#define SifLoadModule(...) -1
#define SifLoadModuleEncrypted(...) -1
#define isMiscDashboardPath(path) 0
#define DashIsActive() 1
#define DashRun(...) assert(0)
#define getFilePath(...) assert(0)
#define executeBrowserSelection(...) assert(0)
static void ExecOSD(int argc,char **argv) {(void)argc;(void)argv;assert(0);}
#define setupPowerOff() assert(0)
#define isPowerOffReady() 0
#define closeAllAndPoweroff() assert(0)
#define hddManager() assert(0)
#define TextEditor(...) 0
#define getTextEditorReturnPath(...) assert(0)
#define DashOpenSettings() 0
#define Load_External_Language() assert(0)
#define loadFont(...) assert(0)
#define config(...) assert(0)
#define ShowFont() assert(0)
#define ShowDebugInfo(...) assert(0)
#define isMiscAboutWlePath(path) 0
#define Show_About_uLE() assert(0)
#define Show_build_info() assert(0)
#define ShowExploitInstaller(...) assert(0)
#define rebootIopAndReloadCoreStack() assert(0)
#define loadCdModules() ((void)0)
'''
for source, signature in (
    (fileops, "int uLE_related("),
    (actions, "static int isHddLaunchPath("),
    (actions, "static const char *getLaunchArgsSidecarBasePath("),
    (actions, "static int elfLaunchIopMode("),
    (actions, "void ExecuteMainAction("),
):
    code += function(source, signature)
code += r'''
static void reset(void) {
 memset(&stored,0,sizeof(stored));
 stored.Misc_OSDSYS="MISC/OSDSYS";stored.Misc_PS2Disc="MISC/PS2Disc";
 stored.Misc_FileBrowser="MISC/FileBrowser";stored.Misc_PS2Browser="MISC/PS2Browser";
 stored.Misc_PS2PowerOff="MISC/PowerOff";stored.Misc_HddManager="MISC/HddManager";
 stored.Misc_TextEditor="MISC/TextEditor";stored.Misc_Configure="MISC/Configure";
 stored.Misc_ShowFont="MISC/ShowFont";stored.Misc_Debug_Info="MISC/DebugInfo";
 stored.Misc_Show_Build_Info="MISC/BuildInfo";stored.Misc_Exploit_Installer="MISC/Installer";
 stored.Misc_Reboot_IOP="MISC/Reboot";
 regular_calls=encrypted_calls=exec_calls=loader_calls=legacy_calls=cleanups=keep_cleanups=0;
 iop_resets=chooser_calls=sidecars=args_pending=args_clears=0;order_count=0;call_order[0]=0;
 ordinary_result=encrypted_result=0;ordinary_entry=encrypted_entry=0x100000;
 header_kind=1;card_slot=0;prepare_ok=legacy_available=1;last_mode=last_kind=-1;
 selected[0]=loaded[0]=partition[0]=sidecar[0]=legacy_arg[0]=0;
}
static void run(const char *path,int override,int saved,int forced,char *message) {
 char input[MAX_PATH];snprintf(input,sizeof(input),"%s",override?"MISC/OSDSYS":path);
 if(override){strcpy(stored.LK_Path[SETTING_LK_OSDSYS],path);stored.LK_Flag[SETTING_LK_OSDSYS]=1;}
 stored.reboot_iop_elf_load=saved;message[0]=0;
 MainExecuteContext ctx={.main_msg=message,.default_osdsys_path="mc:/BEEXEC-SYSTEM/osdmain.elf",.elf_iop_mode=forced};
 ExecuteMainAction(input,&ctx);assert(!strcmp(input,override?"MISC/OSDSYS":path));
}
int main(void) {
 char message[MAX_PATH];
 char long_path[900];strcpy(long_path,"usb1:/Apps/");memset(long_path+strlen(long_path),'A',700);strcpy(long_path+711,"/Program with spaces.ELF");
 const char *paths[]={"usb0:/Apps/Program.ELF","usb1:/Apps/Encrypted.ELF","mass0:/Apps/APP.KELF",
 "mc0:/SYS-CONF/APP.ELF","mc1:/SYS-CONF/APP.KELF","mc:/SYS-CONF/APP.XLF","mmce0:/Apps/Program.ELF",
 "mx4sio0:/Apps/Program.ELF","ata0:/Apps/Program.ELF",long_path,"hdd0:/+APPS/Program.ELF"};
 for(unsigned p=0;p<sizeof(paths)/sizeof(paths[0]);p++)for(int saved=0;saved<2;saved++)
 for(int forced=MAIN_ELF_IOP_DEFAULT;forced<=MAIN_ELF_IOP_REBOOT;forced++)for(int encrypted=0;encrypted<2;encrypted++) {
  char wanted_load[MAX_PATH],wanted_selected[MAX_PATH],wanted_party[MAX_PATH],wanted_sidecar[MAX_PATH];
  for(int override=0;override<2;override++) {
   reset();ordinary_result=encrypted?-1:0;header_kind=encrypted?2:1;card_slot=!strncmp(paths[p],"mc:/",4);
   run(paths[p],override,saved,forced,message);
   assert(loader_calls==1 && exec_calls==1 && !legacy_calls);
   assert(regular_calls==1 && encrypted_calls==encrypted && call_order[0]=='R');
   assert(!encrypted || call_order[1]=='E');
   int expected=forced==MAIN_ELF_IOP_DEFAULT?saved:forced==MAIN_ELF_IOP_REBOOT;
   assert(last_mode==expected && iop_resets==expected && cleanups==expected && keep_cleanups==!expected);
   assert(chooser_calls==(forced==MAIN_ELF_IOP_DEFAULT) && sidecars==1 && last_kind==header_kind);
   if(!override) {
    strcpy(wanted_load,loaded);strcpy(wanted_selected,selected);strcpy(wanted_party,partition);strcpy(wanted_sidecar,sidecar);
   } else {
    assert(!strcmp(wanted_load,loaded) && !strcmp(wanted_selected,selected));
    assert(!strcmp(wanted_party,partition) && !strcmp(wanted_sidecar,sidecar));
   }
  }
 }
 // No entry point counts as a failed ordinary load and triggers the encrypted fallback.
 reset();ordinary_entry=0;run("usb0:/APP.ELF",1,0,0,message);
 assert(regular_calls==1 && encrypted_calls==1 && exec_calls==1);
 // A failed encrypted load never jumps to a zero/invalid entry point.
 reset();ordinary_result=-1;encrypted_result=-1;encrypted_entry=0;
 run("usb0:/APP.KELF",1,1,0,message);assert(regular_calls==1 && encrypted_calls==1 && !exec_calls);
 // Invalid headers and canceled keep-IOP preparation do not commit the launch.
 reset();header_kind=-1;run("usb0:/bad.ELF",1,0,0,message);
 assert(!loader_calls && !cleanups && !keep_cleanups && message[0]);
 reset();prepare_ok=0;run("usb0:/APP.ELF",1,0,0,message);assert(!loader_calls && !cleanups && !keep_cleanups);
 // Resolve uLE-relative overrides and preserve pending launch arguments.
 reset();args_pending=1;run("uLE:/APP.ELF",1,0,0,message);
 assert(exec_calls==1 && !strcmp(selected,"usb0:/Launchstation/APP.ELF") && !args_clears && !sidecars);
 // A manually edited config cannot redirect OSDSYS back into a MISC command.
 reset();run("MISC/OSDSYS",1,0,0,message);assert(!legacy_calls && !loader_calls && strstr(message,"executable file"));
 // Unset/disabled overrides retain the default system-update route.
 for(int disabled=0;disabled<2;disabled++) {
  reset();strcpy(stored.LK_Path[0],"usb0:/Unused.ELF");stored.LK_Flag[0]=0;
  if(!disabled)stored.LK_Path[0][0]=0;
  run("MISC/OSDSYS",0,0,0,message);
  assert(legacy_calls==1 && !loader_calls && cleanups==1);
  assert(!strcmp(legacy_arg,"-x mc:/BEEXEC-SYSTEM/osdmain.elf"));
 }
 puts("PASS: OSDSYS overrides match browser dispatch across devices, long paths, aliases, arguments and IOP policies; regular-then-encrypted loads; default boot retained");
}
'''
with tempfile.TemporaryDirectory(prefix="osdsys-launch-") as directory:
    directory = Path(directory)
    src, binary = directory / "launch.c", directory / "launch"
    src.write_text(code)
    flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if os.environ.get("SANITIZE") else []
    subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    *flags, "-I", str(root / "include"), str(src), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=10)
