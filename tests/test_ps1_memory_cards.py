"""Exercise the physical libmc reader and both browsers' shared menu rules.

The fixtures cover both slots, PS1/PS2 changes, multi-block saves, bounded
listings and failed card requests. They do not emulate physical SIO timing.
"""
from source_groups import component_source
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
filer = (root / 'src/filer.c').read_text()
browser = component_source('src/filer_browser.c')
dash = (root / 'src/dash_browser.c').read_text()
shared = (root / 'include/filer_menu.h').read_text()
header = (root / 'include/launchelf.h').read_text()
fileops = (root / 'src/filer_fileops.c').read_text()
texteditor = (root / 'src/gui_texteditor.c').read_text()
main_fileops = (root / 'src/main_fileops.c').read_text()


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
code = '#include "' + str(root / 'src/filer_menu.c') + '"\n' + r'''
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
static struct {uint64_t color[4];char Misc[MAX_PATH];} settings={.Misc="MISC:/"},*setting=&settings;
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
'''+function(filer, 'int readMC(')+function(header, 'static inline unsigned char wle_ascii_tolower(')+function(header, 'static inline int wle_stricmp(')+'#define stricmp wle_stricmp\n'+function(fileops, 'int genCmpFileExt(')+r'''
static int nclipFiles,archive_kind,import_eligible=1;static FILEINFO clipFiles[MAX_ENTRY];
#define FILER_SAVE_NONE 0
static int filerArchiveClipboardKind(void){return nclipFiles>0?archive_kind:FILER_SAVE_NONE;}
enum {PSU_ACTION_NONE,PSU_ACTION_CREATE,PSU_ACTION_EXTRACT};
static int classifyPsuAction(const char *p){(void)p;return PSU_ACTION_EXTRACT;}
static int cf_online=1;
static int isPcCardCfPath(const char *p){return !strncmp(p,"cf",2);}
static int isPcCardCfOnline(void){return cf_online;}
static int isHddRootPath(const char *p){return !strcmp(p,"hdd0:/");}
static int isTitleCfgPathEligible(const char *p,int disabled){(void)p;return !disabled;}
static int filerCanOrganizeFolderTimestamps(const char *p){(void)p;return 1;}
''' + function(main_fileops, 'int IsTextEditorFileType(') + function(texteditor, 'static int isDirectoryEntry(') + function(texteditor, 'static int isParentEntry(') + function(texteditor, 'int canOpenInTextEditor(') + r'''
static int genCanRenamePath(const char *p){(void)p;return 1;}
static int filerIsExploitProtectedPath(const char *p,const FILEINFO *f){(void)p;(void)f;return 0;}
static int filerCanImportClipboard(void){return nclipFiles>0&&import_eligible;}
static int filerIsPs1Image(const char *p){(void)p;return 0;}
'''+function(browser, 'static int isMcLikePath(')+function(browser, 'static int isVmcImageName(')+function(browser, 'void filerMenuEnables(')+r'''
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
/* Run the classic menu with controller input and capture its final drawn frame. */
typedef uint64_t u64;
#define LNG(label) #label
#define SCREEN_WIDTH 640
#define SCREEN_MARGIN 16
#define FONT_WIDTH 8
#define FONT_HEIGHT 16
#define COLOR_BACKGR 0
#define COLOR_TEXT 1
#define COLOR_FRAME 2
#define COLOR_SELECT 3
#define LEFT_CUR 1
#define PAD_UP 1
#define PAD_DOWN 2
#define PAD_TRIANGLE 4
#define PAD_CROSS 8
#define PAD_CIRCLE 16
#define PAD_SQUARE 32
#define FILER_CARD_PS1 1
static int nmarks,swapKeys,new_pad,Menu_tooltip_y=450;
static int pad_calls,down_count,drawn_mounts,drawn_args,drawn_rows,cursor_y,size_y,date_y,popup_bottom;
static int filerPs1CardCandidate(const FILEINFO *f){(void)f;return 0;}
static void filerClipboardExtractLabel(char *out,size_t n){snprintf(out,n,"Extract archive...");}
static void waitPadReady(int port,int slot){(void)port;(void)slot;}
static int readpad(void){
 assert(++pad_calls<20);if(pad_calls==1)return 0;
 new_pad=pad_calls<=down_count+1?PAD_DOWN:PAD_CIRCLE;return 1;
}
static void drawPopSprite(u64 c,int x,int y,int right,int bottom){
 (void)c;(void)x;(void)y;(void)right;popup_bottom=bottom;drawn_mounts=drawn_args=drawn_rows=0;
}
static void drawFrame(int x,int y,int right,int bottom,u64 c){(void)x;(void)y;(void)right;(void)bottom;(void)c;}
static void drawSprite(u64 c,int x,int y,int right,int bottom){(void)c;(void)x;(void)y;(void)right;(void)bottom;}
static void printXY(const char *text,int x,int y,u64 c,int enabled,int z){
 (void)x;(void)c;(void)enabled;(void)z;
 if(y==Menu_tooltip_y)return;
 drawn_rows++;assert(y<popup_bottom);
 if(!strncmp(text,"Mount vmc",9))drawn_mounts++;
 if(!strcmp(text,"Get_Size"))size_y=y;
 if(!strcmp(text,"Set_Custom_Date"))date_y=y;
 if(!strcmp(text,"Launch_With_Args"))drawn_args++;
}
static void drawChar(int ch,int x,int y,u64 c){(void)ch;(void)x;(void)c;cursor_y=y;}
static void drawScr(void){}
'''+function(browser, 'static int menu(')
native_menu = function(dash, 'static void actionsMenu(void)')
native_menu = native_menu[:native_menu.index('\tr = dashModalMenu("File Browser"')]
start = dash.rfind('enum {', 0, dash.index('\tFB_SORT_TYPE = 0,'))
code += dash[start:dash.index('};', start)+2] + '\n'
icons = sorted(set(re.findall(r'\bDI_\w+', native_menu)))
code += 'enum {' + ','.join(icons) + '};\n'
code += r'''
typedef struct {int icon;const char *label,*detail;int disabled;} DashMenuItem;
static struct {char dir[MAX_PATH];int sel,n,nmarked,card_type;FILEINFO files[1];} fb;
static int fb_sort=FB_SORT_TYPE,fb_sort_desc,fb_show,browser_cut;
static FILEINFO *singleSaveTarget(void){return NULL;}
static int fullPath(const FILEINFO *f,char *out,int size){return snprintf(out,size,"%s%s",fb.dir,f->name)<size;}
static int LaunchArgsPending(void){return 0;}
'''
code += function(dash,'static int isDir(')+function(dash,'static int isMisc(')
code += native_menu.replace('static void actionsMenu(void)','static int argsActionVisible(void)',1)
code += r'''
 (void)ids;(void)r;(void)archive_kind;
 int found=0;for(int item=0;item<n;item++)if(!strcmp(items[item].label,"Use as launch arguments")){
  assert(!items[item].disabled);found++;
 }
 return found;
}
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
 FILEINFO save={0};strcpy(save.name,"SAVE.TXT");nclipFiles=1;
 char enabled[NUM_MENU];
 /* Both browsers offer mounts only for whole-card suffixes, without case sensitivity. */
 const char *extensions[]={"vmc","mcd","mc2","bin","mcr","mc","srm","vm1",
                           "ddf","ps","psm","sav","ps2","vm2","raw","gme","vgs","mem","vmp"};
 for(unsigned i=0;i<sizeof(extensions)/sizeof(extensions[0]);i++) {
  for(int letter_case=0;letter_case<3;letter_case++) {
   snprintf(save.name,sizeof(save.name),"my.card.%s",extensions[i]);
   for(unsigned j=8;save.name[j];j++)
    if(letter_case==1 || (letter_case==2 && j%2==0))
     if(save.name[j]>='a'&&save.name[j]<='z') save.name[j]-='a'-'A';
   filerMenuEnables("usb0:/",&save,0,0,enabled);
   assert(enabled[MOUNTVMC0]&&enabled[MOUNTVMC1]);
   save.stats.AttrFile=sceMcFileAttrSubdir;
   filerMenuEnables("usb0:/",&save,0,0,enabled);
   assert(!enabled[MOUNTVMC0]&&!enabled[MOUNTVMC1]);save.stats.AttrFile=0;
   for(unsigned p=0;p<sizeof(paths)/sizeof(paths[0]);p++) {
    filerMenuEnables(paths[p],&save,0,0,enabled);
    assert(!enabled[MOUNTVMC0]&&!enabled[MOUNTVMC1]);
   }
  }
 }
 const char *other_files[]={"save.mcs","save.psv","save.psu","save.max","save.cbs",
                            "card.vme","card.mci","app.elf","readme.txt","card",
                            "card.","card.vmc.bak","",".."};
 for(unsigned i=0;i<sizeof(other_files)/sizeof(other_files[0]);i++) {
  strcpy(save.name,other_files[i]);
  filerMenuEnables("usb0:/",&save,0,0,enabled);
  assert(!enabled[MOUNTVMC0]&&!enabled[MOUNTVMC1]);
 }
 strcpy(save.name,"SAVE.TXT");
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
 /* The selected save/folder never enables archiving without captured clipboard sources. */
 for(int copied=0;copied<3;copied++) {
  nclipFiles=copied;archive_kind=2;
  filerMenuEnables("usb0:/",&save,0,0,enabled);assert(enabled[CREATE_ARCHIVE]==(copied>0));
 }
 /* A copied native PS1 save offers Paste/Create archive, without Extract. */
 nclipFiles=1;archive_kind=1;import_eligible=0;clipFiles[0].stats.AttrFile=0;
 filerMenuEnables("usb0:/",&save,0,0,enabled);
 assert(enabled[PASTE]&&enabled[CREATE_ARCHIVE]&&!enabled[IMPORT_SAVE]);
 filerMenuEnables("mc0:/",&save,0,1,enabled);
 assert(enabled[PASTE]&&!enabled[CREATE_ARCHIVE]&&!enabled[IMPORT_SAVE]);
 import_eligible=1;
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
 /* Hidden rows shrink the menu; navigation still returns the original command ID. */
 for(int selection=0;selection<3;selection++) {
  int mount=selection==1,args=selection==0;
  strcpy(image.name,mount?"card.VmC":"notes.txt");image.stats.AttrFile=selection==2?sceMcFileAttrSubdir:0;
  down_count=selection==2?8:10;pad_calls=0;
  assert(menu("usb0:/",&image,0,&image)==TIMEMANIP_CUSTOM);
  assert(drawn_mounts==(mount?2:0)&&drawn_args==args);
  int hidden=(mount?0:2)+(args?0:1);
  assert(drawn_rows==NUM_MENU-hidden);
  assert(popup_bottom==64+(drawn_rows+1)*FONT_HEIGHT);
  assert(cursor_y==date_y&&date_y==64+FONT_HEIGHT/2+(TIMEMANIP_CUSTOM-hidden)*FONT_HEIGHT);
 }
 /* Native Options hide the row for directories, unsupported files, no cursor
  * target and device/MISC roots. All supported text suffixes work in any case. */
 const char *text_suffixes[]={"txt","cht","cfg","ini","cnf","pbt","js","lua","xml","toml","yaml","yml","arg"};
 strcpy(fb.dir,"usb0:/");fb.n=1;fb.sel=0;
 for(unsigned ext=0;ext<sizeof(text_suffixes)/sizeof(text_suffixes[0]);ext++)for(int upper=0;upper<2;upper++){
  snprintf(fb.files[0].name,sizeof(fb.files[0].name),"config.%s",text_suffixes[ext]);
  for(char *c=fb.files[0].name;upper&&*c;c++)if(*c>='a'&&*c<='z')*c-='a'-'A';
  assert(argsActionVisible()==1);
 }
 const char *not_text[]={"app.elf","card.bin","game.iso","file","..",""};
 for(unsigned i=0;i<sizeof(not_text)/sizeof(not_text[0]);i++){
  strcpy(fb.files[0].name,not_text[i]);assert(!argsActionVisible());
 }
 strcpy(fb.files[0].name,"folder.txt");fb.files[0].stats.AttrFile=sceMcFileAttrSubdir;assert(!argsActionVisible());
 fb.files[0].stats.AttrFile=0;fb.n=0;assert(!argsActionVisible());fb.n=1;
 fb.dir[0]=0;assert(!argsActionVisible());strcpy(fb.dir,"MISC:/");assert(!argsActionVisible());
 strcpy(fb.dir,"mc0:/");fb.card_type=1;assert(!argsActionVisible());
 strcpy(fb.dir,"cf0:/");fb.card_type=0;assert(argsActionVisible()==1);
 cf_online=0;assert(!argsActionVisible());cf_online=1;
 puts("PASS: both browser menus hide launch arguments for non-text selections; all supported case-insensitive text suffixes offer it without I/O");
 puts("PASS: classic menu hides mount rows, resizes its border and keeps cursor/navigation aligned");
 puts("PASS: real-card libmc path for both slots, flat multi-block saves, card swaps, bounded reads/errors and PS1-only browser actions");
 puts("PASS: both browsers filter mount choices by whole-card extensions in all cases");
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
                    '-I', str(root / 'include'), str(folder / 'test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=20)

    # Compile the complete rules module independently. The runtime harness
    # above defines its device spies before copying functions, which can hide
    # missing production includes. Only the real init.h declares CF queries.
    (folder / 'filer_shared.h').write_text(r'''
#ifndef MENU_COMPILE_PLATFORM
#define MENU_COMPILE_PLATFORM
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "filer_types.h"
#include "filer_menu.h"
typedef uint32_t u32;
#define TRUE 1
#define FALSE 0
#define sceMcFileAttrSubdir 0x20
struct FilerFileInfo { char name[256];struct {unsigned AttrFile;}stats; };
typedef struct {int HOSTwrite;} MenuCompileSettings;
extern MenuCompileSettings *setting;
extern int nclipFiles,host_elflist;
extern FILEINFO clipFiles[32];
int genCmpFileExt(const char *,const char *);
int genCanRenamePath(const char *);
#endif
''')
    (folder / 'filer_actions.h').write_text(
        'int filerCanOrganizeFolderTimestamps(const char *);\n'
        'int filerIsExploitProtectedPath(const char *,const FILEINFO *);\n')
    (folder / 'gui_texteditor.h').write_text(
        'int canOpenInTextEditor(const char *,const FILEINFO *);\n')
    production_flags = ['-DWLE_PS2BUILD', '-DEXFAT', '-DXFROM', '-DDVRP',
                        '-DMMCE', '-DMX4SIO', '-DETH', '-DUDPFS', '-DHOMEBREW_SIO2MAN']
    for variant in ([], production_flags, [*production_flags, '-DDS34']):
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-fsyntax-only', *variant, '-I', str(folder), '-I', str(root / 'include'),
                        str(root / 'src/filer_menu_rules.c')], check=True)
    print('PASS: complete menu rules module compiles independently with real device declarations in minimal and both release configurations')
