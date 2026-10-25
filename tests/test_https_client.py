"""Exercise updater HTTPS framing/redirects after removing the Drive transport.

Compile the production request and streaming functions with deterministic TLS
and storage peers. Actual certificates and console RPCs need hardware testing.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
http = (root / 'src/https_client.c').read_text()
header = (root / 'include/https_client.h').read_text()
build = (root / 'scripts/build_https_tls.sh').read_text()


def function(signature):
    start = http.index(signature)
    # Ignore braces inside strings, character literals and comments.
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]',
                         http[start:], re.S)
    depth = 0
    for token in tokens:
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return http[start:start + token.end()] + '\n'
    raise AssertionError('Unclosed function: ' + signature)


# Retain the verified updater's TLS, timeout and PS2 portability boundaries.
for token in ('MBEDTLS_SSL_VERIFY_REQUIRED', 'mbedtls_ssl_set_hostname',
              'mbedtls_ssl_get_verify_result', 'MBEDTLS_X509_BADCERT_EXPIRED',
              'MBEDTLS_X509_BADCERT_FUTURE', 'verify the PS2 date and time',
              'mbedtls_x509_crt_verify_info', 'HTTPS CA bundle is required',
              'len > 256 * 1024', '#define HTTPS_IO_TIMEOUT_MS 15000',
              'ps2ipc_ioctl(*sock, HTTPS_FIONBIO, &nonblock)',
              'HttpsEntropyMaterial', 'sceCdReadClock', 'https_entropy_network_ticks',
              'never present it to TLS as the sole source'):
    assert token in http, token
assert http.index('ps2_tcp_connect(&tls->sock, host)') < http.index('mbedtls_ctr_drbg_seed')
for token in ('unset MBEDTLS_NET_C', 'MBEDTLS_NO_PLATFORM_ENTROPY',
              'MBEDTLS_ENTROPY_HARDWARE_ALT', '-ffunction-sections -fdata-sections'):
    assert token in build, token

# Removed feature must have no live callers, settings, endpoints or build inputs.
for folder in ('src', 'include', 'scripts', '.github/workflows'):
    for path in (root / folder).rglob('*'):
        if path.is_file() and path.suffix in ('.c', '.h', '.sh', '.py', '.yml'):
            source = path.read_text(errors='replace')
            for token in ('cloudGoogle', 'cloudHttp', 'WLE_NATIVE_CLOUD',
                          'igr_cloud_sync', 'Dash_IGRCloudSync', 'S_GOOGLE_ACCOUNT',
                          'WLE_GOOGLE_CLIENT', 'WLE-CLOUD.TOK', 'www.googleapis.com'):
                assert token not in source, (path, token)
assert 'src/https_client.c' in (root / 'ps2.yaml').read_text()
assert 'WLE_NATIVE_HTTPS' in (root / 'ps2.yaml').read_text()
assert not (root / 'src/cloud_google.c').exists()
assert not (root / 'src/qrcodegen.c').exists()

c = r'''
#include <assert.h>
#include <ctype.h>
#include <limits.h>
#include <malloc.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#define HTTPS_HEADER_MAX 12288
#define HTTPS_IO 16384
#define MBEDTLS_ERR_SSL_WANT_READ -10
#define MBEDTLS_ERR_SSL_WANT_WRITE -11
#define MBEDTLS_ERR_SSL_PEER_CLOSE_NOTIFY -12
typedef struct { int ssl; } HttpsTls;
/* Capture exact hash input rather than substituting a crypto library in CI. */
typedef struct { unsigned char bytes[1024]; size_t len; } mbedtls_sha256_context;
static void mbedtls_sha256_init(mbedtls_sha256_context *s) { memset(s,0,sizeof(*s)); }
static int mbedtls_sha256_starts(mbedtls_sha256_context *s,int n) {(void)s;assert(!n);return 0;}
static int mbedtls_sha256_update(mbedtls_sha256_context *s,const unsigned char *p,size_t n) {
    assert(s->len+n<=sizeof(s->bytes));memcpy(s->bytes+s->len,p,n);s->len+=n;return 0;
}
static int mbedtls_sha256_finish(mbedtls_sha256_context *s,unsigned char *out) {
    memset(out,0,32);memcpy(out,s->bytes,s->len<32?s->len:32);return 0;
}
static void mbedtls_sha256_free(mbedtls_sha256_context *s) {(void)s;}
static const char *replies[8];
static char requests[8][4096], hosts[8][256], output[1024];
static int connections, closed, reply_at, read_step, output_at, write_step;
static int want_read, timeout, fail_write;
static void set_error(char *e,int cap,const char *s,int r) {
    (void)r;if(e && cap>0)snprintf(e,cap,"%s",s);
}
static int tls_open(HttpsTls *tls,const char *host,const char *ca,char *e,int n) {
    (void)e;(void)n;assert(ca && !strcmp(ca,"WLE-UPDATE-CA.PEM"));
    assert(connections<8);snprintf(hosts[connections],256,"%s",host);
    tls->ssl=connections++;reply_at=0;return 0;
}
static void tls_free(HttpsTls *tls) {(void)tls;closed++;}
static int ssl_write_all(HttpsTls *tls,const void *p,int n,char *e,int cap) {
    (void)e;(void)cap;assert(n>0 && n<4096);
    memcpy(requests[tls->ssl],p,n);requests[tls->ssl][n]=0;return 0;
}
static int wait_tls_io(HttpsTls *tls,int r) {(void)tls;(void)r;return timeout?-1:0;}
static int mbedtls_ssl_read(int *ssl,unsigned char *p,size_t n) {
    size_t left;
    if(want_read){want_read=0;return MBEDTLS_ERR_SSL_WANT_READ;}
    assert(replies[*ssl]);left=strlen(replies[*ssl])-reply_at;
    if(n>left)n=left;
    if(read_step && n>(size_t)read_step)n=read_step;
    memcpy(p,replies[*ssl]+reply_at,n);reply_at+=(int)n;return (int)n;
}
static int genLseek(int fd,int offset,int whence) {
    assert(fd==5 && offset==0 && whence==SEEK_SET);output_at=0;return 0;
}
static int genWrite(int fd,void *p,int n) {
    assert(fd==5 && n>0);
    if(fail_write)return -1;
    if(write_step && n>write_step)n=write_step;
    assert(output_at+n<(int)sizeof(output));
    memcpy(output+output_at,p,n);output_at+=n;output[output_at]=0;return n;
}
static void reset(void) {
    memset(replies,0,sizeof(replies));memset(requests,0,sizeof(requests));
    memset(hosts,0,sizeof(hosts));memset(output,0,sizeof(output));
    connections=closed=reply_at=read_step=output_at=write_step=0;
    want_read=timeout=fail_write=0;
}
'''
c += header
# These are the real production functions, including shared JSON responses.
for signature in ('static int header_value(', 'static int decode_chunked(',
                  'static int read_response(', 'void httpsResponseFree(',
                  'static int request_open(', 'int httpsRequest(',
                  'static int split_https_url('):
    c += function(signature)
c += http[http.index('typedef struct {\n    char line[40];'):
          http.index('static int download_write(')]
for signature in ('static int download_write(', 'static int download_chunked_consume(',
                  'int httpsDownloadFd('):
    c += function(signature)
c += r'''
static int download(int limit,int *size,unsigned char *hash,char *error) {
    return httpsDownloadFd("https://github.com/release",5,"WLE-UPDATE-CA.PEM",
                           limit,size,hash,error,256);
}
int main(void) {
    int size, i;
    unsigned char hash[32];
    char error[256];
    HttpsResponse response;
    reset();replies[0]="HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}";
    read_step=1;want_read=1;
    assert(!httpsRequest("GET","api.github.com","/latest",NULL,NULL,0,
                         "WLE-UPDATE-CA.PEM",&response,error,sizeof(error)));
    assert(response.status==200 && response.body_len==2 && !strcmp(response.body,"{}"));
    assert(strstr(requests[0],"GET /latest HTTP/1.1"));
    assert(strstr(requests[0],"User-Agent: Launchstation/HTTPS"));
    httpsResponseFree(&response);assert(!response.body && !response.body_len);
    assert(connections==1 && closed==1);

    reset();replies[0]="HTTP/1.1 302 Found\r\nLocation: https://objects.githubusercontent.com/pkg\r\n\r\n";
    replies[1]="HTTP/1.1 307 Temporary Redirect\r\nLocation: /final\r\n\r\n";
    replies[2]="HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nABCDEF";
    read_step=3;write_step=2;
    assert(!download(100,&size,hash,error));assert(size==6);
    assert(!strcmp(output,"ABCDEF") && !memcmp(hash,"ABCDEF",6));
    assert(connections==3 && closed==3);
    assert(!strcmp(hosts[1],"objects.githubusercontent.com"));
    assert(strstr(requests[2],"GET /final HTTP/1.1"));
    for(i=0;i<connections;i++)assert(!strstr(requests[i],"Authorization:"));

    reset();replies[0]="HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3;x=1\r\nABC\r\n3\r\nDEF\r\n0\r\n\r\n";
    read_step=1;write_step=2;
    assert(!download(6,&size,hash,error));
    assert(size==6 && !strcmp(output,"ABCDEF") && !memcmp(hash,"ABCDEF",6));

    reset();replies[0]="HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nABC";
    assert(download(100,&size,hash,error)<0 && size==0);
    assert(strstr(error,"Truncated HTTPS download") && closed==1);
    reset();replies[0]="HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nABCDEF";
    assert(download(5,&size,hash,error)<0 && !output_at);
    assert(strstr(error,"size limit") && closed==1);
    reset();replies[0]="HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nAB";
    assert(download(100,&size,hash,error)<0 && size==0);
    assert(strstr(error,"Truncated chunked HTTPS download"));
    reset();replies[0]="HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\nABCDEF";fail_write=1;
    assert(download(100,&size,hash,error)<0 && size==0 && closed==1);
    assert(strstr(error,"Could not write downloaded update"));

    reset();replies[0]="HTTP/1.1 404 Missing\r\n\r\n";
    assert(download(100,&size,hash,error)<0 && strstr(error,"HTTP 404"));
    reset();replies[0]="HTTP/1.1 302 Found\r\nLocation: http://example.com/insecure\r\n\r\n";
    assert(download(100,&size,hash,error)<0 && connections==1);
    assert(strstr(error,"Unsupported HTTPS redirect"));
    reset();for(i=0;i<6;i++)replies[i]="HTTP/1.1 302 Found\r\nLocation: /loop\r\n\r\n";
    assert(download(100,&size,hash,error)<0 && connections==6 && closed==6);
    assert(strstr(error,"Too many HTTPS redirects"));
    reset();want_read=timeout=1;
    assert(download(100,&size,hash,error)<0 && closed==1);
    assert(strstr(error,"HTTPS download timed out"));
    puts("PASS: updater HTTPS retains JSON requests, credential-free redirects, chunked streaming, checksums, short writes and failure cleanup");
    return 0;
}
'''
compiler = shutil.which('cc') or shutil.which('gcc')
assert compiler, 'A host C compiler is required'
with tempfile.TemporaryDirectory(prefix='launchstation-https-') as tmp:
    src = Path(tmp) / 'https.c'
    exe = Path(tmp) / 'https'
    src.write_text(c)
    subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
