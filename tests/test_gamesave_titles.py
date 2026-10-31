"""Read real icon.sys/PSU/PS1 fixtures through the production title reader.

Device adapters model path aliases and short/erroring reads; this is not a
physical-driver test. An optional filer_copy.c path is a negative control.
"""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
source = (Path(sys.argv[1]) if len(sys.argv) > 1 else root / "src/filer_copy.c").read_text()


def function(signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>
#include <unistd.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;
#define MAX_PATH 1024
#define MAX_NAME 256
#define FIO_O_RDONLY O_RDONLY
#define sceMcFileAttrSubdir 0x20
#define DVRP 1
typedef struct { char name[MAX_NAME];unsigned char title[66];struct { int AttrFile; } stats; } FILEINFO;
static int read_cap=4096,handles,read_calls,fail_read,fail_seek,fail_resolve;
static int genFixPath(const char *in,char *out) {
    if(fail_resolve)return -1;
    if(!strncmp(in,"mass:",5))snprintf(out,MAX_PATH,"usb0:%s",in+5);
    else if(!strncmp(in,"mass0:",6))snprintf(out,MAX_PATH,"usb0:%s",in+6);
    else if(!strncmp(in,"uLE:/",5))snprintf(out,MAX_PATH,"mc0:/%s",in+5);
    else if(!strncmp(in,"hdd0:/__common/",15))snprintf(out,MAX_PATH,"pfs4:/%s",in+15);
    else if(!strncmp(in,"hdd1:/__common/",15))snprintf(out,MAX_PATH,"pfs7:/%s",in+15);
    else if(!strncmp(in,"dvr_hdd0:/__xdata/",18))snprintf(out,MAX_PATH,"dvr_pfs1:/%s",in+18);
    else snprintf(out,MAX_PATH,"%s",in);
    return 0;
}
static int getHddParty(const char *p,const FILEINFO *f,char *party,char *dir) {
    char full[MAX_PATH];snprintf(full,sizeof(full),"%s%s%s",p,f->name,f->stats.AttrFile&0x20?"/":"");
    snprintf(party,MAX_NAME,"%s",p);return genFixPath(full,dir);
}
static int mountParty(const char *p) { return p[3]=='1'?7:4; }
static int getHddDVRPParty(const char *p,const FILEINFO *f,char *party,char *dir) { return getHddParty(p,f,party,dir); }
static int mountDVRPParty(const char *p) { (void)p;return 1; }
static int genCmpFileExt(const char *p,const char *ext) { const char *dot=strrchr(p,'.');return dot&&!strcasecmp(dot+1,ext); }
static int genOpen(const char *p,int flags) { int fd=open(p,flags);if(fd>=0)handles++;return fd; }
static int genClose(int fd) { handles--;assert(handles>=0);return close(fd); }
static long long genLseek(int fd,long long off,int whence) { return fail_seek?-EIO:lseek(fd,off,whence); }
static int genRead(int fd,void *p,int n) {
    if(++read_calls==fail_read)return -EIO;
    return read(fd,p,n<read_cap?n:read_cap);
}
'''
psu = (root / "include/psu_types.h").read_text()
code += psu[psu.index("typedef struct"):psu.rindex("#endif")] + "\n"
for signature in ("static int isHddRootPath(", "static int copyReadChunk(",
                  "static void joinIconSysTitleLines(", "int filerGetGameTitle("):
    code += function(signature)
code += r'''
static void put(const char *path,const void *bytes,int size) {
    int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);assert(fd>=0);
    assert(write(fd,bytes,size)==size);assert(!close(fd));
}
static void header(int fd,const char *name,int size,int directory) {
    psu_header h={0};h.attr=directory?0x8427:0x8497;h.size=size;
    snprintf((char *)h.name,sizeof(h.name),"%s",name);assert(write(fd,&h,sizeof(h))==sizeof(h));
}
static void payload(int fd,const char *name,const void *bytes,int size) {
    unsigned char padding[1024]={0};header(fd,name,size,0);
    assert(write(fd,bytes,size)==size);
    int pad=(1024-size%1024)%1024;assert(write(fd,padding,pad)==pad);
}
static void archive(const char *path,const unsigned char *icon) {
    unsigned char data[513]={0};int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);assert(fd>=0);
    header(fd,"SAVE",5,1);header(fd,".",0,1);header(fd,"..",0,1);
    payload(fd,"EMPTY",data,0);payload(fd,"DATA",data,sizeof(data));
    payload(fd,"icon.sys",icon,964);assert(!close(fd));
}
static int title(const char *parent,const char *name,int directory,unsigned char *out) {
    FILEINFO f={0};snprintf(f.name,sizeof(f.name),"%s",name);f.stats.AttrFile=directory?0x20:0;
    read_calls=0;int result=filerGetGameTitle(parent,&f,out);assert(!handles);return result;
}
int main(void) {
    assert(sizeof(psu_header)==512);
    const char *devices[]={"mc0:/","mc1:/","vmc0:/","vmc1:/","usb0:/","usb1:/",
        "ata0:/","ata1:/","mmce0:/","mmce1:/","mx4sio:/","cf0:/","host:/","udpfs:/",
        "pfs4:/","pfs7:/","dvr_pfs1:/","mass:/","mass0:/","uLE:/",
        "hdd0:/__common/","hdd1:/__common/","dvr_hdd0:/__xdata/"};
    unsigned char icon[964]={0},out[66],data[8192]={0};
    memcpy(icon,"PS2D",4);icon[6]=5;memcpy(icon+0xc0,"HelloWorld",11);
    for(unsigned d=0;d<sizeof(devices)/sizeof(devices[0]);d++) {
        char logical[MAX_PATH],physical[MAX_PATH],folder[MAX_PATH],base[MAX_PATH];
        snprintf(logical,sizeof(logical),"%sSAVE/icon.sys",devices[d]);assert(!genFixPath(logical,physical));
        snprintf(base,sizeof(base),"%s",physical);char *colon=strchr(base,':');assert(colon);colon[1]=0;mkdir(base,0700);
        snprintf(folder,sizeof(folder),"%s",physical);*strrchr(folder,'/')=0;mkdir(folder,0700);put(physical,icon,sizeof(icon));
        snprintf(logical,sizeof(logical),"%sSAVE.PSU",devices[d]);assert(!genFixPath(logical,physical));archive(physical,icon);
        const int caps[]={4096,7,1};
        for(unsigned c=0;c<sizeof(caps)/sizeof(caps[0]);c++) {
            read_cap=caps[c];
            int r=title(devices[d],"SAVE",1,out);
            if(r || strcmp((char *)out,"Hello World"))fprintf(stderr,"Folder title failed: %s read cap %d result %d\n",devices[d],read_cap,r);
            assert(!r && !strcmp((char *)out,"Hello World"));
            assert(!title(devices[d],"SAVE.PSU",0,out) && !strcmp((char *)out,"Hello World"));
        }
    }
    read_cap=1;
    memcpy(data,"SC",2);memcpy(data+4,"PS1 Save",9);put("mc0:/PS1.MCS",data,sizeof(data));
    assert(!title("mc0:/","PS1.MCS",0,out) && !strcmp((char *)out,"PS1 Save"));
    /* Missing, invalid, truncated and interrupted reads never leak a title/handle. */
    assert(title("mc0:/","MISSING",1,out)<0 && !out[0]);
    put("mc0:/SAVE/icon.sys",icon,4);assert(title("mc0:/","SAVE",1,out)<0 && !out[0]);
    put("mc0:/SAVE.PSU",icon,4);assert(title("mc0:/","SAVE.PSU",0,out)<0 && !out[0]);
    icon[0]='X';put("mc0:/SAVE/icon.sys",icon,sizeof(icon));archive("mc0:/SAVE.PSU",icon);
    assert(title("mc0:/","SAVE",1,out)<0 && !out[0]);
    assert(title("mc0:/","SAVE.PSU",0,out)<0 && !out[0]);icon[0]='P';
    put("mc0:/SAVE/icon.sys",icon,sizeof(icon));archive("mc0:/SAVE.PSU",icon);
    for(int i=1;i<=8;i++) {
        fail_read=i;assert(title("mc0:/","SAVE",1,out)<0 && !out[0]);
        assert(title("mc0:/","SAVE.PSU",0,out)<0 && !out[0]);
    }
    fail_read=0;fail_seek=1;assert(title("mc0:/","SAVE",1,out)<0 && !out[0]);
    assert(title("mc0:/","SAVE.PSU",0,out)<0 && !out[0]);fail_seek=0;
    fail_resolve=1;assert(title("mc0:/","SAVE",1,out)<0 && !out[0]);fail_resolve=0;
    puts("PASS: actual folder/PSU/PS1 titles, 23 device/alias paths, one-byte reads, line breaks and failure cleanup");
}
'''
with tempfile.TemporaryDirectory(prefix="gamesave-titles-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", "-Wno-format-truncation", str(path / "test.c"), "-o", str(path / "test")], check=True)
    subprocess.run([str(path / "test")], cwd=path, check=True, timeout=15)
