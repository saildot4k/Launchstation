"""Exercise the physical libmc reader and both browsers' shared menu rules.

The fixtures cover both slots, PS1/PS2 changes, multi-block saves, bounded
listings and failed card requests. They do not emulate physical SIO timing.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
filer = (root / 'src/filer.c').read_text()
browser = (root / 'src/filer_browser.c').read_text()
dash = (root / 'src/dash_browser.c').read_text()
shared = (root / 'include/filer_shared.h').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


enum_start = shared.index('enum {')
enum_end = shared.index('};', enum_start) + 2
code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#define MAX_PATH 1025
#define MAX_ENTRY 32
#define MC_BROWSER_RETRY_COUNT 4
#define MC_BROWSER_RETRY_DELAY_US 100000
#define sceMcResSucceed 0
#define sceMcResChangedCard -1
#define sceMcResFailDetect -3
#define sceMcFileAttrSubdir 0x20
#define TRUE 1
#define FALSE 0
typedef struct {unsigned AttrFile,FileSizeByte;char EntryName[32];} sceMcTblGetDir;
typedef struct {char name[256];sceMcTblGetDir stats;} FILEINFO;
static int mctype_PSx,time_valid,size_valid,types[2]={1,1},handshake_result;
static int selected_port,dir_start_result,dir_result=2,sync_return=1,dir_calls,limit;
static sceMcTblGetDir entries[4];
static int filerPrepareMemoryCardRead(int port){assert(port>=0&&port<2);selected_port=port;mctype_PSx=types[port];return handshake_result;}
static int mcGetDir(int port,int slot,const char *path,int flags,int max,sceMcTblGetDir *out){
 assert(port==selected_port&&!slot&&!flags&&!strcmp(path,"/*")&&max>0&&max<=MAX_ENTRY-2);
 dir_calls++;limit=max;for(int i=0;i<dir_result&&i<max;i++)out[i]=entries[i];return dir_start_result;
}
static int mcSync(int mode,void *ignored,int *result){(void)ignored;assert(!mode);*result=dir_result<0?dir_result:dir_result<limit?dir_result:limit;return sync_return;}
static int waitMemoryCardReadyForBrowse(int port){(void)port;return 0;}
static void DelayThread(int delay){(void)delay;}
'''+function(filer, 'int readMC(')+shared[enum_start:enum_end]+r'''
static int nclipFiles,archive_kind;static FILEINFO clipFiles[MAX_ENTRY];
#define FILER_SAVE_NONE 0
static int filerArchiveClipboardKind(void){return nclipFiles==1?archive_kind:FILER_SAVE_NONE;}
enum {PSU_ACTION_NONE,PSU_ACTION_CREATE,PSU_ACTION_EXTRACT};
static int classifyPsuAction(const char *p){(void)p;return PSU_ACTION_EXTRACT;}
static int isPcCardCfPath(const char *p){(void)p;return 0;}
static int isPcCardCfOnline(void){return 1;}
static int isHddRootPath(const char *p){return !strcmp(p,"hdd0:/");}
static int isTitleCfgPathEligible(const char *p,int disabled){(void)p;return !disabled;}
static int filerCanOrganizeFolderTimestamps(const char *p){(void)p;return 1;}
static int genCmpFileExt(const char *p,const char *ext){const char *dot=strrchr(p,'.');return dot&&!strcmp(dot+1,ext);}
static int canOpenInTextEditor(const char *p,const FILEINFO *f){(void)p;(void)f;return 1;}
static int genCanRenamePath(const char *p){(void)p;return 1;}
static int filerIsExploitProtectedPath(const char *p,const FILEINFO *f){(void)p;(void)f;return 0;}
static int filerCanImportClipboard(void){return nclipFiles>0;}
static int filerIsPs1Image(const char *p){(void)p;return 0;}
'''+function(browser, 'static int isMcLikePath(')+function(browser, 'void filerMenuEnables(')+r'''
#define MOUNT_LIMIT 4
#define FIO_MT_RDWR 1
static int vmcMounted[2],vmc_PartyIndex[2]={-1,-1},Party_vmcIndex[MOUNT_LIMIT];
static int unmount_error,mount_calls,prepare_calls;
static int fileXioUmount(const char *dev){assert(!strcmp(dev,"vmc0:")||!strcmp(dev,"vmc1:"));return unmount_error;}
static int genFixPath(const char *path,char *out){prepare_calls++;strcpy(out,path);return 1;}
static int load_vmcman(void){return 1;}
static int get_vmcman_last_error(void){return -9;}
static int fileXioMount(const char *dev,const char *image,int flags){
 assert(!strcmp(dev,"vmc0:")||!strcmp(dev,"vmc1:"));assert(flags==FIO_MT_RDWR);
 assert(!strcmp(image,"usb0:/card.mcd")||!strcmp(image,"usb0:/card.MC2"));mount_calls++;return 0;
}
'''+function(browser, 'int filerUnmountVmc(')+function(browser, 'int filerMountVmc(')+r'''
int main(void){
 FILEINFO list[2];
 strcpy(entries[0].EntryName,"BASLUS-ONE");entries[0].AttrFile=0x9017;entries[0].FileSizeByte=8192;
 strcpy(entries[1].EntryName,"BASLUS-THREE");entries[1].AttrFile=0x9017;entries[1].FileSizeByte=3*8192;
 for(int port=0;port<2;port++){
  char path[8];snprintf(path,sizeof(path),"mc%d:/",port);time_valid=1;
  assert(readMC(path,list,2)==2&&!time_valid&&size_valid&&limit==2);
  assert(!strcmp(list[0].name,"BASLUS-ONE")&&list[1].stats.FileSizeByte==3*8192);
  assert(!(list[0].stats.AttrFile&sceMcFileAttrSubdir));
  types[port]=2;assert(readMC(path,list,2)==2&&time_valid);types[port]=1;
  assert(readMC(path,list,2)==2&&!time_valid);
 }
 memset(&list[1],0x6b,sizeof(list[1]));assert(readMC("mc0:/",list,1)==1&&limit==1);
 assert((unsigned char)list[1].name[0]==0x6b);
 int calls=dir_calls;assert(!readMC("mc0:/",list,0)&&dir_calls==calls);
 handshake_result=-3;assert(readMC("mc0:/",list,2)==-3&&dir_calls==calls);handshake_result=0;
 dir_start_result=-7;assert(readMC("mc0:/",list,2)==-7);dir_start_result=0;
 dir_result=-4;assert(readMC("mc0:/",list,2)==-4);dir_result=2;
 sync_return=0;assert(readMC("mc0:/",list,2)==sceMcResFailDetect);sync_return=1;
 /* Card-supplied names are bounded even if every byte of the name is used. */
 memset(entries[0].EntryName,'A',sizeof(entries[0].EntryName));assert(readMC("mc0:/",list,1)==1&&strlen(list[0].name)==32);
 const char *paths[]={"mc0:/","mc1:/","vmc0:/","vmc1:/"};
 FILEINFO save={0};strcpy(save.name,"SAVE.ELF");nclipFiles=1;
 char enabled[NUM_MENU];
 for(unsigned i=0;i<sizeof(paths)/sizeof(paths[0]);i++){
  filerMenuEnables(paths[i],&save,0,1,enabled);
  assert(!enabled[NEWDIR]&&!enabled[NEWICON]&&!enabled[LAUNCH_ELF_ARGS]&&!enabled[OPEN_TEXTEDITOR]);
  assert(!enabled[TITLE_CFG]&&!enabled[TIMEMANIP_CUSTOM]&&!enabled[CREATE_ARCHIVE]);
  assert(enabled[COPY]&&enabled[CUT]&&enabled[PASTE]&&enabled[IMPORT_SAVE]&&enabled[EXPORT_PS1]);
  clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
  filerMenuEnables(paths[i],&save,0,1,enabled);assert(!enabled[PASTE]);clipFiles[0].stats.AttrFile=0;
  filerMenuEnables(paths[i],&save,0,2,enabled);
  assert(enabled[NEWDIR]&&enabled[NEWICON]&&enabled[LAUNCH_ELF_ARGS]&&!enabled[CREATE_ARCHIVE]);
 }
 filerMenuEnables("usb0:/",&save,0,1,enabled);assert(enabled[NEWDIR]&&enabled[LAUNCH_ELF_ARGS]&&!enabled[CREATE_ARCHIVE]);
 archive_kind=1;strcpy(save.name,"..");
 filerMenuEnables("usb0:/",&save,0,0,enabled);assert(enabled[CREATE_ARCHIVE]&&!enabled[COPY]);
 filerMenuEnables("mc0:/",&save,0,1,enabled);assert(!enabled[CREATE_ARCHIVE]);
 filerMenuEnables("mc0:/",&save,0,2,enabled);assert(enabled[CREATE_ARCHIVE]);
 filerMenuEnables("cdfs:/",&save,0,0,enabled);assert(!enabled[CREATE_ARCHIVE]);
 filerMenuEnables("hdd0:/",&save,0,0,enabled);assert(!enabled[CREATE_ARCHIVE]);
 filerMenuEnables("",&save,0,0,enabled);assert(!enabled[CREATE_ARCHIVE]);
 /* The selected save/folder never enables archiving without one captured clipboard source. */
 for(int copied=0;copied<3;copied++) {
  nclipFiles=copied;archive_kind=2;
  filerMenuEnables("usb0:/",&save,0,0,enabled);assert(enabled[CREATE_ARCHIVE]==(copied==1));
 }
 archive_kind=0;nclipFiles=1;
 char message[160];FILEINFO image={0};
 for(int slot=0;slot<2;slot++) {
  strcpy(image.name,"card.mcd");assert(!filerMountVmc("usb0:/",&image,slot,message,sizeof(message)));
  assert(vmcMounted[slot]&&vmc_PartyIndex[slot]==1&&Party_vmcIndex[1]==slot);
  int previous_mounts=mount_calls,previous_prepares=prepare_calls;
  unmount_error=-5;strcpy(image.name,"card.MC2");
  assert(filerMountVmc("usb0:/",&image,slot,message,sizeof(message))==-5);
  assert(strstr(message,"flushed")&&vmcMounted[slot]&&vmc_PartyIndex[slot]==1&&Party_vmcIndex[1]==slot);
  assert(mount_calls==previous_mounts&&prepare_calls==previous_prepares);
  assert(filerUnmountVmc(slot)==-5&&vmcMounted[slot]&&vmc_PartyIndex[slot]==1);
  unmount_error=0;assert(!filerMountVmc("usb0:/",&image,slot,message,sizeof(message)));
  assert(!filerUnmountVmc(slot)&&!vmcMounted[slot]&&vmc_PartyIndex[slot]==-1&&Party_vmcIndex[1]==-1);
 }
 puts("PASS: real-card libmc path for both slots, flat multi-block saves, card swaps, bounded reads/errors and PS1-only browser actions");
 puts("PASS: shared mounts accept MCD/MC2 names and retain mounted state/partition locks when flushing fails");
}
'''

# The two UIs must pass the media type belonging to their current listing.
assert 'filerMenuEnables(path, file, nmarks, card_type, enable)' in browser
assert 'filerMenuEnables(fb.dir, f != NULL ? f : &none, fb.nmarked, fb.card_type, en)' in dash
assert 'int ps1_card = fb.card_type == 1;' in function(dash, 'static void actionsMenu(void)')
assert 'getFilePath(destination, DIR_CNF) >= 0' in browser  # DIR_CNF confirms with 0.

with tempfile.TemporaryDirectory(prefix='ps1-physical-') as folder:
    folder = Path(folder)
    (folder / 'test.c').write_text(code)
    exe = folder / 'test'
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', *flags,
                    str(folder / 'test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=20)
