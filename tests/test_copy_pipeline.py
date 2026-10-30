"""Run the full production clipboard/paste/copy sequence on POSIX fixtures.

Drivers/RPCs are replaced by bounded file adapters and injected failures. The
copy orchestration, recursion, replacement transaction and diagnostics are real.
PSU archives use the real reader/writer helpers and matching MC table layout.
This does not emulate a UDPFS server, libmc or physical memory cards.
An optional copy source path runs the same matrix against a negative control.
"""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
root=Path(__file__).resolve().parents[1]
copy=(Path(sys.argv[1]) if len(sys.argv)>1 else root/'src/filer_copy.c').read_text()
browser=(root/'src/filer_browser.c').read_text()
mmce=(root/'iop/mmceman/src/mmce_fs.c').read_text()
device=(root/'src/filer_device.c').read_text()
hdd=(root/'src/gui_hdd0_format.c').read_text()
fileops=(root/'src/filer_fileops.c').read_text()

def function(source, signature):
    a=source.index(signature);b=source.index('{',a)+1;depth=1
    while depth:
        depth+=(source[b]=='{')-(source[b]=='}');b+=1
    return source[a:b]+'\n'

code=r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <dirent.h>
#include <malloc.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;typedef int64_t s64;
#include "mmce_cmds.h"
#include "mmce_path.h"
#define MAX_PATH 1024
#define MAX_NAME 256
#define MAX_ENTRY 16
#define MAX_RECURSE 16
#define FILEOP_TRACE 0
#define UDPFS 1
#define ETH 1
#define EXFAT 1
#define MMCE 1
#define MX4SIO 1
#define DVRP 1
#define XFROM 1
#define GIT_HASH "fixture-head"
#define TRUE 1
#define FALSE 0
#define PM_NORMAL 0
#define PM_PSU_BACKUP 1
#define PM_PSU_RESTORE 2
#define PM_RENAME 3
#define TRANSFER_STACK_READY 0
#define TRANSFER_STACK_LOAD_FAILED -1
#define TRANSFER_STACK_INCOMPATIBLE -2
#define COPY_BUFFER_FAST_DEFAULT 0x100000
#define TRANSFER_ETA_UPDATE_MS 1000
#define SOURCE_DEVICE_WAIT_TIMEOUT_MS 6000
#define SOURCE_DEVICE_WAIT_INTERVAL_MS 1000
#define MC_SFI 0xFEED
#define MC_ATTR_norm_folder 0x8427
#define MC_ATTR_norm_file 0x8497
#define HDD_ATTR_save_prot_folder 0xC4AF
#define HDD_ATTR_save_folder 0xC4A7
#define sceMcFileAttrSubdir 0x20
#define sceMcFileAttrPDAExec 0x100
#define sceMcFileAttrDupProhibit 0x80
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_EXCL O_EXCL
#define FIO_O_TRUNC O_TRUNC
#define FIO_S_ISDIR S_ISDIR
#define FIO_CST_ATTR 1
#define FIO_CST_CT 2
#define FIO_CST_AT 4
#define FIO_CST_MT 8
#define LNG(x) #x
#define DPRINTF(...) ((void)0)
typedef struct {u8 Reserved,Sec,Min,Hour,Day,Month;u16 Year;} Date;
typedef struct {Date _Create,_Modify;u32 FileSizeByte;u16 AttrFile,Reserve1;u32 Reserve2,PdaAplNo;char EntryName[32];} sceMcTblGetDir;
typedef struct {char name[MAX_NAME];unsigned char title[MAX_NAME];sceMcTblGetDir stats;} FILEINFO;
typedef struct {unsigned mode,attr,size,hisize;char ctime[8],mtime[8],atime[8];unsigned private_0,private_1,private_2;} iox_stat_t;
typedef struct {int unit;} iomanX_iop_file_t;
static struct {int PSU_HugeNames,PSU_DateNames,PSU_NoOverwrite;} config,*setting=&config;
static int PSU_content;
static int PM_flag[MAX_RECURSE],PM_file[MAX_RECURSE],PasteMode,PasteProgress_f,mctype_PSx;
static int nclipFiles,browser_cut,browser_pushed,browser_cd;
static FILEINFO clipFiles[MAX_ENTRY];static char clipPath[MAX_PATH];
static unsigned clipIopResetGeneration,generation;
static u64 written_size,PasteTime,clock_ms;
static int source_ready=1,load_ok=1,reset_preflight,read_cap=4096,write_cap=37,cancel_copy;
static int fail_open,fail_rewind,fail_read,fail_write,fail_close,fail_listing,fail_stat,fail_out_open,early_eof,fail_measure,corrupt_verify,fail_publish;
static int fail_tail_read,fail_tail_write,dash_active=1;
static int hdd_attr_calls,mc_attr_calls,mc_normal_files,mc_normal_folders,mc_last_flags,mc_last_port;
static unsigned hdd_last_attr;
static char hdd_last_path[MAX_PATH];
static sceMcTblGetDir mc_last_info;
static int fd_kind[1024],handles,read_calls,write_calls,psu_stat_is_dir,psu_stat_checks,psu_metadata,folder_deletes,overwrite_confirms;
static unsigned fd_generation[1024];
static int devicePrepareTransfer(const char *a,const char *b);
static int mx4sio_driver_running,USB_mass_loaded=1,host_error;
static int loadFlashModules(void){return 1;}
static int loadMmceModules(void){return 1;}
static int loadMx4sioModules(void){mx4sio_driver_running=1;return 1;}
static int loadAtaModules(void){return 1;}
static int loadPcCardCfModules(void){return 1;}
static int loadHddModules(void){return 1;}
static int loadDVRPHddModules(void){return 1;}
static int load_udpfs(void){return 1;}
static void loadUsbModules(void){USB_mass_loaded=1;}
static void loadCdModules(void){}
static void initHOST(void){host_error=0;}
static int isPathDeviceStackLoaded(const char *p){return !strncmp(p,"mx4sio",6)?mx4sio_driver_running:1;}
static int mmce_unit,mmce_phase,mmce_locked,mmce_stat_calls,mmce_fault_phase,mmce_bad_marker,mmce_status=-1;
static char mmce_name[MAX_PATH];
static int timeout_1s;
static int mmce_fs_getstat(iomanX_iop_file_t *file,const char *name,iox_stat_t *out);
static void mmce_fs_update_unit(int unit){assert(unit==0||unit==1);mmce_unit=unit;mmce_stat_calls++;}
static void mmce_sio2_lock(void){assert(!mmce_locked);mmce_locked=1;mmce_phase=0;}
static void mmce_sio2_unlock(void){assert(mmce_locked);mmce_locked=0;}
static void mmce_stat_word(u8 *out,u32 value){for(int i=0;i<4;i++)out[i]=(u8)(value>>(24-i*8));}
static int mmce_sio2_tx_rx_pio(int sent,int received,const void *send,void *receive,const int *timeout){
 assert(mmce_locked&&timeout==&timeout_1s);mmce_phase++;
 if(mmce_phase==mmce_fault_phase)return -1;
 if(mmce_phase==1){
  const u8 *cmd=send;assert(sent==4&&received==4&&cmd[0]==MMCE_ID&&cmd[1]==MMCE_CMD_FS_GETSTAT);
  memset(receive,0,received);((u8*)receive)[1]=mmce_bad_marker?0:MMCE_REPLY_CONST;
 }else if(mmce_phase==2){
  assert(!received&&sent==(int)strlen(send)+1);snprintf(mmce_name,sizeof(mmce_name),"%s",(const char*)send);
 }else{
  assert(mmce_phase==3&&!sent&&received==43);u8 *reply=receive;struct stat st;char path[MAX_PATH+16];
  snprintf(path,sizeof(path),"mmce%d:%s",mmce_unit,mmce_name);memset(reply,0,received);
  /* Real firmware GETSTAT: a failed read-only open is reported as status 1. */
  int missing=stat(path,&st);int status=mmce_status>=0?mmce_status:missing?1:0;reply[41]=status;
  if(!status){assert(!missing);mmce_stat_word(reply+1,st.st_mode);mmce_stat_word(reply+9,st.st_size);}
 }
 return 0;
}
static u64 Timer(void){return ++clock_ms;}
static unsigned getIopResetGeneration(void){return generation;}
static int prepareTransferDeviceStacks(const char *a,const char *b){assert(!handles || !reset_preflight);if(reset_preflight)generation++;return load_ok?devicePrepareTransfer(a,b):-1;}
static int clipboardSourceDeviceReady(void){return source_ready;}
static void waitUntilTimer(u64 end){clock_ms=end;}
static void drawMsg(const char *s){(void)s;}
static int ynDialog(const char *s){if(strstr(s,"Name_conflict_for_this_folder"))overwrite_confirms++;return cancel_copy?-1:1;}
static int readpad(void){return cancel_copy;}
static int DashIsActive(void){return dash_active;}
static int DashFileProgress(const char *a,const char *b,u64 r,u64 t){(void)a;(void)b;assert(r<=t);return 1;}
static int DashFileTransferProgress(const char *a,const char *b,u64 r,u64 t,const DashTransferStats *stats){
 assert(stats && stats->written_total==written_size && r<=t);
 assert(stats->current_speed>=-1 && stats->average_speed>=-1 && stats->remaining_seconds>=-1);
 if(!r)assert(stats->remaining_seconds==0);
 (void)a;(void)b;return 1;
}
static void nonDialog(char *s){(void)s;}
static int filenameKeyboard(char *s,int n,const char *directory){(void)s;(void)n;(void)directory;return 0;}
static int isPcCardCfPath(const char *s){return s&&!strncmp(s,"cf",2);}
static int isPcCardCfOnline(void){return 1;}
static void ensureMemoryCardPortAccessible(int p){assert(p==0||p==1);if(p==1&&mx4sio_driver_running){assert(!handles);mx4sio_driver_running=0;generation++;}}
static char *makeHostPath(char *d,char *s){if(d!=s)strcpy(d,s);return d;}
static void genLimObjName(char *p,int reserve){(void)p;(void)reserve;}
static int genGetStat(const char *p,iox_stat_t *out){struct stat s;if(!strncmp(p,"mmce",4)){iomanX_iop_file_t file={p[4]-'0'};return mmce_fs_getstat(&file,p+6,out);}if(psu_stat_is_dir && strstr(p,"/APP_LAUNCHSTATION/")){psu_stat_checks++;out->mode=S_IFDIR;return 0;}if(!strncmp(p,"host:",5))return -EIO;if(fail_stat&&!strncmp(p,"mc0:",4))return -EACCES;if(stat(p,&s))return -errno;out->mode=s.st_mode;return 0;}
static int genOpen(const char *p,int flags){
 if(fail_open&&flags==O_RDONLY&&!strncmp(p,"udpfs:",6))return -ENOENT;
 if(fail_out_open&&(flags&O_WRONLY))return -EACCES;
 int fd=open(p,flags,0600);if(fd<0)return -errno;assert(fd<1024);
 fd_kind[fd]=(flags&O_WRONLY)?2:!strncmp(p,"udpfs:",6)?1:3;
 fd_generation[fd]=generation;handles++;return fd;
}
static int genClose(int fd){int kind=fd_kind[fd];assert(kind&&handles>0);fd_kind[fd]=0;handles--;int r=close(fd);return fail_close&&kind==2?-EIO:r;}
static s64 genLseek(int fd,s64 n,int whence){assert(fd_generation[fd]==generation);if(fail_measure&&whence==SEEK_END)return -EIO;if(fail_rewind&&whence==SEEK_SET)return -EIO;return lseek(fd,n,whence);}
static int genRead(int fd,void *p,int n){assert(fd_generation[fd]==generation);read_calls++;if(early_eof&&fd_kind[fd]==1&&read_calls>1)return 0;if(fail_read&&fd_kind[fd]==1&&read_calls>=fail_read)return -ETIMEDOUT;if(fail_tail_read&&fd_kind[fd]==1){int left=256-lseek(fd,0,SEEK_CUR);if(!left)return 0;if(n>left)n=left;}int r=read(fd,p,n>read_cap?read_cap:n);if(corrupt_verify&&fd_kind[fd]==3&&r>0)((char*)p)[0]^=1;return r<0?-errno:r;}
static int genWrite(int fd,void *p,int n){assert(fd_generation[fd]==generation);write_calls++;if(fail_write&&write_calls>=2)return -ENOSPC;if(fail_tail_write){int left=256-lseek(fd,0,SEEK_CUR);if(!left)return 0;if(n>left)n=left;}int r=write(fd,p,n>write_cap?write_cap:n);return r<0?-errno:r;}
static int genRemove(char *p){return unlink(p)?-errno:0;}
static int fileXioRename(const char *a,const char *b){
 if(!strncmp(a,"udpfs:",6))return -EIO; /* Actual embedded UDPFS op is unsupported. */
 if(!strncmp(a,"xfrom",5))return -ENOSYS; /* Requires the flash RPC. */
 if(!strncmp(a,"vmc",3)){
  /* iomanX strips a device prefix, then VMCMAN expects a leaf <=32 bytes. */
  const char *name=strchr(b,':');name=name?name+1:b;
  if(strchr(name,'/')||strlen(name)>32)return -ENAMETOOLONG;
  char sibling[MAX_PATH];strcpy(sibling,a);char *leaf=strrchr(sibling,'/');assert(leaf);
  snprintf(leaf+1,sizeof(sibling)-(leaf+1-sibling),"%s",name);
  return fail_publish?-EIO:rename(a,sibling)?-errno:0;
 }
 return fail_publish?-EIO:rename(a,b)?-errno:0;
}
static int mc_result;
static int mcSetFileInfo(int port,int slot,const char *from,const sceMcTblGetDir *info,int flags){
 if(flags!=0x10){mc_attr_calls++;mc_last_port=port;mc_last_flags=flags;mc_last_info=*info;
  mc_normal_files+=info->AttrFile==MC_ATTR_norm_file;mc_normal_folders+=info->AttrFile==MC_ATTR_norm_folder;}
 (void)slot;if(flags==MC_SFI && strstr(from,"/APP_LAUNCHSTATION")) {
  assert(info->_Create.Year==2025 && info->_Modify.Year==2025);
  assert(info->AttrFile==MC_ATTR_norm_file || info->AttrFile==MC_ATTR_norm_folder);psu_metadata++;
 }
 if(flags==0x10){char a[MAX_PATH],b[MAX_PATH];snprintf(a,sizeof(a),"mc%d:/%s",port,from);strcpy(b,a);char *leaf=strrchr(b,'/');assert(leaf);snprintf(leaf+1,sizeof(b)-(leaf+1-b),"%.32s",info->EntryName);mc_result=fileXioRename(a,b);}else mc_result=0;return 0;
}
static int mcSync(int mode,void *c,int *r){(void)mode;(void)c;if(r)*r=mc_result;return 1;}
static int mcGetInfo(int p,int s,int *type,int *a,int *b){(void)p;(void)s;if(type)*type=2;if(a)*a=1000;if(b)*b=1000;return 0;}
static int xfromSetFileInfo(int port,int slot,const char *from,const sceMcTblGetDir *info,int flags){
 assert(!port&&!slot);mc_result=0;
 if(flags==0x10){
  char a[MAX_PATH],b[MAX_PATH];snprintf(a,sizeof(a),"xfrom0:/%s",from);strcpy(b,a);
  char *leaf=strrchr(b,'/');assert(leaf);snprintf(leaf+1,sizeof(b)-(leaf+1-b),"%.32s",info->EntryName);
  mc_result=fail_publish?-EIO:rename(a,b)?-errno:0;
 }return 0;
}
static int xfromSync(int mode,void *c,int *r){return mcSync(mode,c,r);}
static int xfromGetInfo(int p,int s,int *type,int *a,int *b){return mcGetInfo(p,s,type,a,b);}
static int applyMcInfoToXfromPath(const char *p,const sceMcTblGetDir *s){(void)p;(void)s;return 0;}
static int fileXioChStat(const char *p,const iox_stat_t *s,int f){if(f&FIO_CST_ATTR){hdd_attr_calls++;hdd_last_attr=s->attr;snprintf(hdd_last_path,sizeof(hdd_last_path),"%s",p);}return 0;}
static int getHddParty(const char *p,const FILEINFO *f,char *a,char *b);
static int getHddDVRPParty(const char *p,const FILEINFO *f,char *a,char *b);
static int mountParty(const char *p){assert(!strncmp(p,"hdd",3));return p[3]-'0';}
static int getDVRPPartyMountIndex(const char *p){return strstr(p,"__xdata")?1:0;}
static int mountDVRPParty(const char *p){return getDVRPPartyMountIndex(p);}
static int fileShowTitles(void){return 0;}
static int filerGetGameTitle(const char *p,const FILEINFO *f,unsigned char *out){(void)p;(void)f;out[0]=0;return -1;}
static void transcpy_sjis(char *out,const unsigned char *in){strcpy(out,(const char *)in);}
static int filerConfirmExploitDelete(const char *p,const FILEINFO *f){(void)p;(void)f;return 1;}
static int filerConfirmExploitModify(const char *p,const FILEINFO *f){(void)p;(void)f;return 1;}
static int filerIsExploitProtectedPath(const char *p,const FILEINFO *f){(void)p;(void)f;return 0;}
static int delete(const char *p,const FILEINFO *f){
 char path[MAX_PATH],child[MAX_PATH+MAX_NAME];
 if(!strncmp(p,"hdd",3)){char party[MAX_NAME];assert(!getHddParty(p,f,party,path));path[3]='0'+mountParty(party);}
 else if(!strncmp(p,"dvr_hdd",7)){char party[MAX_NAME];assert(!getHddDVRPParty(p,f,party,path));path[7]='0'+mountDVRPParty(party);}
 else snprintf(path,sizeof(path),"%s%s",p,f->name);
 if(!(f->stats.AttrFile&sceMcFileAttrSubdir))return unlink(path)?-errno:0;
 folder_deletes++;
 DIR *d=opendir(path);assert(d);struct dirent *e;
 while((e=readdir(d))) {
  if(!strcmp(e->d_name,".") || !strcmp(e->d_name,".."))continue;
  snprintf(child,sizeof(child),"%s/%s",path,e->d_name);struct stat st;assert(!stat(child,&st));
  FILEINFO entry={0};snprintf(entry.name,sizeof(entry.name),"%s",e->d_name);
  entry.stats.AttrFile=S_ISDIR(st.st_mode)?sceMcFileAttrSubdir:0;
  char parent[MAX_PATH];snprintf(parent,sizeof(parent),"%s%s",path,path[strlen(path)-1]=='/'?"":"/");
  assert(!delete(parent,&entry));
 }
 assert(!closedir(d));return rmdir(path)?-errno:0;
}
static void markMx4sioDestinationAfterWrite(const char *p){(void)p;}
static int genCmpFileExt(const char *p,const char *e){const char *dot=strrchr(p,'.');return dot && !strcasecmp(dot+1,e);}
static void fixtureDir(const char *logical,char *physical){
 char party[MAX_NAME];
 if(!strncmp(logical,"hdd",3)){assert(!getHddParty(logical,NULL,party,physical));physical[3]='0'+mountParty(party);}
 else if(!strncmp(logical,"dvr_hdd",7)){assert(!getHddDVRPParty(logical,NULL,party,physical));physical[7]='0'+mountDVRPParty(party);}
 else strcpy(physical,logical);
}
static int newdir(const char *parent,const char *name){char p[MAX_PATH],dir[MAX_PATH];fixtureDir(parent,dir);snprintf(p,sizeof(p),"%s%s",dir,name);return mkdir(p,0700)?-errno:0;}
static int getDir(const char *p,FILEINFO *out){
 char physical[MAX_PATH];fixtureDir(p,physical);p=physical;
 if(fail_listing)return -EIO;DIR *d=opendir(p);if(!d)return -errno;struct dirent *e;int n=0;
 while((e=readdir(d))){if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;assert(n<MAX_ENTRY);memset(&out[n],0,sizeof(out[n]));snprintf(out[n].name,sizeof(out[n].name),"%s",e->d_name);char full[MAX_PATH];snprintf(full,sizeof(full),"%s%s",p,e->d_name);struct stat st;assert(!stat(full,&st));out[n].stats.AttrFile=S_ISDIR(st.st_mode)?sceMcFileAttrSubdir:0;out[n].stats.FileSizeByte=st.st_size;n++;}closedir(d);return n;
}
static int applyMcInfoToVmcPath(const char *p,const sceMcTblGetDir *s){(void)p;(void)s;return 0;}
'''
# Compile the real metadata constants too; changing a production flag must
# affect these tests rather than being masked by a fixture definition.
for name in ('MC_SFI', 'MC_ATTR_norm_folder', 'MC_ATTR_norm_file',
             'HDD_ATTR_save_folder', 'HDD_ATTR_save_prot_folder', 'COPY_BUFFER_FAST_DEFAULT'):
    definition = next(line for line in copy.splitlines() if line.startswith('#define ' + name + ' '))
    code = re.sub(r'^#define ' + name + r' .*$', definition, code, flags=re.MULTILINE)
code+=function(mmce,'int mmce_fs_getstat(').replace('int mmce_fs_getstat(', 'static int mmce_fs_getstat(',1)
for sig in ('static int ensurePathPcCardCfOnline(', 'static void normalizePcCardCfPath(',
            'int genCanRenamePath(', 'static int renameCardResult(', 'int genRenameNoReplace('):
    code+=function(fileops,sig)
code+=device[device.index('enum {'):].replace('int prepareTransferDeviceStacks(', 'static int devicePrepareTransfer(')
for sig in ('static int getHddDeviceFromPath(', 'int getHddParty(', 'int getHddDVRPParty('):
    code+=function(hdd,sig).replace('int getHddParty(', 'static int getHddParty(').replace('int getHddDVRPParty(', 'static int getHddDVRPParty(')
# Use the actual archive format and PSU helper implementation.
psu=(root/'include/psu_types.h').read_text();code+=psu[psu.index('typedef struct'):psu.rindex('#endif')]
psu_impl=(root/'src/psu_functions.c').read_text()
code+= "\n".join(line for line in psu_impl.splitlines() if not line.startswith('#include')) + "\n"
dash_header=(root/'include/dash.h').read_text()
start=dash_header.index('typedef struct\n{\n\tu64 written_total;')
stats_type=dash_header[start:dash_header.index('} DashTransferStats;',start)+len('} DashTransferStats;')]
code=code.replace('#include "mmce_cmds.h"',stats_type+'\n#include "mmce_cmds.h"',1)
a=copy.index('/* One paste context');b=copy.index('static int isMemoryCardLikePath(',a);code+=copy[a:b]
for sig in ('static int isMemoryCardLikePath(', 'static int isHddCommonParty(',
            'static int copyReadChunk(', 'static int copyWriteChunk(',
            'static int calcTransferSpeed(', 'static int calcRemainingTime(',
            'static int smoothTransferSpeed(', 'static int applyMcInfoToMcPath(',
            'static const char *getXfromRelativePath(const char *path)\n{'):
    code+=function(copy,sig)
code+=copy[copy.index('int copy('):]
code+=function(browser,'static int waitForClipboardSourceDevice(')
code+=function(browser,'static void subfunc_Paste(')
code+=r'''
static void put(const char *p,const unsigned char *data,int n){int fd=open(p,O_CREAT|O_TRUNC|O_WRONLY,0600);assert(fd>=0);assert(write(fd,data,n)==n);assert(!close(fd));}
static int matches(const char *p,const unsigned char *data,int n){unsigned char out[70000];int fd=open(p,O_RDONLY);if(fd<0)return 0;int count=read(fd,out,sizeof(out));close(fd);return count==n&&!memcmp(data,out,n);}
static unsigned char input[65537];
static void putPattern(const char *path,int size) {
 int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);assert(fd>=0);
 while(size) {int n=size<(int)sizeof(input)?size:(int)sizeof(input);assert(write(fd,input,n)==n);size-=n;}
 assert(!close(fd));
}

static void psuHeader(int fd,const char *name,int size,int directory) {
 psu_header h;memset(&h,0,sizeof(h));h.attr=directory?0x8427:0x8497;h.size=size;
 h.cTime.year=2025;h.cTime.month=7;h.cTime.day=2;h.mTime=h.cTime;
 snprintf((char*)h.name,sizeof(h.name),"%s",name);assert(write(fd,&h,sizeof(h))==sizeof(h));
}

static void psuFile(int fd,const char *name,int size) {
 psuHeader(fd,name,size,0);int left=size;
 while(left) {int chunk=left<(int)sizeof(input)?left:(int)sizeof(input);assert(write(fd,input,chunk)==chunk);left-=chunk;}
 unsigned char padding[1024];memset(padding,255,sizeof(padding));
 int pad=(1024-(size%1024))%1024;assert(write(fd,padding,pad)==pad);
}
static void makePsu(const char *path) {
 int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);assert(fd>=0);
 psuHeader(fd,"APP_LAUNCHSTATION",5,1);psuHeader(fd,".",0,1);psuHeader(fd,"..",0,1);
 psuFile(fd,"LAUNCHSTATION.ELF",1443120);psuFile(fd,"icon.sys",257);psuFile(fd,"EMPTY",0);assert(!close(fd));
}
static int matchesPsu(const char *path,int size) {
 unsigned char bytes[4096];int fd=open(path,O_RDONLY),done=0,n;
 if(fd<0)return 0;
 while((n=read(fd,bytes,sizeof(bytes)))>0) {
  for(int i=0;i<n;i++)assert(bytes[i]==input[(done+i)%sizeof(input)]);
  done+=n;
 }
 close(fd);return !n && done==size;
}
static void reset(void){assert(!handles&&!mmce_locked);hdd_attr_calls=mc_attr_calls=mc_normal_files=mc_normal_folders=0;mx4sio_driver_running=0;USB_mass_loaded=1;mmce_fault_phase=mmce_bad_marker=mmce_stat_calls=0;mmce_status=-1;psu_stat_is_dir=psu_stat_checks=psu_metadata=folder_deletes=overwrite_confirms=0;read_cap=4096;write_cap=37;source_ready=load_ok=dash_active=1;reset_preflight=0;fail_open=fail_rewind=fail_read=fail_write=fail_close=fail_listing=cancel_copy=fail_stat=fail_out_open=early_eof=fail_measure=corrupt_verify=fail_publish=fail_tail_read=fail_tail_write=0;read_calls=write_calls=0;browser_cut=0;browser_cd=0;generation=1;clipIopResetGeneration=1;PasteMode=PM_NORMAL;strcpy(clipPath,"udpfs:/");nclipFiles=1;memset(clipFiles,0,sizeof(clipFiles));strcpy(clipFiles[0].name,"BOOT.ELF");clipFiles[0].stats.FileSizeByte=sizeof(input);}
int main(void){
 assert(sizeof(copy_diag)<=128); /* fixed runtime budget, no log allocation */
 assert(MC_ATTR_norm_folder==0x8427&&MC_ATTR_norm_file==0x8497);
 assert(HDD_ATTR_save_folder==0xC4A7&&HDD_ATTR_save_prot_folder==0xC4AF);
 mkdir("udpfs:",0700);mkdir("mc0:",0700);mkdir("mc1:",0700);mkdir("usb0:",0700);mkdir("host:",0700);
 mkdir("mmce0:",0700);mkdir("mmce1:",0700);
 for(int i=0;i<(int)sizeof(input);i++)input[i]=(unsigned char)(i*19+7);
 put("udpfs:/BOOT.ELF",input,sizeof(input));
 const char *destinations[]={"mc0:/","mc1:/","usb0:/"};char message[MAX_PATH],target[MAX_PATH];
 /* Reproduce MC0 -> MMCE0: actual driver packets return status 1 when the
  * first APOLLO.ELF destination is absent, not a fileXio errno. */
 mkdir("mc0:/APOLLO",0700);putPattern("mc0:/APOLLO/APOLLO.ELF",15523560);
 for(int port=0;port<2;port++)for(int attempt=0;attempt<2;attempt++) {
  reset();strcpy(clipPath,"mc0:/");strcpy(clipFiles[0].name,"APOLLO");
  read_cap=65536;write_cap=4093;
  clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
  char dest[12];snprintf(dest,sizeof(dest),"mmce%d:/",port);
  message[0]=0;subfunc_Paste(message,dest);
  if(message[0])fprintf(stderr,"MC-to-MMCE failure: %s\n",message);
  assert(!message[0]&&!handles&&!mmce_locked&&mmce_stat_calls>0&&generation==1);
  assert(copy_diag.total==15523560&&copy_diag.done==15523560);
  snprintf(target,sizeof(target),"%sAPOLLO/APOLLO.ELF",dest);assert(matchesPsu(target,15523560));
 }
 /* Both MMCE units work in either direction with MC/USB and each other,
  * including shorter verified replacements with no stale trailing bytes. */
 const char *routes[][2]={{"mc0:/","mmce0:/"},{"mc1:/","mmce1:/"},{"usb0:/","mmce0:/"},
  {"mmce0:/","usb0:/"},{"mmce1:/","mc0:/"},{"mmce0:/","mc1:/"},{"mmce0:/","mmce1:/"}};
 for(unsigned route=0;route<sizeof(routes)/sizeof(routes[0]);route++)for(int attempt=0;attempt<2;attempt++) {
  int length=attempt?17:257;char from[MAX_PATH];
  snprintf(from,sizeof(from),"%sROUTE.BIN",routes[route][0]);put(from,input,length);
  reset();strcpy(clipPath,routes[route][0]);strcpy(clipFiles[0].name,"ROUTE.BIN");
  clipFiles[0].stats.FileSizeByte=length;message[0]=0;subfunc_Paste(message,(char*)routes[route][1]);
  assert(!message[0]&&!handles&&!mmce_locked&&generation==1);
  snprintf(target,sizeof(target),"%sROUTE.BIN",routes[route][1]);assert(matches(target,input,length));
 }
 for(unsigned route=0;route<sizeof(routes)/sizeof(routes[0]);route++) {
  char from[MAX_PATH];snprintf(from,sizeof(from),"%sMOVE.BIN",routes[route][0]);put(from,input,257);
  reset();browser_cut=1;strcpy(clipPath,routes[route][0]);strcpy(clipFiles[0].name,"MOVE.BIN");
  clipFiles[0].stats.FileSizeByte=257;message[0]=0;subfunc_Paste(message,(char*)routes[route][1]);
  assert(!message[0]&&!handles&&!nclipFiles&&access(from,F_OK)<0);
  snprintf(target,sizeof(target),"%sMOVE.BIN",routes[route][1]);assert(matches(target,input,257));
 }
 /* Timeouts, bad headers and unknown firmware statuses remain failures.
  * Never classify a transport error as an absent destination and overwrite. */
 const unsigned char guard[]="preserve the old destination";
 put("mc0:/GUARD.BIN",input,257);
 for(int failure=0;failure<6;failure++) {
  put("mmce0:/GUARD.BIN",guard,sizeof(guard));reset();
  strcpy(clipPath,"mc0:/");strcpy(clipFiles[0].name,"GUARD.BIN");
  browser_cut=failure&1;
  if(failure<3)mmce_fault_phase=failure+1;
  else if(failure==3)mmce_bad_marker=1;
  else mmce_status=failure==4?2:255;
  message[0]=0;subfunc_Paste(message,"mmce0:/");
  assert(strstr(message,"Checking destination")&&!handles&&!mmce_locked&&!write_calls);
  assert(matches("mmce0:/GUARD.BIN",guard,sizeof(guard))&&matches("mc0:/GUARD.BIN",input,257));
 }
 reset();iox_stat_t untouched,stat_reply;memset(&untouched,0xa7,sizeof(untouched));
 stat_reply=untouched;assert(genGetStat("mmce0:/ABSENT.BIN",&stat_reply)==-ENOENT);
 assert(!memcmp(&untouched,&stat_reply,sizeof(stat_reply))&&!mmce_locked);
 char long_name[256];memset(long_name,'a',sizeof(long_name));long_name[255]=0;
 iomanX_iop_file_t unit={0};int before_stat=mmce_stat_calls;
 assert(mmce_fs_getstat(&unit,long_name,&stat_reply)==-ENAMETOOLONG);
 assert(mmce_stat_calls==before_stat&&!mmce_locked);
 for(int device=0;device<3;device++)for(int attempt=0;attempt<3;attempt++){
  reset();message[0]=0;char dest[12];strcpy(dest,destinations[device]);
  subfunc_Paste(message,dest);assert(!message[0]&&!handles);
  snprintf(target,sizeof(target),"%sBOOT.ELF",dest);assert(matches(target,input,sizeof(input)));
 }
 /* Legacy host: cannot stat files; new and shorter replacement writes must work. */
 for(int attempt=0;attempt<3;attempt++){
  int length=attempt==2?17:(int)sizeof(input);
  put("usb0:/HOST.BIN",input,length);reset();strcpy(clipPath,"usb0:/");strcpy(clipFiles[0].name,"HOST.BIN");
  message[0]=0;subfunc_Paste(message,"host:/");assert(!message[0]&&!handles);
  assert(matches("host:/HOST.BIN",input,length));
 }
 /* Exercise all fixture boundary lengths through ordinary and replacement I/O. */
 const int lengths[]={0,1,16383,16384,16385,65535,65536,65537};
 for(unsigned length=0;length<sizeof(lengths)/sizeof(lengths[0]);length++){
  put("udpfs:/BOUNDARY.BIN",input,lengths[length]);unlink("mc0:/BOUNDARY.BIN");
  for(int attempt=0;attempt<2;attempt++){
   reset();strcpy(clipFiles[0].name,"BOUNDARY.BIN");clipFiles[0].stats.FileSizeByte=lengths[length];
   message[0]=0;subfunc_Paste(message,"mc0:/");assert(!message[0]&&!handles);
   assert(matches("mc0:/BOUNDARY.BIN",input,lengths[length]));
  }
 }
 const unsigned char old[]="original ELF";
 const char *stages[]={"Opening source","Rewinding source","Reading source","Writing destination","Closing destination","Copy cancelled","Preparing devices","Checking source","Checking destination","Opening destination","Reading source","Measuring source","Verifying replacement","Publishing replacement"};
 for(int failure=0;failure<14;failure++){
  reset();put("mc0:/BOOT.ELF",old,sizeof(old));
  if(failure==0)fail_open=1;if(failure==1)fail_rewind=1;if(failure==2)fail_read=1;
  if(failure==3)fail_write=1;if(failure==4)fail_close=1;if(failure==5)cancel_copy=1;
  if(failure==6)load_ok=0;if(failure==7){source_ready=0;reset_preflight=1;}
  if(failure==8)fail_stat=1;if(failure==9)fail_out_open=1;if(failure==10)early_eof=1;
  if(failure==11)fail_measure=1;if(failure==12)corrupt_verify=1;if(failure==13)fail_publish=1;
  message[0]=0;subfunc_Paste(message,"mc0:/");
  assert(message[0]&&strstr(message,stages[failure])&&strstr(message,"fixture-head"));
  assert(!handles&&matches("mc0:/BOOT.ELF",old,sizeof(old)));
  if(failure==3){assert(strstr(message,"37/65537 B")&&strstr(message,"(-28)")&&strstr(message,"Not enough free space"));}
  if(failure==7)assert(strstr(message,"IOP 1>2"));
 }
 /* Nested ordinary folders use the same production recursion. */
 reset();mkdir("udpfs:/NESTED",0700);put("udpfs:/NESTED/CHILD.BIN",input,257);
 strcpy(clipFiles[0].name,"NESTED");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
 message[0]=0;subfunc_Paste(message,"mc0:/");assert(!message[0]);assert(matches("mc0:/NESTED/CHILD.BIN",input,257));
 /* A failed source listing must not report a successful empty folder copy. */
 reset();strcpy(clipFiles[0].name,"NESTED");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;fail_listing=1;
 message[0]=0;subfunc_Paste(message,"mc1:/");assert(strstr(message,"Listing source (-5)"));
 /* An empty folder can be pasted repeatedly even without a game-save title. */
 reset();mkdir("udpfs:/EMPTY",0700);strcpy(clipFiles[0].name,"EMPTY");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
 for(int attempt=0;attempt<3;attempt++){message[0]=0;subfunc_Paste(message,"mc0:/");assert(!message[0]&&!handles);}
 /* Same-directory paste is a no-op, even for Cut. Preserve the source and
  * do not perform device setup, copy I/O, or move-source deletion. */
 for(int cut=0;cut<2;cut++) {
  reset();strcpy(clipPath,"mc0:/");browser_cut=cut;message[0]=0;
  put("mc0:/BOOT.ELF",input,sizeof(input));load_ok=source_ready=0;
  subfunc_Paste(message,"mc0:/");
  assert(!message[0] && browser_cd && !handles && !read_calls && !write_calls);
  assert(nclipFiles==(cut?0:1));assert(matches("mc0:/BOOT.ELF",input,sizeof(input)));
 }
 /* Repeated operations clear prior error state, and formatting is bounded. */
 reset();message[0]=0;subfunc_Paste(message,"mc0:/");assert(!message[0]);
 char bounded[17];memset(bounded,'x',sizeof(bounded));filerCopyDiagFormat(bounded,16,-1);assert(!bounded[15]&&bounded[16]=='x');

 /* Reproduce the reported MC stat response: it classified the new archive's
  * LAUNCHSTATION.ELF as a directory (-21). R3Z writes PSU entries directly
  * after creating/recreating the restore folder, without querying that stat.
  * Include the original 1,443,120-byte size, padding, empty files and both slots. */
 makePsu("udpfs:/SAVE.PSU");
 for(int port=0;port<2;port++)for(int attempt=0;attempt<2;attempt++) {
  reset();PasteMode=PM_PSU_RESTORE;strcpy(clipFiles[0].name,"SAVE.PSU");psu_stat_is_dir=1;
  char dest[12];snprintf(dest,sizeof(dest),"mc%d:/",port);
  message[0]=0;subfunc_Paste(message,dest);
  if(message[0])fprintf(stderr,"PSU failure: %s\n",message);
  assert(!message[0] && !handles && !copy_diag.error && generation==1);
  assert(!psu_stat_checks && psu_metadata==4);
  assert(folder_deletes==attempt && overwrite_confirms==attempt);
  snprintf(target,sizeof(target),"%sAPP_LAUNCHSTATION/LAUNCHSTATION.ELF",dest);assert(matchesPsu(target,1443120));
  snprintf(target,sizeof(target),"%sAPP_LAUNCHSTATION/icon.sys",dest);assert(matches(target,input,257));
  snprintf(target,sizeof(target),"%sAPP_LAUNCHSTATION/EMPTY",dest);assert(matches(target,input,0));
 }
 /* Keep ordinary-copy directory protections; the exception is PSU restore. */
 reset();psu_stat_is_dir=1;message[0]=0;subfunc_Paste(message,"mc0:/APP_LAUNCHSTATION/");
 assert(strstr(message,"Checking destination (-21)") && psu_stat_checks && !handles);
 assert(matchesPsu("mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF",1443120));
 /* A real write failure still reports the failing entry and can be retried
  * over the empty restore folder left behind, with overwrite confirmation. */
 mkdir("mc0:/PSU-FAIL",0700);reset();PasteMode=PM_PSU_RESTORE;strcpy(clipFiles[0].name,"SAVE.PSU");
 psu_stat_is_dir=1;fail_write=1;message[0]=0;subfunc_Paste(message,"mc0:/PSU-FAIL/");
 assert(strstr(message,"Writing destination (-28)") && strstr(message,"LAUNCHSTATION.ELF") && !handles);
 assert(!psu_stat_checks && access("mc0:/PSU-FAIL/APP_LAUNCHSTATION/LAUNCHSTATION.ELF",F_OK)<0);
 reset();PasteMode=PM_PSU_RESTORE;strcpy(clipFiles[0].name,"SAVE.PSU");psu_stat_is_dir=1;
 message[0]=0;subfunc_Paste(message,"mc0:/PSU-FAIL/");
 assert(!message[0] && !handles && folder_deletes==1 && overwrite_confirms==1);
 assert(matchesPsu("mc0:/PSU-FAIL/APP_LAUNCHSTATION/LAUNCHSTATION.ELF",1443120));
 makePsu("udpfs:/TRUNC.PSU");assert(!truncate("udpfs:/TRUNC.PSU",4*512+1000));
 mkdir("mc0:/PSU-TRUNC",0700);reset();PasteMode=PM_PSU_RESTORE;strcpy(clipFiles[0].name,"TRUNC.PSU");
 message[0]=0;subfunc_Paste(message,"mc0:/PSU-TRUNC/");
 assert(strstr(message,"Reading source (-5)") && strstr(message,"LAUNCHSTATION.ELF") && !handles);
 /* Full device-family matrix: real copy, move and stack policy; file I/O,
  * mounts, flash RPC and VMCMAN rename contract use host adapters. Logical
  * HDD/DVR paths use the actual partition parser, then fixture mount slots. */
 const char *devices[]={"mc0:/","mc1:/","usb0:/","usb1:/","mass0:/","ata0:/",
  "mmce0:/","mmce1:/","mx4sio:/","vmc0:/","vmc1:/","pfs0:/","pfs1:/",
  "hdd0:/TRANSFER/","hdd1:/TRANSFER/","dvr_hdd0:/__xcontents/","dvr_hdd0:/__xdata/",
  "xfrom0:/","cf0:/","host:/","udpfs:/","cdfs:/"};
 const int count=sizeof(devices)/sizeof(devices[0]);int pairs=0,blocked=0,file_ops=0,folder_ops=0;
 for(int i=0;i<count;i++) {
  char dir[MAX_PATH];fixtureDir(devices[i],dir);char *colon=strchr(dir,':');assert(colon);
  char root[MAX_PATH];snprintf(root,sizeof(root),"%.*s:",(int)(colon-dir),dir);mkdir(root,0700);
  snprintf(target,sizeof(target),"%sM-SRC",dir);mkdir(target,0700);
  snprintf(target,sizeof(target),"%sM-DST",dir);mkdir(target,0700);
 }
 for(int s=0;s<count;s++)for(int d=0;d<count;d++) {
  if(!strncmp(devices[d],"cdfs:",5))continue; /* Optical media is a source only. */
  char src[MAX_PATH],dst[MAX_PATH],src_dir[MAX_PATH],dst_dir[MAX_PATH],from[MAX_PATH];
  snprintf(src,sizeof(src),"%sM-SRC/",devices[s]);snprintf(dst,sizeof(dst),"%sM-DST/",devices[d]);
  fixtureDir(src,src_dir);fixtureDir(dst,dst_dir);
  reset();int policy=devicePrepareTransfer(src,dst);
  if(policy==TRANSFER_STACK_INCOMPATIBLE){
   strcpy(clipPath,src);message[0]=0;subfunc_Paste(message,dst);
   assert(!handles&&!read_calls&&!write_calls);blocked++;continue;
  }
  assert(policy==TRANSFER_STACK_READY);pairs++;
  /* New file, smaller replacement, empty replacement, then Cut/Paste. */
  const int sizes[]={257,17,0,257};
  for(int attempt=0;attempt<4;attempt++) {
   if(attempt==3&&!strncmp(devices[s],"cdfs:",5))continue;
   reset();read_cap=127;write_cap=31;strcpy(clipPath,src);strcpy(clipFiles[0].name,"MATRIX.BIN");
   clipFiles[0].stats.FileSizeByte=sizes[attempt];browser_cut=attempt==3;
   snprintf(from,sizeof(from),"%sMATRIX.BIN",src_dir);put(from,input,sizes[attempt]);
   snprintf(target,sizeof(target),"%sMATRIX.BIN",dst_dir);if(!attempt)unlink(target);
   message[0]=0;subfunc_Paste(message,dst);
   if(message[0])fprintf(stderr,"Matrix %s -> %s attempt %d: %s\n",src,dst,attempt,message);
   assert(!message[0]&&!handles&&matches(target,input,sizes[attempt]));
   assert(browser_cut?(!nclipFiles&&access(from,F_OK)<0):matches(from,input,sizes[attempt]));file_ops++;
  }
  /* A nested folder and empty child, then a move over that existing folder. */
  for(int cut=0;cut<2;cut++) {
   if(cut&&!strncmp(devices[s],"cdfs:",5))continue;
   snprintf(from,sizeof(from),"%sTREE",src_dir);mkdir(from,0700);
   snprintf(from,sizeof(from),"%sTREE/EMPTY",src_dir);mkdir(from,0700);
   snprintf(from,sizeof(from),"%sTREE/LEAF.BIN",src_dir);put(from,input,257);
   reset();read_cap=127;write_cap=31;strcpy(clipPath,src);strcpy(clipFiles[0].name,"TREE");
   clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;browser_cut=cut;
   message[0]=0;subfunc_Paste(message,dst);
   if(message[0])fprintf(stderr,"Folder matrix %s -> %s: %s\n",src,dst,message);
   assert(!message[0]&&!handles);snprintf(target,sizeof(target),"%sTREE/LEAF.BIN",dst_dir);
   assert(matches(target,input,257));snprintf(target,sizeof(target),"%sTREE/EMPTY",dst_dir);
   struct stat st;assert(!stat(target,&st)&&S_ISDIR(st.st_mode));
   snprintf(from,sizeof(from),"%sTREE",src_dir);assert(cut?access(from,F_OK)<0:!access(from,F_OK));folder_ops++;
  }
 }
 printf("PASS: host matrix %d compatible ordered pairs, %d blocked, %d file and %d folder operations; 22 paths including HDD/DVR parsers, VMC/flash/UDPFS rename contracts\n",pairs,blocked,file_ops,folder_ops);
 /* The exact last byte must survive around FIFO/alignment and every copy
  * buffer size. Exercise both dashboard and classic buffer selection. */
 const int boundaries[]={0,1,2,3,63,64,65,127,128,129,1459,1460,1461,
  16383,16384,16385,65535,65536,65537,131071,131072,131073,262143,262144,262145,
  393215,393216,393217,524287,524288,524289,1048575,1048576,1048577};
 const char *tail_dest[]={"mc0:/","mc1:/","usb0:/","mmce0:/","mx4sio:/","vmc0:/","pfs0:/","ata0:/","cf0:/"};
 int boundary_ops=0;
 for(unsigned d=0;d<sizeof(tail_dest)/sizeof(tail_dest[0]);d++)
 for(unsigned b=0;b<sizeof(boundaries)/sizeof(boundaries[0]);b++)for(int attempt=0;attempt<2;attempt++) {
  reset();dash_active=attempt;read_cap=8191;write_cap=4093;
  if(!strncmp(tail_dest[d],"cf",2))strcpy(clipPath,"usb0:/");
  strcpy(clipFiles[0].name,"TAIL.BIN");clipFiles[0].stats.FileSizeByte=boundaries[b];
  char from[MAX_PATH];snprintf(from,sizeof(from),"%sTAIL.BIN",clipPath);putPattern(from,boundaries[b]);
  snprintf(target,sizeof(target),"%sTAIL.BIN",tail_dest[d]);if(!attempt)unlink(target);
  message[0]=0;subfunc_Paste(message,(char*)tail_dest[d]);
  assert(!message[0]&&!handles&&matchesPsu(target,boundaries[b]));boundary_ops++;
 }
 /* Premature EOF or a stalled write on byte 257 must retain a Cut source.
  * Old destinations survive staged failure; incomplete new files are removed. */
 for(int reading=0;reading<2;reading++)for(int replacing=0;replacing<2;replacing++) {
  reset();browser_cut=1;strcpy(clipFiles[0].name,"LAST.BIN");clipFiles[0].stats.FileSizeByte=257;
  put("udpfs:/LAST.BIN",input,257);unlink("mmce0:/LAST.BIN");
  if(replacing)put("mmce0:/LAST.BIN",guard,sizeof(guard));
  fail_tail_read=reading;fail_tail_write=!reading;message[0]=0;
  subfunc_Paste(message,"mmce0:/");
  assert(strstr(message,reading?"Reading source":"Writing destination")&&!handles&&nclipFiles==1);
  assert(matches("udpfs:/LAST.BIN",input,257));
  assert(replacing?matches("mmce0:/LAST.BIN",guard,sizeof(guard)):access("mmce0:/LAST.BIN",F_OK)<0);
 }
 /* A later item failing also preserves earlier move sources. */
 reset();browser_cut=1;nclipFiles=2;fail_read=2;
 strcpy(clipFiles[0].name,"FIRST.BIN");clipFiles[1]=clipFiles[0];strcpy(clipFiles[1].name,"SECOND.BIN");
 put("udpfs:/FIRST.BIN",input,257);put("udpfs:/SECOND.BIN",input,257);
 unlink("mmce0:/FIRST.BIN");unlink("mmce0:/SECOND.BIN");message[0]=0;subfunc_Paste(message,"mmce0:/");
 assert(strstr(message,"Reading source")&&!handles&&nclipFiles==2);
 assert(matches("udpfs:/FIRST.BIN",input,257)&&matches("udpfs:/SECOND.BIN",input,257));
 assert(matches("mmce0:/FIRST.BIN",input,257)&&access("mmce0:/SECOND.BIN",F_OK)<0);
 printf("PASS: %d boundary transfers through 1 MiB + 1; last-byte failures and partial multi-item moves retain sources\n",boundary_ops);
 /* R3Z HDD-OSD visibility attributes: assert actual metadata requests, not
  * just the constants. __common applies at the second folder level only;
  * PDA-executable folders retain the original R3Z exclusion. */
 mkdir("usb0:/OSD-APP",0700);put("usb0:/OSD-APP/BOOT.ELF",input,257);
 for(int port=0;port<2;port++)for(int network=0;network<2;network++) {
  char dest[40];snprintf(dest,sizeof(dest),"mc%d:/OSD-%s/",port,network?"NET":"USB");mkdir(dest,0700);
  reset();strcpy(clipPath,network?"udpfs:/":"usb0:/");
  if(network){mkdir("udpfs:/OSD-APP",0700);put("udpfs:/OSD-APP/BOOT.ELF",input,257);}
  strcpy(clipFiles[0].name,"OSD-APP");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
  message[0]=0;subfunc_Paste(message,dest);assert(!message[0]&&!handles);
  assert(mc_attr_calls==2&&mc_normal_files==1&&mc_normal_folders==1&&mc_last_port==port);
  assert(mc_last_flags==(network?4:MC_SFI));
 }
 for(int source_port=0;source_port<2;source_port++) {
  char src[16],dest[40],folder[40];snprintf(src,sizeof(src),"mc%d:/",source_port);
  snprintf(folder,sizeof(folder),"%sOSD-FLAGS",src);mkdir(folder,0700);
  snprintf(dest,sizeof(dest),"mc%d:/OSD-PRESERVE/",1-source_port);mkdir(dest,0700);
  reset();strcpy(clipPath,src);strcpy(clipFiles[0].name,"OSD-FLAGS");
  clipFiles[0].stats.AttrFile=MC_ATTR_norm_folder|sceMcFileAttrPDAExec|sceMcFileAttrDupProhibit;
  clipFiles[0].stats.Reserve1=0x1234;clipFiles[0].stats.Reserve2=0x98765432;
  clipFiles[0].stats._Create.Year=2001;clipFiles[0].stats._Modify.Year=2026;
  sceMcTblGetDir expected=clipFiles[0].stats;message[0]=0;subfunc_Paste(message,dest);
  assert(!message[0]&&!handles&&mc_attr_calls==1&&mc_last_port==1-source_port&&mc_last_flags==MC_SFI);
  assert(!memcmp(&mc_last_info,&expected,sizeof(expected)));
 }
 mkdir("mc0:/OSD-HDD",0700);
 for(int unit=0;unit<2;unit++)for(int kind=0;kind<4;kind++)for(int attempt=0;attempt<2;attempt++) {
  char dest[MAX_PATH],dir[MAX_PATH];snprintf(dest,sizeof(dest),"hdd%d:/__common/OSD-ROOT/",unit);
  fixtureDir(dest,dir);mkdir(dir,0700);
  reset();strcpy(clipPath,"mc0:/");strcpy(clipFiles[0].name,"OSD-HDD");
  clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir|((kind&1)?sceMcFileAttrDupProhibit:0)|((kind&2)?sceMcFileAttrPDAExec:0);
  message[0]=0;subfunc_Paste(message,dest);assert(!message[0]&&!handles);
  assert(hdd_attr_calls==((kind&2)?0:1));
  if(!(kind&2)){assert(hdd_last_attr==((kind&1)?HDD_ATTR_save_prot_folder:HDD_ATTR_save_folder));
   snprintf(target,sizeof(target),"pfs%d:/OSD-ROOT/OSD-HDD/",unit);assert(!strcmp(hdd_last_path,target));}
 }
 const char *no_hdd_flag[]={"hdd0:/__common/","hdd0:/TRANSFER/OSD-ROOT/"};
 for(int i=0;i<2;i++) {
  char dir[MAX_PATH];fixtureDir(no_hdd_flag[i],dir);mkdir(dir,0700);
  reset();strcpy(clipPath,"mc0:/");strcpy(clipFiles[0].name,"OSD-HDD");clipFiles[0].stats.AttrFile=sceMcFileAttrSubdir;
  message[0]=0;subfunc_Paste(message,(char*)no_hdd_flag[i]);assert(!message[0]&&!hdd_attr_calls&&!handles);
 }
 puts("PASS: R3Z MC0/MC1 normalization and preserved application/protection metadata; __common HDD-OSD flags 0xC4A7/0xC4AF, level and PDA exclusions");
 /* Full 32-byte card names, nested well beyond the driver's leaf limit. */
 const char *card_roots[]={"mc0:/","mc1:/","vmc0:/","vmc1:/","xfrom0:/"};
 char long_leaf[33];memset(long_leaf,'A',28);memcpy(long_leaf+28,".ELF",5);
 for(unsigned d=0;d<sizeof(card_roots)/sizeof(card_roots[0]);d++)for(int attempt=0;attempt<2;attempt++) {
  char dest[MAX_PATH],from[MAX_PATH];snprintf(dest,sizeof(dest),"%sLONG-PARENT-FOLDER",card_roots[d]);mkdir(dest,0700);
  strcat(dest,"/SECOND-FOLDER");mkdir(dest,0700);strcat(dest,"/");
  reset();strcpy(clipPath,"usb0:/");strcpy(clipFiles[0].name,long_leaf);
  int size=attempt?17:257;snprintf(from,sizeof(from),"usb0:/%s",long_leaf);put(from,input,size);
  message[0]=0;subfunc_Paste(message,dest);assert(!message[0]&&!handles);
  snprintf(target,sizeof(target),"%s%s",dest,long_leaf);assert(matches(target,input,size));
 }
 puts("PASS: nested MC/VMC/flash replacements preserve all 32 filename bytes");
 puts("PASS: 15,523,560-byte MC-to-MMCE folder copy, both MMCE slots, driver packets, errors, byte boundaries, PSU safeguards");
}
'''
with tempfile.TemporaryDirectory(prefix='copy-pipeline-') as folder:
    p=Path(folder);(p/'test.c').write_text(code);exe=p/'test'
    (p/'tamtypes.h').write_text('/* Types are defined by the host harness. */\n')
    cc=shutil.which('gcc') or shutil.which('cc')
    if not cc: raise SystemExit('Host C compiler required')
    subprocess.run([cc,'-std=gnu99','-Werror=implicit-function-declaration','-I'+str(p),
                    '-I'+str(root/'iop/mmceman/include'),str(p/'test.c'),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],cwd=p,check=True,timeout=20)
