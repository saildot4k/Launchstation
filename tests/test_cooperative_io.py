"""Exercise the production wait shim with delayed RPC/MC/reset/codec replies.

The fake IOP completes requests only as EE time passes; a blocking EE would
produce zero intermediate frames. No source-text substitute for the shim.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
wraps = ("sceSifCallRpc", "sceSifBindRpc", "mcSync", "xfromSync", "SifIopReset",
         "SifIopSync", "DelayThread", "saveArchiveParse", "saveArchiveBuild")
for build_file in ("Makefile", "ps2.yaml"):
    text = (root / build_file).read_text()
    for name in wraps:
        assert "--wrap=" + name in text, (build_file, name)
    assert "dash_io" in text

header = r'''
#include <stdint.h>
#include <stddef.h>
typedef uint64_t u64;
typedef int32_t s32;
typedef void (*SifRpcEndFunc_t)(void *);
typedef struct { int busy; void *server; } SifRpcClientData_t;
#define SIF_RPC_M_NOWAIT 1
#define SifCheckStatRpc mockCheckStatRpc
int GetThreadId(void);
u64 Timer(void);
int DashIsActive(void);
int DashIoBusy(void);
int dashIoBusy(void);
int dashGfxCanYield(void);
int dashWorkerIoBusy(void);
int dashIopParked(void);
int dashWorkerBusy(void);
void dashWorkerPump(void);
int dashWorkerSubmit(const char *, int, void (*)(void *), void (*)(void *), void *);
int dashWorkerDone(int);
void dashLoadingRedraw(void);
int mockCheckStatRpc(SifRpcClientData_t *);
void dashIoInit(void);
int __wrap_sceSifCallRpc(SifRpcClientData_t *,int,int,void *,int,void *,int,SifRpcEndFunc_t,void *);
int __wrap_sceSifBindRpc(SifRpcClientData_t *,int,int);
int __wrap_mcSync(int,int *,int *);
int __wrap_xfromSync(int,int *,int *);
int __wrap_SifIopReset(const char *,int);
int __wrap_SifIopSync(void);
s32 __wrap_DelayThread(s32);
'''
code = r'''
#include "dash_internal.h"
#include "save_archive.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int __wrap_saveArchiveParse(SaveArchive *,uint8_t *,size_t,const char *);
int __wrap_saveArchiveBuild(const SaveArchive *,int,uint8_t **,size_t *);
static u64 usec,finish_at,card_finish,reset_finish,worker_finish;
static int tid=1,active=1,frame_open,parked,frames,checks,calls,last_mode,last_number;
static int rpc_delay=97000,delay_error;
static int error,callback_count,card_pending,worker_pending,worker_complete,worker_id;
static int pump_count,codec_count,reject_job,last_codec_thread,bind_missing;
static void *last_send,*last_receive,*last_arg;
static int last_ssize,last_rsize;
static SifRpcClientData_t *pending;
static SifRpcEndFunc_t callback;
static uint64_t *reply;
static void (*worker_run)(void *);
static void *worker_arg;
static int placeholder_done;
static void codecRunPlaceholder(void *arg) {assert(!arg && tid==2);placeholder_done++;}
int GetThreadId(void) {return tid;}
u64 Timer(void) {return usec/1000;}
int DashIsActive(void) {return active;}
int dashGfxCanYield(void) {return !frame_open;}
int dashWorkerIoBusy(void) {return worker_pending && !worker_complete;}
int dashIopParked(void) {return parked;}
int dashWorkerBusy(void) {return worker_pending;}
static void advance(int delta) {
    assert(delta>=0);usec+=delta;
    if(pending && usec>=finish_at) {
        if(reply)*reply=UINT64_C(0xfedcba9876543210);
        if(!bind_missing)pending->server=(void *)1;
        if(callback)callback(last_arg);
        pending->busy=0;pending=NULL;
    }
    if(worker_pending && !worker_complete && usec>=worker_finish) {
        int saved=tid;tid=2;worker_run(worker_arg);tid=saved;worker_complete=1;
    }
}
s32 __real_DelayThread(s32 delay) {if(delay_error)return delay_error;advance(delay);return 0;}
void dashLoadingRedraw(void) {
    assert(tid==1 && !frame_open && dashIoBusy() && DashIoBusy());
    frames++;frame_open=1;advance(2000);frame_open=0;
}
static void completed(void *arg) {assert(arg==(void *)0x1234);callback_count++;}
int mockCheckStatRpc(SifRpcClientData_t *cd) {checks++;return cd->busy;}
int __real_sceSifCallRpc(SifRpcClientData_t *cd,int number,int mode,void *send,int ssize,
                       void *receive,int rsize,SifRpcEndFunc_t done,void *arg) {
    calls++;last_mode=mode;last_number=number;last_send=send;last_receive=receive;
    last_ssize=ssize;last_rsize=rsize;last_arg=arg;
    if(error)return error;
    assert(!pending);pending=cd;cd->busy=1;finish_at=usec+rpc_delay;
    callback=done;reply=rsize==8?receive:NULL;
    if(!(mode&1) || !rpc_delay)advance(rpc_delay);
    return 0;
}
int __real_sceSifBindRpc(SifRpcClientData_t *cd,int server,int mode) {
    calls++;last_mode=mode;last_number=server;
    if(error)return error;
    assert(!pending);pending=cd;cd->busy=1;cd->server=NULL;
    finish_at=usec+97000;callback=NULL;reply=NULL;
    if(!(mode&1))advance(97000);
    return 0;
}
int __real_mcSync(int mode,int *cmd,int *result) {
    if(!card_pending)return -1;
    if(!mode && usec<card_finish)advance(card_finish-usec);
    if(cmd)*cmd=12;
    if(usec<card_finish)return 0;
    card_pending=0;if(result)*result=-4;return 1;
}
int __real_xfromSync(int mode,int *cmd,int *result) {return __real_mcSync(mode,cmd,result);}
int __real_SifIopReset(const char *args,int mode) {assert(!strcmp(args,"") && !mode);return usec>=reset_finish;}
int __real_SifIopSync(void) {return usec>=reset_finish;}
int dashWorkerSubmit(const char *label,int flags,void (*run)(void *),void (*done)(void *),void *arg) {
    assert(label && !flags && !done && !worker_pending && tid==1);
    if(reject_job)return -1;
    worker_run=run;worker_arg=arg;worker_pending=1;worker_complete=0;
    worker_finish=usec+97000;return ++worker_id;
}
void dashWorkerPump(void) {
    assert(tid==1 && !frame_open);pump_count++;
    if(worker_complete){worker_pending=0;worker_complete=0;}
}
int dashWorkerDone(int id) {return id==worker_id && !worker_pending;}
int __real_saveArchiveParse(SaveArchive *save,uint8_t *data,size_t size,const char *name) {
    codec_count++;last_codec_thread=tid;
    assert(data[0]==0x42 && size==23 && !strcmp(name,"test.psv"));
    save->count=3;return 17;
}
int __real_saveArchiveBuild(const SaveArchive *save,int format,uint8_t **output,size_t *size) {
    codec_count++;last_codec_thread=tid;assert(save->count==3 && format==SAVE_OUTPUT_PSV);
    *output=(uint8_t *)save;*size=999;return -18;
}
static void idle(void) {assert(!dashIoBusy() && !DashIoBusy());}
int main(void) {
    SifRpcClientData_t cd={0};uint64_t value=0;uint8_t send[17]={0};
    /* Before dashboard initialization retain the SDK's blocking behavior. */
    assert(!__wrap_sceSifCallRpc(&cd,1,0,send,17,&value,8,NULL,NULL));
    assert(!frames && !last_mode && value==UINT64_C(0xfedcba9876543210));
    dashIoInit();idle();value=0;
    int before=frames,pumps=pump_count;
    assert(!__wrap_sceSifCallRpc(&cd,91,2,send,17,&value,8,completed,(void *)0x1234));
    assert(frames-before>=5 && frames-before<=8 && last_mode==3 && last_number==91);
    assert(callback_count==1 && !cd.busy && value==UINT64_C(0xfedcba9876543210));
    assert(last_send==send && last_receive==&value && last_ssize==17 && last_rsize==8);
    assert(pump_count==pumps);idle();
    /* Null callbacks still request RPC_END and complete before returning. */
    before=frames;value=0;
    assert(!__wrap_sceSifCallRpc(&cd,3,0,NULL,0,&value,8,NULL,NULL));
    assert(callback && frames>before && value==UINT64_C(0xfedcba9876543210));idle();
    /* Submission failures preserve native errors and do not wait. */
    error=-77;before=frames;int old_checks=checks;
    assert(__wrap_sceSifCallRpc(&cd,1,0,NULL,0,NULL,0,NULL,NULL)==-77);
    assert(frames==before && checks==old_checks);error=0;idle();
    /* Existing NOWAIT calls, worker calls, classic mode and an unfinished
     * graphics frame retain their original ownership and timing. */
    assert(!__wrap_sceSifCallRpc(&cd,1,1,NULL,0,NULL,0,completed,(void *)0x1234));
    assert(cd.busy && frames==before);advance(100000);assert(callback_count==2);
    for(int mode=0;mode<3;mode++) {
        tid=mode==0?2:1;active=mode!=1;frame_open=mode==2;before=frames;
        assert(!__wrap_sceSifCallRpc(&cd,1,0,NULL,0,NULL,0,NULL,NULL));
        assert(!last_mode && frames==before);
    }
    tid=1;active=1;frame_open=1;assert(DashIoBusy());
    frame_open=0;idle();
    rpc_delay=0;before=frames;u64 fast_started=usec;
    for(int i=0;i<1000;i++)assert(!__wrap_sceSifCallRpc(&cd,1,0,NULL,0,NULL,0,NULL,NULL));
    assert(frames==before && usec==fast_started);rpc_delay=97000;
    before=frames;assert(!__wrap_sceSifBindRpc(&cd,0x80000006,0));
    assert(frames>before && cd.server && last_mode==1);idle();
    bind_missing=1;assert(!__wrap_sceSifBindRpc(&cd,5,0) && !cd.server);bind_missing=0;
    error=-22;assert(__wrap_sceSifBindRpc(&cd,5,0)==-22);error=0;idle();
    /* libmc/flash preserve completion status, output command and error. */
    for(int flash=0;flash<2;flash++) {
        int cmd=-1,result=123;card_pending=1;card_finish=usec+97000;before=frames;
        assert(__wrap_mcSync(1,&cmd,&result)==0 && result==123 && frames==before);
        assert((flash?__wrap_xfromSync(0,&cmd,&result):__wrap_mcSync(0,&cmd,&result))==1);
        assert(frames>before && cmd==12 && result==-4);
        assert(__wrap_mcSync(0,&cmd,&result)==-1);idle();
    }
    /* Reset polling must keep returning pending; the caller controls reset. */
    before=frames;reset_finish=usec+97000;
    while(!__wrap_SifIopReset("",0))assert(usec<reset_finish+1000);
    assert(frames>before);before=frames;reset_finish=usec+97000;
    while(!__wrap_SifIopSync()){}
    assert(frames>before);idle();
    before=frames;u64 started=usec;assert(!__wrap_DelayThread(100000));
    assert(usec>=started+100000 && frames>before);idle();
    before=frames;assert(!__wrap_DelayThread(250) && frames==before);
    delay_error=-9;assert(__wrap_DelayThread(10000)==-9);delay_error=0;idle();
    /* Codec callers wait for the bounded worker, with their snapshot alive. */
    SaveArchive save={0};uint8_t data[23]={0x42},*output=NULL;size_t size=0;
    before=frames;
    assert(__wrap_saveArchiveParse(&save,data,23,"test.psv")==17);
    assert(save.count==3 && codec_count==1 && last_codec_thread==2 && frames>before);idle();
    assert(__wrap_saveArchiveBuild(&save,SAVE_OUTPUT_PSV,&output,&size)==-18);
    assert(output==(uint8_t *)&save && size==999 && last_codec_thread==2);idle();
    /* A codec first drains a pre-existing job without losing its callback. */
    worker_run=codecRunPlaceholder;worker_arg=NULL;worker_pending=1;worker_complete=0;
    worker_finish=usec+31000;before=placeholder_done;
    assert(__wrap_saveArchiveParse(&save,data,23,"test.psv")==17);
    assert(placeholder_done==before+1 && last_codec_thread==2);idle();
    /* Worker unavailable: preserve functionality and all output ownership. */
    reject_job=1;assert(__wrap_saveArchiveParse(&save,data,23,"test.psv")==17);
    assert(last_codec_thread==1);idle();
    puts("PASS: frames during RPC/bind/card/reset/delay/codec waits; native results, callbacks, buffers, thread/frame ownership and no nested job dispatch");
}
'''
compiler = shutil.which("gcc") or shutil.which("clang")
if not compiler:
    raise SystemExit("Host gcc or clang required")
with tempfile.TemporaryDirectory(prefix="wle-cooperative-io-") as temp:
    tmp = Path(temp)
    (tmp / "dash_internal.h").write_text(header)
    (tmp / "test.c").write_text(code)
    flags = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-g"]
    if os.getenv("SANITIZE"):
        flags += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    exe = tmp / "test"
    subprocess.run([compiler, *flags, "-I" + str(tmp), "-I" + str(root / "include"),
                    os.getenv("COOPERATIVE_IO_SOURCE", str(root / "src/dash_io.c")), str(tmp / "test.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=15)
