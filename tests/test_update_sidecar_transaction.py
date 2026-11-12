"""Execute the production native-update transaction with a mock app filesystem.

Tests existing custom sidecars, missing-only publication, legacy PSU packages,
staging collisions and failed updates. This does not emulate real PS2 filesystem
or HTTP behavior; the real PSU parser is exercised in test_app_packages.py.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
source=(Path(sys.argv[1]) if len(sys.argv)>1 else root/"src/self_update.c").read_text()

def function(signature):
    start=source.index(signature)
    end=source.index("{",start)+1
    depth=1
    while depth:
        depth+=(source[end]=="{")-(source[end]=="}")
        end+=1
    return source[start:end]+"\n"

url_definition=next(line for line in source.splitlines() if line.startswith("#define UPDATE_ELF_URL "))
program=url_definition+"\n"+r'''
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdint.h>
typedef uint64_t u64;
#define UPDATE_SPACE_MARGIN (100*1024)
#define FIO_O_WRONLY 1
#define FIO_O_CREAT 2
#define FIO_O_EXCL 4
#include "self_update.h"
#define MAX_PATH 256
#define MAX_NAME 128
#define UPDATE_MAX_ELF (16*1024*1024)
#define FIO_S_ISREG(mode) ((mode)==1)
#define FIO_S_ISDIR(mode) ((mode)==2)
#define sceMcFileAttrFile 0x10
#define MAX_ENTRY 2048
#define stricmp strcasecmp
typedef struct { unsigned char bytes[8]; } sceMcStDateTime;
typedef struct { int mode; } iox_stat_t;
typedef struct { char name[MAX_NAME];struct { int AttrFile; } stats; } FILEINFO;
static const char *boot="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF";
static const char *parent="mc0:/APP_LAUNCHSTATION/";
static char files[64][MAX_PATH];
static int values[64];
static int capture_result,restore_error,captures,restores,mutations,restored_at;
static int title_stage_fail,title_backup_fail,title_publish_fail,title_applied_fail;
static int title_rollback_fail,remove_title_backup_fail,elf_applied_fail;
static int count,downloads,sidecar_calls,legacy,fail_bgm_stage,fail_bgm_rename;
static int bad_digest,fail_elf_rename,fail_elf_once,bad_header;
static int case_insensitive,listing_alloc_fail,lookup_error,lookup_directory,path_error;
static int backup_error,backup_applied_error,renames,protected_path,fixes,stats;
static char last_fixed[MAX_PATH];
static int same_file(const char *a,const char *b) {
    return case_insensitive ? !strcasecmp(a,b) : !strcmp(a,b);
}
static int has(const char *p) {
    for(int i=0;i<count;i++)if(same_file(files[i],p))return 1;
    return 0;
}
static int put(const char *p) {
    if(has(p))return 0;
    assert(count<64);
    values[count]=1;mutations++;
    snprintf(files[count++],MAX_PATH,"%s",p);
    return 1;
}
static int del(const char *p) {
    for(int i=0;i<count;i++)if(same_file(files[i],p)) {
        memmove(values+i,values+i+1,(size_t)(count-i-1)*sizeof(*values));mutations++;
        memmove(files[i],files[i+1],(size_t)(count-i-1)*MAX_PATH);
        count--;return 0;
    }
    return -1;
}
static int wleExists(const char *p) { return has(p); }
static int reserve_bytes, reserve_limit=UPDATE_SPACE_MARGIN, space_known=1;
static u64 available=1024*1024;
static int delete_boot_fail, progress_count;
static void DashStorageProbeStatus(const char *text) { assert(text && *text);progress_count++; }
static int filerFreeSpace(const char *p,u64 *out) { assert(!strcmp(p,parent));*out=available;return space_known; }
static int genOpen(const char *p,int flags) {
    assert(flags==(FIO_O_WRONLY|FIO_O_CREAT|FIO_O_EXCL));
    if(has(p))return -EEXIST;
    put(p);return 7;
}
static int genWrite(int fd,const void *data,int size) {
    assert(fd==7 && data && size>0);
    if(reserve_bytes>=reserve_limit)return -ENOSPC;
    if(size>reserve_limit-reserve_bytes)size=reserve_limit-reserve_bytes;
    reserve_bytes+=size;return size;
}
static int genClose(int fd) { assert(fd==7);return 0; }
static int genRemove(const char *p) {
    if(same_file(p,boot)) {
        char staged[MAX_PATH];snprintf(staged,sizeof(staged),"%s.UPDATE",boot);
        assert(has(staged) && reserve_bytes==UPDATE_SPACE_MARGIN);
        if(delete_boot_fail)return -EACCES;
    }
    if(remove_title_backup_fail && strstr(p,"title.cfg.BAK"))return -EACCES;
    return del(p);
}
static int value(const char *p) {
    for(int i=0;i<count;i++)if(same_file(files[i],p))return values[i];
    return 0;
}
static void set_value(const char *p,int v) {
    for(int i=0;i<count;i++)if(same_file(files[i],p)){values[i]=v;return;}
    assert(0);
}
static int filerCaptureSasTimestamp(const char *p,sceMcStDateTime *ts) {
    assert(!strcmp(p,parent) && !mutations);captures++;
    memset(ts,0x2a,sizeof(*ts));return capture_result;
}
static int filerRestoreSasTimestamp(const char *p,const sceMcStDateTime *ts) {
    assert(!strcmp(p,parent) && ts->bytes[0]==0x2a);restores++;
    restored_at=mutations;return restore_error;
}
static const char *wleBootElfPath(void) { return boot; }
static int ensurePathDeviceStackReady(const char *p) {
    assert(!strcmp(p,parent));return 1;
}
static int parse_expected_sha(const char *text,unsigned char expected[32]) {
    (void)text;memset(expected,0x5a,32);return 1;
}
static int download_file(const char *url,const char *path,const char *ca,
                         int max_bytes,unsigned char actual[32],
                         char *error,int error_size) {
    (void)ca;(void)error;(void)error_size;
    assert(!strcmp(url,"https://github.com/saildot4k/Launchstation/releases/download/latest/" SELF_UPDATE_ASSET));
    assert(max_bytes>=4096);downloads++;
    memset(actual,bad_digest?0:0x5a,32);
    put(path);
    return 8192;
}
int selfUpdateExtractPsu(const char *pkg,const char *stage,int size) {
    assert(has(pkg) && size==8192);put(stage);set_value(stage,2);return 4096;
}
int selfUpdateExtractPsuSidecar(const char *pkg,const char *asset,
                                       const char *stage,int size) {
    assert(has(pkg) && size==8192);
    sidecar_calls++;
    if(legacy)return 0;
    if(fail_bgm_stage && !strcmp(asset,"BGM.ADP"))return -1;
    assert(!has(stage));put(stage);return 128;
}
int selfUpdateExtractPsuTitle(const char *pkg,const char *stage,int size,const char *leaf) {
    assert(has(pkg) && size==8192 && !strcmp(leaf,strrchr(boot,'/')+1));
    if(title_stage_fail)return -EIO;
    assert(!has(stage));put(stage);set_value(stage,2);return 128;
}
static int checkELFheader(const char *stage) { assert(has(stage));return bad_header?-1:0; }
int genFixPath(const char *path,char *resolved) {
    fixes++;
    if(path_error)return -1;
    if(!strncmp(path,"mass:",5))snprintf(resolved,MAX_PATH,"usb0:%s",path+5);
    else if(!strncmp(path,"hdd0:/__common/",15))snprintf(resolved,MAX_PATH,"pfs4:/%s",path+15);
    else snprintf(resolved,MAX_PATH,"%s",path);
    snprintf(last_fixed,sizeof(last_fixed),"%s",resolved);
    return 0;
}
int genGetStat(const char *path,iox_stat_t *stat) {
    char logical[MAX_PATH];
    stats++;assert(!strcmp(path,last_fixed));
    if(!strncmp(parent,"mass:",5))snprintf(logical,sizeof(logical),"mass:%s",path+5);
    else if(!strncmp(parent,"hdd0:/__common/",15))snprintf(logical,sizeof(logical),"hdd0:/__common/%s",path+6);
    else snprintf(logical,sizeof(logical),"%s",path);
    if(same_file(logical,boot)) {
        if(lookup_error)return lookup_error;
        if(lookup_directory){stat->mode=2;return 0;}
    }
    if(!has(logical))return -ENOENT;
    stat->mode=1;return 0;
}
static int Rename(const char *p,const FILEINFO *file,const char *newname) {
    char from[MAX_PATH],to[MAX_PATH];
    const char *old=file->name;
    renames++;assert(!strcmp(p,parent));
    if(protected_path)return -EPERM;
    if(backup_error && strstr(newname,".BAK"))return backup_error;
    snprintf(from,sizeof(from),"%s%s",p,old);
    snprintf(to,sizeof(to),"%s%s",p,newname);
    if(fail_bgm_rename && !strcmp(newname,"BGM.ADP"))return -1;
    if(fail_elf_rename && !strcmp(newname,"LAUNCHSTATION.ELF"))return -1;
    if(fail_elf_once && !strcmp(newname,"LAUNCHSTATION.ELF")) {
        fail_elf_once=0;return -EIO;
    }
    if(title_backup_fail && !strcmp(old,"title.cfg"))return -EACCES;
    if(title_publish_fail && !strcmp(old,"title.cfg.UPDATE"))return -ENOSPC;
    if(title_rollback_fail && !strcmp(old,"title.cfg.BAK"))return -EIO;
    if(!has(from) || has(to))return -1;
    int original=value(from);
    del(from);put(to);set_value(to,original);
    if(title_applied_fail && !strcmp(old,"title.cfg.UPDATE"))return -EIO;
    if(elf_applied_fail && strstr(old,".ELF.UPDATE"))return -EIO;
    return backup_applied_error && strstr(newname,".BAK") ? -EIO : 0;
}
'''
# Retain an optional old-source run to reproduce the browser-listing defect.
if "getDir(" in function("static int find_file_info("):
    program+=r'''
void *memalign(size_t alignment,size_t size) {
    (void)alignment;return listing_alloc_fail?NULL:malloc(size);
}
static int filerPrepareDirRead(const char *path) { assert(!strcmp(path,parent));return 1; }
static int getDir(const char *path,FILEINFO *out) {
    int n=0;size_t length=strlen(path);
    for(int i=0;i<count;i++)if(!strncmp(path,files[i],length)) {
        memset(&out[n],0,sizeof(out[n]));
        snprintf(out[n++].name,MAX_NAME,"%s",files[i]+length);
    }
    return n;
}
'''
for sig in [
    "static int device_path(",
    "static int supported_boot_path(",
    "static int split_parent_leaf(",
    "static int join_leaf(",
    "static int find_file_info(",
    "static int rename_leaf(",
]:
    program+=function(sig)
program+=function("static int reserve_update_space(")
program+=function("static int install_update_files(")
program+=function("int selfUpdateInstall(")
program+=r'''
static void reset(void) {
    count=downloads=sidecar_calls=0;
    reserve_bytes=delete_boot_fail=progress_count=0;
    reserve_limit=UPDATE_SPACE_MARGIN;space_known=1;available=1024*1024;
    capture_result=1;restore_error=captures=restores=mutations=restored_at=0;
    title_stage_fail=title_backup_fail=title_publish_fail=title_applied_fail=0;
    title_rollback_fail=remove_title_backup_fail=elf_applied_fail=0;
    legacy=fail_bgm_stage=fail_bgm_rename=0;
    bad_digest=fail_elf_rename=fail_elf_once=bad_header=0;
    case_insensitive=listing_alloc_fail=lookup_error=lookup_directory=path_error=0;
    backup_error=backup_applied_error=renames=protected_path=fixes=stats=0;
    boot="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF";
    parent="mc0:/APP_LAUNCHSTATION/";
    put(boot);mutations=0;
}
static int install(char *msg) {
    mutations=0;
    int ret=selfUpdateInstall("settings/legacy-ca.pem","sha256:mock",msg,512);
    assert(captures==1);
    assert(restores==(capture_result>0));
    if(restores)assert(restored_at==mutations);
    return ret;
}
int main(void) {
    const char *title="mc0:/APP_LAUNCHSTATION/title.cfg";
    const char *tmp="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF.UPDATE";
    const char *pkg="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF.PACKAGE";
    const char *reserve="mc0:/APP_LAUNCHSTATION/WLE-UPDATE.SPACE";
    const char *ca="mc0:/APP_LAUNCHSTATION/WLE-UPDATE-CA.PEM";
    const char *bgm="mc0:/APP_LAUNCHSTATION/BGM.ADP";
    char msg[512];
    reset();put(title);assert(install(msg)==0);
    assert(value(boot)==2 && value(title)==2 && has(ca) && has(bgm));
    assert(!has(tmp) && !has(pkg) && !has(reserve) && progress_count>=7);
    for(int i=0;i<count;i++)assert(!strstr(files[i],".BAK"));
    reset();put(ca);put(bgm);put(title);assert(install(msg)==0);
    assert(value(ca)==1 && value(bgm)==1 && !sidecar_calls && value(title)==2);
    reset();legacy=1;assert(install(msg)==0 && !has(ca) && !has(bgm));
    reset();space_known=0;assert(install(msg)==0 && !has(reserve));
    reset();available=8192;assert(install(msg)==0); /* exact contents upper bound */
    reset();available=8191;assert(install(msg)<0 && value(boot)==1);
    assert(strstr(msg,"Not enough free space") && !has(pkg) && !has(tmp) && !has(reserve));
    reset();reserve_limit=100*1024-1;assert(install(msg)<0 && !downloads);
    assert(value(boot)==1 && !has(reserve));
    reset();put(reserve);assert(install(msg)<0 && !downloads && has(reserve));
    for(int kind=0;kind<3;kind++) {
        reset();put(kind==0?tmp:kind==1?pkg:"mc0:/APP_LAUNCHSTATION/title.cfg.UPDATE");
        assert(install(msg)<0 && !downloads && value(boot)==1 && !has(reserve));
    }
    reset();bad_digest=1;assert(install(msg)<0 && value(boot)==1 && !has(pkg));
    reset();bad_header=1;assert(install(msg)<0 && value(boot)==1 && !has(tmp));
    reset();title_stage_fail=1;assert(install(msg)<0 && value(boot)==1 && !has(tmp));
    reset();fail_bgm_stage=1;assert(install(msg)<0 && value(boot)==1 && !has(ca));
    reset();fail_bgm_rename=1;assert(install(msg)<0 && value(boot)==1 && has(ca));
    reset();delete_boot_fail=1;assert(install(msg)<0 && value(boot)==1 && has(tmp));
    reset();fail_elf_rename=1;assert(install(msg)<0 && !has(boot) && has(tmp));
    assert(strstr(msg,"No backup") && !has(reserve));
    reset();put(title);title_publish_fail=1;assert(install(msg)<0 && value(boot)==2);
    assert(!has(title) && has("mc0:/APP_LAUNCHSTATION/title.cfg.UPDATE"));
    reset();elf_applied_fail=1;assert(install(msg)<0 && value(boot)==2 && !has(tmp));
    reset();capture_result=-EIO;mutations=0;
    assert(selfUpdateInstall("ca","sha256:mock",msg,sizeof(msg))<0 && !mutations && !downloads);
    reset();restore_error=-EIO;assert(install(msg)==0 && strstr(msg,"SAS date"));
    reset();count=0;boot="mc0:/APP_LAUNCHSTATION/BOOT.ELF";put(boot);
    assert(install(msg)==0 && value(boot)==2 && value(title)==2);
    puts("PASS: delete/replace without backups, reserved 100 KB, space bounds, popup phases, failure retention and SAS timestamps");
}

'''
compiler=shutil.which("gcc") or shutil.which("clang")
assert compiler,"Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-update-transaction-") as tmp:
    path=Path(tmp)/"test.c"
    exe=Path(tmp)/"test"
    path.write_text(program)
    for variant in ([], ["-DDS34"]):
        subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                        "-I",str(root/"include"),*variant,
                        str(path),"-o",str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=5)
