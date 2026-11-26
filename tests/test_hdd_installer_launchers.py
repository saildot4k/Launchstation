"""Exercise production launcher discovery/downloads with a local HTTPS facade."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
native = (root / "src/hdd_install_ps2.c").read_text()


def function(signature, source=native):
    start = source.index(signature)
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[start:], re.S):
        depth += (token.group() == "{") - (token.group() == "}")
        if not depth and token.group() == "}":
            return source[start:start + token.end()] + "\n"
    raise AssertionError(signature)


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
#include <unistd.h>
#include "hdd_install.h"
#include "https_client.h"
#include "save_sign.h"
#define MAX_PATH 1025
#define FIO_O_RDONLY O_RDONLY
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_EXCL O_EXCL
#define FIO_O_TRUNC O_TRUNC
typedef int64_t s64;
typedef uint64_t u64;
static const char *work, *failure;
static unsigned requests, downloads, read_bytes;
static int migration;
static uint64_t overall_bytes, overall_total;
int httpsFailureRetryable(void){return 0;}
static void DelayThread(int us){(void)us;assert(0);}
int hddInstallResumeSave(HddInstall *in){assert(in);return 0;}
void hddInstallLog(const char *fmt, ...) { assert(fmt); }
void hddInstallLogFlush(HddInstall *in) { assert(in); }
void httpsSetCaBundle(const unsigned char *data,unsigned size) { (void)data;(void)size; }
void hddInstallStatus(const char *s, int done, int total) { assert(s && done >= 0 && total >= 0); }
void hddInstallProgress(const char *s, int done, int total) { hddInstallStatus(s,done,total); }
void hddInstallOverall(uint64_t done,uint64_t total) { assert(total&&done>=overall_bytes&&done<=total);overall_bytes=done;overall_total=total; }
static int genOpen(const char *p, int mode) {
    char path[2048]; assert(!strncmp(p,"pfs2:/stage/",12));
    snprintf(path,sizeof(path),"%s/stage/%s",work,p+12); return open(path,mode,0600);
}
static int makeDirectory(const char *p,int visible){
 char path[2048];struct stat st;assert(!visible&&!strncmp(p,"pfs2:/stage",11));
 if(!strcmp(failure,"mkdir"))return -EIO;
 snprintf(path,sizeof(path),"%s/stage%s",work,p+11);
 if(!mkdir(path,0700))return 0;
 return errno==EEXIST&&!stat(path,&st)&&S_ISDIR(st.st_mode)?0:-EIO;
}
static int genRemove(char *p){char path[2048];assert(!strncmp(p,"pfs2:/stage/",12));snprintf(path,sizeof(path),"%s/stage/%s",work,p+12);return unlink(path)<0?-errno:0;}
static int fileXioRename(const char *from,const char *to){
 char a[2048],b[2048];assert(!strncmp(from,"pfs2:/stage/",12)&&!strncmp(to,"pfs2:/stage/",12));
 if(migration&&!strcmp(failure,"legacy-rename"))return -EIO;
 snprintf(a,sizeof(a),"%s/stage/%s",work,from+12);snprintf(b,sizeof(b),"%s/stage/%s",work,to+12);
 return rename(a,b)<0?-errno:0;
}
static int genRead(int fd, void *data, unsigned n) { int r=read(fd,data,n > 97 ? 97 : n);if(r>0)read_bytes+=r;return r; }
static int genWrite(int fd, const void *data, unsigned n) { return write(fd,data,n > 31 ? 31 : n); }
#define genLseek lseek
#define genClose close
static char *load(const char *path, int *size) {
    FILE *f=fopen(path,"rb");char *data;long n;
    if(!f)return NULL;assert(!fseek(f,0,SEEK_END));n=ftell(f);rewind(f);assert(n>=0&&n<65536);
    data=malloc(n+1);assert(data&&fread(data,1,n,f)==(size_t)n);data[n]=0;fclose(f);*size=n;return data;
}
int httpsRequest(const char *method,const char *host,const char *url,const char *headers,
                 const void *body,int body_size,const char *ca,HttpsResponse *response,char *error,int error_size) {
    const char *begin=strstr(url,"/contents/"),*end=strchr(url,'?');char path[2048];int n;
    (void)error;(void)error_size;
    assert(!strcmp(method,"GET")&&!strcmp(host,"api.github.com")&&headers&&!body&&!body_size&&ca&&begin&&end);
    assert(!strcmp(end,"?ref=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"));requests++;
    if(!strcmp(failure,"request"))return -EIO;
    begin+=10;n=end-begin;snprintf(path,sizeof(path),"%s/api/%.*s.json",work,n,begin);
    response->body=load(path,&response->body_len);response->status=response->body?200:404;return 0;
}
void httpsResponseFree(HttpsResponse *r) { free(r->body);memset(r,0,sizeof(*r)); }
int httpsDownloadFd(const char *url,int fd,const char *ca,int maximum,int *size,unsigned char digest[32],
                    HttpsProgressCallback progress,void *context,char *error,int error_size) {
    const char prefix[]="https://raw.githubusercontent.com/" HDD_INSTALL_REPOSITORY "/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/";
    char path[2048];unsigned char buffer[71];FILE*f;size_t n;
    assert(!strncmp(url,prefix,sizeof(prefix)-1)&&ca&&maximum>0&&!digest&&progress);(void)error;(void)error_size;
    downloads++;*size=0;
    if(!strcmp(failure,"write"))return -EIO;
    if(!strncmp(failure,"resume",6)&&downloads==3){
        assert(genWrite(fd,"unfinished",10)==10);hddInstallRecoveryObserve(-502);return -502;
    }
    snprintf(path,sizeof(path),"%s/remote/%s",work,url+sizeof(prefix)-1);f=fopen(path,"rb");assert(f);
    while((n=fread(buffer,1,sizeof(buffer),f))){
        for(unsigned offset=0;offset<n;){int w=genWrite(fd,buffer+offset,n-offset);assert(w>0);offset+=w;}
        *size+=n;progress(*size,maximum,context);
    }
    fclose(f);if(!strcmp(failure,"truncated"))(*size)--;return 0;
}
'''
start = native.index("static const char *const launcher_required[]")
code += native[start:native.index("static int launcherManifest(", start)]
for signature in ("static int pathJoin(", "static int readAll(", "static int closeResult(",
                  "static int checkFileSize(", "static int launcherStageName(", "static void legacyLauncherStageName(", "static int makeParents(char *path)\n{", "static int findLauncher(",
                  "static const char *launcherIcon(", "static const char *launcherArt(", "static int launcherManifest(", "static int checkLaunchers("):
    code += function(signature)
start = native.index("typedef struct { const char *name;")
end = native.index("static void installerHttpsStatus(", start)
# Capacity preflight has its own storage tests; this facade exercises downloads.
section = native[start:end]
section = section.replace(function("static int stageSpace(").rstrip(), "")
code += section
code += r'''
int main(int argc,char **argv) {
    HddInstall in={.flags=7,.jail=1,.owned=1};const char *phase="metadata";int ret;
    assert(argc==4);work=argv[1];failure=argv[2];in.game_launcher=atoi(argv[3]);
    strcpy(in.stage,"pfs2:/stage");strcpy(in.ca_path,"fixture.pem");memset(in.commit,'a',40);
    ret=launcherMetadata(&in);
    if(ret>=0)ret=prepareLauncherStage(&in);
    if(!strncmp(failure,"resume",6))hddInstallRecoveryBegin();
    if(ret>=0)ret=downloadLaunchers(&in,&phase,0,downloadBytes(&in));
    int resuming=!strncmp(failure,"resume",6), corrupt_cache=!strcmp(failure,"resume-corrupt");
    if(resuming){
        assert(ret==-502&&in.downloaded_launchers==2&&hddInstallRecoveryFault()==-502);
        hddInstallRecoveryEnd();in.recovery_attempts=1;in.owned=1;overall_bytes=0;
        if(corrupt_cache){int fd=genOpen("pfs2:/stage/OPL/OPNPS2LD.ELF",FIO_O_WRONLY|FIO_O_TRUNC);assert(fd>=0);close(fd);}
        unsigned saved_requests=requests;
        hddInstallRecoveryBegin();ret=downloadLaunchers(&in,&phase,0,downloadBytes(&in));
        assert(!hddInstallRecoveryFault()&&requests==saved_requests&&in.downloaded_launchers==in.launcher_count);
        hddInstallRecoveryEnd();
    }
    int legacy=!strncmp(failure,"legacy",6);
    if(legacy){
        assert(!ret);unsigned before=downloads;
        for(unsigned i=0;i<in.launcher_count;i++){
            char name[192],from[1200],to[1200];assert(!launcherStageName(in.launcher_files[i].path,name));
            snprintf(from,sizeof(from),"pfs2:/stage/%s",name);snprintf(to,sizeof(to),"pfs2:/stage/launcher-%03u.bin",i);
            assert(!fileXioRename(from,to));
        }
        if(!strcmp(failure,"legacy-partial")){
            int fd=genOpen("pfs2:/stage/OPL/OPNPS2LD.ELF",FIO_O_WRONLY|FIO_O_CREAT);assert(fd>=0);assert(write(fd,"partial",7)==7);close(fd);
        }
        in.resumed=1;migration=1;ret=prepareLauncherStage(&in);
        if(!strcmp(failure,"legacy-rename")){assert(ret==-EIO);free(in.launcher_files);return 0;}
        assert(!ret);overall_bytes=0;
        ret=downloadLaunchers(&in,&phase,0,downloadBytes(&in));assert(!ret&&downloads==before);
        for(unsigned i=0;i<in.launcher_count;i++){
            char old[64];snprintf(old,sizeof(old),"pfs2:/stage/launcher-%03u.bin",i);assert(genOpen(old,FIO_O_RDONLY)<0);
        }
    }
    assert((ret==0)==(!strcmp(failure,"ok")||!strcmp(failure,"hash-ignored")||resuming||legacy));
    unsigned nonempty=0;for(unsigned i=0;i<in.launcher_count;i++)nonempty+=!!in.launcher_files[i].size;
    if(!ret){assert(in.launcher_count>=15&&downloads==nonempty+resuming+2*corrupt_cache&&requests>=8&&read_bytes==(legacy?6u:3u)*52);
             assert(overall_bytes==downloadBytes(&in)&&overall_total==overall_bytes);
             assert(findLauncher(&in,launcherIcon(&in))>=0&&findLauncher(&in,launcherArt(&in))>=0);}
    free(in.launcher_files);return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="hdd-installer-launchers-") as directory:
    d = Path(directory)
    (d / "test.c").write_text(code)
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-Wno-misleading-indentation",
                    "-fsanitize=undefined", "-I", str(root / "include"), str(d / "test.c"),
                    str(root / "src/hdd_install_plan.c"), str(root / 'src/hdd_install_recovery.c'), str(root / "src/save_sign.c"), "-o", str(d / "test")], check=True)
    elf = bytearray(120)
    elf[:6] = b"\x7fELF\x01\x01"
    elf[18] = 8
    files = {"scripts/assets/OPL/OPNPS2LD.ELF": bytes(elf), "scripts/assets/NHDDL/nhddl.elf": bytes(elf),
             "scripts/assets/neutrino/neutrino.elf": bytes(elf), "scripts/assets/OPL/version.txt": b"OPL",
             "scripts/assets/NHDDL/version.txt": b"NHDDL", "scripts/assets/neutrino/version.txt": b"Neutrino",
             "scripts/assets/OPL/LNG/lang_French.lng": b"translation", "scripts/assets/neutrino/config/system.toml": b"config",
             "scripts/assets/neutrino/modules/ata_bd.irx": b"IRX runtime", "scripts/assets/neutrino/udpfs_server/compressed_iso/__init__.py": b"helper",
             "scripts/assets/neutrino/udpfs_server/compressed_iso/empty.py": b"",
             **{f"scripts/licenses/{name}": b"license" for name in ("OPL", "nhddl", "neutrino")},
             **{f"icons/{kind}/APP_{app}{suffix}": b"icon" for app in ("OPL", "NHDDL")
                for kind, suffix in (("art", ".png"), ("ico", "_LST.ico"))}}
    for choice in (0, 1):
        for failure in ("ok", "hash-ignored", "resume", "resume-corrupt", "truncated", "request", "write", "missing", "duplicate", "symlink", "traversal", "oversize", "file-limit", "directory-limit", "mkdir", "legacy", "legacy-partial", "legacy-rename"):
            work = d / f"{choice}-{failure}"
            (work / "stage").mkdir(parents=True)
            listings = {path: [] for path in ("scripts/assets/OPL", "scripts/assets/NHDDL", "scripts/assets/neutrino", "icons/art", "icons/ico", "scripts/licenses")}
            def ensure_directory(parent):
                if parent in listings:
                    return
                ancestor = str(Path(parent).parent)
                ensure_directory(ancestor)
                listings[parent] = []
                listings[ancestor].append({"name": Path(parent).name, "type": "dir", "size": 0, "sha": "a" * 40})
            for remote, data in files.items():
                if failure == "missing" and remote.endswith("neutrino.elf"):
                    continue
                path = work / "remote" / remote
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                parent = str(Path(remote).parent)
                ensure_directory(parent)
                listings[parent].append({"name": Path(remote).name, "type": "file", "size": len(data),
                                         "sha": "b"*40 if failure=="hash-ignored" else hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
            if failure in ("duplicate", "symlink", "traversal", "oversize"):
                entry = dict(listings["scripts/assets/OPL"][0])
                if failure == "symlink": entry["type"] = "symlink"
                if failure == "traversal": entry["name"] = "../escape"
                if failure == "oversize": entry["size"] = 16 * 1024 * 1024 + 1
                listings["scripts/assets/OPL"].append(entry)
            if failure in ("file-limit", "directory-limit"):
                count = 161 if failure == "file-limit" else 16
                listings["scripts/assets/OPL"].extend({"name": f"extra-{i}", "type": "file" if failure == "file-limit" else "dir",
                                                       "size": 1, "sha": "c" * 40} for i in range(count))
            for parent, entries in listings.items():
                path = work / "api" / (parent + ".json")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(entries))
            subprocess.run([str(d / "test"), str(work), failure, str(choice)], check=True, timeout=10)
            if failure in ('ok', 'hash-ignored', 'resume', 'resume-corrupt', 'legacy', 'legacy-partial'):
                assert not list((work / 'stage').glob('launcher-*.bin'))
                for remote, payload in files.items():
                    if remote.startswith('icons/') and f'APP_{"NHDDL" if choice else "OPL"}' not in remote:
                        continue
                    if remote.startswith('scripts/assets/'):
                        relative = remote[len('scripts/assets/'):]
                        if relative.startswith('neutrino/'):
                            relative = 'Neutrino/' + relative[len('neutrino/'):]
                    elif remote.startswith('scripts/licenses/'):
                        relative = 'Licenses/' + remote[len('scripts/licenses/'):]
                    else:
                        relative = 'Icons/' + remote[len('icons/'):]
                    assert (work / 'stage' / relative).read_bytes() == payload
    print("PASS: pinned launcher discovery, both defaults, size/header checks without content hashing, short I/O, download errors and bounded/restricted metadata")
    # Run the actual PATINFO writer, including the optional NHDDL argument,
    # against a raw-write facade that only inspects memory.
    header = (root / "src/hdd_header_injector.c").read_text()
    header_code = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "hdd_header_injector.h"
typedef uint32_t u32;
typedef struct { unsigned mode,private_5; } iox_stat_t;
#define MAX_NAME 32
#define APA_TYPE_PFS 0x100
#define HDIOC_FLUSH 1
'''
    header_code += "\n".join(re.findall(r"^#define APA_HEADER_.*$", header, re.M)) + "\n"
    a = header.index("enum HddHeaderFileKind {")
    b = header.index("} HddHeaderFileSpec;", a) + len("} HddHeaderFileSpec;")
    header_code += header[a:b] + "\n"
    a = header.index("static const HddHeaderFileSpec hdd_header_files[")
    header_code += header[a:header.index("};", a) + 2] + "\n"
    header_code += r'''
static unsigned char hdd_header_buffer[APA_HEADER_SIZE];
static int writes,flushes,write_error;
static const char *expected;
static int hddHeaderBuildPartitionPath(char *p,unsigned size,const char *name){return snprintf(p,size,"hdd0:%s",name)>=(int)size?-EINVAL:0;}
static int fileXioGetStat(const char*p,iox_stat_t*s){assert(!strcmp(p,"hdd0:PP.LAUNCHER"));s->mode=APA_TYPE_PFS;s->private_5=262144;return 0;}
static int hddHeaderWriteRawRange(u32 lba,u32 offset,const void *data,u32 size){
 assert(lba==262144&&offset==0x1000&&data==hdd_header_buffer+offset&&size==0x800+4);writes++;
 assert(!strncmp((char*)data,"PS2ICON3D",9));
 u32 bytes;memcpy(&bytes,hdd_header_buffer+0x1014,4);assert(bytes<512);
 assert(!memcmp(hdd_header_buffer+0x1200,expected,bytes)&&bytes==strlen(expected));
 assert(!memcmp(hdd_header_buffer+0x1800,"ICON",4));return write_error;
}
static int fileXioDevctl(const char*p,int command,const void*in,int size,void*out,int outsize){
 assert(!strcmp(p,"hdd0:")&&command==HDIOC_FLUSH&&!in&&!size&&!out&&!outsize);flushes++;return 0;
}
'''
    header_code += function("int InjectHddAppLauncher(", header) + function("int InjectHddAppLauncherWithArg(", header)
    header_code += r'''
int main(void){
 const char*elf="hdd0:__system:pfs:/launcher/nhddl.elf";
 expected="BOOT2 = PATINFO\nHDDUNITPOWER = NICHDD\npath = hdd0:__system:pfs:/launcher/nhddl.elf\narg = -mode=ata\n";
 assert(!InjectHddAppLauncherWithArg("PP.LAUNCHER",elf,"NHDDL","ICON",4,"-mode=ata")&&writes==1&&flushes==1);
 expected="BOOT2 = PATINFO\nHDDUNITPOWER = NICHDD\npath = hdd0:__system:pfs:/launcher/nhddl.elf\n";
 assert(!InjectHddAppLauncher("PP.LAUNCHER",elf,"NHDDL","ICON",4)&&writes==2&&flushes==2);
 assert(InjectHddAppLauncherWithArg("PP.LAUNCHER",elf,"NHDDL","ICON",4,"-mode=ata\npath=bad")==-EINVAL&&writes==2);
 char large[600];memset(large,'a',599);large[599]=0;
 assert(InjectHddAppLauncherWithArg("PP.LAUNCHER",elf,"NHDDL","ICON",4,large)==-ENAMETOOLONG&&writes==2);
 write_error=-EIO;assert(InjectHddAppLauncher("PP.LAUNCHER",elf,"NHDDL","ICON",4)==-EIO&&writes==3&&flushes==2);
 puts("PASS: production PATINFO includes the NHDDL ATA argument, preserves icon metadata and rejects invalid/oversized arguments and raw-write failures");
}
'''
    (d / "header.c").write_text(header_code)
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-I", str(root / "include"),
                    str(d / "header.c"), "-o", str(d / "header")], check=True)
    subprocess.run([str(d / "header")], check=True, timeout=10)
