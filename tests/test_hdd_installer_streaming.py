"""Run the real PSBBN extraction flow with gzip archives and disk/FS facades."""
from pathlib import Path
import gzip
import io
import random
import re
import subprocess
import tarfile
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'src/hdd_install_psbbn.c').read_text()


def function(signature, source=source):
    a = source.index(signature)
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[a:], re.S):
        depth += (token.group() == '{') - (token.group() == '}')
        if not depth and token.group() == '}':
            return source[a:a + token.end()] + '\n'
    raise AssertionError(signature)


code = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "hdd_install.h"
#include "install_ext2.h"
#define MAX_PATH 1025
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_TRUNC O_TRUNC
#define FIO_MT_RDWR 1
#define FIO_S_ISDIR S_ISDIR
#define FIO_S_ISREG S_ISREG
typedef struct {unsigned mode;} iox_stat_t;
static const char *work;
static unsigned mounted,unmounted,created,finished,config_writes,entries,archive_opens,slots=4;
static HddInstall settings;
static unsigned destinations,linux1,linux4;
static int scenario;
static unsigned reboots, syncs, stage_mounts, stage_unmounts, archive_offset;
static unsigned checkpoint_lines, checkpoints, previous_routed, last_count[2];
static char last_archive[2048];
static int archive_fd=-1;
struct InstallExt2 {unsigned entries, route;};
int installExt2Create(InstallExt2 **out,const HddFormatIo *io,uint32_t a,uint32_t b,uint32_t serial){
 (void)b;(void)serial;assert(io);*out=calloc(1,sizeof(**out));assert(*out);
 (*out)->route=(a-8192-2048)/10000000;created++;return 0;
}
int installExt2Begin(InstallExt2 *fs,const InstallTarEntry *e){
 assert(fs&&e);entries++;fs->entries++;
 return scenario==9&&!strcmp(e->name,"etc/httpd/conf/httpd.conf")?-EINVAL:0;
}
int installExt2Data(InstallExt2 *fs,const void *p,unsigned n){assert(fs&&p&&n);return 0;}
int installExt2End(InstallExt2 *fs){
 assert(fs);return scenario==18&&fs->route==0&&fs->entries==100?-EIO:0;
}
int installExt2Sync(InstallExt2 *fs){
 assert(fs&&archive_fd>=0&&!finished);
 if(scenario==17)return -EIO;
 if(fs->route==0)assert(fs->entries==(reboots==0?2000:reboots==1?4000:4001));
 if(fs->route==2)assert(fs->entries==(reboots<2?1999:2000));
 syncs++;return 0;
}
int installExt2Finish(InstallExt2 *fs){assert(fs);finished++;return 0;}
void installExt2Free(InstallExt2 *fs){free(fs);}
int installPsbbnSwap(const HddFormatIo *io,uint32_t a,uint32_t b){(void)io;(void)a;(void)b;return 0;}
int installPsbbnMusic(const HddFormatIo *io,uint32_t a,uint32_t b,uint32_t c){(void)io;(void)a;(void)b;(void)c;return 0;}
int hddInstallResumeSave(HddInstall *in){assert(in);return 0;}
void hddInstallLog(const char *s,...){
 assert(s);
 if(!strcmp(s,"Archive destination: %s (%s)")){
  va_list a;va_start(a,s);const char *name=va_arg(a,const char*),*type=va_arg(a,const char*);
  destinations++;
  if(!strcmp(name,"__linux.1")){linux1++;assert(!strcmp(type,"ext2/raw HDD"));}
  if(!strcmp(name,"__linux.4")){linux4++;assert(!strcmp(type,"ext2/raw HDD"));}
  va_end(a);
 }else if(!strncmp(s,"EXTRACT progress",16)){
  va_list a;va_start(a,s);
  const char *archive=va_arg(a,const char*),*partition=va_arg(a,const char*);
  unsigned count=va_arg(a,unsigned),routed=va_arg(a,unsigned),read=va_arg(a,unsigned);
  const char *last=va_arg(a,const char*);
  va_end(a);
  assert(!strcmp(archive,"system.tar.gz")&&!strncmp(last,partition,strlen(partition)));
  assert(!strcmp(partition,"__linux.1")||!strcmp(partition,"__linux.4"));
  unsigned index=!strcmp(partition,"__linux.4");
  assert(count==last_count[index]+100&&routed>previous_routed&&read==archive_offset);
  if(!index&&count==100)assert(!strcmp(last,"__linux.1/bulk/first95"));
  last_count[index]=count;previous_routed=routed;checkpoint_lines++;
 }
}
void hddInstallLogFlush(HddInstall *in){assert(in);}
void hddInstallLogCheckpoint(HddInstall *in){
 assert(in==&settings&&archive_fd>=0&&strstr(last_archive,"system.tar.gz")&&checkpoint_lines==checkpoints+1);
 checkpoints++;
}
void hddInstallStatus(const char *s,int a,int b){assert(s&&a>=0&&b>=a);}
void hddInstallProgress(const char *s,int a,int b){assert(s&&a>=0&&b>=a);}
void hddInstallOverall(uint64_t a,uint64_t b){assert(b&&a<=b);}
int hddInstallWriteConfigs(HddInstall *in){assert(in);config_writes++;return scenario==8?-EINVAL:0;}
static const char *translate(const char *p){
 static char path[2048];
 if(!strncmp(p,"pfs",3)){assert(slots&(1u<<(p[3]-'0')));assert(p[3]>='0'&&p[3]<='3'&&p[4]==':');snprintf(path,sizeof(path),"%s/pfs%c%s",work,p[3],p+5);return path;}
 if(!strncmp(p,"ata0:",5)){snprintf(path,sizeof(path),"%s/ata%s",work,p+5);return path;}
 return p;
}
static int genOpen(const char *p,int flags){
 int fd=open(translate(p),flags,0600);
 if(fd<0)return -errno;
 if(strstr(p,".tar.gz")){
  assert(flags==O_RDONLY&&archive_fd<0);archive_fd=fd;archive_opens++;
  if(strcmp(last_archive,p)){archive_offset=0;strcpy(last_archive,p);}
 }
 return fd;
}
static int genRead(int fd,void *p,unsigned n){
 int r=read(fd,p,n);if(r>0&&fd==archive_fd)archive_offset+=r;return r<0?-errno:r;
}
static int genWrite(int fd,void *p,unsigned n){int r=write(fd,p,n);return r<0?-errno:r;}
static int64_t genLseek(int fd,int offset,int whence){
 if(fd==archive_fd)assert(whence==SEEK_SET&&offset>=0&&(unsigned)offset==archive_offset);
 return lseek(fd,offset,whence);
}
static int genClose(int fd){
 assert(fd>=0);if(fd==archive_fd)archive_fd=-1;return close(fd);
}
static int genMkdir(const char *p,int mode){return mkdir(translate(p),mode)<0?-errno:0;}
static int fileXioGetStat(const char *p,iox_stat_t *out){struct stat st;if(stat(translate(p),&st)<0)return -errno;out->mode=st.st_mode;return 0;}
#define genGetStat fileXioGetStat
static int genRemove(char *p){return unlink(translate(p))<0?-errno:0;}
static int fileXioRename(const char *from,const char *to){
 char src[2048];strcpy(src,translate(from));return rename(src,translate(to))<0?-errno:0;
}
static int fileXioMount(const char *p,const char *partition,int mode){
 unsigned slot=p[3]-'0';assert(slot<4&&!(slots&(1u<<slot))&&mode==1);
 assert(!strcmp(partition,slot==0?"hdd0:__system":slot==1?"hdd0:__sysconf":"hdd0:__contents"));
 slots|=1u<<slot;mounted++;return 0;
}
static int fileXioUmount(const char *p){
 unsigned slot=p[3]-'0';assert(slot<4&&slot!=2&&(slots&(1u<<slot))&&archive_fd<0);
 slots&=~(1u<<slot);unmounted++;return 0;
}
int hddInstallMountStage(HddInstall *in){
 assert(in==&settings&&!slots&&archive_fd<0);
 if(!in->stage_on_ata)slots=4;
 stage_mounts++;return 0;
}
int hddInstallUnmountStage(HddInstall *in){
 assert(in==&settings&&slots==(in->stage_on_ata?0u:4u)&&archive_fd<0);
 slots=0;stage_unmounts++;return 0;
}
static int restart(void *context){
 assert(scenario>=13&&context==&settings&&!slots&&archive_fd<0&&archive_offset);
 assert(stage_unmounts==reboots+1&&stage_mounts==reboots);
 assert(syncs==created*(reboots+1)&&!finished&&!config_writes);
 reboots++;return scenario==15?-ENODEV:0;
}
'''
a = source.index('static const char *const linux_names')
code += source[a:source.index('static uint32_t le32(', a)] + function('static uint32_t le32(')
output = (root / 'src/hdd_install_ps2.c').read_text()
code += output[output.index('static int outputPath('):output.index('void hddInstallRelease(')]
code += function('int hddInstallEnsureDirectory(', output)
a = source.index('typedef struct PendingPfsFile {')
code += source[a:source.index('} Payload;', a) + len('} Payload;')]
for sig in ('static int routePath(', 'static int mkdirParents(', 'static int stagePfsFile(',
            'static int mountTargets(', 'static int unmountTargets(', 'static int finishPfsFiles(',
            'static int begin(', 'static int data(', 'static int rebootBetweenEntries(',
            'static int end(', 'static int readArchive(', 'static int archives(', 'static int verifyRequired(', 'int hddInstallPsbbnPayload('):
    code += function(sig)
code += r'''
static void put32(unsigned char *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=n>>(8*i);}
static int rawRead(void *ctx,uint32_t lba,unsigned n,void *p){
 HddInstall *in=ctx;unsigned char *bytes=p;assert(n==2);memset(p,0,1024);
 unsigned i=0;while(i<10&&in->linux[i].start!=lba)i++;assert(i<10);
 put32(bytes+4,0x00415041);strcpy((char*)bytes+16,linux_names[i]);
 put32(bytes+64,lba);put32(bytes+68,in->linux[i].sectors);put32(bytes+72,i==1?0x82:0x83);
 uint32_t sum=0;for(unsigned w=1;w<256;w++)sum+=le32(bytes+w*4);put32(bytes,sum);return 0;
}
static int rawFlush(void *ctx){assert(ctx);return 0;}
int main(int argc,char **argv){
 assert(argc==3);work=argv[1];scenario=atoi(argv[2]);int linux=scenario==5||scenario==6;
 settings.flags=7|(linux?HDD_INSTALL_PS2LINUX:0);settings.jail=1;
 settings.stage_on_ata=scenario==14;slots=settings.stage_on_ata?0:4;
 strcpy(settings.stage,settings.stage_on_ata?"ata0:/tmp":"pfs2:/tmp");
 for(unsigned i=0;i<10;i++){settings.linux[i].start=2048+i*10000000;settings.linux[i].sectors=hddInstallPartitionMb(&settings,i)*2048;}
 const unsigned assets[]={HI_SYSTEM,HI_LANGUAGE,HI_PS2LINUX};
 for(unsigned i=0;i<(linux?3u:2u);i++){
  char path[2048];struct stat st;
  snprintf(path,sizeof(path),"%s/%s",settings.stage,hddInstallAssetName(assets[i]));
  assert(!stat(translate(path),&st));settings.sizes[assets[i]]=st.st_size;
 }
 HddFormatIo io={.context=&settings,.read=rawRead,.flush=rawFlush};
 int ret=hddInstallPsbbnPayload(&settings,&io,restart);
 if(scenario==13||scenario==14){
  assert(!ret&&finished==created&&config_writes==1&&archive_opens==5&&reboots==3&&settings.populated);
 }
 else if(scenario==0||scenario==5){assert(!ret&&finished==created&&config_writes==1&&archive_opens==(linux?3u:2u)&&destinations>=6&&linux1==2&&linux4==2);}
 else{
  assert(ret<0&&!finished&&config_writes==(scenario==8));
  assert(!strstr(settings.error,"Boot MBR"));
  if(scenario==1)assert(strstr(settings.error,"required archive entry")&&strstr(settings.error,"__system/osd100/TEXIMAGE"));
  if(scenario==2)assert(strstr(settings.error,"language.tar.gz")&&!strstr(settings.error,"__linux.1/revisit"));
  if(scenario==6)assert(strstr(settings.error,"required archive entry")&&strstr(settings.error,"PS2Linux.tar.gz bin/sh"));
  if(scenario==7)assert(strstr(settings.error,"after extracting __linux.1/etc/httpd/conf/httpd.conf"));
  if(scenario==8)assert(strstr(settings.error,"Installing launchers and boot configuration")&&!strstr(settings.error,"httpd.conf"));
  if(scenario==9)assert(strstr(settings.error,"while processing __linux.1/etc/httpd/conf/httpd.conf"));
  if(scenario==15)assert(ret==-ENODEV&&reboots==1&&archive_opens==1&&strstr(settings.error,"IOP reboot at __linux.1 entry 2000"));
  if(scenario==16)assert(reboots==2&&archive_opens==3&&strstr(settings.error,"Reading or validating system.tar.gz"));
  if(scenario==17)assert(ret==-EIO&&!reboots&&archive_opens==1&&strstr(settings.error,"syncing ext2 metadata"));
  if(scenario==18)assert(ret==-EIO&&!reboots&&strstr(settings.error,"while processing __linux.1/bulk/first95"));
 }
 assert(mounted==3*(1+reboots)&&unmounted==mounted&&(entries>0||scenario>=11)&&slots==(settings.stage_on_ata?0u:4u));
 assert(stage_mounts==reboots&&stage_unmounts==reboots&&archive_fd<0);
 if(scenario>=13) assert(syncs==created*reboots);
 unsigned expected=(scenario==13||scenario==14||scenario==16)?59:(scenario==15||scenario==17)?39:0;
 assert(checkpoints==expected&&checkpoint_lines==expected);
 puts("PASS: single-pass extraction checks CRCs, required boot files, protected paths and capacity before clean/boot commit");
}
'''


def archive(path, entries, bad_padding=False):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as t:
        for name, content in entries:
            e = tarfile.TarInfo(name)
            if content is None:
                e.type = tarfile.DIRTYPE
                e.mode = 0o755
                t.addfile(e)
            else:
                e.mode = 0o644
                e.size = len(content)
                t.addfile(e, io.BytesIO(content))
    tar_data = payload.getvalue()
    if bad_padding:
        tar_data = tar_data[:-1] + b"X"
    path.write_bytes(gzip.compress(tar_data, mtime=0))


with tempfile.TemporaryDirectory(prefix='hdd-installer-streaming-') as directory:
    d = Path(directory)
    (d / 'test.c').write_text(code)
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
                    '-I', str(root / 'include'), str(d / 'test.c'), str(root / 'src/hdd_install_plan.c'), str(root / 'src/hdd_install_recovery.c'),
                    str(root / 'src/install_tar.c'), '-lz', '-o', str(d / 'test')], check=True)
    required = ['__system/p2lboot/osdboot.elf', '__system/p2lboot/vmlinux', '__linux.1/sbin/init',
                '__linux.1/bin/sh', '__linux.1/etc/fstab', '__linux.4/bn/script/utility/sysconf.xml']
    required += ['__system/osd100/' + name for name in ('OSDSYS_A.XLF', 'FNTOSD', 'ICOIMAGE', 'JISUCS', 'SKBIMAGE', 'SNDIMAGE', 'TEXIMAGE')]
    for scenario in range(19):
        work = d / str(scenario)
        work.mkdir()
        for i in range(4): (work / f'pfs{i}').mkdir()
        stage = work / ('ata/tmp' if scenario == 14 else 'pfs2/tmp')
        stage.mkdir(parents=True)
        names = required[:-1] if scenario == 1 else required
        entries = [(name, b'fixture') for name in names]
        if scenario == 3: entries.append(('__system/osdmenu/hosdmenu.elf', b'protected'))
        if scenario == 4: entries.append(('__system/oversized', bytes(33 * 1024 * 1024)))
        entries.append(('__contents/fixture', b'contents data'))
        entries.append(('__linux.1/revisit', b'partition revisited later in the same archive'))
        if scenario in (0, 5):
            entries.extend((('__contents/fixture', b'last entry wins'), ('__contents/empty', b'')))
        kernel = work / 'pfs0/p2lboot/vmlinux'
        if scenario == 0:
            kernel.parent.mkdir()
            (kernel.parent / 'keep').write_bytes(b'existing contents')
            entries.append(('__system/p2lboot', None))
        if scenario >= 13:
            rng = random.Random(0)
            entries.extend((f'__linux.1/bulk/first{i}', rng.randbytes(96)) for i in range(1995))
            entries.extend((f'__linux.4/bulk/independent{i}', rng.randbytes(96)) for i in range(1998))
            entries.extend((f'__linux.1/bulk/second{i}', rng.randbytes(96)) for i in range(2002))
        if scenario in (15, 16, 17):
            kernel.parent.mkdir()
            kernel.write_bytes(b'previous good kernel')
        archive(stage / 'system.tar.gz', entries, bad_padding=scenario == 16)
        if scenario in (11, 12):
            kernel.parent.mkdir()
            kernel.write_bytes(b'previous good kernel')
            entry = tarfile.TarInfo('__system/p2lboot/vmlinux')
            entry.size = 65536
            partial = b'X' * (0 if scenario == 11 else 32768)
            (stage / 'system.tar.gz').write_bytes(gzip.compress(entry.tobuf() + partial, mtime=0))
        language = [('__linux.4/translation', b'localized')]
        if scenario == 10:
            language.extend((('__system/p2lboot/vmlinux', b'bad overlay'), ('__contents/unpublished', b'new file')))
        if scenario >= 7:
            language.append(('__linux.1/etc/httpd/conf/httpd.conf', b'httpd fixture'))
        archive(stage / 'language.tar.gz', language, bad_padding=scenario == 7)
        if scenario in (2, 10):
            p = stage / 'language.tar.gz'
            corrupted = bytearray(p.read_bytes()); corrupted[-8] ^= 1; p.write_bytes(corrupted)
        if scenario in (5, 6):
            archive(stage / 'PS2Linux.tar.gz', [('sbin/init', b'init')] + ([] if scenario == 6 else [('bin/sh', b'shell')]))
        subprocess.run([str(d / 'test'), str(work), str(scenario)], check=True)
        if scenario in (0, 5):
            assert (work / 'pfs3/fixture').read_bytes() == b'last entry wins'
            assert (work / 'pfs3/empty').read_bytes() == b''
            assert not (work / 'pfs2/fixture').exists()
        if scenario == 0:
            assert kernel.read_bytes() == b'fixture'
            assert (kernel.parent / 'keep').read_bytes() == b'existing contents'
        if scenario == 10:
            assert kernel.read_bytes() == b'fixture'
            assert not (work / 'pfs3/unpublished').exists()
        if scenario in (11, 12, 15, 16, 17):
            assert kernel.read_bytes() == b'previous good kernel'
        if scenario in (13, 14):
            assert (work / 'pfs3/fixture').read_bytes() == b'contents data'
            assert kernel.read_bytes() == b'fixture'
        assert not list(work.rglob('.LSINST-*'))
    print('PASS: 100-entry system extraction log records are saved per ext2 partition after completed entries')
    print('PASS: per-partition IOP checkpoints continue the same gzip stream from PFS and ATA staging')
    print('PASS: archive and reboot failures preserve existing PFS files without publishing partial files')
