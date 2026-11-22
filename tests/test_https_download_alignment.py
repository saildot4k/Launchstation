"""Run production download writes through fileXio/FatFs/ATA alignment models.

The IOP fileXio server splits a misaligned EE source into an inline prefix and
an aligned DMA buffer. FatFs consumes a partial sector before directly writing
whole sectors; ATA DMA rounds an IOP source address down to a four-byte boundary.
This reproduces the 1/2/3-byte sector shifts from the supplied OSDMBR.XLF.
No network, copyrighted payload or physical disk is needed.
"""
from pathlib import Path
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'src/https_client.c').read_text()
def function(signature):
    start = source.index(signature)
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]', source[start:], re.S)
    depth = 0
    for token in tokens:
        depth += (token.group() == '{') - (token.group() == '}')
        if not depth and token.group() == '}':
            return source[start:start + token.end()] + '\n'
    raise AssertionError(signature)

code = r'''
#define _POSIX_C_SOURCE 200112L
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define HTTPS_IO 16384
#define CAP 400000
static unsigned char original[CAP], output[CAP];
static unsigned offset, shifted_sectors, writes, short_step;
static int write_error, write_zero, overreport;
typedef struct {unsigned done;} mbedtls_sha256_context;
static int mbedtls_sha256_update(mbedtls_sha256_context *s,const unsigned char *p,size_t n){
    assert(s->done+n<=CAP && !memcmp(original+s->done,p,n));s->done+=n;return 0;
}
static void set_error(char *out,int cap,const char *text,int code){(void)code;snprintf(out,cap,"%s",text);}
static int fatfs_write(const unsigned char *p,unsigned n){
    unsigned all=n,head=offset%512?512-offset%512:0;
    if(head>n)head=n;
    memcpy(output+offset,p,head);offset+=head;p+=head;n-=head;
    if(n>=512){
        unsigned sectors=n/512,bytes=sectors*512;
        const unsigned char *dma=(const unsigned char *)((uintptr_t)p&~(uintptr_t)3);
        if(dma!=p)shifted_sectors+=sectors;
        memcpy(output+offset,dma,bytes);offset+=bytes;p+=bytes;n-=bytes;
    }
    memcpy(output+offset,p,n);offset+=n;return all;
}
static int genWrite(int fd,void *data,int size){
    static unsigned char rpc_inline[64] __attribute__((aligned(64)));
    static unsigned char rpc_dma[HTTPS_IO] __attribute__((aligned(64)));
    const unsigned char *p=data;
    unsigned n=size,mis=(64-((uintptr_t)p&63))&63;
    assert(fd==5 && size>0 && n<=HTTPS_IO && offset+n<=CAP);writes++;
    if(write_error)return write_error;
    if(write_zero)return 0;
    if(overreport)return size+1;
    if(short_step && n>short_step)n=short_step;
    if(mis>n)mis=n;
    memcpy(rpc_inline,p,mis);fatfs_write(rpc_inline,mis);
    memcpy(rpc_dma,p+mis,n-mis);fatfs_write(rpc_dma,n-mis);
    return n;
}
'''
code += source[source.index('typedef struct {\n    char line[40];'):source.index('static int download_write(')]
code += function('static int download_write(') + function('static int download_chunked_consume(')
code += r'''
static void run(unsigned size,unsigned fragment,unsigned source_misalignment,int chunked,unsigned short_write){
    unsigned char *allocation,*input,*buffer;
    int written=0,ret;
    char error[256];
    mbedtls_sha256_context sha={0};
    HttpsChunkDecoder decoder={0};
    assert(!posix_memalign((void **)&allocation,64,CAP+64));
    assert(!posix_memalign((void **)&buffer,64,HTTPS_IO));
    input=allocation+source_misalignment;memcpy(input,original,size);
    memset(output,0,sizeof(output));offset=shifted_sectors=writes=0;short_step=short_write;
    HttpsDownloadBuffer pending={.data=buffer};
    unsigned at=0;
    while(at<size){
        unsigned n=size-at;if(n>fragment)n=fragment;
        if(chunked){
            char line[32];int line_size=snprintf(line,sizeof(line),"%x\r\n",n);
#define CONSUME(ptr,len) download_chunked_consume(&decoder,(const unsigned char *)(ptr),len,5,&pending,CAP,&written,&sha,error,sizeof(error))
            /* Delimiters and payload may arrive in separate TLS reads. */
            for(int i=0;i<line_size;i++)assert(CONSUME(line+i,1)==0);
            assert(CONSUME(input+at,n)==0);assert(CONSUME("\r",1)==0);assert(CONSUME("\n",1)==0);
        }else{
            ret=download_write(5,&pending,input+at,n,CAP,&written,&sha,error,sizeof(error));
            assert(ret==0);
        }
        at+=n;
    }
    if(chunked)assert(CONSUME("0\r\n\r\n",5)==1);
    assert(download_flush(5,&pending,error,sizeof(error))==0);
    assert(!pending.used && pending.offset==(int)size);
    if(shifted_sectors)fprintf(stderr,"size=%u fragment=%u source+%u: %u shifted ATA sectors\n",size,fragment,source_misalignment,shifted_sectors);
    assert(!shifted_sectors && offset==size && written==(int)size && sha.done==size);
    assert(!memcmp(output,original,size));
    if(!short_write)assert(writes==(size+HTTPS_IO-1)/HTTPS_IO);
    free(buffer);free(allocation);
}
int main(void){
    for(unsigned i=0;i<CAP;i++)original[i]=(i*73+i/7)%251+1;
    /* Same size as the reported OSDMBR, with unaligned network fragments. */
    run(389632,1378,13,0,0);
    const unsigned sizes[]={0,1,511,512,513,16383,16384,16385,389632,389633};
    const unsigned fragments[]={1,3,1378,1380,4095,16384,32769};
    for(unsigned s=0;s<sizeof(sizes)/sizeof(*sizes);s++)
        for(unsigned f=0;f<sizeof(fragments)/sizeof(*fragments);f++)
            for(unsigned mis=0;mis<4;mis++)
                for(int chunked=0;chunked<2;chunked++)run(sizes[s],fragments[f],mis,chunked,0);
    for(unsigned step=1;step<=511;step=step==1?97:step==97?511:512)run(65537,1378,13,0,step);
    unsigned char buffer[HTTPS_IO] __attribute__((aligned(64)));
    HttpsDownloadBuffer pending={.data=buffer};
    char error[256];int written=0;mbedtls_sha256_context sha={0};
    offset=0;short_step=0;write_error=-1;
    /* A final partial block still reports write failures. */
    assert(!download_write(5,&pending,original,27,CAP,&written,&sha,error,sizeof(error)));
    assert(download_flush(5,&pending,error,sizeof(error))<0 && strstr(error,"write"));
    write_error=0;write_zero=1;
    assert(download_flush(5,&pending,error,sizeof(error))<0);
    write_zero=0;overreport=1;
    assert(download_flush(5,&pending,error,sizeof(error))<0);
    overreport=0;pending.used=0;written=CAP;
    assert(download_write(5,&pending,original,1,CAP,&written,&sha,error,sizeof(error))<0);
    puts("PASS: raw/chunked downloads preserve exact bytes through fileXio/FatFs/ATA DMA, all alignments, sector/buffer tails, bounded writes and short/error writes");
}
'''
with tempfile.TemporaryDirectory(prefix='https-download-alignment-') as directory:
    d = Path(directory);(d/'check.c').write_text(code)
    subprocess.run(['gcc','-O2','-std=c99','-Wall','-Wextra','-Werror',str(d/'check.c'),'-o',str(d/'check')],check=True)
    subprocess.run([str(d/'check')],check=True,timeout=60)
