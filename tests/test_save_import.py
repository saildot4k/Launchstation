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
extern int vmcMounted[2], nclipFiles, browser_cut;
extern unsigned clipIopResetGeneration;
extern FILEINFO clipFiles[MAX_ENTRY];extern char clipPath[MAX_PATH];
enum { FILER_SAVE_NONE, FILER_SAVE_PS1, FILER_SAVE_PS2, FILER_ARCHIVE_PS1, FILER_ARCHIVE_PS2, FILER_CARD_PS1 };
int filerCardInfo(const char *,VmcInfo *);
int filerExtractSave(const SaveArchive *, const char *, char *, int);
int filerPrepareMemoryCardRead(int);int mcGetInfo(int,int,int*,int*,int*);int mcSync(int,void*,int*);
int genFixPath(const char*,char*);int genOpen(const char*,int);s64 genLseek(int,s64,int);int genRead(int,void*,int);int genWrite(int,void*,int);int genClose(int);
int genDopen(char*);int genDclose(int);int genMkdir(const char*,int);int genRemove(char*);int genRmdir(char*);
int genCmpFileExt(const char*,const char*);int genCanRenamePath(const char*);int genRenameNoReplace(const char*,const char*);
int fileXioDevctl(const char*,int,void*,unsigned,void*,unsigned);int fileXioGetStat(const char*,iox_stat_t*);int fileXioChStat(const char*,iox_stat_t*,unsigned);
int mcGetDir(int,int,const char*,int,int,sceMcTblGetDir*);int mcSetFileInfo(int,int,const char*,sceMcTblGetDir*,int);
int prepareTransferDeviceStacks(const char*,const char*);unsigned getIopResetGeneration(void);int getDir(const char*,FILEINFO*);
int isPathDeviceStackLoaded(const char*);int filerConfirmExploitDelete(const char*,const FILEINFO*);
int delete(const char*,const FILEINFO*);
#endif
'''
code = r'''
#define _DEFAULT_SOURCE
#include "filer_saves.h"
#include "save_archive.h"
#include <strings.h>
int vmcMounted[2]={1,1},nclipFiles,browser_cut;
unsigned clipIopResetGeneration=1;FILEINFO clipFiles[MAX_ENTRY];char clipPath[MAX_PATH];
static int card_type=1,free_units=15,fail_after=-1,fail_close,fail_rename,handles,physical_mkdirs;
static unsigned generation=1;
static int source_loaded=1,delete_calls,delete_failure;
int filerPrepareMemoryCardRead(int port){(void)port;return 0;}
int mcGetInfo(int port,int slot,int *type,int *units,int *format){(void)port;(void)slot;*type=card_type;*units=free_units;if(format)*format=1;return 0;}
int mcSync(int x,void *y,int *result){(void)x;(void)y;if(result)*result=0;return 1;}
int genFixPath(const char *in,char *out){strcpy(out,in);return 0;}
int genOpen(const char *p,int flags){int f=open(p,flags,0600);if(f>=0)handles++;return f;}
s64 genLseek(int f,s64 offset,int how){return lseek(f,offset,how);}
int genRead(int f,void *p,int n){return read(f,p,n>17?17:n);}
int genWrite(int f,void *p,int n){if(fail_after==0)return -EIO;if(fail_after>0)fail_after--;return write(f,p,n>13?13:n);}
int genClose(int f){handles--;int result=close(f);return fail_close?-EIO:result;}
int genDopen(char *p){return genOpen(p,O_RDONLY|O_DIRECTORY);}
int genDclose(int f){return genClose(f);}
int genMkdir(const char *p,int mode){(void)mode;if(!strncmp(p,"mc",2))physical_mkdirs++;return mkdir(p,0700);}
int genRemove(char *p){return unlink(p);}
int genRmdir(char *p){return rmdir(p);}
int genCmpFileExt(const char *p,const char *ext){const char *dot=strrchr(p,'.');return dot&&!strcasecmp(dot+1,ext);}
int genCanRenamePath(const char *p){(void)p;return 1;}
int genRenameNoReplace(const char *from,const char *to){if(fail_rename)return -EIO;if(!access(to,F_OK))return -EEXIST;return rename(from,to);}
int fileXioDevctl(const char *p,int cmd,void *arg,unsigned arglen,void *buf,unsigned buflen){
 (void)p;(void)arg;(void)arglen;(void)buflen;if(cmd!=VMCCTL_GET_INFO)return -EINVAL;
 VmcInfo *info=buf;info->type=card_type;info->free_units=free_units;info->unit_bytes=card_type==1?8192:1024;return 0;
}
int fileXioGetStat(const char *p,iox_stat_t *out){struct stat s;int r=stat(p,&s);memset(out,0,sizeof(*out));out->ctime[4]=out->mtime[4]=1;return r;}
int fileXioChStat(const char *p,iox_stat_t *out,unsigned flags){(void)p;assert(flags==0xFEED&&out->private_0);return 0;}
int mcGetDir(int p,int s,const char *path,int flags,int count,sceMcTblGetDir *info){(void)p;(void)s;(void)path;(void)flags;(void)count;(void)info;return 0;}
int mcSetFileInfo(int p,int s,const char *path,sceMcTblGetDir *info,int flags){(void)p;(void)s;(void)path;(void)info;(void)flags;return 0;}
int prepareTransferDeviceStacks(const char *a,const char *b){(void)a;(void)b;return 0;}
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
 DIR *dir=opendir(p);if(!dir)return -EIO;struct dirent *e;int count=0;
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
#include "PRODUCTION_SAVES"
static void put(const char *name,const void *p,size_t n){FILE *f=fopen(name,"wb");assert(f&&fwrite(p,1,n,f)==n);fclose(f);}
static void no_temps(const char *p){DIR *dir=opendir(p);assert(dir);struct dirent *e;while((e=readdir(dir)))assert(strncmp(e->d_name,"LSI",3));closedir(dir);assert(!handles);}
int main(int argc,char **argv){
 assert(argc==2&&!chdir(argv[1]));mkdir("vmc0:",0700);mkdir("storage",0700);
 unsigned char save[8320]={0};save[0]=0x51;memcpy(save+10,"BASLUS-TEST",11);memcpy(save+128,"SC",2);put("input.mcs",save,sizeof(save));
 char message[MAX_PATH];
 for(int failure=0;failure<3;failure++){
   fail_after=failure==0?7:-1;fail_rename=failure==1;
   assert(filerImportSave("input.mcs","vmc0:/",message,sizeof(message))==(failure==2?1:-1));
   no_temps("vmc0:");
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
 selected.stats.FileSizeByte=8192;uint8_t *archive;size_t archive_size;char archive_name[80];
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
  fail_after=0;assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))<0);no_temps("storage");
  fail_after=-1;fail_rename=1;assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))<0);no_temps("storage");
  fail_rename=0;assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))==1);no_temps("storage");
  assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))<0&&strstr(message,"already exists"));
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
 // Copy snapshots survive removal of the source, IOP resets and retired VMCs.
 save[128]='S';
 const char *cards[]={"mc0:/","mc1:/","vmc0:/","vmc1:/"};
 for(int slot=0;slot<4;slot++) {
  char source[MAX_PATH],destination[MAX_PATH],root_name[8];
  snprintf(root_name,sizeof(root_name),slot<2?"mc%d:":"vmc%d:",slot%2);mkdir(root_name,0700);
  snprintf(source,sizeof(source),"%sCLIP-SAVE",cards[slot]);put(source,save+128,8192);
  memset(clipFiles,0,sizeof(clipFiles));strcpy(clipPath,cards[slot]);strcpy(clipFiles[0].name,"CLIP-SAVE");
  clipFiles[0].stats.AttrFile=0x9017;clipFiles[0].stats.FileSizeByte=8192;
  nclipFiles=1;browser_cut=0;card_type=1;
  assert(filerCaptureArchiveClipboard(1,message,sizeof(message))==1&&filerArchiveClipboardKind()==FILER_SAVE_PS1);
  assert(!unlink(source));generation++;vmcMounted[slot%2]=0;
  for(int format=SAVE_OUTPUT_PSV;format<=SAVE_OUTPUT_PSX;format++) {
   assert(filerCreateClipboardArchive(format,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
   SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name)&&parsed.ps1&&parsed.count==1);
   assert(!strcmp(parsed.files[0].name,"CLIP-SAVE")&&!memcmp(parsed.files[0].data,save+128,8192));saveArchiveFree(&parsed);
   snprintf(destination,sizeof(destination),"storage/COPY%d-%d.arc",slot,format);
   assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))==1);free(archive);
   assert(filerFinishArchiveClipboard(destination,message,sizeof(message))==1&&nclipFiles==1);
  }
  // Cut checks happen only after a committed archive, and preserve changed,
  // unavailable or undeletable sources. A successful Cut consumes the clipboard.
  vmcMounted[slot%2]=1;put(source,save+128,8192);browser_cut=1;
  assert(filerCaptureArchiveClipboard(1,message,sizeof(message))==1);
  assert(filerCreateClipboardArchive(SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  snprintf(destination,sizeof(destination),"storage/CUT%d.mcs",slot);
  fail_after=0;assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))<0);
  assert(!access(source,F_OK)&&nclipFiles==1);fail_after=-1;
  assert(filerWriteArchive(archive,archive_size,destination,message,sizeof(message))==1);free(archive);
  unsigned before_generation=generation;generation++;
  assert(!filerFinishArchiveClipboard(destination,message,sizeof(message))&&!access(source,F_OK));generation=before_generation;
  if(slot<2){source_loaded=0;assert(!filerFinishArchiveClipboard(destination,message,sizeof(message)));source_loaded=1;}
  else {vmcMounted[slot%2]=0;assert(!filerFinishArchiveClipboard(destination,message,sizeof(message)));vmcMounted[slot%2]=1;}
  save[131]^=1;put(source,save+128,8192);
  assert(!filerFinishArchiveClipboard(destination,message,sizeof(message))&&!access(source,F_OK)&&nclipFiles==1);
  save[131]^=1;put(source,save+128,8192);delete_failure=1;
  assert(!filerFinishArchiveClipboard(destination,message,sizeof(message))&&!access(source,F_OK));delete_failure=0;
  int before_deletes=delete_calls;
  assert(filerFinishArchiveClipboard(destination,message,sizeof(message))==1&&access(source,F_OK)<0);
  assert(delete_calls==before_deletes+1&&!nclipFiles&&!browser_cut&&!filerArchiveClipboardKind());
 }
 // Eligibility comes from a copied/cut item; a generic flat folder needs no icon.sys.
 card_type=0;nclipFiles=1;browser_cut=0;strcpy(clipPath,"storage/");
 memset(&clipFiles[0],0,sizeof(clipFiles[0]));strcpy(clipFiles[0].name,"FLAT");
 clipFiles[0].stats.AttrFile=0x8427;
 assert(!mkdir("storage/FLAT",0700));put("storage/FLAT/data",save,32);
 assert(filerSaveKind(clipPath,&clipFiles[0],0)==FILER_SAVE_NONE);
 assert(filerCaptureArchiveClipboard(0,message,sizeof(message))==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 SaveArchive flat;assert(saveArchiveParse(&flat,archive,archive_size,archive_name));
 assert(!flat.ps1&&flat.count==1&&!strcmp(flat.folder.name,"FLAT")&&!strcmp(flat.files[0].name,"data"));
 assert(flat.files[0].size==32&&!memcmp(flat.files[0].data,save,32));saveArchiveFree(&flat);
 assert(filerWriteArchive(archive,archive_size,"storage/flat.psu",message,sizeof(message))==1);free(archive);
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_PSV,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&!archive&&strstr(message,"icon.sys"));
 // A subdirectory added after Copy keeps a Cut source safe after publishing its snapshot.
 browser_cut=1;assert(!mkdir("storage/FLAT/subdir",0700));
 assert(!filerFinishArchiveClipboard("storage/flat.psu",message,sizeof(message))&&!access("storage/FLAT/data",F_OK));
 assert(!rmdir("storage/FLAT/subdir"));
 assert(filerFinishArchiveClipboard("storage/flat.psu",message,sizeof(message))==1&&access("storage/FLAT",F_OK)<0);
 // A PS1 backup wrapper with extra files uses PSU so Cut cannot discard those files.
 browser_cut=0;nclipFiles=1;strcpy(clipPath,"storage/");strcpy(clipFiles[0].name,"PS1EXTRA");
 assert(!mkdir("storage/PS1EXTRA",0700));put("storage/PS1EXTRA/PS1EXTRA",save+128,8192);
 put("storage/PS1EXTRA/extra",save,32);
 assert(filerSaveKind(clipPath,&clipFiles[0],0)==FILER_SAVE_PS1);
 assert(filerCaptureArchiveClipboard(0,message,sizeof(message))==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(saveArchiveParse(&flat,archive,archive_size,archive_name)&&flat.count==2&&!flat.ps1);
 saveArchiveFree(&flat);free(archive);
 // Nested folders are ineligible both with and without PS2 save icon metadata.
 for(int with_icon=0;with_icon<2;with_icon++) {
  strcpy(clipFiles[0].name,with_icon?"PS2SAVE":"NESTED");nclipFiles=1;browser_cut=0;
  const char *nested=with_icon?"storage/PS2SAVE/subdir":"storage/NESTED/subdir";
  if(!with_icon)assert(!mkdir("storage/NESTED",0700));
  assert(!mkdir(nested,0700));
  assert(!filerCaptureArchiveClipboard(0,message,sizeof(message))&&!filerArchiveClipboardKind());
  assert(nclipFiles==1);assert(!rmdir(nested));
  if(!with_icon)assert(!rmdir("storage/NESTED"));
 }
 // A capped listing cannot prove that all children are files, so it stays ineligible.
 assert(!mkdir("storage/CAPPED",0700));strcpy(clipFiles[0].name,"CAPPED");
 for(int i=0;i<MAX_ENTRY-2;i++) {char path[80];snprintf(path,sizeof(path),"storage/CAPPED/file%02d",i);put(path,save,1);}
 assert(!mkdir("storage/CAPPED/hidden-subdir",0700));
 assert(!filerCaptureArchiveClipboard(0,message,sizeof(message))&&!filerArchiveClipboardKind());
 // Ordinary files and a selection with no clipboard are never archive sources.
 strcpy(clipFiles[0].name,"plain.bin");clipFiles[0].stats.AttrFile=0x8497;clipFiles[0].stats.FileSizeByte=32;
 put("storage/plain.bin",save,32);assert(!filerCaptureArchiveClipboard(0,message,sizeof(message))&&!filerArchiveClipboardKind());
 nclipFiles=0;assert(!filerCaptureArchiveClipboard(0,message,sizeof(message))&&!filerArchiveClipboardKind());
 // PS2 clipboard snapshots preserve all files and work with both output formats.
 card_type=2;nclipFiles=1;browser_cut=0;strcpy(clipPath,"storage/");
 memset(&clipFiles[0],0,sizeof(clipFiles[0]));strcpy(clipFiles[0].name,"PS2SAVE");clipFiles[0].stats.AttrFile=0x8427;
 assert(filerCaptureArchiveClipboard(0,message,sizeof(message))==1&&filerArchiveClipboardKind()==FILER_SAVE_PS2);
 for(int format=SAVE_OUTPUT_PSU;format<=SAVE_OUTPUT_PSV;format++) {
  assert(filerCreateClipboardArchive(format,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
  SaveArchive parsed;assert(saveArchiveParse(&parsed,archive,archive_size,archive_name)&&!parsed.ps1&&parsed.count==4);
  assert(!strcmp(parsed.folder.name,"PS2SAVE"));saveArchiveFree(&parsed);free(archive);
 }
 browser_cut=1;
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_PSU,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(filerWriteArchive(archive,archive_size,"storage/PS2SAVE/nested.psu",message,sizeof(message))==1);free(archive);
 assert(!filerFinishArchiveClipboard("storage/PS2SAVE/nested.psu",message,sizeof(message))&&!access("storage/PS2SAVE/icon.sys",F_OK));
 unlink("storage/PS2SAVE/nested.psu");
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_PSV,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))==1);
 assert(filerWriteArchive(archive,archive_size,"storage/clipboard-ps2.PSV",message,sizeof(message))==1);free(archive);
 assert(filerFinishArchiveClipboard("storage/clipboard-ps2.PSV",message,sizeof(message))==1&&access("storage/PS2SAVE",F_OK)<0&&!nclipFiles);
 nclipFiles=2;assert(!filerCaptureArchiveClipboard(0,message,sizeof(message))&&!filerArchiveClipboardKind());
 assert(filerCreateClipboardArchive(SAVE_OUTPUT_MCS,&archive,&archive_size,archive_name,sizeof(archive_name),message,sizeof(message))<0&&!archive);
 filerClearArchiveClipboard();
 char label[40];filerExtractLabel("file.pSv",label,sizeof(label));assert(!strcmp(label,"Extract PSV..."));
 selected.stats.AttrFile=0x8497;strcpy(selected.name,"input.mcs");
 assert(filerSaveKind("",&selected,0)==FILER_ARCHIVE_PS1);
 strcpy(selected.name,"bad.mcs");assert(filerSaveKind("",&selected,0)==FILER_ARCHIVE_PS1); // Hint only; full parsing rejects it.
 SaveArchive parsed;uint8_t *snapshot;assert(filerLoadSave("input.mcs",&parsed,&snapshot,message,sizeof(message)));
 assert(filerExtractSave(&parsed,"host:/",message,sizeof(message))<0);saveArchiveFree(&parsed);free(snapshot);assert(!handles);
 memset(clipFiles,0,sizeof(clipFiles));browser_cut=0;
 nclipFiles=1;strcpy(clipFiles[0].name,"BASLUS-RAW");clipFiles[0].stats.FileSizeByte=8192;
 assert(filerCanImportClipboard());clipFiles[0].stats.FileSizeByte=8191;assert(!filerCanImportClipboard());
 nclipFiles=1;strcpy(clipFiles[0].name,"input.mcs");clipPath[0]=0;generation=2;
 assert(filerImportClipboard("storage/",message,sizeof(message))<0&&strstr(message,"stack changed"));
 assert(!handles);puts("PASS: real save import/export, direct extraction, MCS/PSU/PSV creation, source snapshots, flat-folder clipboard eligibility without icon.sys, nested/capped folder rejection, empty files, both physical PS1 slots without mkdir, short I/O, card types, space preflight and failed-write/rename cleanup");
}
'''.replace('PRODUCTION_SAVES', str(root / 'src/filer_saves.c'))

with tempfile.TemporaryDirectory(prefix='save-import-') as folder:
    folder = Path(folder)
    for header in ('filer_saves.h', 'filer_shared.h', 'filer_actions.h', 'init.h'):
        (folder / header).write_text(stub)
    (folder / 'test.c').write_text(code)
    exe = folder / 'test'
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', *flags,
                    '-I', str(folder), '-I', str(root / 'include'), str(folder / 'test.c'),
                    str(root / 'src/save_archive.c'), str(root / 'src/save_lzari.c'), str(root / 'src/save_sign.c'), '-lz', '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder)], check=True, timeout=20)
