"""Run the production VMCMAN backing against real files and failed I/O.

Checks PS1 geometry/sector writes, slot bounds, failed mount cleanup, PS2
regression, cache invalidation and the EE/IOP free-block/read-sector contract.
"""
from pathlib import Path
import os
import hashlib
import hmac
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
internal = (root / 'iop/vmcman/src/mcman-internal.h').read_text()
start = internal.index('typedef struct {', internal.index('extern int mcman_iomanx_backing_'))
end = internal.index('MCDevInfo;', start) + len('MCDevInfo;')
backing = (root / 'iop/vmcman/src/mciomanx_backing.c').read_text()
backing = '\n'.join(line for line in backing.splitlines() if not line.startswith('#include'))
signer = (root / 'iop/vmcman/src/vmp_sign.c').read_text()
signer = '\n'.join(line for line in signer.splitlines() if not line.startswith('#include'))
main = (root / 'iop/vmcman/src/main.c').read_text()
table_start = main.index('static const u8 mcman_xortable[256]')
table_end = main.index('};', table_start) + 2
checksum_start = main.index('void McDataChecksum(')
checksum_end = main.index('//--------------------------------------------------------------', checksum_start)
dev = (root / 'iop/vmcman/src/mcdev.c').read_text()
start_dev = dev.index('int mc_devctl(', dev.index('int mc_devctl(') + 1)
end_dev = dev.index('//--------------------------------------------------------------', start_dev)

code = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "vmc_control.h"
#include "save_sign.h"
#define BUILDING_VMCMAN 1
#define MCMAN_MAXSLOT 10
#define SUPERBLOCK_MAGIC "Sony PS2 Memory Card Format "
#define sceMcTypePS1 1
#define sceMcTypePS2 2
#define sceMcResSucceed 0
#define CF_ERASE_ZEROES 0x10
#define FIO_O_RDWR O_RDWR
#define FIO_SEEK_END SEEK_END
#define FIO_SEEK_SET SEEK_SET
#define FIO_SEEK_CUR SEEK_CUR
typedef int16_t s16;typedef uint16_t u16;typedef uint8_t u8;typedef uint32_t u32;
'''+internal[start:end]+r'''
static MCDevInfo mcman_devinfos[1][MCMAN_MAXSLOT];
static int handles,invalidated,cleared,fail_read,fail_write,fail_seek,flush_error,locked,short_io;
static int mcman_mc_port,mcman_mc_slot,mcman_io_sema;
typedef struct {int unit;} MC_IO_FIL_T;
static int iomanX_open(const char *p,int flags,int unused){(void)unused;int fd=open(p,flags);if(fd>=0)handles++;return fd;}
static int iomanX_close(int fd){assert(handles>0);handles--;return close(fd);}
static int iomanX_lseek(int fd,int p,int how){return fail_seek?-EIO:lseek(fd,p,how);}
static int iomanX_read(int fd,void *p,int n){return fail_read?-EIO:read(fd,p,short_io&&n>7?7:n);}
static int iomanX_write(int fd,const void *p,int n){return fail_write?-EIO:write(fd,p,short_io&&n>7?7:n);}
static void mcman_invhandles(int port,int slot){assert(!port&&slot>=0&&slot<MCMAN_MAXSLOT);invalidated++;}
static void mcman_clearcache(int port,int slot){assert(!port&&slot>=0&&slot<MCMAN_MAXSLOT);cleared++;}
static int mcman_setPS1devinfos(int port,int slot);
static int mcman_probePS2Card(int port,int slot);
static int McGetFormat(int port,int slot){return mcman_devinfos[port][slot].cardform;}
static int McFlushCache(int port,int slot){(void)port;(void)slot;return flush_error;}
int mcman_iomanx_backing_commit(int port,int slot);
int mcman_iomanx_backing_umount(int port,int slot);
'''+main[table_start:table_end]+main[checksum_start:checksum_end]+signer+backing+r'''
static int mcman_setPS1devinfos(int port,int slot){
    unsigned char page[128];
    assert(mcman_iomanx_backing_ps1(port,slot));
    assert(!mcman_iomanx_backing_read(port,slot,0,page,NULL)&&!memcmp(page,"MC",2));
    mcman_devinfos[port][slot].cardtype=1;mcman_devinfos[port][slot].cardform=1;return 0;
}
static int mcman_probePS2Card(int port,int slot){
    mcman_devinfos[port][slot].cardtype=2;mcman_devinfos[port][slot].cardform=1;return 0;
}
static void WaitSema(int s){(void)s;assert(!locked);locked=1;}
static void SignalSema(int s){(void)s;assert(locked);locked=0;}
static void mcman_unit2card(int unit){assert(unit>=0&&unit<MCMAN_MAXSLOT);mcman_mc_port=0;mcman_mc_slot=unit;}
static int McGetMcType(int port,int slot){return mcman_devinfos[port][slot].cardtype;}
static int McGetFreeClusters(int port,int slot){(void)port;(void)slot;return 7;}
static int McReadPS1PDACard(int port,int slot,int page,void *buf){return mcman_iomanx_backing_read(port,slot,page,buf,NULL)?-1:0;}
'''+dev[start_dev:end_dev]+r'''
static void make_card(const char *name,const void *header,int header_length,const void *payload,int length){
    FILE *f=fopen(name,"wb");assert(f);
    if(header_length)assert(fwrite(header,1,header_length,f)==(unsigned)header_length);
    assert(fwrite(payload,1,length,f)==(unsigned)length);assert(!fclose(f));
}
static void ps2_card(const char *name,MCDevInfo *super,int stride){
    FILE *f=fopen(name,"wb");assert(f&&fwrite(super,1,sizeof(*super),f)==sizeof(*super));
    assert(!fseek(f,16384*stride-1,SEEK_SET));assert(fputc(0,f)!=EOF);assert(!fclose(f));
}
int main(int argc,char **argv){
    assert(argc==2);chdir(argv[1]);
    unsigned char *raw=calloc(1,131073);memcpy(raw,"MC",2);
    FILE *file=fopen("raw.vmc","wb");assert(file&&fwrite(raw,1,131072,file)==131072);fclose(file);
    file=fopen("bad.vmc","wb");assert(file&&fwrite(raw,1,131073,file)==131073);fclose(file);
    for(int slot=0;slot<2;slot++) {
        assert(!mcman_iomanx_backing_mount(0,slot,"raw.vmc")&&handles==1);
        s16 pagesize;u16 blocksize;int pages;u8 flags;
        assert(!mcman_iomanx_backing_getcardspec(0,slot,&pagesize,&blocksize,&pages,&flags));
        assert(pagesize==128&&pages==1024&&blocksize==64);
        unsigned char data[128];memset(data,0x5a,sizeof(data));
        assert(!mcman_iomanx_backing_write(0,slot,1023,data,NULL));
        memset(data,0,sizeof(data));assert(!mcman_iomanx_backing_read(0,slot,1023,data,NULL)&&data[127]==0x5a);
        assert(mcman_iomanx_backing_read(0,slot,1024,data,NULL));
        assert(mcman_iomanx_backing_write(0,slot,-1,data,NULL));
        fail_write=1;assert(mcman_iomanx_backing_write(0,slot,1,data,NULL));fail_write=0;
        fail_read=1;assert(mcman_iomanx_backing_read(0,slot,1,data,NULL));fail_read=0;
        fail_seek=1;assert(mcman_iomanx_backing_read(0,slot,1,data,NULL));fail_seek=0;
        MC_IO_FIL_T f={slot};VmcInfo info;
        assert(!mc_devctl(&f,"",VMCCTL_GET_INFO,NULL,0,&info,sizeof(info)));
        assert(info.type==1&&info.free_units==7&&info.unit_bytes==8192&&!locked);
        int page=1023;
        assert(!mc_devctl(&f,"",VMCCTL_READ_PS1_PAGE,&page,sizeof(page),data,sizeof(data))&&data[0]==0x5a);
        assert(mc_devctl(&f,"",VMCCTL_GET_INFO,NULL,0,&info,1)==-EINVAL);
        assert(mc_devctl(&f,"",0,NULL,0,NULL,0)==-EINVAL&&!locked);
        page=1024;assert(mc_devctl(&f,"",VMCCTL_READ_PS1_PAGE,&page,sizeof(page),data,sizeof(data))==-EINVAL);
        flush_error=-1;assert(mcman_iomanx_backing_umount(0,slot)<0&&handles==1);
        assert(mcman_iomanx_backing_mount(0,slot,"bad.vmc")<0&&handles==1);
        assert(mcman_iomanx_backing_ps1(0,slot));
        flush_error=0;assert(!mcman_iomanx_backing_umount(0,slot)&&!handles);
        assert(mcman_devinfos[0][slot].cardform==0&&mcman_devinfos[0][slot].cardtype==0);
        assert(mcman_iomanx_backing_mount(0,slot,"bad.vmc")<0&&!handles);
        fail_read=1;assert(mcman_iomanx_backing_mount(0,slot,"raw.vmc")<0&&!handles);fail_read=0;
    }
    assert(mcman_iomanx_backing_mount(0,MCMAN_MAXSLOT,"raw.vmc")==-EOVERFLOW&&!handles);
    assert(mcman_iomanx_backing_mount(0,-1,"raw.vmc")==-EOVERFLOW&&!handles);
    const char *names[]={"card.VMP","card.MCR","card.VM1","card.BIN","card.VmC","card.GME","card.VGS","card.SRM","card.mCd","card.MC2","card.anything"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);i++) {
        make_card(names[i],NULL,0,raw,131072);
        for(int slot=0;slot<2;slot++) {
            assert(!mcman_iomanx_backing_mount(0,slot,names[i])&&mcman_iomanx_backing_ps1(0,slot));
            assert(!mcman_iomanx_backing_umount(0,slot)&&!handles);
        }
    }
    const char *wrapped[]={"wrapped.VGS","wrapped.VMP","wrapped.GME"};
    int offsets[]={64,128,3904};
    for(int kind=0;kind<3;kind++) {
        unsigned char header[3904];memset(header,0xa7,sizeof(header));
        if(kind==0)memcpy(header,"VgsM",4);
        if(kind==1){memcpy(header,"\0PMV",4);header[4]=128;}
        if(kind==2)memcpy(header,"123-456-STD",11);
        make_card(wrapped[kind],header,offsets[kind],raw,131072);
        for(int slot=0;slot<2;slot++) {
            assert(!mcman_iomanx_backing_mount(0,slot,wrapped[kind]));
            assert(mcman_iomanx_backing_ps1(0,slot));
            unsigned char page[128];for(int i=0;i<128;i++)page[i]=(i*13+slot*19)&255;
            assert(!mcman_iomanx_backing_write(0,slot,700,page,NULL));
            memset(page,0,sizeof(page));page[0]=0x51;page[8]=0xff;
            assert(!mcman_iomanx_backing_write(0,slot,1,page,NULL));
            if(kind) {
                fail_read=1;assert(mcman_iomanx_backing_commit(0,slot));fail_read=0;
                fail_write=1;assert(mcman_iomanx_backing_umount(0,slot)<0&&handles==1);fail_write=0;
                fail_seek=1;assert(mcman_iomanx_backing_commit(0,slot));fail_seek=0;
            }
            assert(!mcman_iomanx_backing_commit(0,slot));
            assert(!mcman_iomanx_backing_umount(0,slot)&&!handles);
        }
        // The signer must consume and emit all bytes even with positive short I/O.
        if(kind==1) {
            int fd=iomanX_open(wrapped[kind],O_RDWR,0);assert(fd>=0);short_io=1;
            assert(!vmc_vmp_sign(fd));short_io=0;assert(!iomanX_close(fd));
        }
    }
    MCDevInfo super={0};memcpy(super.magic,SUPERBLOCK_MAGIC,28);super.cardtype=2;
    super.pagesize=512;super.blocksize=16;super.pages_per_cluster=2;super.clusters_per_card=8192;
    file=fopen("ps2.vmc","wb");assert(file&&fwrite(&super,1,sizeof(super),file)==sizeof(super));
    fseek(file,8388607,SEEK_SET);fputc(0,file);fclose(file);
    assert(!mcman_iomanx_backing_mount(0,0,"ps2.vmc")&&!mcman_iomanx_backing_ps1(0,0));
    s16 pagesize;int pages;assert(!mcman_iomanx_backing_getcardspec(0,0,&pagesize,NULL,&pages,NULL));
    assert(pagesize==512&&pages==16384);
    assert(!mcman_iomanx_backing_umount(0,0)&&!handles&&cleared==invalidated);
    const char *ps2_names[]={"ps2.mcd","ps2.MC2","ps2.VMC","ps2.raw","ps2.BIN"};
    unsigned char data[512],spare[16],rdata[512],rspare[16];
    for(unsigned n=0;n<sizeof(ps2_names)/sizeof(ps2_names[0]);n++) {
        ps2_card(ps2_names[n],&super,512);
        for(int slot=0;slot<2;slot++) {
            assert(!mcman_iomanx_backing_mount(0,slot,ps2_names[n])&&!mcman_iomanx_backing_ps1(0,slot));
            for(int i=0;i<512;i++)data[i]=(i*29+slot*3)&255;
            assert(!mcman_iomanx_backing_write(0,slot,16383,data,NULL));
            assert(!mcman_iomanx_backing_read(0,slot,16383,rdata,rspare)&&!memcmp(data,rdata,512));
            assert(mcman_iomanx_backing_write(0,slot,16384,data,NULL));
            assert(!mcman_iomanx_backing_umount(0,slot)&&!handles);
        }
    }
    for(int slot=0;slot<2;slot++) {
        const char *name=slot?"ecc1.MCD":"ecc0.MC2";ps2_card(name,&super,528);
        assert(!mcman_iomanx_backing_mount(0,slot,name)&&!mcman_iomanx_backing_ps1(0,slot));
        for(int page=123;page<=124;page++) {
            for(int i=0;i<512;i++)data[i]=(i*37+(i>>3)+page)&255;
            memset(spare,0xa5,16);memcpy(spare+12,"TAIL",4);
            assert(!mcman_iomanx_backing_write(0,slot,page,data,spare));
            if(page==124){data[177]^=0x69;assert(!mcman_iomanx_backing_write(0,slot,page,data,NULL));}
            assert(!mcman_iomanx_backing_read(0,slot,page,rdata,rspare)&&!memcmp(data,rdata,512));
            assert(!memcmp(rspare+12,"TAIL",4)&&memcmp(rspare,spare,12));
            if(page==123) {
                // A spare-only write retains data, recalculates ECC and updates its tail.
                memcpy(spare+12,"LAST",4);assert(!mcman_iomanx_backing_write(0,slot,page,NULL,spare));
            }
        }
        assert(!mcman_iomanx_backing_umount(0,slot)&&!handles);
    }
    for(int invalid=0;invalid<7;invalid++) {
        MCDevInfo bad=super;
        switch(invalid){case 0:bad.pagesize=528;break;case 1:bad.pages_per_cluster=4;break;
        case 2:bad.clusters_per_card=0;break;case 3:bad.clusters_per_card=0xffffffff;break;
        case 4:bad.blocksize=64;break;case 5:bad.blocksize=3;break;case 6:bad.blocksize=0;break;}
        ps2_card("malformed.vmc",&bad,512);
        assert(mcman_iomanx_backing_mount(0,0,"malformed.vmc")<0&&!handles);
    }
    assert(cleared==invalidated);
    free(raw);puts("PASS: all PS1 containers and arbitrary raw suffixes in both slots, safe wrapper commits, real PS2 ECC writes, malformed geometry, bounded I/O and mount cleanup");
}
'''

with tempfile.TemporaryDirectory(prefix='ps1-vmc-') as folder:
    folder = Path(folder)
    (folder / 'test.c').write_text(code)
    exe = folder / 'test'
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', *flags,
                    '-I', str(root / 'include'), str(folder / 'test.c'), str(root / 'src/save_sign.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder)], check=True, timeout=20)
    for name, offset in [('wrapped.VGS', 64), ('wrapped.VMP', 128), ('wrapped.GME', 3904)]:
        content = (folder / name).read_bytes()
        assert len(content) == 131072 + offset and content[offset:offset+2] == b'MC'
        assert content[offset+700*128:offset+701*128] == bytes((i*13+19)&255 for i in range(128))
        original = bytearray([0xa7]*offset)
        if name.endswith('VGS'):
            original[:4] = b'VgsM'
        elif name.endswith('VMP'):
            original[:4] = b'\0PMV'
            original[4] = 128
            # OpenSSL AES and Python HMAC provide an independent whole-file oracle.
            seed = content[12:28]
            def aes(decrypt):
                return subprocess.run(['openssl', 'enc', '-aes-128-ecb', '-d' if decrypt else '-e',
                                       '-K', 'ab5abc9fc1f49de6a051dbaefa518859', '-nopad', '-nosalt'],
                                      input=seed, stdout=subprocess.PIPE, check=True).stdout
            key = bytes(a ^ b for a,b in zip(aes(True), bytes.fromhex('b30ffeedb7dc5eb7133da60d1b6b2cdc')))
            key += bytes(a ^ b for a,b in zip(aes(False)[:4], content[28:32]))
            unsigned = content[:32] + bytes(20) + content[52:]
            signature = hmac.digest(key, unsigned, hashlib.sha1)
            assert content[32:52] == signature
            original[32:52] = signature
        else:
            original[:11] = b'123-456-STD'
            original[22:37] = content[offset+128:offset+128+1] + bytes(14)
            original[38:53] = content[offset+136:offset+136+1] + bytes(14)
        assert content[:offset] == original, f'{name}: unrelated header bytes changed'

    # Independent parity equations from Ross Ridge's public-domain mymc ECC reference.
    def ecc(block):
        column, even, odd = 0x77, 0x7f, 0x7f
        for i, value in enumerate(block):
            column ^= sum(((value & mask).bit_count() & 1) << j
                          for j, mask in enumerate([0x55,0x33,0x0f,0,0xaa,0xcc,0xf0]))
            if value.bit_count() & 1:
                even ^= ~i
                odd ^= i
        return bytes([column, even & 0x7f, odd])

    for name in ['ecc0.MC2', 'ecc1.MCD']:
        content = (folder / name).read_bytes()
        assert len(content) == 16384*528
        for page in [123,124]:
            data = bytearray((i*37+(i>>3)+page)&255 for i in range(512))
            if page == 124:
                data[177] ^= 0x69
            expected = data + b''.join(ecc(data[i:i+128]) for i in range(0,512,128))
            expected += b'LAST' if page == 123 else b'TAIL'
            assert content[page*528:(page+1)*528] == expected
        assert content[122*528:123*528] == bytes(528)
    print('PASS: independent OpenSSL/Python VMP signature, GME directory tables, untouched headers and PS2 ECC/spare-byte preservation')
