"""Run production app/HOSD installation against a host-backed PFS/ATA facade."""
from pathlib import Path
import hashlib
import io
import struct
import subprocess
import tempfile
import zipfile

root = Path(__file__).resolve().parents[1]
native = (root / 'src/hdd_install_ps2.c').read_text().replace('#include "launchelf.h"', '').replace('#include "dash_internal.h"', '')
code = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include "hdd_install.h"
#define MAX_PATH 1025
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_EXCL O_EXCL
#define FIO_O_TRUNC O_TRUNC
#define FIO_MT_RDWR 1
#define FIO_CST_ATTR 1
#define FIO_S_ISDIR S_ISDIR
#define FS_GROUP_APPLICATION 1
#define HDIOC_FLUSH 1
typedef uint64_t u64;
typedef int64_t s64;
typedef struct { unsigned mode,attr,size,private_0,private_5; } iox_stat_t;
static char work[1024];
static const char *mounted[4];
static unsigned mounts,attrcalls,partitions,injected,psbbn_parts;
static int attr_error, replay, jail_install, partition_error;
static unsigned legacy_launcher_mb;
static u64 Timer(void){return 1;}
static void dashWorkerStatus(const char*s,unsigned n,unsigned total){assert(s);(void)n;(void)total;}
static int map(const char*p,char*out,size_t cap) {
    const char *colon=strchr(p,':'),*base;
    char prefix[2048];
    if(!colon)return -EINVAL;
    if(!strncmp(p,"usb0:",5))base="stage";
    else if(!strncmp(p,"ata0:",5))base="ata";
    else if(!strncmp(p,"pfs",3)&&p[3]>='0'&&p[3]<='3'&&p[4]==':') {
        unsigned i=p[3]-'0';if(!mounted[i])return -ENODEV;base=mounted[i];
    } else return -ENOENT;
    if(snprintf(prefix,sizeof(prefix),"%s/%s",work,base)>=(int)sizeof(prefix))return -ENAMETOOLONG;
    return snprintf(out,cap,"%s%s",prefix,colon+1)<(int)cap?0:-ENAMETOOLONG;
}
static int genOpen(const char*p,int mode){char path[4096];int r=map(p,path,sizeof(path));return r<0?r:open(path,mode,0600);}
static int genRead(int fd,void*p,unsigned n){if(n>97)n=97;return read(fd,p,n);}
static int genWrite(int fd,const void*p,unsigned n){if(n>31)n=31;return write(fd,p,n);}
#define genLseek lseek
#define genClose close
static int genMkdir(const char*p,int mode){char path[4096];int r=map(p,path,sizeof(path));return r<0?r:mkdir(path,mode)<0?-errno:0;}
static int genRemove(char*p){char path[4096];int r=map(p,path,sizeof(path));return r<0?r:unlink(path);}
static int genRmdir(char*p){char path[4096];int r=map(p,path,sizeof(path));return r<0?r:rmdir(path);}
static int fileXioGetStat(const char*p,iox_stat_t*s){
    char path[4096];struct stat st;
    if(!strncmp(p,"hdd0:PP.",8)){
        snprintf(path,sizeof(path),"%s/%s",work,p+5);if(stat(path,&st)<0)return -errno;
        memset(s,0,sizeof(*s));s->mode=0x100;s->size=(legacy_launcher_mb?legacy_launcher_mb:HDD_INSTALL_APP_MB)*2048u;s->private_5=1024*2048u;return 0;
    }
    int r=map(p,path,sizeof(path));if(r<0)return r;if(stat(path,&st)<0)return -errno;s->mode=st.st_mode;return 0;
}
static int fileXioFormat(const char*fs,const char*p,const char*args,int n){
    assert(!strcmp(fs,"pfs:")&&!strncmp(p,"hdd0:PP.",8)&&n==sizeof(int)&&*(const int*)args==8192&&replay);return 0;
}
static int fileXioChStat(const char*p,const iox_stat_t*s,int flags){assert(strstr(p,"pfs2:/APPS") && s->attr==0xc4a7 && flags==FIO_CST_ATTR);attrcalls++;return attr_error;}
static int fileXioMount(const char*m,const char*p,int flags){unsigned i=m[3]-'0';assert(i<4&&!mounted[i]&&flags==FIO_MT_RDWR);mounted[i]=p+5;mounts++;return 0;}
static int fileXioUmount(const char*m){unsigned i=m[3]-'0';assert(i<4&&mounted[i]);mounted[i]=NULL;mounts--;return 0;}
static int hddMakeFilesystem(int mb,char*name,int group){char path[4096];assert(mb==(int)HDD_INSTALL_APP_MB&&group==FS_GROUP_APPLICATION);if(partition_error)return partition_error;partitions++;snprintf(path,sizeof(path),"%s/%s",work,name);assert(!mkdir(path,0700));return mb;}
static int InjectHddAppLauncher(const char*p,const char*elf,const char*title,const void*icon,unsigned size){
    char expected[256];
    const char *app=!strcmp(p,"PP.APP_WLE-R3Z")?"APP_WLE-R3Z/WLE-R3Z.ELF":"SYS_R3CONFIGURATOR/r3configurator.elf";
    assert(!strcmp(p,"PP.APP_WLE-R3Z")||!strcmp(p,"PP.SYS_R3CONFIGURATOR"));
    snprintf(expected,sizeof(expected),"%s/%s",jail_install?"ata0:/APPS":"hdd0:__common:pfs:/APPS",app);
    assert(title&&icon&&size&&!strcmp(elf,expected)&&(replay||partitions==injected+1));
    injected++;return 0;
}
static int InjectHddAppLauncherWithArg(const char*p,const char*elf,const char*title,const void*icon,unsigned size,const char*arg){
    assert(!strcmp(p,"PP.LAUNCHER")&&title&&icon&&size&&(replay||partitions==injected+1));
    assert(strstr(elf,"hdd0:__system:pfs:/launcher/"));
    if(strstr(elf,"nhddl"))assert(arg&&!strcmp(arg,"-mode=ata"));else assert(!arg&&(strstr(elf,"OPNPS2LD.ELF")||strstr(elf,"RIPTOPL-RA-UNPAKT.ELF")));
    injected++;return 0;
}
int hddInstallPsbbnPartitions(HddInstall*in){assert(in->jail&&(in->flags&7)==7);psbbn_parts++;return 0;}
'''
code += r'''

int hddInstallResumeSave(HddInstall *in){assert(in);return 0;}
int hddInstallResumeRemove(HddInstall *in){assert(in);return 0;}
void hddInstallLog(const char *format, ...) { (void)format; }
int hddInstallLogEnabled(void) { return 0; }
void hddInstallLogFlush(HddInstall *in) { (void)in; }
void hddInstallStatus(const char *s,int done,int total) { dashWorkerStatus(s,done,total); }
void hddInstallProgress(const char *s,int done,int total) { assert(done>=0&&total>=0&&done<=total);dashWorkerStatus(s,done,total); }
void hddInstallOverall(uint64_t done,uint64_t total) { assert(total&&done<=total); }
void hddInstallPhase(unsigned phase) { assert(phase==HDD_INSTALL_PHASE_INSTALL); }
'''
code += native
code += r'''
int main(int argc,char**argv){
    HddInstall in={0};FILE*f;char path[4096],hash[41];unsigned i,size;int ret;
    assert(argc==5);snprintf(work,sizeof(work),"%s",argv[1]);in.flags=atoi(argv[2]);in.jail=!!(in.flags&4);in.game_launcher=atoi(argv[4]);jail_install=in.jail;
    in.ready=in.owned=1;strcpy(in.stage,in.jail?"pfs2:/tmp":"pfs2:/PSBBN_DP_TEMP");memset(in.commit,'a',40);
    snprintf(path,sizeof(path),"%s/manifest",work);f=fopen(path,"r");assert(f);
    while(fscanf(f,"%u %u %40s",&i,&size,hash)==3){assert(i<HDD_INSTALL_ASSETS);in.sizes[i]=size;strcpy(in.hashes[i],hash);}fclose(f);
    if(in.jail){
        in.launcher_files=calloc(HDD_INSTALL_LAUNCHER_FILES,sizeof(*in.launcher_files));assert(in.launcher_files);
        snprintf(path,sizeof(path),"%s/launcher-manifest",work);f=fopen(path,"r");assert(f);
        char remote[192];
        while(fscanf(f,"%u %191s %u %40s",&i,remote,&size,hash)==4){
            assert(i==in.launcher_count&&i<HDD_INSTALL_LAUNCHER_FILES);
            strcpy(in.launcher_files[i].path,remote);strcpy(in.launcher_files[i].hash,hash);in.launcher_files[i].size=size;in.launcher_count++;
        }fclose(f);
    }
    if(!strcmp(argv[3],"hash-ignored"))in.hashes[2][0]^=1;
    if(!strcmp(argv[3],"attr"))attr_error=-EIO;
    if(!strcmp(argv[3],"size"))in.sizes[2]--;
    if(!strcmp(argv[3],"launcher-size"))in.launcher_files[0].size--;
    if(!strcmp(argv[3],"mini-create"))partition_error=-ENOSPC;
    ret=hddInstallApply(&in);assert(!mounts);
    if(strcmp(argv[3],"ok")&&strcmp(argv[3],"hash-ignored")){assert(ret<0);assert(!partitions&&!injected);hddInstallRelease(&in);return 0;}
    assert(ret==0);
    if(in.flags&4){
        assert(!fileXioMount("pfs0:","hdd0:__system",1));assert(!fileXioMount("pfs1:","hdd0:__sysconf",1));
        assert(!hddInstallMountStage(&in));assert(hddInstallWriteConfigs(&in)==0);assert(!hddInstallUnmountStage(&in));
        assert(!fileXioUmount("pfs1:")&&!fileXioUmount("pfs0:"));
    }
    assert(attrcalls==(!in.jail&&(in.flags&2)?3:0));
    assert(partitions==(in.flags&2?(in.jail?3:2):0)&&injected==partitions&&psbbn_parts==(unsigned)in.jail);
    if(in.flags&2){snprintf(path,sizeof(path),"%s/%s/APPS/APP_WLE-R3Z/WLE-R3Z.ELF",work,in.jail?"ata":"__common");assert(!access(path,F_OK));}
    if(in.flags&1){snprintf(path,sizeof(path),"%s/__system/osdmenu/hosdmenu.elf",work);assert(!access(path,F_OK));}
    if(!in.jail&&(in.flags&1)){snprintf(path,sizeof(path),"%s/__sysconf/osdmenu/OSDMBR.CNF",work);assert(!access(path,F_OK));}
    /* Replaying an incomplete apply overwrites generated/app files and
     * reuses only installer-owned partitions, without creating duplicates. */
    in.recovery_attempts=1;in.apa_sectors=131072u*2048;replay=1;
    assert(hddInstallApply(&in)==0&&!mounts);
    assert(partitions==(in.flags&2?(in.jail?3:2):0)&&injected==partitions*2);
    if(in.jail&&in.game_launcher==HDD_GAME_RIPTOPL_NEUTRINO){
        /* Resuming an old install preserves its existing larger volumes. */
        legacy_launcher_mb=128;
        assert(!hddInstallApply(&in)&&!mounts&&partitions==3&&injected==9);
        const unsigned bad[]={16,32,64,256};
        for(unsigned k=0;k<sizeof(bad)/sizeof(*bad);k++){
            legacy_launcher_mb=bad[k];
            assert(hddInstallPfsPartition(&in,HDD_INSTALL_APP_MB,"PP.LAUNCHER")==-EINVAL);
        }
    }
    hddInstallRelease(&in);return 0;
}
'''

def psu(folder, boot):
    elf = bytearray(120); elf[:6] = b'\x7fELF\x01\x01'; elf[18] = 8
    files = [(boot, bytes(elf)), ('title.cfg', b'boot=' + boot.encode()), ('list.icn', b'icon fixture' * 10)]
    def header(name, mode, size):
        h = bytearray(512); struct.pack_into('<H', h, 0, mode); struct.pack_into('<I', h, 4, size)
        h[64:64 + len(name)] = name.encode(); return bytes(h)
    out = header(folder, 0x8427, len(files) + 2) + header('.', 0x8427, 0) + header('..', 0x8427, 0)
    for n, data in files: out += header(n, 0x8497, len(data)) + data + bytes((-len(data)) % 1024)
    return out

with tempfile.TemporaryDirectory(prefix='hdd-installer-apply-') as directory:
    d = Path(directory); (d / 'test.c').write_text(code)
    subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root / 'include'), str(d / 'test.c'),
                    *[str(root / 'src' / (n + '.c')) for n in ('hdd_install_plan','hdd_install_recovery','install_archive','save_archive','save_lzari','save_sign')],
                    '-lz', '-o', str(d / 'test')], check=True)
    extra = io.BytesIO()
    with zipfile.ZipFile(extra, 'w', zipfile.ZIP_DEFLATED) as z:
        for name in ('OSDSYS_A.XLF','FNTOSD','ICOIMAGE','JISUCS','SKBIMAGE','SNDIMAGE','TEXIMAGE'):
            z.writestr('extras/' + name, b'OSD fixture ' * 1000)
    assets = [('OSDMBR.XLF', b'\x01\x00\x00\x04' + bytes(508)), ('hosdmenu.elf', b'ELF fixture'),
              ('APP_WLE-R3Z.psu', psu('APP_WLE-R3Z','WLE-R3Z.ELF')),
              ('SYS_R3CONFIGURATOR.psu', psu('SYS_R3CONFIGURATOR','r3configurator.elf')),
              ('extras.zip', extra.getvalue()), ('version.txt', b'fixture'),
              ('system.tar.gz', b'preflight fixture'), ('language.tar.gz', b'preflight fixture'),
              ('APP_WLER3Z.png', b'jacket fixture'), ('SYS_R3CONFIG.png', b'jacket fixture'), ('PS2Linux.tar.gz', b'linux preflight fixture'), ('ps2-linux-ntsc', b'new NTSC kernel'), ('ps2-linux-vga', b'new VGA kernel')]
    elf = bytearray(120); elf[:6] = b'\x7fELF\x01\x01'; elf[18] = 8
    launchers = [
        ('scripts/assets/OPL/OPNPS2LD.ELF', bytes(elf)), ('scripts/assets/NHDDL/nhddl.elf', bytes(elf)),
        ('scripts/assets/neutrino/neutrino.elf', bytes(elf)), ('scripts/assets/neutrino/modules/ata_bd.irx', b'ATA module'),
        ('scripts/assets/neutrino/config/system.toml', b'Neutrino configuration'), ('scripts/assets/neutrino/version.txt', b'v1.8.0'),
        ('scripts/assets/neutrino/udpfs_server/compressed_iso/__init__.py', b'UDPFS helper'),
        ('scripts/assets/OPL/version.txt', b'OPL version'), ('scripts/assets/NHDDL/version.txt', b'NHDDL version'),
        ('scripts/assets/OPL/LNG/lang_French.lng', b'French translation'),
        ('scripts/licenses/OPL', b'OPL license'), ('scripts/licenses/nhddl', b'NHDDL license'), ('scripts/licenses/neutrino', b'Neutrino license'),
    ]
    for flags, failure, launcher in ((1,'ok',0),(2,'ok',0),(3,'ok',0),(7,'ok',0),(7,'ok',1),(7,'ok',2),(15,'ok',2),(7,'ok',3),
                                    (15,'ok',0),(15,'ok',1),(3,'hash-ignored',0),(3,'size',0),(3,'attr',0),(3,'mini-create',0),(7,'launcher-size',0)):
        work = d / (str(flags) + failure + str(launcher)); work.mkdir()
        for part in ('stage','ata','__system','__sysconf','__common'): (work / part).mkdir()
        stage = work / '__common' / ('tmp' if flags & 4 else 'PSBBN_DP_TEMP'); stage.mkdir()
        if flags & 8: (work / '__system/p2lboot').mkdir()
        (stage / 'owner.bin').write_bytes(bytes(20))
        manifest = []
        for i, (name, data) in enumerate(assets):
            (stage / name).write_bytes(data)
            prefix = b'' if i in (4,6,7,10) else b'blob ' + str(len(data)).encode() + b'\0'
            manifest.append(f'{i} {len(data)} {hashlib.sha1(prefix+data).hexdigest()}\n')
        (work / 'manifest').write_text(''.join(manifest))
        if flags & 4:
            selected_launchers = launchers
            if launcher>=2:
                selected_launchers = [(remote,payload) for remote,payload in launchers if not any(x in remote for x in ('NHDDL','OPNPS2LD','scripts/licenses/'))]
                selected_launchers += [('scripts/assets/OPL/RIPTOPL-RA-UNPAKT.ELF',bytes(elf)),('scripts/assets/Ember/ember.elf',bytes(elf)),
                    ('scripts/assets/Ember/version.txt',b'0.8'),('scripts/licenses/EMBER-LICENSE-BETA.txt',b'Ember license'),
                    ('scripts/licenses/RiptOPL.txt',b'RiptOPL license'),('scripts/licenses/neutrino.txt',b'Neutrino license')]
                dep=io.BytesIO()
                with zipfile.ZipFile(dep,'w',zipfile.ZIP_DEFLATED) as z:
                    z.writestr('dep/bios.bin',b'B'*524288)
                    z.writestr('dep/ignored.bin',b'unneeded')
                (stage/'extras.zip').write_bytes(dep.getvalue())
                manifest[4]=f'4 {len(dep.getvalue())} '+ 'a'*40+'\n'
                (work/'manifest').write_text(''.join(manifest))
            package = selected_launchers + [('icons/ico/APP_RIPTOPL_LST.ico' if launcher>=2 else 'icons/ico/APP_NHDDL_LST.ico' if launcher else 'icons/ico/APP_OPL_LST.ico', b'launcher icon'),
                                   ('icons/art/APP_RIPTOPL.png' if launcher>=2 else 'icons/art/APP_NHDDL.png' if launcher else 'icons/art/APP_OPL.png', b'launcher art')]
            manifest = []
            for i, (remote, data) in enumerate(package):
                if remote.startswith('scripts/assets/'):
                    relative = remote[len('scripts/assets/'):]
                    if relative.startswith('neutrino/'):
                        relative = 'Neutrino/' + relative[len('neutrino/'):]
                elif remote.startswith('scripts/licenses/'):
                    relative = 'Licenses/' + remote[len('scripts/licenses/'):]
                else:
                    relative = 'Icons/' + remote[len('icons/'):]
                local = stage / relative
                local.parent.mkdir(parents=True, exist_ok=True)
                if not remote.startswith('scripts/licenses/'): local.write_bytes(data)
                digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
                manifest.append(f'{i} {remote} {len(data)} {digest}\n')
            (work / 'launcher-manifest').write_text(''.join(manifest))
            (work / '__system/launcher').mkdir()
            for name in ('OPNPS2LD.ELF', 'nhddl.elf'):
                (work / '__system/launcher' / name).write_bytes(b'older archive launcher')
        subprocess.run([str(d / 'test'),str(work),str(flags),failure,str(launcher)],check=True,timeout=20)
        if flags & 8:
            assert (work / '__system/p2lboot/ps2-linux-ntsc').read_bytes() == b'new NTSC kernel'
            assert (work / '__system/p2lboot/ps2-linux-vga').read_bytes() == b'new VGA kernel'
            assert b'boot_circle = $PSBBN' in (work / '__sysconf/osdmenu/OSDMBR.CNF').read_bytes()
        if flags & 4 and failure == 'ok':
            assert (work / 'PP.APP_WLE-R3Z/res/info.sys').exists()
            assert (work / 'PP.SYS_R3CONFIGURATOR/res/jkt_001.png').read_bytes() == b'jacket fixture'
            assert (work / 'PP.LAUNCHER/res/jkt_001.png').read_bytes() == b'launcher art'
            assert (b'APP_RIPTOPL' if launcher>=2 else b'APP_NHDDL' if launcher else b'APP_OPL') in (work / 'PP.LAUNCHER/res/info.sys').read_bytes()
            if launcher>=2:
                assert (work/'__system/launcher/RIPTOPL-RA-UNPAKT.ELF').read_bytes()==bytes(elf)
                assert (work/'ata/Ember/ember.elf').read_bytes()==bytes(elf)
                assert (work/'ata/Ember/bios.bin').read_bytes()==b'B'*524288
                assert not (work/'ata/Ember/LICENSE.txt').exists()
                assert b'Gageformer' in (work/'ata/Ember/README.txt').read_bytes()
                assert (work/'ata/Ember/games').is_dir() and not (work/'ata/Ember/ignored.bin').exists()
            else:
                assert (work / '__system/launcher/OPNPS2LD.ELF').read_bytes() == bytes(elf)
                assert (work / '__system/launcher/nhddl.elf').read_bytes() == bytes(elf)
            assert (work / 'ata/neutrino/modules/ata_bd.irx').read_bytes() == b'ATA module'
            assert (work / 'ata/neutrino/config/system.toml').read_bytes() == b'Neutrino configuration'
            assert (work / 'ata/neutrino/udpfs_server/compressed_iso/__init__.py').read_bytes() == b'UDPFS helper'
            assert (work / 'ata/LNG/lang_French.lng').read_bytes() == b'French translation'
            assert b'enable_bdm_hdd=1' in (work / 'ata' / ('settings_riptopl.cfg' if launcher>=2 else 'conf_opl.cfg')).read_bytes()
            if launcher>=2:
                assert f'default_core={int(launcher==3)}'.encode() in (work/'ata/settings_riptopl.cfg').read_bytes()
            assert not (work/'__system/launcher/licenses').exists()
            config = (work / '__sysconf/osdmenu/OSDMENU.CNF').read_bytes()
            assert b'name_OSDSYS_ITEM_1 = ' + (b'RiptOPL (Neutrino)' if launcher==3 else b'Open PS2 Loader: RiptOPL' if launcher>=2 else b'Neutrino (NHDDL)' if launcher else b'Open PS2 Loader') in config
        if flags & 2 and not flags & 4 and failure in ('ok','hash-ignored'):
            assert (work/'PP.APP_WLE-R3Z').is_dir() and (work/'PP.SYS_R3CONFIGURATOR').is_dir()
            assert not (work/'PP.LAUNCHER').exists()
            if flags & 1:
                config=(work/'__sysconf/osdmenu/OSDMENU.CNF').read_bytes()
                assert b'hdd0:__common:pfs:/APPS/APP_WLE-R3Z/WLE-R3Z.ELF' in config
                assert b'hdd0:__common:pfs:/APPS/SYS_R3CONFIGURATOR/r3configurator.elf' in config
    print('PASS: pure APA/Jail 8 MiB launchers, persistent launch paths, production PSU/app/HOSD copying, shared APPS attributes, launcher resources, fast size checks without content hashing, short I/O and failed-install unmounts')
