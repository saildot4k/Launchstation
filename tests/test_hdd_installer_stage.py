"""Internal temporary folders preserve the CA through format and check ownership."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
s = (root / 'src/hdd_install_ps2.c').read_text()
helpers = s[s.index('static int pathJoin('):s.index('/* Short sibling names')]
helpers += s[s.index('void hddInstallRelease('):s.index('static int checkFileSize(')]
stage = s[s.index('int hddInstallClaimStage('):s.index('static int makeDirectory(', s.index('int hddInstallClaimStage('))]
code = r'''
#define _POSIX_C_SOURCE 200809L
#define ETH
#define WLE_NATIVE_HTTPS
#include "hdd_install.h"
#include "save_sign.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#define MAX_PATH 1025
#define FIO_O_CREAT O_CREAT
#define FIO_O_EXCL O_EXCL
#define FIO_O_TRUNC O_TRUNC
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_MT_RDWR 1
typedef uint64_t u64;
typedef int64_t s64;
static unsigned ticks;
static const char *work;
static int mounted;
static u64 Timer(void) { return ++ticks; }
static int mapped(const char *p, char *out, size_t cap) {
    const char *base,*tail=strchr(p,':');int n;
    if(!tail)return -EINVAL;
    if(!strncmp(p,"ata0:",5))base="ata";
    else if(!strncmp(p,"pfs2:",5)&&mounted)base="common";
    else return -ENOENT;
    n=snprintf(out,cap,"%s/%s%s",work,base,tail+1);return n<0||n>=(int)cap?-ENAMETOOLONG:0;
}
static int genOpen(const char*p,int mode) { char path[2048]; int r=mapped(p,path,sizeof(path));return r<0?r:open(path,mode,0600); }
static int genRead(int fd,void*p,unsigned n) {if(n>3)n=3;return read(fd,p,n);}
static int genWrite(int fd,const void*p,unsigned n) {if(n>3)n=3;return write(fd,p,n);}
#define genLseek lseek
#define genClose close
static int genRemove(char*p) {char path[2048];int r=mapped(p,path,sizeof(path));return r<0?r:unlink(path);}
static int genRmdir(char*p) {char path[2048];int r=mapped(p,path,sizeof(path));return r<0?r:rmdir(path);}
static int genMkdir(const char*p,int mode) {char path[2048];int r=mapped(p,path,sizeof(path));return r<0?r:mkdir(path,mode)<0?-errno:0;}
static int fileXioMount(const char*m,const char*p,int flags){assert(!strcmp(m,"pfs2:")&&!strcmp(p,"hdd0:__common")&&flags==FIO_MT_RDWR&&!mounted);mounted=1;return 0;}
static int fileXioUmount(const char*m){assert(!strcmp(m,"pfs2:")&&mounted);mounted=0;return 0;}
'''
code += r'''

unsigned char *httpsLoadCaBundle(const char *path, unsigned *size){
    assert(!*path);
    unsigned char *data=malloc(9);assert(data);memcpy(data,"embedded",9);*size=8;
    return data;
}
int hddInstallResumeSave(HddInstall *in){assert(in);return 0;}
int hddInstallResumeRemove(HddInstall *in){assert(in);return 0;}
void hddInstallLog(const char *format, ...) { (void)format; }
int hddInstallLogEnabled(void) { return 0; }
void hddInstallLogFlush(HddInstall *in) { (void)in; }
void hddInstallStatus(const char *s,int done,int total) { (void)s;(void)done;(void)total; }
'''
a=s.index('static int launcherStageName('); b=s.index('static int findLauncher(',a)
code += helpers + s[a:b] + stage
code += r'''
int main(int argc,char**argv) {
    char path[2048]; HddInstall in={0},other={0}; int fd; char ca[16]={0};
    assert(argc==2);work=argv[1];
    snprintf(path,sizeof(path),"%s/ata/old-ca.pem",work);fd=open(path,O_CREAT|O_WRONLY,0600);assert(fd>=0);assert(write(fd,"CA fixture",10)==10);close(fd);
    strcpy(in.ca_path,"ata0:/old-ca.pem");assert(hddInstallLoadCa(&in)==0&&in.ca_size==10);
    assert(!unlink(path)); /* source disappears during formatting */
    in.jail=1;strcpy(in.stage,"pfs2:/tmp");
    assert(hddInstallMountStage(&in)==0&&mounted);
    assert(hddInstallCreateStage(&in)==0&&in.owned&&!in.ca_data);
    assert(!strcmp(in.ca_path,"pfs2:/tmp/INSTALL_CA.PEM"));
    fd=genOpen(in.ca_path,FIO_O_RDONLY);assert(fd>=0);assert(read(fd,ca,16)==10&&!strcmp(ca,"CA fixture"));close(fd);
    assert(hddInstallFindStage(&in)==0);
    /* Interrupted CA copy: keep the EE snapshot and replace only our file. */
    in.ca_data=malloc(10);memcpy(in.ca_data,"CA fixture",10);in.ca_size=10;
    in.stage_ready=0;in.recovery_attempts=1;
    fd=genOpen(in.ca_path,FIO_O_WRONLY|FIO_O_TRUNC);assert(fd>=0);assert(write(fd,"bad trailing data",17)==17);close(fd);
    assert(hddInstallCreateStage(&in)==0&&in.stage_ready&&!in.ca_data);
    fd=genOpen(in.ca_path,FIO_O_RDONLY);assert(fd>=0);memset(ca,0,sizeof(ca));assert(read(fd,ca,16)==10&&!strcmp(ca,"CA fixture"));close(fd);
    in.launcher_files=calloc(1,sizeof(*in.launcher_files));assert(in.launcher_files);in.launcher_count=1;
    strcpy(in.launcher_files[0].path,"scripts/assets/neutrino/modules/ata_bd.irx");
    assert(!genMkdir("pfs2:/tmp/Neutrino",0777)&&!genMkdir("pfs2:/tmp/Neutrino/modules",0777));
    fd=genOpen("pfs2:/tmp/Neutrino/modules/ata_bd.irx",FIO_O_CREAT|FIO_O_EXCL|FIO_O_WRONLY);assert(fd>=0);close(fd);
    fd=genOpen("pfs2:/tmp/Neutrino/keep.txt",FIO_O_CREAT|FIO_O_EXCL|FIO_O_WRONLY);assert(fd>=0);close(fd);
    fd=genOpen("pfs2:/tmp/launcher-000.bin",FIO_O_CREAT|FIO_O_EXCL|FIO_O_WRONLY);assert(fd>=0);close(fd);
    other.jail=1;strcpy(other.stage,in.stage);other.ca_data=malloc(1);other.ca_data[0]=0;other.ca_size=1;
    assert(hddInstallCreateStage(&other)==-EEXIST&&!other.owned);
    other.owned=1;other.recovery_attempts=1;memset(other.owner,0xcc,sizeof(other.owner));
    assert(hddInstallCreateStage(&other)==-ENOENT&&other.ca_data);other.owned=0;other.recovery_attempts=0;
    hddInstallCleanup(&other);assert(!other.ca_data&&hddInstallFindStage(&in)==0);
    snprintf(path,sizeof(path),"%s/common/tmp/OSDMBR.XLF",work);fd=open(path,O_CREAT|O_WRONLY,0600);assert(fd>=0);close(fd);
    hddInstallCleanup(&in);assert(!in.owned&&!in.stage[0]);assert(access(path,F_OK)<0);
    snprintf(path,sizeof(path),"%s/common/tmp/Neutrino/modules",work);assert(access(path,F_OK)<0);
    snprintf(path,sizeof(path),"%s/common/tmp/launcher-000.bin",work);assert(access(path,F_OK)<0);
    snprintf(path,sizeof(path),"%s/common/tmp/Neutrino/keep.txt",work);assert(!access(path,F_OK));
    assert(hddInstallUnmountStage(&in)==0&&!mounted);
    strcpy(other.stage,"pfs2:/PSBBN_DP_TEMP");other.jail=0;other.ca_data=malloc(2);memcpy(other.ca_data,"CA",2);other.ca_size=2;
    assert(hddInstallMountStage(&other)==0&&mounted);
    assert(hddInstallCreateStage(&other)==0&&other.owned);
    assert(hddInstallUnmountStage(&other)==0&&!mounted);
    assert(hddInstallMountStage(&other)==0);hddInstallCleanup(&other);assert(!other.owned);assert(hddInstallUnmountStage(&other)==0);
    other.stage_on_ata=other.jail=1;strcpy(other.stage,"ata0:/tmp");
    other.ca_path[0]=0;
    assert(!hddInstallLoadCa(&other)&&other.ca_size==8);
    assert(hddInstallMountStage(&other)==0&&!mounted);
    assert(hddInstallCreateStage(&other)==0&&other.owned&&other.stage_ready);
    assert(!strcmp(other.ca_path,"ata0:/tmp/INSTALL_CA.PEM"));
    fd=genOpen(other.ca_path,FIO_O_RDONLY);assert(fd>=0);memset(ca,0,sizeof(ca));
    assert(read(fd,ca,16)==8&&!strcmp(ca,"embedded"));close(fd);
    assert(!hddInstallLoadCa(&other)&&other.ca_size==8&&!memcmp(other.ca_data,"embedded",8));
    assert(hddInstallFindStage(&other)==0);
    hddInstallCleanup(&other);assert(!other.owned&&!other.stage[0]);
    assert(hddInstallUnmountStage(&other)==0&&!mounted);
    puts("PASS: create PFS and ATA temp folders, preserve CA before erasure, short I/O, refuse existing folders and ownership-checked cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix='hdd-installer-stage-') as directory:
    d = Path(directory); (d / 'test.c').write_text(code); (d / 'ata').mkdir(); (d / 'common').mkdir()
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-I', str(root / 'include'),
                    str(d / 'test.c'), str(root / 'src/hdd_install_plan.c'), str(root / 'src/hdd_install_recovery.c'), str(root / 'src/save_sign.c'),
                    '-o', str(d / 'test')], check=True)
    subprocess.run([str(d / 'test'), str(d)], check=True, timeout=10)
