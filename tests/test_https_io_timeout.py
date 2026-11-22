"""Real TLS BIO/retry code times out when readiness never produces bytes."""
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
s=(root/'src/https_client.c').read_text()
def function(signature):
    a=s.index(signature);b=s.index('{',a)+1;depth=1
    while depth: depth+=(s[b]=='{')-(s[b]=='}');b+=1
    return s[a:b]+'\n'
code=r'''
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
typedef uint64_t u64;
typedef struct {int sock;u64 wait_started;int waiting;} HttpsTls;
#define HTTPS_IO_TIMEOUT_MS 15000
#define MBEDTLS_ERR_SSL_WANT_READ -10
#define MBEDTLS_ERR_SSL_WANT_WRITE -11
static u64 now;
static int polls,timeout_arg,last_write,moved,ready=1;
static u64 Timer(void){return now;}
static int socket_wait(int sock,int write,int timeout){assert(sock==42&&timeout>0&&timeout<=15000);polls++;timeout_arg=timeout;last_write=write;return ready;}
static int ps2ipc_send(int sock,const unsigned char*p,int n,int flags){assert(sock==42&&p&&n>0&&!flags);return moved?1:-1;}
static int ps2ipc_recv(int sock,unsigned char*p,int n,int flags){assert(sock==42&&p&&n>0&&!flags);return moved?1:-1;}
'''
code+='\n'.join(function(x) for x in ('static int ps2_tls_send(','static int ps2_tls_recv(','static int wait_tls_io('))
code+=r'''
int main(void){
 HttpsTls tls={.sock=42};unsigned char byte=0;
 assert(ps2_tls_recv(&tls,&byte,1)==MBEDTLS_ERR_SSL_WANT_READ);
 assert(!wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)&&polls==1&&timeout_arg==15000&&!last_write);
 now=5000;assert(ps2_tls_recv(&tls,&byte,1)==MBEDTLS_ERR_SSL_WANT_READ);
 assert(!wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)&&timeout_arg==10000);
 now=15000;assert(wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)<0&&polls==2);
 moved=1;assert(ps2_tls_recv(&tls,&byte,1)==1&&!tls.waiting);moved=0;
 now=20000;assert(!wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)&&timeout_arg==15000);
 now=35000;assert(wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)<0);
 moved=1;assert(ps2_tls_send(&tls,&byte,1)==1&&!tls.waiting);moved=0;
 now=40000;assert(ps2_tls_send(&tls,&byte,1)==MBEDTLS_ERR_SSL_WANT_WRITE);
 assert(!wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_WRITE)&&last_write&&timeout_arg==15000);
 now=55000;assert(wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_WRITE)<0);
 tls.waiting=0;ready=0;assert(wait_tls_io(&tls,MBEDTLS_ERR_SSL_WANT_READ)<0);
 puts("PASS: ready-but-no-data sockets hit a 15s idle deadline; only real send/receive progress resets it");
}
'''
with tempfile.TemporaryDirectory(prefix='https-idle-') as directory:
 d=Path(directory);(d/'check.c').write_text(code)
 subprocess.run(['gcc','-std=c99','-Wall','-Wextra','-Werror',str(d/'check.c'),'-o',str(d/'check')],check=True)
 subprocess.run([str(d/'check')],check=True,timeout=5)
