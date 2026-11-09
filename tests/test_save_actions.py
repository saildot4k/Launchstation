"""Exercise both browsers' actual archive dialogs with cancellation/device-switch spies."""
from pathlib import Path
import os
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
dash=(root/'src/dash_browser.c').read_text()
classic=(root/'src/filer_browser.c').read_text()

def function(source, signature):
    start=source.index(signature)
    end=source.index('{',start)+1
    depth=1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}')
        end+=1
    return source[start:end]+'\n'

code=r'''
#include "save_archive.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define MAX_PATH 1025
#define MAX_ENTRY 2
#define DASH_TOAST_INFO 1
#define DASH_TOAST_WARN 2
#define sceMcFileAttrSubdir 0x20
#define DASH_PICK_FOLDER 1
#define DIR_CNF 1
#define DI_WARNING 1
#define DI_MC 2
enum { FILER_SAVE_NONE,FILER_SAVE_PS1,FILER_SAVE_PS2,FILER_ARCHIVE_PS1,FILER_ARCHIVE_PS2,FILER_CARD_PS1 };
typedef struct {char name[256];struct {unsigned AttrFile;}stats;} FILEINFO;
typedef struct {int icon;const char *label,*detail;int disabled;} DashMenuItem;
static struct {int sel,n,card_type,nmarked;char mark[2];char dir[MAX_PATH],msg[MAX_PATH];FILEINFO files[2];}fb;
static int choice,pick_ok,prompt_ok,prepare_ok,read_ok,kind,expected_ps1;
static int nclipFiles,browser_cut,cached_kind,finish_calls,write_ok;
static FILEINFO clipFiles[2];static char clipPath[MAX_PATH];
static unsigned clipIopResetGeneration;
static int reads,switches,writes,extracts,prompts,loading,allocated,freed_saves,messages,refreshes,expected_format;
static char observed_source[MAX_PATH],observed_destination[MAX_PATH],first_choice[80];
static void *allocate(void){allocated++;return malloc(16);}
static void release(void *p){if(p){assert(allocated>0);allocated--;free(p);}}
#define free release
static int prepareOp(void){return prepare_ok;}
static void opDone(void){loading=0;}
static void refresh(void){refreshes++;}
static void dashLoadingBegin(const char *title){assert(title&&!loading);loading=1;}
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail){(void)icon;(void)detail;assert(title&&body&&!loading);messages++;}
static int fullPath(const FILEINFO *f,char *out,int size){return snprintf(out,size,"%s%s%s",fb.dir,f->name,f->stats.AttrFile&sceMcFileAttrSubdir?"/":"")<size;}
static int dashModalChoice(const char *title,const char *const *items,int count,int initial){
 assert(title&&!initial&&(count==2||count==3||count==5));
 if(!strcmp(title,"Create archive")) {
  assert(count==(kind==FILER_SAVE_PS1?3:2));
  assert(!strcmp(items[1],"PSV - PS3 export"));
  if(count==3)assert(!strcmp(items[2],"PSX - Action Replay / GameShark"));
 }
 strcpy(first_choice,items[0]);return choice;
}
static int saveChoice(const char *title,const char *subtitle,const char *const *items,int count){
 if(!strcmp(title,"Create archive"))assert(subtitle&&!strcmp(subtitle,kind==FILER_SAVE_PS1?"PS1 save":"PS2 save"));
 else assert(!subtitle);
 return dashModalChoice(title,items,count,0);
}
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int count,int initial){
 const char *labels[3];assert(!strcmp(title,"Create archive")&&subtitle&&!strcmp(subtitle,clipFiles[0].name));
 for(int i=0;i<count;i++) {
  assert(items[i].icon==DI_MC&&!items[i].disabled);labels[i]=items[i].label;
  if(i==1)assert(items[i].detail&&!strcmp(items[i].detail,kind==FILER_SAVE_PS1?"PS1 save":"PS2 save"));
  else assert(!items[i].detail);
 }
 return dashModalChoice(title,labels,count,initial);
}
static int dashPickPath(const char *title,const char *start,int mode,const char *ext,char *out,int size){
 (void)start;assert(title&&mode==DASH_PICK_FOLDER&&!ext&&reads==1&&!loading);
 switches++;snprintf(out,size,"usb1:/output/");return pick_ok;
}
static int getFilePath(char *out,int mode){assert(mode==DIR_CNF);return dashPickPath("Destination",fb.dir,DASH_PICK_FOLDER,NULL,out,MAX_PATH)?0:-1;}
static int dashModalFilename(const char *title,char *name,int capacity,const char *folder){assert(title&&name[0]&&capacity>=31&&switches&&!strcmp(folder,"usb1:/output/"));prompts++;return prompt_ok;}
static int filenameKeyboard(char *name,int capacity,const char *folder){return dashModalFilename("Filename",name,capacity,folder);}
static int filerConfirmExploitModify(const char *path,const FILEINFO *file){assert(!strcmp(path,"usb1:/output/")&&!file);return 1;}
static int isMcLikePath(const char *path){return !strncmp(path,"mc",2)||!strncmp(path,"vmc",3);}
static unsigned getIopResetGeneration(void){return 1;}
static void dashStrCopy(char *out,const char *in,int size){snprintf(out,size,"%s",in);}
static void dashToast(int type,const char *message){(void)type;assert(message);}
static int filerIsExploitProtectedPath(const char *folder,const FILEINFO *file){(void)folder;(void)file;return 0;}
static int filerArchiveClipboardKind(void){return nclipFiles==1?cached_kind:FILER_SAVE_NONE;}
static void source(const char *path){assert(!switches&&reads==0);reads++;strcpy(observed_source,path);}
static int filerLoadSave(const char *path,SaveArchive *save,uint8_t **data,char *message,int size){
 (void)message;(void)size;source(path);if(!read_ok)return 0;*data=allocate();save->ps1=expected_ps1;return 1;
}
static void saveArchiveFreeSpy(SaveArchive *save){freed_saves++;memset(save,0,sizeof(*save));}
#define saveArchiveFree saveArchiveFreeSpy
static int filerExtractSave(const SaveArchive *save,const char *destination,char *message,int size){
 assert(save->ps1==expected_ps1&&allocated==1&&switches==1);extracts++;snprintf(message,size,"Extracted save");strcpy(observed_destination,destination);return 1;
}
static int filerCaptureArchiveClipboard(int card_type,char *message,int size){
 (void)message;(void)size;assert(card_type==fb.card_type);cached_kind=FILER_SAVE_NONE;
 if(nclipFiles!=1)return 0;
 char path[MAX_PATH];assert(strlen(clipPath)+strlen(clipFiles[0].name)<sizeof(path));strcpy(path,clipPath);strcat(path,clipFiles[0].name);
 source(path);cached_kind=kind;return 1;
}
static int filerCreateClipboardArchive(int format,uint8_t **data,size_t *length,char *name,int name_size,char *message,int size){
 (void)message;(void)size;assert(filerArchiveClipboardKind()==kind&&format==expected_format&&reads==1&&switches==1);if(!read_ok)return -1;
 *data=allocate();*length=16;snprintf(name,name_size,"SAVE.%s",format==SAVE_OUTPUT_PSV?"PSV":format==SAVE_OUTPUT_PSU?"psu":format==SAVE_OUTPUT_PSX?"psx":"mcs");return 1;
}
static int filerFinishArchiveClipboard(const char *destination,char *message,int size){
 (void)destination;(void)message;(void)size;assert(writes==1&&!allocated&&write_ok);finish_calls++;
 if(browser_cut)nclipFiles=0;
 return 1;
}
static int filerWriteArchive(const uint8_t *data,size_t length,const char *destination,char *message,int size){
 assert(data&&length==16&&allocated==1&&reads==1&&switches==1);writes++;strcpy(observed_destination,destination);snprintf(message,size,"Archive created");return write_ok?1:-1;
}
static unsigned char *filerReadPs1Card(const char *path,char *message,int size){(void)message;(void)size;source(path);return read_ok?allocate():NULL;}
static int filerSavePs1Card(const uint8_t *data,const char *destination,char *message,int size){return filerWriteArchive(data,16,destination,message,size);}
'''
code+=function(dash,'static int targets(')+function(dash,'static FILEINFO *singleSaveTarget(void)')
for signature in ['static void opCopy(int cut)','static void opExtractSave(void)','static void opCreateArchive(int kind)','static void opExportPs1(void)']:
    code+=function(dash,signature)
for signature in ['static void classicExtractSave(','static void classicCreateArchive(','static void classicExportPs1(']:
    code+=function(classic,signature)
code+=r'''
static void reset(int ps1){
 assert(!allocated);memset(&fb,0,sizeof(fb));fb.n=1;fb.card_type=ps1?1:2;
 strcpy(fb.dir,ps1?"mc0:/":"vmc1:/");strcpy(fb.files[0].name,"SAVE");
 fb.files[0].stats.AttrFile=ps1?0:sceMcFileAttrSubdir;kind=ps1?FILER_SAVE_PS1:FILER_SAVE_PS2;expected_ps1=ps1;
 choice=0;pick_ok=prompt_ok=prepare_ok=read_ok=write_ok=1;reads=switches=writes=extracts=prompts=loading=freed_saves=messages=refreshes=0;
 nclipFiles=browser_cut=cached_kind=finish_calls=0;
 first_choice[0]=observed_source[0]=observed_destination[0]=0;
}
static void copySave(int cut){
 opCopy(cut);assert(reads==1&&nclipFiles==1&&cached_kind==kind);
 strcpy(fb.dir,"usb1:/output/");fb.n=0;fb.sel=0;switches=1;
}
int main(void){
 for(int ps1=0;ps1<2;ps1++)for(int format=0;format<(ps1?3:2);format++)for(int native=0;native<2;native++) {
  reset(ps1);copySave(format&1);choice=format;expected_format=format==2?SAVE_OUTPUT_PSX:format==1?SAVE_OUTPUT_PSV:ps1?SAVE_OUTPUT_MCS:SAVE_OUTPUT_PSU;
  if(native)classicCreateArchive(fb.dir,fb.msg,sizeof(fb.msg));else opCreateArchive(kind);
  assert(reads==1&&switches==1&&writes==1&&prompts==1&&finish_calls==1&&!allocated&&!loading);
  assert(!strcmp(first_choice,ps1?"MCS - PS1 save backup":"PSU - PS2 save backup (EMS/wLE)"));
  assert(!strcmp(observed_destination,format==2?"usb1:/output/SAVE.psx":format==1?"usb1:/output/SAVE.PSV":ps1?"usb1:/output/SAVE.mcs":"usb1:/output/SAVE.psu"));
 }
 for(int native=0;native<2;native++)for(int ps1=0;ps1<2;ps1++) {
  reset(ps1);strcpy(fb.files[0].name,"archive.PSV");fb.files[0].stats.AttrFile=0;
  if(native)classicExtractSave(fb.dir,&fb.files[0],fb.msg,sizeof(fb.msg));else opExtractSave();
  assert(reads==1&&switches==1&&extracts==1&&freed_saves==1&&!allocated&&!loading);
  assert(!strcmp(observed_destination,"usb1:/output/"));
 }
 for(int native=0;native<2;native++)for(int selected=0;selected<5;selected++) {
  reset(1);choice=selected;
  if(native)classicExportPs1(fb.dir,&fb.files[0],1,fb.msg,sizeof(fb.msg));else opExportPs1();
  assert(reads==1&&writes==1&&!allocated&&prompts==!selected&&!strcmp(observed_source,"mc0:/"));
  const char *names[]={"card.mcr","MC1.vmc","MC2.vmc","SLOT0.VMC","SLOT1.VMC"};
  assert(!strcmp(observed_destination+13,names[selected]));
 }
 for(int native=0;native<2;native++)for(int failure=0;failure<4;failure++) {
  reset(1);copySave(1);expected_format=SAVE_OUTPUT_MCS;
  if(failure==0)choice=-1;else if(failure==1)read_ok=0;else if(failure==2)prompt_ok=0;else write_ok=0;
  if(native)classicCreateArchive(fb.dir,fb.msg,sizeof(fb.msg));else opCreateArchive(kind);
  assert(writes==(failure==3)&&!finish_calls&&!allocated&&!loading&&nclipFiles==1);
 }
 reset(1);fb.n=2;fb.sel=1;strcpy(fb.files[1].name,"OTHER");fb.nmarked=1;fb.mark[0]=1;
 expected_format=SAVE_OUTPUT_MCS;copySave(0);opCreateArchive(FILER_SAVE_PS1);
 assert(!strcmp(observed_source,"mc0:/SAVE")&&!allocated);
 reset(1);opCreateArchive(FILER_SAVE_PS1);assert(!reads&&!writes&&!finish_calls);
 reset(1);pick_ok=0;opExtractSave();assert(!extracts&&!allocated&&freed_saves==1);
 reset(1);read_ok=0;opExtractSave();assert(!switches&&!allocated&&!loading);
 puts("PASS: both browsers' clipboard PS1/PS2 archiving in empty destinations, direct extraction, card exports, canceled/failed writes retain Cut sources");
}
'''
with tempfile.TemporaryDirectory(prefix='save-actions-') as temp:
    temp=Path(temp)
    (temp/'test.c').write_text(code)
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC','cc'),'-std=c99','-Wall','-Wextra','-Werror',*flags,
                    '-I',str(root/'include'),str(temp/'test.c'),'-o',str(temp/'test')],check=True)
    subprocess.run([str(temp/'test')],check=True,timeout=20)
