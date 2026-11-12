"""Exercise production import/export transactions on bounded POSIX adapters."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
stub = r'''
#ifndef SAVE_TEST_PLATFORM
#define SAVE_TEST_PLATFORM
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <dirent.h>
#include <errno.h>
#include <assert.h>
#include "vmc_control.h"
#include "save_archive.h"
typedef uint64_t u64;typedef int64_t s64;
#define MAX_PATH 1025
#define MAX_NAME 256
#define MAX_ENTRY 32
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_TRUNC O_TRUNC
#define FIO_O_CREAT O_CREAT
#define FIO_S_IFDIR S_IFDIR
#define FIO_S_IFREG S_IFREG
#define sceMcFileAttrSubdir 0x20
typedef struct {uint8_t bytes[8];} sceMcStDateTime;
typedef struct {unsigned AttrFile,Reserve1,Reserve2,FileSizeByte;char EntryName[32];sceMcStDateTime _Create,_Modify;} sceMcTblGetDir;
typedef struct {unsigned mode,private_0;uint8_t ctime[8],mtime[8];} iox_stat_t;
typedef struct {char name[256];struct {unsigned AttrFile,Reserve2,FileSizeByte;sceMcStDateTime _Create,_Modify;}stats;} FILEINFO;
typedef struct {int PSU_HugeNames,PSU_DateNames,PSU_NoOverwrite;} SETTING;
extern SETTING *setting;
int fileShowTitles(void);int filerGetGameTitle(const char*,const FILEINFO*,unsigned char*);
char *transcpy_sjis(char*,const unsigned char*);void genLimObjName(char*,int);
extern int vmcMounted[2], nclipFiles, browser_cut;
extern unsigned clipIopResetGeneration;
extern FILEINFO clipFiles[MAX_ENTRY];extern char clipPath[MAX_PATH];
enum { FILER_SAVE_NONE, FILER_SAVE_PS1, FILER_SAVE_PS2, FILER_ARCHIVE_PS1, FILER_ARCHIVE_PS2, FILER_CARD_PS1, FILER_SAVE_MIXED };
typedef struct
{
	u64 written_total;
	int current_speed;
	int average_speed;
	int remaining_seconds;
	u64 file_index; /* One-based file or save within this operation. */
	u64 file_count;
} DashTransferStats;
u64 Timer(void);int DashIsActive(void);
int DashFileTransferProgress(const char*,const char*,u64,u64,const DashTransferStats*);
int DashFileOperationStatus(const char*,const char*,u64,u64);
void DashFileOperationEnd(void);void nonDialog(char*);void drawMsg(const char*);
int filerCardInfo(const char *,VmcInfo *);
int filerExtractSave(const SaveArchive *, const char *, char *, int);
int filerPrepareMemoryCardRead(int);int mcGetInfo(int,int,int*,int*,int*);int mcSync(int,void*,int*);
int genFixPath(const char*,char*);int genOpen(const char*,int);s64 genLseek(int,s64,int);int genRead(int,void*,int);int genWrite(int,void*,int);int genClose(int);
int genDopen(char*);int genDclose(int);int genMkdir(const char*,int);int genRemove(char*);int genRmdir(char*);
int genCmpFileExt(const char*,const char*);int genCanRenamePath(const char*);int genRenameNoReplace(const char*,const char*);
int fileXioDevctl(const char*,int,void*,unsigned,void*,unsigned);int fileXioGetStat(const char*,iox_stat_t*);int fileXioChStat(const char*,iox_stat_t*,unsigned);
int mcGetDir(int,int,const char*,int,int,sceMcTblGetDir*);int mcSetFileInfo(int,int,const char*,sceMcTblGetDir*,int);
int prepareTransferDeviceStacks(const char*,const char*);unsigned getIopResetGeneration(void);int getDir(const char*,FILEINFO*);
int filerPrepareClipboardTransfer(const char*,char*,int);
int isPathDeviceStackLoaded(const char*);int filerConfirmExploitDelete(const char*,const FILEINFO*);
int delete(const char*,const FILEINFO*);
int filerIsPs1Image(const char*);
void filerExtractLabel(const char*,char*,int);void filerClearArchiveClipboard(void);
#endif
'''
fileops = (root / 'src/filer_fileops.c').read_text()
name_limits = fileops[fileops.index('void genLimObjName('):fileops.index('\nint genRmdir(')]
code = r'''
#define _DEFAULT_SOURCE
#include "filer_saves.h"
#include "save_archive.h"
#include <strings.h>
int vmcMounted[2]={1,1},nclipFiles,browser_cut;
static SETTING config;SETTING *setting=&config;
static int show_titles,batch_titles;static const char *game_title="";
int fileShowTitles(void){return show_titles;}
int filerGetGameTitle(const char *path,const FILEINFO *file,unsigned char *out){
 assert(path[0]&&path[strlen(path)-1]=='/'&&file->name[0]);
 if(batch_titles){snprintf((char*)out,66,"Title %.59s",file->name);return 0;}
 strcpy((char*)out,game_title);return game_title[0]?0:-1;
}
char *transcpy_sjis(char *out,const unsigned char *in){return strcpy(out,(const char*)in);}
PRODUCTION_NAME_LIMITS
unsigned clipIopResetGeneration=1;FILEINFO clipFiles[MAX_ENTRY];char clipPath[MAX_PATH];
static int card_type=1,free_units=15,fail_after=-1,fail_close,fail_rename,handles,physical_mkdirs;
static unsigned generation=1;
static int rename_calls,fail_after_archive;
static int write_handles[1024];
static int source_loaded=1,delete_calls,delete_failure,extract_hook;
static int open_calls,dir_calls,prepare_calls,incompatible,restore_ok=1;
static char changed_archive[MAX_PATH];
int filerPrepareMemoryCardRead(int port){(void)port;return 0;}
int mcGetInfo(int port,int slot,int *type,int *units,int *format){(void)port;(void)slot;*type=card_type;*units=free_units;if(format)*format=1;return 0;}
int mcSync(int x,void *y,int *result){(void)x;(void)y;if(result)*result=0;return 1;}
int genFixPath(const char *in,char *out){strcpy(out,in);return 0;}
int genOpen(const char *p,int flags){open_calls++;int f=open(p,flags,0600);if(f>=0){assert(f<1024);handles++;write_handles[f]=(flags&O_ACCMODE)!=O_RDONLY;}return f<0?-errno:f;}
s64 genLseek(int f,s64 offset,int how){return lseek(f,offset,how);}
int genRead(int f,void *p,int n){return read(f,p,n>17?17:n);}
int genWrite(int f,void *p,int n){if(fail_after==0)return -EIO;if(fail_after>0)fail_after--;return write(f,p,n>13?13:n);}
int genClose(int f){
 handles--;int wrote=write_handles[f];write_handles[f]=0;int result=close(f);
 if(wrote && !result && extract_hook==1){int fd=open(changed_archive,O_RDWR);assert(fd>=0);uint8_t b;assert(pread(fd,&b,1,256)==1);b^=1;assert(pwrite(fd,&b,1,256)==1);close(fd);}
 if(wrote && !result && extract_hook==2)generation++;
 if(wrote && !result && extract_hook==3){source_loaded=0;restore_ok=0;}
 if(wrote&&!result&&fail_after_archive>0&&!--fail_after_archive)fail_after=0;
 return fail_close?-EIO:result;
}
int genDopen(char *p){return genOpen(p,O_RDONLY|O_DIRECTORY);}
int genDclose(int f){return genClose(f);}
int genMkdir(const char *p,int mode){(void)mode;if(!strncmp(p,"mc",2))physical_mkdirs++;return mkdir(p,0700);}
int genRemove(char *p){return unlink(p);}
int genRmdir(char *p){return rmdir(p);}
int genCmpFileExt(const char *p,const char *ext){const char *dot=strrchr(p,'.');return dot&&!strcasecmp(dot+1,ext);}
int genCanRenamePath(const char *p){(void)p;return 1;}
int genRenameNoReplace(const char *from,const char *to){
 rename_calls++;
 if(fail_rename)return -ENOSYS;
 if(!access(to,F_OK))return -EEXIST;
 return rename(from,to);
}
int fileXioDevctl(const char *p,int cmd,void *arg,unsigned arglen,void *buf,unsigned buflen){
 (void)p;(void)arg;(void)arglen;(void)buflen;if(cmd!=VMCCTL_GET_INFO)return -EINVAL;
 VmcInfo *info=buf;info->type=card_type;info->free_units=free_units;info->unit_bytes=card_type==1?8192:1024;return 0;
}
int fileXioGetStat(const char *p,iox_stat_t *out){struct stat s;int r=stat(p,&s);memset(out,0,sizeof(*out));out->ctime[4]=out->mtime[4]=1;return r;}
int fileXioChStat(const char *p,iox_stat_t *out,unsigned flags){(void)p;assert(flags==0xFEED&&out->private_0);return 0;}
int mcGetDir(int p,int s,const char *path,int flags,int count,sceMcTblGetDir *info){(void)p;(void)s;(void)path;(void)flags;(void)count;(void)info;return 0;}
int mcSetFileInfo(int p,int s,const char *path,sceMcTblGetDir *info,int flags){(void)p;(void)s;(void)path;(void)info;(void)flags;return 0;}
int prepareTransferDeviceStacks(const char *a,const char *b){(void)a;(void)b;prepare_calls++;return incompatible?-2:0;}
int filerPrepareClipboardTransfer(const char *destination,char *message,int size){
 int result=prepareTransferDeviceStacks(clipPath,destination);
 if(result<0){snprintf(message,size,"Incompatible drivers to perform action");return result;}
 if(!restore_ok || (!strncmp(clipPath,"vmc",3)&&!vmcMounted[clipPath[3]-'0'])){
  snprintf(message,size,"The clipboard source device is unavailable.");return -1;
 }
 if(!source_loaded){source_loaded=1;generation++;}
 clipIopResetGeneration=generation;return 0;
}
unsigned getIopResetGeneration(void){return generation;}
int isPathDeviceStackLoaded(const char *path){(void)path;return source_loaded;}
int filerConfirmExploitDelete(const char *path,const FILEINFO *file){(void)path;(void)file;return 1;}
int delete(const char *parent,const FILEINFO *file){
 char path[MAX_PATH];snprintf(path,sizeof(path),"%s%s",parent,file->name);delete_calls++;
 if(delete_failure)return -EIO;
 if(file->stats.AttrFile&sceMcFileAttrSubdir){
  DIR *dir=opendir(path);assert(dir);struct dirent *e;
  while((e=readdir(dir)))if(strcmp(e->d_name,".")&&strcmp(e->d_name,"..")){
   char child[MAX_PATH];assert(strlen(path)+strlen(e->d_name)+2<sizeof(child));strcpy(child,path);strcat(child,"/");strcat(child,e->d_name);assert(!unlink(child));
  }
  closedir(dir);return rmdir(path);
 }
 return unlink(path);
}
int getDir(const char *p,FILEINFO *f){
 dir_calls++;DIR *dir=opendir(p);if(!dir)return -EIO;struct dirent *e;int count=0;
 while(count<MAX_ENTRY-2 && (e=readdir(dir))){
  if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
  memset(&f[count],0,sizeof(f[count]));strcpy(f[count].name,e->d_name);
  char path[MAX_PATH];snprintf(path,sizeof(path),"%s/%s",p,e->d_name);struct stat st;assert(!stat(path,&st));
  f[count].stats.AttrFile=S_ISDIR(st.st_mode)?0x8427:0x8497;f[count].stats.FileSizeByte=st.st_size;
  f[count].stats._Create.bytes[4]=f[count].stats._Modify.bytes[4]=1;
  count++;
 }
 closedir(dir);return count;
}

static int progress_events,phase_events,progress_partial,progress_complete,classic_events,classic_closes;
static int dashboard_active=1;static u64 progress_tick;
static int progress_ends;
static unsigned seen_stages;static u64 seen_ordinals;
static char last_progress_action[80],last_progress_name[128];
u64 Timer(void){progress_tick+=7;return progress_tick;}
int DashIsActive(void){return dashboard_active;}
int DashFileOperationStatus(const char *action,const char *name,u64 index,u64 count){
 assert(action&&name&&name[0]&&index>=1&&index<=count&&count<=MAX_ENTRY);
 if(!dashboard_active)return 0;
 phase_events++;snprintf(last_progress_action,sizeof(last_progress_action),"%s",action);
 snprintf(last_progress_name,sizeof(last_progress_name),"%s",name);
 if(!strcmp(action,"Reading save"))seen_stages|=1;
 if(!strcmp(action,"Preparing archive"))seen_stages|=2;
 if(!strcmp(action,"Creating archive"))seen_stages|=4;
 if(!strcmp(action,"Reading archive"))seen_stages|=8;
 if(!strcmp(action,"Opening archive"))seen_stages|=16;
 if(!strcmp(action,"Extracting save"))seen_stages|=32;
 if(!strcmp(action,"Verifying source"))seen_stages|=64;
 seen_ordinals|=1ULL<<index;
 return 1;
}
int DashFileTransferProgress(const char *action,const char *name,u64 remaining,u64 total,const DashTransferStats *stats){
 assert(action&&name&&name[0]&&remaining<=total&&stats&&stats->file_index>=1&&stats->file_index<=stats->file_count);
 assert(stats->average_speed>=-1&&stats->remaining_seconds>=-1);
 if(!dashboard_active)return 0;
 progress_events++;snprintf(last_progress_action,sizeof(last_progress_action),"%s",action);
 snprintf(last_progress_name,sizeof(last_progress_name),"%s",name);
 seen_ordinals|=1ULL<<stats->file_index;
 if(remaining&&remaining<total)progress_partial++;
 if(!remaining){assert(!handles);progress_complete++;assert(stats->remaining_seconds==0);}
 return 1;
}
void DashFileOperationEnd(void){if(dashboard_active){assert(!handles);progress_ends++;}}
void nonDialog(char *text){if(text){assert(text[0]);classic_events++;}else classic_closes++;}
void drawMsg(const char *text){assert(text);}
#include "PRODUCTION_SAVES"
static int rememberAndProbe(int type){
 int opened=open_calls,listed=dir_calls,prepared=prepare_calls,progress=progress_events,phases=phase_events;
 filerRememberArchiveClipboard(type);
 filerArchiveClipboardKind();
 assert(opened==open_calls&&listed==dir_calls&&prepared==prepare_calls&&!archive_clip_data&&progress==progress_events&&phases==phase_events);
 return filerProbeArchiveClipboard("storage/")!=FILER_SAVE_NONE;
}
static void put(const char *name,const void *p,size_t n){FILE *f=fopen(name,"wb");assert(f&&fwrite(p,1,n,f)==n);fclose(f);}
static void no_temps(const char *p){DIR *dir=opendir(p);assert(dir);struct dirent *e;while((e=readdir(dir)))assert(strncmp(e->d_name,"LSI",3));closedir(dir);assert(!handles);}

static void startArchiveBatch(const char *parent,int count,int cut){
 assert(!mkdir(parent,0700));filerClearArchiveClipboard();memset(clipFiles,0,sizeof(clipFiles));
 strcpy(clipPath,parent);nclipFiles=count;browser_cut=cut;card_type=0;show_titles=0;game_title="";
 memset(&config,0,sizeof(config));
}
static void makeArchiveBatchItem(const char *parent,int index,int ps1,int wrapped){
 char source[MAX_PATH],path[MAX_PATH];FILEINFO *file=&clipFiles[index];
 snprintf(file->name,sizeof(file->name),"BATCH-%c",'A'+index);
 assert(snprintf(source,sizeof(source),"%s%s",parent,file->name)<(int)sizeof(source));
 file->stats.AttrFile=ps1&&!wrapped?0x9017:0x8427;file->stats.FileSizeByte=ps1&&!wrapped?8192:0;
 const uint8_t date[8]={0,56,34,12,(uint8_t)(index+1),11,0xea,7};
 memcpy(&file->stats._Create,date,8);memcpy(&file->stats._Modify,date,8);
 if(!ps1||wrapped)assert(!mkdir(source,0700));
 if(ps1){
  uint8_t data[8192]={0};memcpy(data,"SC",2);data[8]=index+1;
  if(wrapped){assert(snprintf(path,sizeof(path),"%s/%s",source,file->name)<(int)sizeof(path));put(path,data,sizeof(data));}
  else put(source,data,sizeof(data));
 }else{
  uint8_t iconsys[964]={0},icon[257]={0},data[123]={0};memcpy(iconsys,"PS2D",4);strcpy((char*)iconsys+260,"icon.icn");data[0]=index+1;
  assert(snprintf(path,sizeof(path),"%s/icon.sys",source)<(int)sizeof(path));put(path,iconsys,sizeof(iconsys));
  assert(snprintf(path,sizeof(path),"%s/icon.icn",source)<(int)sizeof(path));put(path,icon,sizeof(icon));
  assert(snprintf(path,sizeof(path),"%s/data",source)<(int)sizeof(path));put(path,data,sizeof(data));
 }
}
int main(int argc,char **argv){
 assert(argc==2&&!chdir(argv[1]));mkdir("vmc0:",0700);mkdir("storage",0700);
 unsigned char save[8320]={0};save[0]=0x51;memcpy(save+10,"BASLUS-TEST",11);memcpy(save+128,"SC",2);put("input.mcs",save,sizeof(save));
 char message[MAX_PATH];
 for(int failure=0;failure<3;failure++){
   fail_after=failure==0?7:-1;fail_close=failure==1;
   assert(filerImportSave("input.mcs","vmc0:/",message,sizeof(message))==(failure==2?1:-1));
   fail_close=0;no_temps("vmc0:");
 }
 assert(filerImportSave("input.mcs","vmc0:/",message,sizeof(message))<0&&strstr(message,"already exists"));
 struct stat st;assert(!stat("vmc0:/BASLUS-TEST",&st)&&st.st_size==8192);
 unlink("vmc0:/BASLUS-TEST");free_units=0;
 assert(filerImportSave("input.mcs","vmc0:/",message,sizeof(message))<0&&strstr(message,"free space"));no_temps("vmc0:");
 free_units=8192;card_type=2;
 assert(filerImportSave("input.mcs","vmc0:/",message,sizeof(message))==1);
 assert(!stat("vmc0:/BASLUS-TEST/BASLUS-TEST",&st)&&st.st_size==8192);
 unlink("vmc0:/BASLUS-TEST/BASLUS-TEST");rmdir("vmc0:/BASLUS-TEST");no_temps("vmc0:");
 assert(filerImportSave("input.mcs","storage/",message,sizeof(message))==1);
 assert(!stat("storage/BASLUS-TEST/BASLUS-TEST",&st)&&st.st_size==8192);
 save[128]=0;put("bad.mcs",save,sizeof(save));
 assert(filerImportSave("bad.mcs","vmc0:/",message,sizeof(message))<0);no_temps("vmc0:");
 /* A physical PS1 card receives one flat save, never a folder. */
 card_type=1;free_units=15;
 for(int port=0;port<2;port++){
   char root[16],path[MAX_PATH];snprintf(root,sizeof(root),"mc%d:",port);assert(!mkdir(root,0700));
   snprintf(root,sizeof(root),"mc%d:/",port);
   assert(filerImportSave("input.mcs",root,message,sizeof(message))==1);
   snprintf(path,sizeof(path),"%sBASLUS-TEST",root);assert(!stat(path,&st)&&S_ISREG(st.st_mode)&&st.st_size==8192);
   VmcInfo info;assert(filerCardInfo(root,&info)&&info.type==1&&info.free_units==15&&info.unit_bytes==8192);
   unsigned char *snapshot=filerReadPs1Card(root,message,sizeof(message));
   assert(snapshot&&ps1CardOffset(snapshot,PS1_CARD_SIZE)==0&&snapshot[128]==0x51);
   assert(!memcmp(snapshot+138,"BASLUS-TEST",11)&&!memcmp(snapshot+8192,"SC",2));free(snapshot);
   assert(filerImportSave("input.mcs",root,message,sizeof(message))<0&&strstr(message,"already exists"));
   assert(!physical_mkdirs);no_temps(root);
 }
 unsigned char *card=malloc(PS1_CARD_SIZE);ps1CardFormat(card);
 for(int i=0;i<4;i++){
   const char *names[]={"MC1.vmc","MC2.vmc","SLOT0.VMC","SLOT1.VMC"};char path[MAX_PATH];snprintf(path,sizeof(path),"storage/%s",names[i]);
   fail_after=5;assert(filerSavePs1Card(card,path,message,sizeof(message))<0);no_temps("storage");
   fail_after=-1;assert(filerSavePs1Card(card,path,message,sizeof(message))==1);
   assert(!stat(path,&st)&&st.st_size==131072);
   assert(filerSavePs1Card(card,path,message,sizeof(message))<0);no_temps("storage");
 }
 free(card);
 /* Single-save archives snapshot the source before a destination can retire its stack. */
 FILEINFO selected={0};strcpy(selected.name,"BASLUS-TEST");selected.stats.AttrFile=0x8497;
 selected.stats.FileSizeByte=8192;uint8_t *archive;size_t archive_size;char archive_name[MAX_NAME];
 assert(filerSaveKind("mc0:/",&selected,1)==FILER_SAVE_PS1);
 for(int format=SAVE_OUTPUT_PSV;format<=SAVE_OUTPUT_PSX;format++) {
  assert(filerCreateArchive("mc0:/BASLUS-TEST",&selected,FILER_SAVE_PS1,format,&archive,&archive_size,
                            archive_name,sizeof(archive_name),message,sizeof(message))==1);
  SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name)&&parsed.ps1&&parsed.files[0].size==8192);
  saveArchiveFree(&parsed);free(archive);
 }
 selected.stats.AttrFile=0x9027;
 assert(filerSaveKind("storage/",&selected,0)==FILER_SAVE_PS1);
 assert(filerCreateArchive("storage/BASLUS-TEST",&selected,FILER_SAVE_PS1,SAVE_OUTPUT_MCS,&archive,&archive_size,
                           archive_name,sizeof(archive_name),message,sizeof(message))==1);free(archive);
 unsigned char iconsys[964]={0},icon[257]={0},payload[123]={0};
 memcpy(iconsys,"PS2D",4);strcpy((char*)iconsys+260,"icon.icn");
 mkdir("storage/PS2SAVE",0700);put("storage/PS2SAVE/icon.sys",iconsys,sizeof(iconsys));
 put("storage/PS2SAVE/icon.icn",icon,sizeof(icon));put("storage/PS2SAVE/data",payload,sizeof(payload));
 put("storage/PS2SAVE/empty",payload,0);
 strcpy(selected.name,"PS2SAVE");selected.stats.AttrFile=0x8427;
 assert(filerSaveKind("storage/",&selected,0)==FILER_SAVE_PS2);
 for(int format=SAVE_OUTPUT_PSU;format<=SAVE_OUTPUT_PSV;format++) {
  assert(filerCreateArchive("storage/PS2SAVE/",&selected,FILER_SAVE_PS2,format,&archive,&archive_size,
                            archive_name,sizeof(archive_name),message,sizeof(message))==1);
  char destination[MAX_PATH];snprintf(destination,sizeof(destination),"storage/%s",archive_name);
  fail_after=0;assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))<0);no_temps("storage");
  fail_after=-1;fail_close=1;assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))<0);no_temps("storage");
  fail_close=0;fail_rename=1;int renames_before=rename_calls;
  assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))==1&&rename_calls==renames_before);no_temps("storage");fail_rename=0;
  if(format==SAVE_OUTPUT_PSU) {
   config.PSU_NoOverwrite=1;
   assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))==0&&strstr(message,"skipped"));
   config.PSU_NoOverwrite=0;
   assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))==1);no_temps("storage");
  } else assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))<0&&strstr(message,"already exists"));
  strcpy(selected.name,archive_name);selected.stats.AttrFile=0x8497;selected.stats.FileSizeByte=archive_size;
  assert(filerSaveKind("storage/",&selected,0)==FILER_ARCHIVE_PS2);
  SaveArchive parsed;uint8_t *snapshot;assert(filerLoadSave(destination,&parsed,&snapshot,message,sizeof(message)));
  // Removing the archive after reading simulates a source device going away in the picker.
  assert(!unlink(destination));card_type=1;
  assert(filerExtractSave(&parsed,"mc1:/",message,sizeof(message))<0&&strstr(message,"PS2"));
  card_type=2;assert(filerExtractSave(&parsed,"vmc0:/",message,sizeof(message))==1);
  assert(!stat("vmc0:/PS2SAVE/empty",&st)&&!st.st_size);
  unlink("vmc0:/PS2SAVE/icon.sys");unlink("vmc0:/PS2SAVE/icon.icn");unlink("vmc0:/PS2SAVE/data");unlink("vmc0:/PS2SAVE/empty");rmdir("vmc0:/PS2SAVE");
  saveArchiveFree(&parsed);free(snapshot);free(archive);
  strcpy(selected.name,"PS2SAVE");selected.stats.AttrFile=0x8427;
 }
 // The clipboard path honors PSU naming settings and the original folder modification date.
 strcpy(clipPath,"storage/");memset(clipFiles,0,sizeof(clipFiles));clipFiles[0]=selected;
 const uint8_t modified[8]={0,56,34,12,9,11,0xea,7};
 memcpy(&clipFiles[0].stats._Modify,modified,8);nclipFiles=1;browser_cut=0;card_type=0;
 game_title="Example: Game/Save?";
 for(int titles=0;titles<2;titles++)for(int huge=0;huge<2;huge++)for(int dated=0;dated<2;dated++)for(int nover=0;nover<2;nover++) {
  show_titles=titles;config.PSU_HugeNames=huge;config.PSU_DateNames=dated;config.PSU_NoOverwrite=nover;
  filerRememberArchiveClipboard(0);
  assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  char expected[MAX_NAME];snprintf(expected,sizeof(expected),"%s%s.psu",
   huge?"PS2SAVE_Example_ Game_Save_":titles?"Example_ Game_Save_":"PS2SAVE",dated?"_2026-11-09_12-34-56":"");
  assert(!strcmp(archive_name,expected));
  SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name));
  assert(!strcmp(parsed.folder.name,"PS2SAVE")&&!memcmp(parsed.folder.modified,modified,8));
  saveArchiveFree(&parsed);free(archive);
 }
 // Missing titles fall back to the game folder. Long titles fit without a keyboard.
 show_titles=0;config.PSU_HugeNames=config.PSU_DateNames=1;config.PSU_NoOverwrite=0;
 game_title="";
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(!strcmp(archive_name,"PS2SAVE_2026-11-09_12-34-56.psu"));free(archive);
 char long_title[65];memset(long_title,'A',64);long_title[64]=0;game_title=long_title;
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(strlen(archive_name)>80&&!strncmp(archive_name,"PS2SAVE_",8)&&strstr(archive_name,"_2026-11-09_12-34-56.psu"));free(archive);
 assert(filerCreateClipboardArchive("mc1:/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(strlen(archive_name)==32&&!strcmp(archive_name,"PS2SAVE_AAAAAAAAAAAAAAAAAAAA.psu"));free(archive);
 // PSU preferences leave the PS3-required PSV filename unchanged.
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSV,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(!strcmp(archive_name,"PS2SAVE.PSV"));free(archive);
 config=(SETTING){0};game_title="";filerClearArchiveClipboard();
 // A device without native rename still creates archives and extracts them.
 save[128]='S';
 const char *devices[]={"mmce0:","mmce1:","usb0:","mx4sio:","pfs0:","ata0:","cf0:"};
 const int formats[]={SAVE_OUTPUT_PSU,SAVE_OUTPUT_PSV,SAVE_OUTPUT_MCS,SAVE_OUTPUT_PSV,SAVE_OUTPUT_PSX};
 fail_rename=1;int renames_before=rename_calls;
 for(unsigned d=0;d<sizeof(devices)/sizeof(*devices);d++)for(int f=0;f<5;f++) {
  mkdir(devices[d],0700);char folder[MAX_PATH],destination[MAX_PATH];
  snprintf(folder,sizeof(folder),"%s/case%d/",devices[d],f);assert(!mkdir(folder,0700));
  FILEINFO item={0};strcpy(item.name,f<2?"PS2SAVE":"BASLUS-TEST");item.stats.AttrFile=f<2?0x8427:0x8497;
  assert(filerCreateArchive(f<2?"storage/PS2SAVE/":"mc0:/BASLUS-TEST",&item,f<2?FILER_SAVE_PS2:FILER_SAVE_PS1,formats[f],&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  assert(snprintf(destination,sizeof(destination),"%s%s",folder,archive_name)<(int)sizeof(destination));
  assert(filerWriteArchive(archive,archive_size,formats[f],destination,message,sizeof(message))==1);
  SaveArchive roundtrip;assert(saveArchiveParse(&roundtrip,archive,archive_size,archive_name));
  assert(filerExtractSave(&roundtrip,folder,message,sizeof(message))==1);
  const char *id=f<2?"PS2SAVE":"BASLUS-TEST";
  assert(snprintf(destination,sizeof(destination),"%s%s/%s",folder,id,f<2?"data":id)<(int)sizeof(destination));
  size_t actual_size;uint8_t *actual=readSource(destination,&actual_size);assert(actual);
  assert(actual_size==(f<2?sizeof(payload):8192)&&!memcmp(actual,f<2?payload:save+128,actual_size));free(actual);
  if(f<2){assert(snprintf(destination,sizeof(destination),"%sPS2SAVE/empty",folder)<(int)sizeof(destination));assert(!stat(destination,&st)&&!st.st_size);}
  saveArchiveFree(&roundtrip);free(archive);no_temps(folder);
 }
 assert(rename_calls==renames_before);fail_rename=0;
 // Source folder metadata is retained in PSU, independent of naming choices.
 assert(filerCreateArchive("storage/PS2SAVE/",&selected,FILER_SAVE_PS2,SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 const char old_psu[]="previous PSU backup";
 put("storage/replace.psu",old_psu,sizeof(old_psu));config.PSU_NoOverwrite=1;
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSU,"storage/replace.psu",message,sizeof(message))==0&&strstr(message,"skipped"));
 size_t kept_size;uint8_t *kept=readSource("storage/replace.psu",&kept_size);
 assert(kept&&kept_size==sizeof(old_psu)&&!memcmp(kept,old_psu,kept_size));free(kept);no_temps("storage");
 config.PSU_NoOverwrite=0;
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSU,"storage/replace.psu",message,sizeof(message))==1);
 kept=readSource("storage/replace.psu",&kept_size);
 assert(kept&&kept_size==archive_size&&!memcmp(kept,archive,kept_size));free(kept);no_temps("storage");
 assert(!mkdir("storage/folder.psu",0700));put("storage/folder.psu/keep",old_psu,sizeof(old_psu));
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSU,"storage/folder.psu",message,sizeof(message))<0&&!access("storage/folder.psu/keep",F_OK));
 free(archive);
 // Copy/Cut stores metadata only; archive creation restores source drivers on demand.
 save[128]='S';
 const char *cards[]={"mc0:/","mc1:/","vmc0:/","vmc1:/"};
 for(int slot=0;slot<4;slot++) {
  char source[MAX_PATH],destination[MAX_PATH],root_name[8];
  snprintf(root_name,sizeof(root_name),slot<2?"mc%d:":"vmc%d:",slot%2);mkdir(root_name,0700);
  snprintf(source,sizeof(source),"%sCLIP-SAVE",cards[slot]);put(source,save+128,8192);
  memset(clipFiles,0,sizeof(clipFiles));strcpy(clipPath,cards[slot]);strcpy(clipFiles[0].name,"CLIP-SAVE");
  clipFiles[0].stats.AttrFile=0x9017;clipFiles[0].stats.FileSizeByte=8192;
  nclipFiles=1;browser_cut=0;card_type=1;
  int opened=open_calls,listed=dir_calls,prepared=prepare_calls;
  filerRememberArchiveClipboard(1);
  assert(opened==open_calls&&listed==dir_calls&&prepared==prepare_calls&&!archive_clip_data);
  source_loaded=0;generation++;
  for(int format=SAVE_OUTPUT_PSV;format<=SAVE_OUTPUT_PSX;format++) {
   assert(filerCreateClipboardArchive("storage/",format,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1&&source_loaded);
   SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name)&&parsed.ps1&&parsed.count==1);
   assert(!strcmp(parsed.files[0].name,"CLIP-SAVE")&&!memcmp(parsed.files[0].data,save+128,8192));saveArchiveFree(&parsed);
   snprintf(destination,sizeof(destination),"storage/COPY%d-%d.arc",slot,format);
   assert(filerWriteArchive(archive,archive_size,format,destination,message,sizeof(message))==1);free(archive);
   assert(filerFinishArchiveClipboard(destination,message,sizeof(message))==1&&nclipFiles==1&&!archive_clip_data);
  }
  // An unavailable/unmounted source cannot be recreated from an eager Copy snapshot.
  assert(!unlink(source));
  assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&!archive);
  put(source,save+128,8192);
  if(slot>=2){vmcMounted[slot%2]=0;assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0);vmcMounted[slot%2]=1;}
  // Cut removes unchanged data only after successful publication, even after a legitimate driver restore.
  browser_cut=1;
  assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  snprintf(destination,sizeof(destination),"storage/CUT%d.mcs",slot);
  fail_after=0;assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_MCS,destination,message,sizeof(message))<0&&!access(source,F_OK));fail_after=-1;
  assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_MCS,destination,message,sizeof(message))==1);free(archive);
  source_loaded=0;generation++;int before_deletes=delete_calls;
  assert(filerFinishArchiveClipboard(destination,message,sizeof(message))==1&&source_loaded&&access(source,F_OK)<0);
  assert(delete_calls==before_deletes+1&&!nclipFiles&&!browser_cut&&!archive_clip_data);
 }
 // Eligibility comes from a copied/cut item; a generic flat folder needs no icon.sys.
 card_type=0;nclipFiles=1;browser_cut=0;strcpy(clipPath,"storage/");
 memset(&clipFiles[0],0,sizeof(clipFiles[0]));strcpy(clipFiles[0].name,"FLAT");
 clipFiles[0].stats.AttrFile=0x8427;
 assert(!mkdir("storage/FLAT",0700));put("storage/FLAT/data",save,32);
 assert(filerSaveKind(clipPath,&clipFiles[0],0)==FILER_SAVE_NONE);
 assert(rememberAndProbe(0)==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 SaveArchive flat;assert(saveArchiveParse(&flat,archive,archive_size,archive_name));
 assert(!flat.ps1&&flat.count==1&&!strcmp(flat.folder.name,"FLAT")&&!strcmp(flat.files[0].name,"data"));
 assert(flat.files[0].size==32&&!memcmp(flat.files[0].data,save,32));saveArchiveFree(&flat);
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSU,"storage/flat.psu",message,sizeof(message))==1);free(archive);
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSV,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&!archive&&strstr(message,"icon.sys"));
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);free(archive);
 // A subdirectory added after an archive read keeps the Cut source safe.
 browser_cut=1;assert(!mkdir("storage/FLAT/subdir",0700));
 assert(!filerFinishArchiveClipboard("storage/flat.psu",message,sizeof(message))&&!access("storage/FLAT/data",F_OK));
 assert(!rmdir("storage/FLAT/subdir"));
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);free(archive);
 assert(filerFinishArchiveClipboard("storage/flat.psu",message,sizeof(message))==1&&access("storage/FLAT",F_OK)<0);
 // A PS1 backup wrapper with extra files uses PSU so Cut cannot discard those files.
 browser_cut=0;nclipFiles=1;strcpy(clipPath,"storage/");strcpy(clipFiles[0].name,"PS1EXTRA");
 assert(!mkdir("storage/PS1EXTRA",0700));put("storage/PS1EXTRA/PS1EXTRA",save+128,8192);
 put("storage/PS1EXTRA/extra",save,32);
 assert(filerSaveKind(clipPath,&clipFiles[0],0)==FILER_SAVE_PS1);
 assert(rememberAndProbe(0)==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(saveArchiveParse(&flat,archive,archive_size,archive_name)&&flat.count==2&&!flat.ps1);
 saveArchiveFree(&flat);free(archive);
 // Nested folders are ineligible both with and without PS2 save icon metadata.
 for(int with_icon=0;with_icon<2;with_icon++) {
  strcpy(clipFiles[0].name,with_icon?"PS2SAVE":"NESTED");nclipFiles=1;browser_cut=0;
  const char *nested=with_icon?"storage/PS2SAVE/subdir":"storage/NESTED/subdir";
  if(!with_icon)assert(!mkdir("storage/NESTED",0700));
  assert(!mkdir(nested,0700));
  assert(!rememberAndProbe(0)&&!filerArchiveClipboardKind());
  assert(nclipFiles==1);assert(!rmdir(nested));
  if(!with_icon)assert(!rmdir("storage/NESTED"));
 }
 // A capped listing cannot prove that all children are files, so it stays ineligible.
 assert(!mkdir("storage/CAPPED",0700));strcpy(clipFiles[0].name,"CAPPED");
 for(int i=0;i<MAX_ENTRY-2;i++) {char path[80];snprintf(path,sizeof(path),"storage/CAPPED/file%02d",i);put(path,save,1);}
 assert(!mkdir("storage/CAPPED/hidden-subdir",0700));
 assert(!rememberAndProbe(0)&&!filerArchiveClipboardKind());
 // Ordinary files and a selection with no clipboard are never archive sources.
 strcpy(clipFiles[0].name,"plain.bin");clipFiles[0].stats.AttrFile=0x8497;clipFiles[0].stats.FileSizeByte=32;
 put("storage/plain.bin",save,32);assert(!rememberAndProbe(0)&&!filerArchiveClipboardKind());
 nclipFiles=0;assert(!rememberAndProbe(0)&&!filerArchiveClipboardKind());
 // PS2 clipboard snapshots preserve all files and work with both output formats.
 card_type=2;nclipFiles=1;browser_cut=0;strcpy(clipPath,"storage/");
 memset(&clipFiles[0],0,sizeof(clipFiles[0]));strcpy(clipFiles[0].name,"PS2SAVE");clipFiles[0].stats.AttrFile=0x8427;
 assert(rememberAndProbe(0)==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 for(int format=SAVE_OUTPUT_PSU;format<=SAVE_OUTPUT_PSV;format++) {
  assert(filerCreateClipboardArchive("storage/",format,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name)&&!parsed.ps1&&parsed.count==4);
  assert(!strcmp(parsed.folder.name,"PS2SAVE"));saveArchiveFree(&parsed);free(archive);
 }
 browser_cut=1;
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSU,"storage/PS2SAVE/nested.psu",message,sizeof(message))==1);free(archive);
 assert(!filerFinishArchiveClipboard("storage/PS2SAVE/nested.psu",message,sizeof(message))&&!access("storage/PS2SAVE/icon.sys",F_OK));
 unlink("storage/PS2SAVE/nested.psu");
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_PSV,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(filerWriteArchive(archive,archive_size,SAVE_OUTPUT_PSV,"storage/clipboard-ps2.PSV",message,sizeof(message))==1);free(archive);
 assert(filerFinishArchiveClipboard("storage/clipboard-ps2.PSV",message,sizeof(message))==1&&access("storage/PS2SAVE",F_OK)<0&&!nclipFiles);
 nclipFiles=2;assert(!rememberAndProbe(0)&&!filerArchiveClipboardKind());
 assert(filerCreateClipboardArchive("storage/",SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&!archive);
 filerClearArchiveClipboard();
 // Each clipboard entry produces its own archive, with bounded per-save memory.
 int batch_case=0;
 for(int ps1=0;ps1<2;ps1++)for(int wrapped=0;wrapped<=(ps1?1:0);wrapped++)for(int f=0;f<(ps1?3:2);f++)for(int cut=0;cut<2;cut++) {
  char source[100],out[100],path[MAX_PATH];
  snprintf(source,sizeof(source),"storage/batch-source-%d/",batch_case);
  snprintf(out,sizeof(out),"mmce0:/batch-out-%d/",batch_case++);assert(!mkdir(out,0700));
  startArchiveBatch(source,3,cut);
  for(int i=0;i<3;i++)makeArchiveBatchItem(source,i,ps1,wrapped);
  int opened=open_calls,listed=dir_calls,prepared=prepare_calls;
  filerRememberArchiveClipboard(ps1&&!wrapped?1:0);
  assert(filerArchiveClipboardKind()==(ps1&&!wrapped?FILER_SAVE_PS1:FILER_SAVE_PS2));
  assert(opened==open_calls&&listed==dir_calls&&prepared==prepare_calls&&!archive_clip_data);
  source_loaded=0;generation++;
  assert(filerProbeArchiveClipboard(out)==(ps1?FILER_SAVE_PS1:FILER_SAVE_PS2)&&source_loaded);
  int ps1_formats[]={SAVE_OUTPUT_MCS,SAVE_OUTPUT_PSV,SAVE_OUTPUT_PSX};
  int format=ps1?ps1_formats[f]:f;
  fail_rename=1;int renamed=rename_calls;
  assert(filerCreateClipboardArchives(out,format,message,sizeof(message))==3);
  assert(rename_calls==renamed&&nclipFiles==(cut?0:3)&&!browser_cut&&!archive_clip_data);fail_rename=0;
  for(int i=0;i<3;i++) {
   snprintf(path,sizeof(path),"%sBATCH-%c.%s",out,'A'+i,format==SAVE_OUTPUT_PSU?"psu":format==SAVE_OUTPUT_PSV?"PSV":format==SAVE_OUTPUT_MCS?"mcs":"psx");
   SaveArchive parsed;uint8_t *snapshot;assert(filerLoadSave(path,&parsed,&snapshot,message,sizeof(message)));
   assert(parsed.ps1==ps1&&parsed.count==(unsigned)(ps1?1:3));
   int found=0;for(unsigned j=0;j<parsed.count;j++)if(ps1||!strcmp(parsed.files[j].name,"data")){
    assert(parsed.files[j].data[ps1?8:0]==i+1);found++;
   }
   assert(found==1);saveArchiveFree(&parsed);free(snapshot);
   snprintf(path,sizeof(path),"%sBATCH-%c",source,'A'+i);assert((access(path,F_OK)<0)==cut);
  }
 }

 // PSU title/date policies use each save's metadata, including subsequent items.
 startArchiveBatch("storage/batch-names/",3,0);
 for(int i=0;i<3;i++)makeArchiveBatchItem(clipPath,i,0,0);
 assert(!mkdir("storage/batch-names-out",0700));show_titles=batch_titles=1;config.PSU_HugeNames=config.PSU_DateNames=1;
 filerRememberArchiveClipboard(0);assert(filerCreateClipboardArchives("storage/batch-names-out/",SAVE_OUTPUT_PSU,message,sizeof(message))==3);
 for(int i=0;i<3;i++) {
  char path[200];snprintf(path,sizeof(path),"storage/batch-names-out/BATCH-%c_Title BATCH-%c_2026-11-%02d_12-34-56.psu",'A'+i,'A'+i,i+1);
  assert(!access(path,F_OK));
 }
 batch_titles=0;
 // Never-overwrite skips only its matching PSU and preserves that Cut item.
 startArchiveBatch("storage/batch-skipped/",3,1);
 for(int i=0;i<3;i++)makeArchiveBatchItem(clipPath,i,0,0);
 assert(!mkdir("storage/batch-skipped-out",0700));put("storage/batch-skipped-out/BATCH-B.psu","old PSU",8);
 config.PSU_NoOverwrite=1;filerRememberArchiveClipboard(0);
 assert(filerCreateClipboardArchives("storage/batch-skipped-out/",SAVE_OUTPUT_PSU,message,sizeof(message))==0);
 assert(strstr(message,"2 archives created; 1 skipped")&&nclipFiles==1&&browser_cut&&!strcmp(clipFiles[0].name,"BATCH-B"));
 assert(!access("storage/batch-skipped/BATCH-B/data",F_OK)&&access("storage/batch-skipped/BATCH-A",F_OK)<0&&access("storage/batch-skipped/BATCH-C",F_OK)<0);
 size_t old_size;uint8_t *old_data=readSource("storage/batch-skipped-out/BATCH-B.psu",&old_size);assert(old_data&&old_size==8&&!memcmp(old_data,"old PSU",8));free(old_data);
 // A failure partway through consumes only completed Cuts; retry starts at the failed item.
 for(int write_failure=0;write_failure<2;write_failure++) {
  char source[100],out[100],target[150];
  snprintf(source,sizeof(source),"storage/batch-partial-%d/",write_failure);
  snprintf(out,sizeof(out),"storage/batch-partial-out-%d/",write_failure);assert(!mkdir(out,0700));
  startArchiveBatch(source,3,1);for(int i=0;i<3;i++)makeArchiveBatchItem(source,i,0,0);
  snprintf(target,sizeof(target),"%sBATCH-B.PSV",out);
  if(!write_failure)put(target,"existing PSV",13);else fail_after_archive=1;
  filerRememberArchiveClipboard(0);assert(filerCreateClipboardArchives(out,SAVE_OUTPUT_PSV,message,sizeof(message))<0);
  assert(strstr(message,"1 archive created; stopped at BATCH-B")&&nclipFiles==2&&browser_cut);
  assert(!strcmp(clipFiles[0].name,"BATCH-B")&&!strcmp(clipFiles[1].name,"BATCH-C"));
  snprintf(source,sizeof(source),"storage/batch-partial-%d/BATCH-A",write_failure);assert(access(source,F_OK)<0);
  if(write_failure)assert(access(target,F_OK)<0);else assert(!unlink(target));
  fail_after=-1;fail_after_archive=0;
  assert(filerArchiveClipboardKind()==FILER_SAVE_PS2);
  assert(filerCreateClipboardArchives(out,SAVE_OUTPUT_PSV,message,sizeof(message))==2&&!nclipFiles&&!browser_cut);
 }
 // Unverified Cut removal of an earlier item must not skip subsequent entries.
 startArchiveBatch("storage/batch-kept/",3,1);
 for(int i=0;i<3;i++)makeArchiveBatchItem(clipPath,i,1,0);
 assert(!mkdir("storage/batch-kept-out",0700));strcpy(changed_archive,"storage/batch-kept/BATCH-A");extract_hook=1;
 filerRememberArchiveClipboard(1);assert(filerCreateClipboardArchives("storage/batch-kept-out/",SAVE_OUTPUT_MCS,message,sizeof(message))==0);
 assert(strstr(message,"3 archives created; 0 skipped; 1 source save kept")&&nclipFiles==1&&browser_cut&&!strcmp(clipFiles[0].name,"BATCH-A"));
 assert(!access(changed_archive,F_OK)&&access("storage/batch-kept/BATCH-B",F_OK)<0&&access("storage/batch-kept/BATCH-C",F_OK)<0);extract_hook=0;
 // A batch naming collision must preserve the first archive and the later Cut sources.
 startArchiveBatch("storage/batch-collision/",3,1);
 for(int i=0;i<3;i++)makeArchiveBatchItem(clipPath,i,0,0);
 assert(!mkdir("storage/batch-collision-out",0700));show_titles=1;game_title="Same Title";
 filerRememberArchiveClipboard(0);assert(filerCreateClipboardArchives("storage/batch-collision-out/",SAVE_OUTPUT_PSU,message,sizeof(message))<0);
 assert(strstr(message,"same archive name")&&nclipFiles==2&&!strcmp(clipFiles[0].name,"BATCH-B"));
 SaveArchive first_batch;uint8_t *first_data;assert(filerLoadSave("storage/batch-collision-out/Same Title.psu",&first_batch,&first_data,message,sizeof(message)));
 assert(!strcmp(first_batch.folder.name,"BATCH-A"));saveArchiveFree(&first_batch);free(first_data);show_titles=0;game_title="";

 // Case-only differences also collide on FAT storage and must not lose a Cut save.
 startArchiveBatch("storage/batch-case-collision/",2,1);
 for(int i=0;i<2;i++)makeArchiveBatchItem(clipPath,i,1,0);
 assert(!rename("storage/batch-case-collision/BATCH-B","storage/batch-case-collision/batch-a"));strcpy(clipFiles[1].name,"batch-a");
 assert(!mkdir("storage/batch-case-collision-out",0700));filerRememberArchiveClipboard(1);
 assert(filerCreateClipboardArchives("storage/batch-case-collision-out/",SAVE_OUTPUT_MCS,message,sizeof(message))<0);
 assert(nclipFiles==1&&!strcmp(clipFiles[0].name,"batch-a")&&!access("storage/batch-case-collision/batch-a",F_OK));
 assert(!access("storage/batch-case-collision-out/BATCH-A.mcs",F_OK)&&access("storage/batch-case-collision-out/batch-a.mcs",F_OK)<0);
 // Mixed PS1/PS2 saves share PSV, and nested folders are rejected before the format menu.
 startArchiveBatch("storage/batch-mixed/",2,0);
 makeArchiveBatchItem(clipPath,0,1,1);makeArchiveBatchItem(clipPath,1,0,0);
 assert(!mkdir("storage/batch-mixed-out",0700));filerRememberArchiveClipboard(0);
 assert(filerProbeArchiveClipboard("storage/batch-mixed-out/")==FILER_SAVE_MIXED);
 assert(filerCreateClipboardArchives("storage/batch-mixed-out/",SAVE_OUTPUT_PSV,message,sizeof(message))==2&&nclipFiles==2);
 assert(!mkdir("storage/batch-mixed/BATCH-B/nested",0700));
 assert(!filerProbeArchiveClipboard("storage/batch-mixed-out/"));
 filerClearArchiveClipboard();browser_cut=0;
 char label[40];filerExtractLabel("file.pSv",label,sizeof(label));assert(!strcmp(label,"Extract PSV..."));
 selected.stats.AttrFile=0x8497;strcpy(selected.name,"input.mcs");
 assert(filerSaveKind("",&selected,0)==FILER_ARCHIVE_PS1);
 strcpy(selected.name,"bad.mcs");assert(filerSaveKind("",&selected,0)==FILER_ARCHIVE_PS1); // Hint only; full parsing rejects it.
 SaveArchive parsed;uint8_t *snapshot;assert(filerLoadSave("input.mcs",&parsed,&snapshot,message,sizeof(message)));
 assert(filerExtractSave(&parsed,"host:/",message,sizeof(message))<0);saveArchiveFree(&parsed);free(snapshot);assert(!handles);
 memset(clipFiles,0,sizeof(clipFiles));browser_cut=0;
 nclipFiles=1;strcpy(clipFiles[0].name,"BASLUS-RAW");clipFiles[0].stats.FileSizeByte=8192;
 assert(!filerCanImportClipboard());clipFiles[0].stats.FileSizeByte=8191;assert(!filerCanImportClipboard());
 // Native saves, including archive-looking names on either PS1 card type, are already extracted.
 for(int slot=0;slot<4;slot++)for(int cut=0;cut<2;cut++) {
  strcpy(clipPath,cards[slot]);nclipFiles=1;browser_cut=cut;
  memset(clipFiles,0,sizeof(clipFiles));strcpy(clipFiles[0].name,"SAVE.PSV");clipFiles[0].stats.FileSizeByte=8192;
  filerRememberArchiveClipboard(1);
  int opened=open_calls,listed=dir_calls,prepared=prepare_calls,progress=progress_events;
  assert(!filerCanImportClipboard()&&filerArchiveClipboardKind()==FILER_SAVE_PS1);
  assert(filerImportClipboard("storage/",message,sizeof(message))<0&&strstr(message,"save archives"));
  assert(nclipFiles==1&&browser_cut==cut&&open_calls==opened&&dir_calls==listed&&prepare_calls==prepared&&progress_events==progress);
 }
 // Eligibility uses a recognized extension, independently of block-aligned file size.
 strcpy(clipPath,"storage/");browser_cut=0;nclipFiles=1;
 memset(clipFiles,0,sizeof(clipFiles));strcpy(clipFiles[0].name,"save.pSu");clipFiles[0].stats.FileSizeByte=8192;
 filerRememberArchiveClipboard(0);assert(filerCanImportClipboard());
 strcpy(clipFiles[0].name,"raw.bin");assert(!filerCanImportClipboard());
 strcpy(clipFiles[0].name,"a.psv");strcpy(clipFiles[1].name,"BASLUS-RAW");clipFiles[1].stats.FileSizeByte=8192;nclipFiles=2;
 assert(!filerCanImportClipboard());strcpy(clipFiles[1].name,"b.mcs");assert(filerCanImportClipboard());
 clipFiles[1].stats.AttrFile=sceMcFileAttrSubdir;assert(!filerCanImportClipboard());
 memset(clipFiles,0,sizeof(clipFiles));
 // Clipboard extraction labels follow the copied extension, case-insensitively.
 browser_cut=1;strcpy(clipFiles[0].name,"a.pSv");nclipFiles=1;
 filerClipboardExtractLabel(label,sizeof(label));assert(!strcmp(label,"Extract PSV..."));assert(filerCanImportClipboard());
 nclipFiles=2;strcpy(clipFiles[1].name,"b.PSV");
 filerClipboardExtractLabel(label,sizeof(label));assert(!strcmp(label,"Extract PSV..."));
 strcpy(clipFiles[1].name,"b.mcs");filerClipboardExtractLabel(label,sizeof(label));assert(!strcmp(label,"Extract saves..."));
 nclipFiles=0;filerClipboardExtractLabel(label,sizeof(label));assert(!strcmp(label,"Extract saves..."));
 assert(!filerCanImportClipboard());
 // Copy and Cut both extract directly into the supplied folder, with no picker.
 size_t fixture_size;uint8_t *fixture=readSource("input.mcs",&fixture_size);assert(fixture);
 assert(!mkdir("storage/archives",0700));
 for(int cut=0;cut<2;cut++) {
  char out[80];snprintf(out,sizeof(out),"storage/extracted-%d/",cut);assert(!mkdir(out,0700));
  put("storage/archives/one.mcs",fixture,fixture_size);
  memset(clipFiles,0,sizeof(clipFiles));strcpy(clipPath,"storage/archives/");strcpy(clipFiles[0].name,"one.mcs");
  clipFiles[0].stats.FileSizeByte=fixture_size;nclipFiles=1;browser_cut=cut;clipIopResetGeneration=generation;
  assert(filerImportClipboard(out,message,sizeof(message))==1);
  char target[120];snprintf(target,sizeof(target),"%sBASLUS-TEST/BASLUS-TEST",out);assert(!access(target,F_OK));
  assert((access("storage/archives/one.mcs",F_OK)<0)==cut);
  assert(nclipFiles==(cut?0:1)&&!browser_cut);
 }
 // Failures before publish keep a Cut source; changes/unavailable stacks after publish also keep it.
 for(int failure=0;failure<6;failure++) {
  char out[80];snprintf(out,sizeof(out),"storage/extract-failure-%d/",failure);assert(!mkdir(out,0700));
  put("storage/archives/one.mcs",fixture,fixture_size);strcpy(changed_archive,"storage/archives/one.mcs");
  strcpy(clipPath,"storage/archives/");strcpy(clipFiles[0].name,"one.mcs");
  nclipFiles=1;browser_cut=1;clipIopResetGeneration=generation;source_loaded=1;
  if(failure==0)fail_after=0;
  if(failure==1)fail_close=1;
  if(failure==2)delete_failure=1;
  if(failure>=3)extract_hook=failure-2;
  int before=delete_calls;int result=filerImportClipboard(out,message,sizeof(message));
  if(failure==4)assert(result==1&&access(changed_archive,F_OK)<0&&!nclipFiles&&!browser_cut);
  else assert(result==(failure<2?-1:0)&&!access(changed_archive,F_OK)&&nclipFiles==1&&browser_cut);
  assert(delete_calls==before+(failure==2||failure==4));
  if(failure>=2&&failure!=4)assert(strstr(message,"source archive kept"));
  fail_after=-1;fail_close=delete_failure=extract_hook=0;source_loaded=restore_ok=1;
 }
 // Mixed PS1/PS2 batches use one action and keep iteration correct as Cut entries are consumed.
 size_t psu_size;uint8_t *psu_fixture=readSource("storage/flat.psu",&psu_size);assert(psu_fixture);
 for(int cut=0;cut<2;cut++) {
  char out[80],target[120];snprintf(out,sizeof(out),"storage/extract-batch-%d/",cut);assert(!mkdir(out,0700));
  put("storage/archives/first.mcs",fixture,fixture_size);put("storage/archives/second.psu",psu_fixture,psu_size);
  memset(clipFiles,0,sizeof(clipFiles));strcpy(clipPath,"storage/archives/");
  strcpy(clipFiles[0].name,"first.mcs");strcpy(clipFiles[1].name,"second.psu");
  nclipFiles=2;browser_cut=cut;clipIopResetGeneration=generation;
  assert(filerImportClipboard(out,message,sizeof(message))==2);
  snprintf(target,sizeof(target),"%sBASLUS-TEST/BASLUS-TEST",out);assert(!access(target,F_OK));
  snprintf(target,sizeof(target),"%sFLAT/data",out);assert(!access(target,F_OK));
  assert((access("storage/archives/first.mcs",F_OK)<0)==cut&&(access("storage/archives/second.psu",F_OK)<0)==cut);
  assert(nclipFiles==(cut?0:2)&&!browser_cut);
 }
 free(psu_fixture);
 // Partial Cut batches consume only completed sources and retain unprocessed entries.
 assert(!mkdir("storage/extract-partial",0700));
 put("storage/archives/first.mcs",fixture,fixture_size);put("storage/archives/broken.mcs","bad",3);
 strcpy(clipPath,"storage/archives/");memset(clipFiles,0,sizeof(clipFiles));
 strcpy(clipFiles[0].name,"first.mcs");strcpy(clipFiles[1].name,"broken.mcs");
 nclipFiles=2;browser_cut=1;clipIopResetGeneration=generation;
 assert(filerImportClipboard("storage/extract-partial/",message,sizeof(message))<0);
 assert(strstr(message,"1 extracted; stopped")&&nclipFiles==1&&!strcmp(clipFiles[0].name,"broken.mcs"));
 assert(access("storage/archives/first.mcs",F_OK)<0&&!access("storage/archives/broken.mcs",F_OK));
 free(fixture);browser_cut=0;
 nclipFiles=1;strcpy(clipFiles[0].name,"input.mcs");clipPath[0]=0;generation++;
 strcpy(clipPath,"storage/archives/");strcpy(clipFiles[0].name,"broken.mcs");restore_ok=0;
 assert(filerImportClipboard("storage/",message,sizeof(message))<0&&strstr(message,"unavailable"));restore_ok=1;
 // Incompatible pairs fail before any source reads or output writes.
 browser_cut=1;nclipFiles=1;strcpy(clipFiles[0].name,"broken.mcs");incompatible=1;
 int before_open=open_calls;
 assert(filerImportClipboard("storage/",message,sizeof(message))<0&&strstr(message,"Incompatible drivers")&&open_calls==before_open);
 strcpy(clipFiles[0].name,"FLAT");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;filerRememberArchiveClipboard(0);
 assert(filerCreateClipboardArchive("mx4sio:/",SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&strstr(message,"Incompatible drivers")&&open_calls==before_open);
 incompatible=0;

 // Actual archive actions drive the shared paste popup from measured I/O, with stable batch ordinals.
 startArchiveBatch("storage/progress-source/",3,1);
 for(int i=0;i<3;i++)makeArchiveBatchItem(clipPath,i,0,0);
 assert(!mkdir("storage/progress-created",0700));
 int before_progress=progress_events,before_phases=phase_events,before_partial=progress_partial,before_complete=progress_complete;
 seen_stages=0;seen_ordinals=0;filerRememberArchiveClipboard(0);
 assert(filerArchiveClipboardKind()==FILER_SAVE_PS2&&progress_events==before_progress&&phase_events==before_phases);
 assert(filerCreateClipboardArchives("storage/progress-created/",SAVE_OUTPUT_PSU,message,sizeof(message))==3);
 assert(!save_progress.active&&!save_progress.action&&!save_progress.classic_drawn&&progress_ends>0);
 assert(progress_events>before_progress&&phase_events>before_phases&&progress_partial>before_partial&&progress_complete>before_complete);
 assert((seen_stages&71)==71&&seen_ordinals==14&&!nclipFiles); // read/prepare/create/verify, items 1..3.
 // Extraction reports archive reads, parsing, actual output file bytes and Cut verification.
 memset(clipFiles,0,sizeof(clipFiles));strcpy(clipPath,"storage/progress-created/");nclipFiles=3;browser_cut=1;
 for(int i=0;i<3;i++)snprintf(clipFiles[i].name,sizeof(clipFiles[i].name),"BATCH-%c.psu",'A'+i);
 assert(!mkdir("storage/progress-extracted",0700));seen_stages=0;seen_ordinals=0;before_progress=progress_events;
 assert(filerImportClipboard("storage/progress-extracted/",message,sizeof(message))==3);
 assert(!save_progress.active&&!save_progress.action&&progress_events>before_progress);
 assert((seen_stages&120)==120&&seen_ordinals==14&&!nclipFiles);
 // A failed close never publishes 100%, and its overlay context cannot leak into later operations.
 for(int failure=0;failure<2;failure++) {
  saveProgressBegin(1);saveProgressItem(1,"failure.psu","Creating archive");before_complete=progress_complete;
  if(failure)fail_close=1;else fail_after=1;
  assert(filerWriteArchive(save,sizeof(save),SAVE_OUTPUT_PSU,"storage/progress-failure.psu",message,sizeof(message))<0);
  assert(progress_complete==before_complete&&access("storage/progress-failure.psu",F_OK)<0);
  fail_close=0;fail_after=-1;saveProgressEnd();
  assert(!save_progress.active&&!save_progress.action);
 }
 // Classic mode keeps its normal paste-style progress text; it never opens a dashboard popup.
 startArchiveBatch("storage/progress-classic/",1,0);makeArchiveBatchItem(clipPath,0,0,0);
 assert(!mkdir("storage/progress-classic-out",0700));filerRememberArchiveClipboard(0);
 dashboard_active=0;before_progress=progress_events;before_phases=phase_events;
 assert(filerCreateClipboardArchives("storage/progress-classic-out/",SAVE_OUTPUT_PSU,message,sizeof(message))==1);
 assert(classic_events>0&&classic_closes>0&&progress_events==before_progress&&phase_events==before_phases&&!save_progress.active);
 dashboard_active=1;
 assert(!handles);puts("PASS: real save import/export, direct extraction, MCS/PSU/PSV creation, PSU title/date/overwrite settings, direct PSU/PSV/MCS/PSX creation and extraction across seven device paths without rename, single/multiple Copy/Cut archive creation, partial retries, skips, retained sources, duplicate names and mixed PSV batches, archive-only extraction eligibility (including PS1 card saves with archive-like names), clipboard extension labels, Copy/Cut extraction and partial batches, measured read/write progress, batch ordinals, close-failure completion guards and classic popup fallback, metadata-only Copy/Cut and on-demand source restoration, flat-folder clipboard eligibility without icon.sys, nested/capped folder rejection, empty files, both physical PS1 slots without mkdir, short I/O, card types, space preflight and failed-write/close cleanup");
}
'''.replace('PRODUCTION_SAVES', os.environ.get('SAVE_TEST_SOURCE', str(root / 'src/filer_saves.c'))).replace('PRODUCTION_NAME_LIMITS', name_limits)

with tempfile.TemporaryDirectory(prefix='save-import-') as folder:
    folder = Path(folder)
    for header in ('filer_saves.h', 'filer_shared.h', 'filer_actions.h', 'filer_copy.h', 'init.h', 'dash.h'):
        (folder / header).write_text(stub)
    (folder / 'test.c').write_text(code)
    exe = folder / 'test'
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', *flags,
                    '-I', str(folder), '-I', str(root / 'include'), str(folder / 'test.c'),
                    str(root / 'src/save_archive.c'), str(root / 'src/save_lzari.c'), str(root / 'src/save_sign.c'), '-lz', '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder)], check=True, timeout=20)
