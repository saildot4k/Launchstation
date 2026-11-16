"""Compile the real bounded walker/sizer against deterministic device adapters."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
platform = r'''
#ifndef TREE_TEST_PLATFORM
#define TREE_TEST_PLATFORM
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
#define MAX_PATH 1025
#define MAX_NAME 256
#define MAX_ENTRY 2048
#define sceMcFileAttrSubdir 0x20
typedef struct {unsigned AttrFile;} McStat;
typedef struct {char name[MAX_NAME];char title[66];McStat stats;} FILEINFO;
typedef struct {unsigned size,hisize;} iox_stat_t;
typedef int (*FilerTreeVisit)(const char *,const FILEINFO *,void *);
int getDir(const char *,FILEINFO *);
int ensurePathDeviceStackReady(const char *);
int getHddParty(const char *,const FILEINFO *,char *,char *);
int mountParty(const char *);
int genGetStat(const char *,iox_stat_t *);
#endif
'''
code = r'''
#include "filer_tree.h"
static int mode,calls,stats,mount_error,ready=1,allocations,fail_allocation;
static size_t live,peak;
typedef union {max_align_t align;size_t size;} Allocation;
static void *treeMalloc(size_t bytes){
 if(++allocations==fail_allocation)return NULL;
 Allocation *p=malloc(sizeof(*p)+bytes);assert(p);p->size=bytes;
 live+=bytes;if(live>peak)peak=live;return p+1;
}
static void treeFree(void *pointer){
 if(pointer){Allocation *p=(Allocation*)pointer-1;live-=p->size;free(p);}
}
#define malloc treeMalloc
#define free treeFree
#include "PRODUCTION_TREE"
#undef malloc
#undef free
int ensurePathDeviceStackReady(const char *path){assert(path);return ready;}
int getHddParty(const char *path,const FILEINFO *file,char *party,char *out){
 (void)path;strcpy(party,"partition");snprintf(out,MAX_PATH,"pfs0:/%s",file->name);return 0;
}
int mountParty(const char *party){assert(!strcmp(party,"partition"));return mount_error?-EIO:2;}
int genGetStat(const char *path,iox_stat_t *out){
 stats++;if(mode==3&&strstr(path,"large"))return -EIO;
 out->hisize=strstr(path,"large")?2:0;out->size=strstr(path,"small")?5:strstr(path,"large")?7:0;return 0;
}
static void entry(FILEINFO *out,int index,const char *name,int directory){
 memset(&out[index],0,sizeof(out[index]));strcpy(out[index].name,name);
 out[index].stats.AttrFile=directory?sceMcFileAttrSubdir:0;
}
int getDir(const char *path,FILEINFO *out){
 calls++;
 if(mode==1)return -EIO;
 if(mode==2&&strstr(path,"nested"))return -ETIMEDOUT;
 if(mode==4)return MAX_ENTRY-4;
 if(mode==5){entry(out,0,"next",1);return 1;}
 if(mode==6){for(int i=0;i<MAX_ENTRY-5;i++){char name[30];snprintf(name,sizeof(name),"folder%04d",i);entry(out,i,name,1);}return MAX_ENTRY-5;}
 if(mode==7){entry(out,0,"bad/name",0);return 1;}
 if(strstr(path,"empty/"))return 0;
 if(strstr(path,"nested/")){entry(out,0,"zero",0);return 1;}
 entry(out,0,"small",0);entry(out,1,"large",0);entry(out,2,"nested",1);entry(out,3,"empty",1);return 4;
}
static char visited[1024];
static int visit(const char *parent,const FILEINFO *file,void *context){
 (void)parent;(void)context;
 if(mode==8&&!strcmp(file->name,"large"))return -EACCES;
 strcat(visited,file->name);strcat(visited," ");return 0;
}
static void reset(int next){assert(!live);mode=next;calls=stats=allocations=fail_allocation=0;ready=1;peak=0;visited[0]=0;}
int main(void){
 FILEINFO root={0};strcpy(root.name,"root");root.stats.AttrFile=sceMcFileAttrSubdir;
 u64 size=123;
 reset(0);assert(getFileSize("usb0:/",&root,&size)==0&&size==((u64)2<<32)+12&&stats==3&&!live);
 reset(0);assert(!filerWalkTree("usb0:/",&root,visit,NULL));
 assert(!strcmp(visited,"small large zero nested empty root ")&&!live);
 for(int failure=1;failure<=7;failure++){
  reset(failure);size=123;assert(getFileSize("usb0:/",&root,&size)<0&&size==123&&!live);
  if(failure==5)assert(calls==TREE_DEPTH_LIMIT);
  if(failure==6)assert(peak<=TREE_METADATA_LIMIT);
 }
 reset(8);assert(filerWalkTree("usb0:/",&root,visit,NULL)==-EACCES&&!live&&!strstr(visited,"root"));
 for(int failure=1;failure<=3;failure++){
  reset(0);fail_allocation=failure;size=123;
  assert(getFileSize("usb0:/",&root,&size)==-ENOMEM&&size==123&&!live);
 }
 reset(0);ready=0;assert(getFileSize("usb0:/",&root,&size)<0&&!allocations);
 reset(0);root.stats.AttrFile=0;strcpy(root.name,"large");
 assert(!getFileSize("usb0:/",&root,&size)&&size==((u64)2<<32)+7&&!allocations);
 reset(0);mount_error=1;size=123;assert(getFileSize("hdd0:/PART/",&root,&size)<0&&size==123);mount_error=0;
 reset(0);root.stats.AttrFile=sceMcFileAttrSubdir;char long_path[MAX_PATH];memset(long_path,'x',sizeof(long_path)-1);long_path[MAX_PATH-1]=0;
 assert(getFileSize(long_path,&root,&size)==-ENAMETOOLONG&&!allocations);
 puts("PASS: real tree walker postorder, negative listing/stat/mount/visitor errors, 64-bit sizing, unchanged error output, capped listings, bounded metadata/depth, malformed paths and allocation cleanup");
}
'''.replace('PRODUCTION_TREE', str(root / 'src/filer_tree.c'))
with tempfile.TemporaryDirectory(prefix='filer-tree-') as folder:
    folder = Path(folder)
    (folder / 'filer_tree.h').write_text(platform)
    (folder / 'filer_shared.h').write_text(platform)
    (folder / 'gui_hdd0_format.h').write_text(platform)
    (folder / 'test.c').write_text(code)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror', *flags,
                    '-I', str(folder), str(folder / 'test.c'), '-o', str(folder / 'test')], check=True)
    subprocess.run([str(folder / 'test')], check=True)
