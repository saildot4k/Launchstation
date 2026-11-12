"""Execute production buffer selection, IOP tuning and MMCE startup retries."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
copy = (root / 'src/filer_copy.c').read_text()
init = (root / 'src/init.c').read_text()
mmce = (root / 'iop/mmceman/src/mmceman.c').read_text()


def function(source, signature):
    a = source.index(signature)
    b = source.index('{', a) + 1
    depth = 1
    while depth:
        depth += (source[b] == '{') - (source[b] == '}')
        b += 1
    return source[a:b] + '\n'


code = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
#define FILEOP_TRACE 0
#define MX4SIO 1
#define ETH 1
#define UDPFS 1
#define PM_PSU_BACKUP 1
#define DPRINTF(...) ((void)0)
static int PM_flag[1], alloc_calls, fail_alloc, closed, removed;
static size_t allocations[2];
static int isPcCardCfPath(const char *p) { return !strncmp(p,"cf",2); }
static void filerCopyDiagStage(const char *s) { (void)s; }
static int genClose(int fd) { assert(fd==99);closed++;return 0; }
static int genRemove(const char *p) { (void)p;removed++;return 0; }
static void *memalign(size_t alignment,size_t bytes) {
 assert(alignment==64 && alloc_calls<2);allocations[alloc_calls++]=bytes;
 return alloc_calls==fail_alloc?NULL:malloc(bytes);
}
struct buffers { int size,count,result; };
static struct buffers buffers_for(const char *in,const char *out,u64 size) {
 int buffSize,buffCount=1,ret=0,out_fd=99,recurses=0;
 void *buff=NULL,*buff2=NULL;
 alloc_calls=closed=removed=0;
'''
code += next(line for line in copy.splitlines() if line.startswith('#define COPY_BUFFER_FAST_DEFAULT ')) + '\n'
a = copy.index('\t/* Determine the block size.')
b = copy.index('\n\told_size = written_size;', a)
code += copy[a:b] + r'''
copy_file_data_done:
copy_file_exit_mem_err:
 ;struct buffers result={buffSize,buffCount,ret};
 free(buff2);free(buff);return result;
}
static int tune_calls,tune_fail_mask,rw_available,requests[3];
static int fileXioSetRWBufferSize(int size) {
 assert(tune_calls<3);requests[tune_calls]=size;
 /* SDK resizing frees the previous allocation even if the new one fails. */
 rw_available=!(tune_fail_mask&(1<<tune_calls++));
 return rw_available?0:-ENOMEM;
}
static int have_filexio_ready,have_mc_rpc_ready,fxio_inits,mc_inits;
static int mc_resets,mc_init_result,mc_bound,pending_mc_requests,mc_drains,vmc_loads;
#ifndef TEST_LEGACY_MC
#define HOMEBREW_SIO2MAN 1
#endif
#define MC_TYPE_XMC 1
#define MC_TYPE_MC 0
static void loadBasicModules(void) {}
static void fileXioInit(void) { fxio_inits++; }
static void filerRootMcPollIdle(void) { mc_drains++;pending_mc_requests=0; }
static int mcReset(void) { assert(!pending_mc_requests);mc_resets++;mc_bound=0;return 0; }
static int mcInit(int type) {
#ifdef HOMEBREW_SIO2MAN
 assert(type==MC_TYPE_XMC);
#else
 assert(type==MC_TYPE_MC);
#endif
 mc_inits++;
 if(mc_bound)return -1; /* An already-bound client must be cleared first. */
 if(mc_init_result<0)return mc_init_result;
 mc_bound=1;return 0;
}
static void load_vmcman_module(void) { vmc_loads++; }
'''
code += function(init, 'static void configureFileXioTransferBuffer(')
code += function(init, 'int ensureMemoryCardRpcReady(void)\n{')
code += function(init, 'int isMemoryCardRpcReady(void)\n{')
code += function(init, 'void ensureCoreIoStackReady(void)\n{')
code += r'''
static int ping_calls,ping_success,card_resets;
static void mmce_sio2_set_port(int port) { assert(port==2||port==3); }
static int mmce_cmd_ping(void) { return ping_calls++==ping_success?0x010100:-1; }
static int mmce_cmd_reset(void) { card_resets++;return 0; }
'''
code += next(line for line in mmce.splitlines() if line.startswith('#define MMCE_PING_ATTEMPTS ')) + '\n'
code += function(mmce, 'static void mmce_init(')
code += r'''
int main(void) {
 const struct {const char *from,*to;int bytes;} routes[]={
  {"udpfs:/A","pfs0:/B",1048576},{"udpfs:/A","mmce0:/B",1048576},
  {"udpfs:/A","usb0:/B",1048576},{"pfs0:/A","ata0:/B",1048576},
  {"udpfs:/A","mc0:/B",131072},{"udpfs:/A","mc1:/B",131072},
  {"udpfs:/A","vmc0:/B",131072},{"pfs0:/A","mass0:/B",131072},
  {"udpfs:/A","mx4sio:/B",131072},{"udpfs:/A","cf0:/B",131072},
  {"mc0:/A","usb0:/B",262144},{"mc0:/A","udpfs:/B",262144},
  {"mc0:/A","mc1:/B",131072},{"udpfs:/A","host:/B",393216},
  {"host:/A","pfs0:/B",524288},{"mass0:/A","pfs0:/B",524288},
  {"mx4sio:/A","pfs0:/B",524288},{"cf0:/A","pfs0:/B",524288}
 };
 const int sizes[]={0,1,16384,65536,131072,262144,524288,1048575,1048576,1048577,3145728};
 for(unsigned r=0;r<sizeof(routes)/sizeof(*routes);r++)
 for(unsigned s=0;s<sizeof(sizes)/sizeof(*sizes);s++) {
  fail_alloc=0;struct buffers b=buffers_for(routes[r].from,routes[r].to,sizes[s]);
  int expected=sizes[s]<routes[r].bytes?sizes[s]:routes[r].bytes;
  assert(!b.result&&b.size==expected&&b.count==(expected==1048576?2:1));
  assert(alloc_calls==(expected?b.count:0)&&!closed&&!removed);
  if(expected)assert(allocations[0]==(size_t)expected);
 }
 fail_alloc=2;struct buffers b=buffers_for("udpfs:/A","pfs0:/B",3145728);
 assert(!b.result&&b.size==1048576&&b.count==1&&alloc_calls==2&&!closed&&!removed);
 fail_alloc=1;b=buffers_for("udpfs:/A","mc0:/B",3145728);
 assert(b.result==-ENOMEM&&alloc_calls==1&&closed==1&&removed==1);
 puts("PASS: R3Z per-device buffers, 64-byte alignment, UDPFS double-buffer threshold and single-buffer allocation fallback");
 for(int failed=0;failed<3;failed++) {
  tune_calls=0;tune_fail_mask=(1<<failed)-1;rw_available=1;
  have_filexio_ready=have_mc_rpc_ready=fxio_inits=mc_inits=0;
  ensureCoreIoStackReady();ensureCoreIoStackReady();
  assert(tune_calls==failed+1&&rw_available&&fxio_inits==1&&mc_inits==1);
  assert(requests[0]==131072);
  if(failed>0)assert(requests[1]==65536);
  if(failed>1)assert(requests[2]==16384);
  /* Reset invalidates the configuration; the new IOP session is tuned again. */
  have_filexio_ready=have_mc_rpc_ready=0;tune_calls=tune_fail_mask=0;
  ensureCoreIoStackReady();assert(tune_calls==1&&fxio_inits==2&&mc_inits==2);
 }
 puts("PASS: R3Z 128/64 KiB IOP tuning, explicit 16 KiB recovery, once per IOP session");
 const int init_failures[]={-1,-100,-120,-121,-122};
 for(unsigned i=0;i<sizeof(init_failures)/sizeof(*init_failures);i++) {
  have_mc_rpc_ready=0;mc_init_result=init_failures[i];mc_bound=1;pending_mc_requests=1;
  int inits=mc_inits,resets=mc_resets,drains=mc_drains;
  assert(!isMemoryCardRpcReady());
  assert(ensureMemoryCardRpcReady()==init_failures[i]&&!isMemoryCardRpcReady());
  assert(mc_inits==inits+1&&mc_resets==resets+1&&mc_drains==drains+1&&!mc_bound);
  /* A failed MC client must not prevent unrelated FILEXIO/VMC use. */
  int vmcs=vmc_loads,fxios=fxio_inits;
  ensureCoreIoStackReady();assert(!isMemoryCardRpcReady()&&vmc_loads==vmcs+1&&fxio_inits==fxios);
  /* A later explicit attempt succeeds, including an implicit libmc binding. */
  mc_init_result=0;mc_bound=1;pending_mc_requests=1;
  assert(!ensureMemoryCardRpcReady()&&isMemoryCardRpcReady()&&mc_bound&&!pending_mc_requests);
  inits=mc_inits;resets=mc_resets;drains=mc_drains;
  assert(!ensureMemoryCardRpcReady()&&mc_inits==inits&&mc_resets==resets&&mc_drains==drains);
 }
 puts("PASS: MC init errors stay unready, propagate unchanged, allow later recovery and preserve other devices; existing bindings drain before reset");
 assert(MMCE_PING_ATTEMPTS==2);
 for(int port=2;port<=3;port++)for(int success=-1;success<MMCE_PING_ATTEMPTS;success++) {
  ping_calls=card_resets=0;ping_success=success;mmce_init(port);
  assert(ping_calls==(success<0?MMCE_PING_ATTEMPTS:success+1)&&card_resets==(success<0?0:1));
 }
 puts("PASS: preferred two MMCE startup attempts per port, each response and absent-card bound");
}
'''

with tempfile.TemporaryDirectory(prefix='r3z-file-io-') as folder:
    path = Path(folder)
    (path / 'test.c').write_text(code)
    compiler = shutil.which('gcc') or shutil.which('cc')
    if not compiler:
        raise SystemExit('Host C compiler required')
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    for variant in ([], ['-DTEST_LEGACY_MC=1']):
        subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', *flags, *variant,
                        str(path / 'test.c'), '-o', str(path / 'test')], check=True)
        subprocess.run([str(path / 'test')], check=True)
