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
static int genRemove(const char *p) {
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
program+=function("static int install_update_files(")
program+=function("int selfUpdateInstall(")
program+=r'''
static void reset(void) {
    count=downloads=sidecar_calls=0;
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
    const char *ca="mc0:/APP_LAUNCHSTATION/WLE-UPDATE-CA.PEM";
    const char *bgm="mc0:/APP_LAUNCHSTATION/BGM.ADP";
    const char *ca_tmp="mc0:/APP_LAUNCHSTATION/WLE-UPDATE-CA.PEM.UPDATE";
    const char *bgm_tmp="mc0:/APP_LAUNCHSTATION/BGM.ADP.UPDATE";
    const char *backup="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF.BAK";
    const char *elf_tmp="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF.UPDATE";
    const char *package_tmp="mc0:/APP_LAUNCHSTATION/LAUNCHSTATION.ELF.PACKAGE";
    char msg[512];
    reset();
    assert(install(msg)==0);
    assert(has(ca)&&has(bgm)&&has(boot)&&has(backup));
    assert(!has(ca_tmp)&&!has(bgm_tmp)&&sidecar_calls==2&&downloads==1);
    reset();put(ca);put(bgm);
    assert(install(msg)==0);
    assert(has(ca)&&has(bgm)&&sidecar_calls==0&&has(backup));
    reset();put(ca); /* only restore missing music */
    assert(install(msg)==0);
    assert(has(ca)&&has(bgm)&&sidecar_calls==1);
    reset();legacy=1;
    assert(install(msg)==0);
    assert(!has(ca)&&!has(bgm)&&has(boot)&&has(backup));
    reset();put(ca_tmp);
    assert(install(msg)<0 && downloads==0&&has(boot)&&has(ca_tmp)&&!has(backup));
    /* An interrupted ELF stage/download must not be truncated or removed.
     * No network traffic or package parsing should begin in these cases. */
    reset();put(elf_tmp);
    assert(install(msg)<0 && downloads==0 && sidecar_calls==0);
    assert(has(elf_tmp) && has(boot) && !has(backup) && !has(package_tmp));
    reset();put(package_tmp);
    assert(install(msg)<0 && downloads==0 && sidecar_calls==0);
    assert(has(package_tmp) && has(boot) && !has(backup) && !has(elf_tmp));
    reset();put(elf_tmp);put(package_tmp);
    assert(install(msg)<0 && downloads==0 && has(elf_tmp) && has(package_tmp));
    assert(has(boot) && !has(backup));
    reset();fail_bgm_stage=1;
    assert(install(msg)<0 && !has(ca_tmp)&&!has(bgm_tmp));
    assert(has(boot)&&!has(backup)&&!has(ca)&&!has(bgm));
    reset();fail_bgm_rename=1;
    assert(install(msg)<0 && has(boot)&&!has(backup)&&has(ca));
    assert(!has(bgm)&&!has(bgm_tmp)); /* previously absent CA may remain */
    reset();bad_digest=1;
    assert(install(msg)<0 && has(boot)&&!has(backup)&&!has(ca)&&!has(bgm));
    reset();bad_header=1;
    assert(install(msg)<0 && has(boot)&&!has(backup)&&!has(ca)&&!has(bgm));
    reset();fail_elf_once=1;
    assert(install(msg)<0 && has(boot) && !has(backup) && has(elf_tmp));
    assert(strstr(msg,"original ELF was restored"));
    reset();fail_elf_rename=1;
    assert(install(msg)<0 && !has(boot)&&has(backup)); /* simulated rollback fails too */
    /* Lookup must not allocate a full browser listing just to rename the
     * known boot file. Reproduce the reported standard memory-card layout. */
    reset();listing_alloc_fail=1;put(ca);put(bgm);
    assert(install(msg)==0 && has(boot) && has(backup));
    assert(fixes==3 && stats==3 && renames==3);
    /* FAT/exFAT accepts a differently capitalized boot argument. The updater
     * must let that filesystem resolve it rather than scan for an exact name. */
    const char *parents[]={"usb0:/APP_LAUNCHSTATION/","mass:/APP_LAUNCHSTATION/",
                           "mmce0:/APP_LAUNCHSTATION/","hdd0:/__common/APP_LAUNCHSTATION/"};
    for(unsigned i=0;i<sizeof(parents)/sizeof(*parents);i++) {
        char boot_path[MAX_PATH],stored[MAX_PATH],old_copy[MAX_PATH];
        reset();count=0;parent=parents[i];case_insensitive=1;
        snprintf(boot_path,sizeof(boot_path),"%sLAUNCHSTATION.ELF",parent);boot=boot_path;
        snprintf(stored,sizeof(stored),"%sLaunchstation.ELF",parent);put(stored);
        snprintf(old_copy,sizeof(old_copy),"%sLAUNCHSTATION.ELF.BAK",parent);
        assert(install(msg)==0 && has(boot) && has(old_copy));
        assert(fixes==5 && stats==5 && renames==5);
    }
    /* Native errors survive lookup/rename; a failed backup cannot proceed
     * to installing the staged ELF. Existing readable boot files stay put. */
    const int errors[]={-EACCES,-ENOSPC,-EIO,-ENOENT,-ENAMETOOLONG,-ENOSYS};
    for(unsigned i=0;i<sizeof(errors)/sizeof(*errors);i++) {
        char expected[40];
        reset();put(ca);put(bgm);backup_error=errors[i];
        assert(install(msg)<0 && has(boot) && !has(backup) && !has(elf_tmp));
        snprintf(expected,sizeof(expected),"error %d",errors[i]);
        assert(renames==1 && strstr(msg,expected) && strstr(msg,boot));
        assert(strstr(msg,"not changed"));
    }
    reset();put(ca);put(bgm);lookup_error=-EIO;
    assert(install(msg)<0 && has(boot) && !has(backup) && !renames && !has(elf_tmp));
    assert(strstr(msg,"error -5") && strstr(msg,boot));
    reset();put(ca);put(bgm);lookup_directory=1;
    assert(install(msg)<0 && !renames && has(boot) && !has(backup));
    reset();put(ca);put(bgm);path_error=1;
    assert(install(msg)<0 && !stats && !renames && has(boot) && !has(backup));
    reset();put(ca);put(bgm);protected_path=1;
    assert(install(msg)<0 && has(boot) && !has(backup) && !has(elf_tmp));
    /* A failed verification can follow an applied rename. Keep both the
     * original backup and verified new stage instead of deleting recovery. */
    reset();put(ca);put(bgm);backup_applied_error=1;
    assert(install(msg)<0 && !has(boot) && has(backup) && has(elf_tmp));
    assert(renames==1 && strstr(msg,"not readable") && !strstr(msg,"not changed"));
    const char *title="mc0:/APP_LAUNCHSTATION/title.cfg";
    const char *title_tmp="mc0:/APP_LAUNCHSTATION/title.cfg.UPDATE";
    const char *title_bak="mc0:/APP_LAUNCHSTATION/title.cfg.BAK";
    reset();put(title);put(title_bak);set_value(title_bak,9);
    assert(install(msg)==0 && value(boot)==2 && value(backup)==1);
    assert(value(title)==2 && value(title_bak)==1 && !has(title_tmp));
    reset();legacy=1;put(title);
    assert(install(msg)==0 && value(title)==2 && value(title_bak)==1);
    reset();
    assert(install(msg)==0 && value(title)==2 && !has(title_bak));
    reset();put(title_tmp);
    assert(install(msg)<0 && !downloads && has(title_tmp) && value(boot)==1);
    reset();put(title_bak);
    assert(install(msg)<0 && !downloads && has(title_bak) && !has(title));
    reset();put(title);title_stage_fail=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1 && !has(backup));
    assert(!has(title_tmp) && !has(elf_tmp) && !has(package_tmp));
    reset();put(title);put(title_bak);remove_title_backup_fail=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1 && !has(backup));
    assert(has(title_bak) && !has(title_tmp) && !has(elf_tmp));
    reset();put(title);title_backup_fail=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1);
    assert(!has(backup) && !has(title_bak));
    reset();put(title);title_publish_fail=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1);
    assert(!has(backup) && !has(title_bak) && has(title_tmp));
    reset();put(title);title_applied_fail=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1 && !has(backup));
    assert(!has(title_bak) && !has(title_tmp));
    reset();put(title);fail_elf_once=1;
    assert(install(msg)<0 && value(title)==1 && value(boot)==1);
    assert(!has(backup) && !has(title_bak));
    reset();fail_elf_once=1; /* no original title: rollback removes new metadata */
    assert(install(msg)<0 && value(boot)==1 && !has(title) && !has(title_bak));
    reset();put(title);elf_applied_fail=1;
    assert(install(msg)<0 && value(boot)==1 && value(title)==1 && !has(backup));
    reset();put(title);fail_elf_once=1;title_rollback_fail=1;
    assert(install(msg)<0 && value(boot)==1 && value(title_bak)==1 && !has(title));
    assert(strstr(msg,"rollback also failed"));
    reset();capture_result=0;
    assert(install(msg)==0 && !restores);
    reset();capture_result=-EIO;
    assert(install(msg)<0 && !downloads && !mutations && !restores);
    reset();restore_error=-EIO;
    assert(install(msg)==0 && value(boot)==2 && strstr(msg,"Could not restore"));
    reset();restore_error=1;
    assert(install(msg)==0 && strstr(msg,"Could not restore"));
    reset();restore_error=-EIO;
    char small[32];
    assert(selfUpdateInstall("ca","sha256:mock",small,sizeof(small))==0);
    assert(!strncmp(small,"Could not restore",17) && small[sizeof(small)-1]=='\0');
    reset();restore_error=-EIO;
    char minimal='x';
    assert(selfUpdateInstall("ca","sha256:mock",&minimal,1)==0 && minimal=='\0');
    /* The actual boot filename is passed to metadata extraction unchanged. */
    reset();count=0;boot="mc0:/APP_LAUNCHSTATION/BOOT.ELF";put(boot);
    assert(install(msg)==0 && value(boot)==2 && value(title)==2);
    puts("PASS: verified metadata refresh, renamed ELF, matching recovery/rollback, SAS capture before writes and restore after cleanup");
    puts("PASS: updater refuses to truncate old stages; missing-only sidecars and ELF recover safely");
    puts("PASS: mc0 recovery without a directory allocation, native lookup/aliases, error details and ambiguous-rename recovery");
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
