"""Run the real UDPFS initializer/reader with directory RPC failures."""
from source_groups import component_source
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'src/filer.c').read_text()

def function(signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

code = r'''
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#define FIO_S_IFDIR 0x2000
#define MAX_PATH 1025
#define FIO_S_ISDIR(mode) ((mode) & FIO_S_IFDIR)
#define FIO_S_ISREG(mode) (!FIO_S_ISDIR(mode))
#define DPRINTF(...) ((void)0)
#define sceMcFileAttrExists 0x8000
#define sceMcFileAttrSubdir 0x20
#define sceMcFileAttrFile 0x10
typedef unsigned short u16;
#define MC_ATTR_norm_file 0x8497
#define MC_ATTR_norm_folder 0x8427
typedef struct { unsigned mode,size,hisize,private_0,private_1,private_2;char ctime[8],mtime[8]; } Stat;
typedef struct { char name[64];Stat stat; } iox_dirent_t;
typedef struct { unsigned AttrFile,FileSizeByte,Reserve1,Reserve2;char _Create[8],_Modify[8],EntryName[32]; } McStat;
typedef struct { char name[64];McStat stats; } FILEINFO;
static int host_error,host_elflist,host_ready,udpfs_dir_open_failed,size_valid,time_valid;
static int loaded=1,opens,closes,reads,fail_open_call,fail_close_call,fail_read_at=-1;
static int entries=4;
static int load_udpfs(void){host_ready=host_error=0;host_elflist=99;return loaded;}
static int fileXioDopen(const char *path){assert(!strncmp(path,"udpfs:/",7)||!strncmp(path,"vmc0:/",6));return ++opens==fail_open_call?-ENOENT:opens-1;}
static int fileXioDclose(int fd){assert(fd>=0);return ++closes==fail_close_call?-EIO:0;}
static int fileXioDread(int fd,iox_dirent_t *out){
 const char *names[]={".","..","BOOT.ELF","NESTED"};assert(fd>=0);
 if(reads==fail_read_at)return -ETIMEDOUT;
 if(reads==entries)return 0;
 memset(out,0,sizeof(*out));strcpy(out->name,names[reads]);
 out->stat.mode=reads!=2?FIO_S_IFDIR:0;out->stat.size=37;reads++;return 1;
}
static void clearMcTable(McStat *s){memset(s,0,sizeof(*s));}
'''
code += function('static int initUDPFS(' if 'static int initUDPFS(' in source else 'static void initUDPFS(') + '\n' + function('int readUDPFS(')
code += function('int readGENERIC(const char *path, FILEINFO *info, int max)\n{') + function('int readVMC(')
code += r'''
static void reset(void){loaded=1;opens=closes=reads=fail_open_call=fail_close_call=host_error=0;fail_read_at=-1;entries=4;}
int main(void){
 FILEINFO info[6];
 reset();assert(readUDPFS("udpfs:/folder/",info,4)==2);
 assert(!strcmp(info[0].name,"BOOT.ELF")&&info[0].stats.FileSizeByte==37);
 assert(!strcmp(info[1].name,"NESTED")&&info[1].stats.AttrFile==MC_ATTR_norm_folder);
 assert(opens==2&&closes==2&&!host_error&&!udpfs_dir_open_failed&&host_ready&&!host_elflist);
 reset();entries=0;assert(!readUDPFS("udpfs:/folder/",info,4));assert(closes==2);
 reset();fail_open_call=1;assert(readUDPFS("udpfs:/folder/",info,4)==-ENOENT);assert(!closes&&udpfs_dir_open_failed);
 reset();fail_open_call=2;assert(readUDPFS("udpfs:/folder/",info,4)==-ENOENT);assert(closes==1&&udpfs_dir_open_failed);
 reset();loaded=0;assert(readUDPFS("udpfs:/folder/",info,4)==-ENODEV);assert(!opens&&udpfs_dir_open_failed&&host_error);
 reset();fail_close_call=1;assert(readUDPFS("udpfs:/folder/",info,4)==-EIO);assert(opens==1&&closes==1);
 reset();fail_read_at=0;assert(readUDPFS("udpfs:/folder/",info,4)==-ETIMEDOUT);assert(closes==2);
 reset();fail_read_at=3;assert(readUDPFS("udpfs:/folder/",info,4)==-ETIMEDOUT);assert(closes==2); /* partial list rejected */
 reset();fail_close_call=2;assert(readUDPFS("udpfs:/folder/",info,4)==-EIO);assert(closes==2);
 reset();fail_read_at=3;fail_close_call=2;assert(readUDPFS("udpfs:/folder/",info,4)==-ETIMEDOUT);
 reset();assert(readUDPFS("udpfs:/folder/",info,1)==1);assert(reads==3&&closes==2); /* retain browser cap */
 reset();assert(readGENERIC("udpfs:/folder/",info,4)==2);assert(opens==1&&closes==1);
 reset();entries=0;assert(!readGENERIC("udpfs:/folder/",info,4)&&closes==1);
 reset();fail_open_call=1;assert(readGENERIC("udpfs:/folder/",info,4)==-ENOENT&&!closes);
 reset();fail_read_at=0;assert(readGENERIC("udpfs:/folder/",info,4)==-ETIMEDOUT&&closes==1);
 reset();fail_read_at=3;assert(readGENERIC("udpfs:/folder/",info,4)==-ETIMEDOUT&&closes==1);
 reset();fail_close_call=1;assert(readGENERIC("udpfs:/folder/",info,4)==-EIO&&closes==1);
 reset();fail_read_at=3;fail_close_call=1;assert(readGENERIC("udpfs:/folder/",info,4)==-ETIMEDOUT);
 reset();assert(readGENERIC("udpfs:/folder/",info,1)==1&&reads==3&&closes==1);
 reset();assert(readVMC("vmc0:/folder/",info,4)==2&&opens==1&&closes==1);
 reset();entries=0;assert(!readVMC("vmc0:/folder/",info,4)&&closes==1);
 reset();fail_open_call=1;assert(readVMC("vmc0:/folder/",info,4)==-ENOENT&&!closes);
 reset();fail_read_at=3;assert(readVMC("vmc0:/folder/",info,4)==-ETIMEDOUT&&closes==1);
 reset();fail_close_call=1;assert(readVMC("vmc0:/folder/",info,4)==-EIO&&closes==1);
 puts("PASS: generic storage and VMC readers reject failed opens, partial reads and failed closes while preserving empty/capped browser listings");
 puts("PASS: UDPFS empty versus failed/partial listing, exact errors and closed directory handles");
}
'''
# Bind the negative reader result to its callers: transfer/delete abort, while
# the classic browser keeps its parent row and never sorts with a negative count.
assert 'n = readUDPFS(path, info, max);' in function('int getDir(')
assert 'if (nfiles < 0) return copyDiagFail(nfiles);' in (root / 'src/filer_copy.c').read_text()
actions = component_source('src/filer_actions.c')
delete = actions[actions.index('int delete ('):actions.index('int Rename(')]
with tempfile.TemporaryDirectory(prefix='udpfs-dir-') as folder:
    path = Path(folder)
    (path / 'test.c').write_text(code)
    cc = shutil.which('gcc') or shutil.which('cc')
    if not cc:
        raise SystemExit('Host C compiler required')
    exe = path / 'test'
    subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Werror', str(path / 'test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
assert 'nfiles = getDir(path, &files[1]);\n\t\tif (nfiles < 0) nfiles = 0;\n\t\tnfiles++;' in source
assert 'filerWalkTree(path, file, deleteTreeEntry, NULL)' in delete
assert 'if (count < 0) return count;' in (root / 'src/filer_tree.c').read_text()
