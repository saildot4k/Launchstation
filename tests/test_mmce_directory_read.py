"""Run the MMCE wire reader through the browser's real generic directory reader.

sd2psXtd firmware ps2_mmceman_fs.c reports exhausted sd_iterate_dir as -1;
ps2_mmceman_commands.c sends DREAD packet-1 status 1 for that condition.
Successful packet 4 contains an iterator handle, which may legally be zero.
An optional driver snapshot provides an executable negative control.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
driver = (Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'iop/mmceman/src/mmce_fs.c').read_text()
filer = (root / 'src/filer.c').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


code = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef struct { unsigned mode,attr,size,hisize;u8 ctime[8],atime[8],mtime[8]; } iox_stat_t;
typedef struct { iox_stat_t stat;char name[256]; } iox_dirent_t;
typedef struct { int unit;void *privdata; } iomanX_iop_file_t;
typedef struct { unsigned AttrFile,FileSizeByte,Reserve2;u8 _Create[8],_Modify[8];char EntryName[32]; } sceMcTblGetDir;
typedef struct { char name[256];sceMcTblGetDir stats; } FILEINFO;
#define DPRINTF(...) ((void)0)
#define MMCE_ID 0x8b
#define MMCE_CMD_FS_DREAD 0x4b
#define MMCE_RESERVED 0xff
#define MMCE_REPLY_CONST 0xaa
#define MMCE_FS_MAX_FD 16
#define FIO_S_ISDIR(mode) ((mode)&0x2000)
#define FIO_S_ISREG(mode) ((mode)&0x10)
#define MC_ATTR_norm_folder 0x8427
#define MC_ATTR_norm_file 0x8497
#define sceMcFileAttrSubdir 0x20
#define sceMcFileAttrFile 0x10
static int timeout_1s,locked,stage,entry,total,iterator,status_reply,bad_reply,fail_stage;
static int opens,closes,unit,handle=3,size_valid,time_valid;
static iomanX_iop_file_t card;
static int mmce_fs_update_unit(int n) { assert(n==unit);return 0; }
static void mmce_sio2_lock(void) { assert(!locked);locked=1; }
static void mmce_sio2_unlock(void) { assert(locked);locked=0; }
static int mmce_sio2_tx_rx_pio(u8 tx,u8 rx,const void *in,void *out,void *timeout) {
    assert(locked&&timeout==&timeout_1s);stage++;
    if(stage==fail_stage)return -1;
    memset(out,0,rx);u8 *reply=out;
    if(stage==1) {
        assert(tx==5&&rx==5&&in&&((const u8 *)in)[3]==handle);
        assert(((const u8 *)in)[0]==0x8b&&((const u8 *)in)[1]==0x4b&&((const u8 *)in)[2]==0xff);
        reply[1]=bad_reply?0:MMCE_REPLY_CONST;
        reply[4]=status_reply?status_reply:entry==total?1:0;
    } else if(stage==2) {
        assert(!tx&&rx==42&&!in);reply[4]=0x10;reply[12]=64;reply[41]=8;
    } else if(stage==3) {
        assert(!tx&&rx==8&&!in);memcpy(reply,entry?"B.ELF\0\0\0":"A.ELF\0\0\0",8);
    } else {
        assert(stage==4&&!tx&&rx==3&&!in);reply[1]=iterator;entry++;
    }
    return 0;
}
'''
code += function(driver, 'int mmce_fs_dread(')
code += r'''
static int fileXioDopen(const char *path) {
    assert(!strcmp(path,unit?"mmce1:/":"mmce0:/"));
    card.unit=unit;card.privdata=&handle;opens++;entry=0;return 7;
}
static int fileXioDread(int fd,iox_dirent_t *out) {
    assert(fd==7&&!locked);stage=0;return mmce_fs_dread(&card,out);
}
static int fileXioDclose(int fd) { assert(fd==7&&!locked);closes++;return 0; }
static void clearMcTable(sceMcTblGetDir *s) { memset(s,0,sizeof(*s)); }
'''
code += function(filer, 'int readGENERIC(const char *path, FILEINFO *info, int max)\n{')
code += r'''
int main(void) {
    FILEINFO files[4];iox_dirent_t dirent;
    for(unit=0;unit<2;unit++) {
        const char *path=unit?"mmce1:/":"mmce0:/";
        for(total=0;total<=2;total++)for(iterator=0;iterator<16;iterator++) {
            memset(files,0xa5,sizeof(files));
            assert(readGENERIC(path,files,4)==total);
            assert(opens==closes&&!locked);
            if(total)assert(!strcmp(files[0].name,"A.ELF")&&files[0].stats.FileSizeByte==64);
            if(total==2)assert(!strcmp(files[1].name,"B.ELF"));
        }
        total=2;iterator=4;
        for(fail_stage=1;fail_stage<=4;fail_stage++) {
            assert(readGENERIC(path,files,4)<0&&opens==closes&&!locked);
        }
        fail_stage=0;bad_reply=1;
        assert(readGENERIC(path,files,4)<0&&!locked);bad_reply=0;
        status_reply=2;assert(readGENERIC(path,files,4)<0&&!locked);status_reply=0;
        iterator=16;assert(readGENERIC(path,files,4)<0&&!locked);
        /* The firmware's iterator handle is not an entry count. */
        iterator=0;assert(readGENERIC(path,files,1)==1&&entry==1);
        /* Invalid local handles must not be mistaken for firmware EOF. */
        card.privdata=NULL;stage=0;
        assert(mmce_fs_dread(&card,&dirent)<0&&!stage&&!locked);
        card.privdata=&handle;int saved=handle;handle=-1;
        assert(mmce_fs_dread(&card,&dirent)<0&&!stage&&!locked);handle=saved;
    }
    puts("PASS: both MMCE slots retain complete/empty listings at firmware EOF, accept iterator zero and preserve transport/protocol errors");
}
'''
compiler = shutil.which('gcc') or shutil.which('clang')
assert compiler, 'Host C compiler required'
with tempfile.TemporaryDirectory(prefix='mmce-directory-') as folder:
    folder = Path(folder)
    source, binary = folder / 'test.c', folder / 'test'
    source.write_text(code)
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror',
                    str(source), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=10, cwd=folder)
