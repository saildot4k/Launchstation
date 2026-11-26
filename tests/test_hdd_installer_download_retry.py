"""Real installer file retries: bounded delays, truncation and failure classes."""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/hdd_install_ps2.c").read_text()


def function(signature):
    a = source.index(signature)
    depth = 0
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[a:], re.S):
        depth += (token.group() == "{") - (token.group() == "}")
        if not depth and token.group() == "}":
            return source[a:a + token.end()] + "\n"
    raise AssertionError(signature)


code = r'''
#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "hdd_install.h"
#include "https_client.h"
#define MAX_PATH 1025
#define FIO_O_WRONLY O_WRONLY
#define FIO_O_CREAT O_CREAT
#define FIO_O_EXCL O_EXCL
#define FIO_O_TRUNC O_TRUNC
static const char *target;
static HddInstall settings;
static int scenario,opens,closes,downloads,seconds,countdowns,retries,last_fd,retryable;
static int genOpen(const char *path,int flags){
 assert(!strcmp(path,"pfs2:/tmp/system.tar.gz"));opens++;
 assert(flags==(O_WRONLY|O_CREAT|((opens>1||settings.resumed)?O_TRUNC:O_EXCL)));
 if(scenario==9)return -ENOSPC;
 int fd=open(target,flags,0600);assert(fd>=0);last_fd=fd;
 struct stat st;assert(!fstat(fd,&st)&&st.st_size==0);return fd;
}
static int genClose(int fd){
 assert(fd==last_fd);closes++;assert(!close(fd));
 if(scenario==10){hddInstallRecoveryObserve(-502);return -502;}
 return scenario==6?-EIO:0;
}
int httpsFailureRetryable(void){return retryable;}
void hddInstallLog(const char *fmt,...){
 char text[512];va_list args;va_start(args,fmt);vsnprintf(text,sizeof(text),fmt,args);va_end(args);
 if(strstr(text,"DOWNLOAD retry")){assert(strstr(text,"system.tar.gz"));retries++;}
}
void hddInstallLogFlush(HddInstall *in){assert(in==&settings);}
void hddInstallProgress(const char *text,int done,int total){
 assert(text&&done>=0&&done<=total);
 if(strstr(text,"Retry")){assert(!done&&!total&&strstr(text,"system.tar.gz"));countdowns++;}
}
void hddInstallOverall(uint64_t done,uint64_t total){assert(done<=total&&total==6);}
static void DelayThread(int usec){assert(usec==1000000);seconds++;}
int httpsDownloadFd(const char *url,int fd,const char *ca,int max,int *size,unsigned char digest[32],
                    HttpsProgressCallback progress,void *context,char *error,int error_size){
 assert(!strcmp(url,"https://example.com/system.tar.gz")&&fd==last_fd&&!strcmp(ca,"ca.pem")&&max==6&&!digest);
 downloads++;*size=0;retryable=0;
 if((scenario==1&&downloads<3)||scenario==3||scenario==6){
  retryable=1;snprintf(error,error_size,"TCP connection");return -1;
 }
 if(scenario==2&&downloads==1){
  assert(write(fd,"old",3)==3);retryable=1;snprintf(error,error_size,"Truncated HTTPS download");return -1;
 }
 if(scenario==4||scenario==5){snprintf(error,error_size,scenario==4?"TLS certificate verification failed":"Could not write downloaded update");return -1;}
 if(scenario==8){hddInstallRecoveryObserve(-502);return -502;}
 const char *body="ABCDEF";*size=scenario==7?5:6;
 assert(write(fd,body,*size)==*size);progress(*size,*size,context);return 0;
}
'''
start = source.index("typedef struct { const char *name;")
code += source[start:source.index("} InstallTransfer;", start) + len("} InstallTransfer;")]
code += function("static int pathJoin(") + function("static void transferProgress(") + function("static int downloadFile(")
code += r'''
int main(int argc,char **argv){
 assert(argc==2);char path[2048],keep[2048],data[16];
 snprintf(keep,sizeof(keep),"%s/completed.elf",argv[1]);int fd=open(keep,O_CREAT|O_WRONLY,0600);assert(fd>=0&&write(fd,"keep",4)==4);close(fd);
 for(scenario=0;scenario<=12;scenario++){
  snprintf(path,sizeof(path),"%s/file-%d",argv[1],scenario);target=path;
  memset(&settings,0,sizeof(settings));strcpy(settings.stage,"pfs2:/tmp");strcpy(settings.ca_path,"ca.pem");settings.downloaded_assets=1u<<HI_MBR;
  opens=closes=downloads=seconds=countdowns=retries=retryable=0;last_fd=-1;
  if(scenario==12){settings.resumed=1;fd=open(target,O_CREAT|O_WRONLY,0600);assert(fd>=0&&write(fd,"old data",8)==8);close(fd);}
  hddInstallRecoveryBegin();InstallTransfer transfer={"system.tar.gz",0,6,6};
  int ret=downloadFile(&settings,"https://example.com/system.tar.gz","system.tar.gz",scenario==11?0:6,&transfer);
  assert(settings.downloaded_assets==(1u<<HI_MBR));
  if(scenario==0||scenario==1||scenario==2||scenario==11||scenario==12){
   assert(!ret&&!settings.error[0]);fd=open(target,O_RDONLY);assert(fd>=0);
   int n=read(fd,data,sizeof(data));close(fd);assert(n==(scenario==11?0:6));if(n)assert(!memcmp(data,"ABCDEF",6));
  }else if(scenario==6||scenario==7)assert(ret==-EIO);
  else if(scenario==8||scenario==10)assert(ret==-502);
  else if(scenario==9)assert(ret==-ENOSPC);
  else assert(ret==-1);
  int attempts=scenario==1||scenario==3?3:scenario==2?2:1;
  assert(opens==attempts&&downloads==(scenario==9||scenario==11?0:attempts));
  assert(closes==(scenario==8||scenario==9?0:attempts));
  assert(seconds==((attempts-1)*2)&&countdowns==seconds&&retries==attempts-1);
  if(scenario==8)assert(!close(last_fd)); /* Simulate releasing it only after reset acknowledgement. */
  hddInstallRecoveryEnd();
  fd=open(keep,O_RDONLY);assert(fd>=0&&read(fd,data,sizeof(data))==4&&!memcmp(data,"keep",4));close(fd);
 }
 puts("PASS: 3 file attempts with 2s delays, partial-file truncation, completed-file retention, and immediate certificate/storage/ATA/size-error stops");
}
'''
with tempfile.TemporaryDirectory(prefix="hdd-download-retry-") as directory:
    d = Path(directory)
    (d / "test.c").write_text(code)
    subprocess.run(["gcc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-I", str(root / "include"),
                    str(d / "test.c"), str(root / "src/hdd_install_recovery.c"), "-o", str(d / "test")], check=True)
    subprocess.run([str(d / "test"), str(d)], check=True, timeout=10)
