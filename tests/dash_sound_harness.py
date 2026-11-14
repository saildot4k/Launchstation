"""Compile the full audio implementation with a manually stepped work queue.

SDK calls assert their owner; a hook can run UI actions between worker calls.
This exercises queue, publication and RPC ownership without hardware timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "dash_sound.h"
typedef uint8_t u8;
typedef uint32_t u32;
#include "audsrv.h"
#define MAX_PATH 256
#define DASH_TOAST_WARN 1
#define DASH_JOB_VISIBLE 1
#define FIO_O_RDONLY 1
static struct { int sound, sound_vol, bgm, bgm_vol; } dashCfg = {1,60,1,80};
static char LaunchElfBootDir[MAX_PATH]="usb0:/BOOT/", LaunchElfDir[MAX_PATH]="mc0:/SYS-CONF/";
u8 libsd_irx[1], audsrv_irx[1];
int size_libsd_irx=1, size_audsrv_irx=1;
u8 sfx_cursor_adp[16], sfx_confirm_adp[16], sfx_cancel_adp[16], sfx_transition_adp[16];
u8 sfx_message_adp[16], sfx_boot_adp[16], sfx_connect_adp[16], sfx_disconnect_adp[16];
int size_sfx_cursor_adp=16, size_sfx_confirm_adp=16, size_sfx_cancel_adp=16, size_sfx_transition_adp=16;
int size_sfx_message_adp=16, size_sfx_boot_adp=16, size_sfx_connect_adp=16, size_sfx_disconnect_adp=16;
static unsigned generation;
static int worker_thread, active, parked, foreground_io, frame_active, reject_submit, status_quiet;
static int isStartupDriverStatusQuiet(void) {return status_quiet;}
static int module_failure, init_failure, adpcm_failure, sample_failures, upload_error;
static int module_calls, init_calls, adpcm_calls, sample_uploads, music_uploads, warnings;
static int quits, stops, rpc_calls, ui_steps, storage_steps;
static int volumes[24], plays[24], volume_error, bad_channel_reply;
static audsrv_adpcm_t *uploaded_ids[64];
static int uploaded_count;
static int exists=1, stack_loaded=1, file_size=64, file_bytes=64, position, close_error;
static int opens, closes, reads, allocations;
static u8 track[64];
static char opened[MAX_PATH], last_warning[128];
static void (*during_rpc)(void);
typedef void (*JobFn)(void *);
static struct {int id;JobFn run,done;void *arg;} jobs[32];
static int q_head,q_count,next_id=1,completed_id,submitted;
static unsigned int getIopResetGeneration(void) { return generation; }
static int dashIopParked(void) { return parked; }
static int dashIoBusy(void) { return foreground_io; }
static int dashWorkerIoBusy(void) { return active; }
static int DashIoBusy(void) { return active || parked || foreground_io || frame_active; }
static void finish_one(void);
static int dashWorkerSubmit(const char *label,int flags,JobFn run,JobFn done,void *arg) {
    assert(!worker_thread && label && flags==DASH_JOB_VISIBLE);
    if(reject_submit || q_count==32)return -1;
    int i=(q_head+q_count++)%32;
    jobs[i].id=next_id++;jobs[i].run=run;jobs[i].done=done;jobs[i].arg=arg;submitted++;
    return jobs[i].id;
}
static int dashWorkerAwait(int id,const char *label,int cancelable) {
    assert(!worker_thread && !cancelable && (status_quiet ? label==NULL : label!=NULL));
    while(completed_id<id)finish_one();
    return 1;
}
static void finish_one(void) {
    assert(!active && !worker_thread && q_count);
    int i=q_head;q_head=(q_head+1)%32;q_count--;
    int id=jobs[i].id;JobFn run=jobs[i].run,done=jobs[i].done;void *arg=jobs[i].arg;
    active=worker_thread=1;run(arg);worker_thread=active=0;
    completed_id=id;
    if(during_rpc)during_rpc(); /* UI may run after the worker, before publication. */
    if(done)done(arg);
}
static void rpc(void) {
    assert(!foreground_io && !parked);
    assert(worker_thread || !active);rpc_calls++;
    if(worker_thread && during_rpc) {
        worker_thread=0;during_rpc();worker_thread=1;
    }
}
static int SifExecModuleBuffer(void *p,int size,int n,void *args,int *ret) {
    assert(worker_thread && size==1 && !n && !args);rpc();module_calls++;*ret=0;
    return (module_failure==1 && p==libsd_irx) || (module_failure==2 && p==audsrv_irx) ? -1:1;
}
int audsrv_init(void) { assert(worker_thread);rpc();init_calls++;return init_failure; }
int audsrv_adpcm_init(void) { rpc();adpcm_calls++;return adpcm_failure; }
int audsrv_quit(void) { rpc();quits++;return 0; }
int audsrv_stop_audio(void) {rpc();stops++;return 0;}
int audsrv_load_adpcm(audsrv_adpcm_t *sample,void *data,int size) {
    assert(worker_thread);rpc();
    assert(uploaded_count<64);uploaded_ids[uploaded_count++]=sample;
    if(size==16) {
        int fail=sample_uploads++<sample_failures;sample->buffer=fail?NULL:data;return fail?-1:0;
    }
    assert(size==64 && !memcmp(data,"APCM",4));music_uploads++;
    u8 *p=data;assert(p[6]==1 && p[17]==6 && p[33]==2 && p[49]==3);
    if(upload_error)return -1;sample->buffer=data;return 0;
}
int audsrv_adpcm_set_volume_and_pan(int ch,int v,int pan) {
    assert(ch>=0 && ch<24 && v>=0 && v<=100 && !pan);rpc();
    if(volume_error)return -1;volumes[ch]=v;return 0;
}
int audsrv_ch_play_adpcm(int ch,audsrv_adpcm_t *sample) {
    assert(ch>=0 && ch<24 && sample->buffer);
    int found=0;for(int i=0;i<uploaded_count;i++)found|=uploaded_ids[i]==sample;
    assert(found); /* audsrv identifies uploads by the sample object's EE address. */
    rpc();plays[ch]++;
    return bad_channel_reply?24:ch;
}
static int isPathDeviceStackLoaded(const char *path) { assert(path);return stack_loaded; }
static void filerRootMcPollIdle(void) {assert(worker_thread);}
static int genFixPath(const char *path,char *out) {assert(worker_thread);strcpy(out,path);return 0;}
static int genOpen(const char *path,int mode) {
    assert(worker_thread && mode==FIO_O_RDONLY);opens++;strcpy(opened,path);position=0;return exists?0:-1;
}
static int genLseek(int fd,int offset,int mode) {
    assert(worker_thread && fd==0 && !offset);if(mode==SEEK_END)return file_size;position=0;return 0;
}
static int genRead(int fd,void *out,int size) {
    assert(worker_thread && fd==0);reads++;
    if(position>=file_bytes)return 0;
    if(size>16)size=16;if(size>file_bytes-position)size=file_bytes-position;
    memcpy(out,track+position,size);position+=size;return size;
}
static int genClose(int fd) {assert(worker_thread && fd==0);closes++;return close_error?-1:0;}
static void *allocate(int align,int size) {assert(align==64);allocations++;return calloc(1,size);}
static void release(void *ptr) {if(ptr)allocations--;free(ptr);}
#define memalign allocate
#define free release
static void dashToast(int kind,const char *message) {
    assert(!worker_thread && kind==DASH_TOAST_WARN && message[0]);
    warnings++;snprintf(last_warning,sizeof(last_warning),"%s",message);
}
'''
RESET = r'''
static void reset(void) {
    during_rpc=NULL;foreground_io=parked=frame_active=status_quiet=0;
    dashSoundShutdown();assert(!allocations && !q_count);
    memset(&sound_job,0,sizeof(sound_job));sound_job_id=sound_closing=sound_volume_pending=sound_boot_pending=sound_music_pending=0;
    sound_ready=bgm_loaded=bgm_tried=0;bgm_channel=-1;bgm_data=NULL;
    sound_tried_generation=(unsigned)-1;generation=sound_reboot_generation=sound_retry=0;
    module_failure=init_failure=adpcm_failure=sample_failures=upload_error=0;
    module_calls=init_calls=adpcm_calls=sample_uploads=music_uploads=warnings=0;
    quits=stops=rpc_calls=ui_steps=storage_steps=0;
    memset(volumes,0,sizeof(volumes));memset(plays,0,sizeof(plays));uploaded_count=0;
    volume_error=bad_channel_reply=reject_submit=0;
    exists=stack_loaded=1;file_size=file_bytes=64;position=close_error=0;
    opens=closes=reads=0;opened[0]=last_warning[0]=0;submitted=0;
    strcpy(LaunchElfBootDir,"usb0:/BOOT/");strcpy(LaunchElfDir,"mc0:/SYS-CONF/");
    dashCfg.sound=1;dashCfg.sound_vol=60;dashCfg.bgm=1;dashCfg.bgm_vol=80;
    memset(track,0,sizeof(track));memcpy(track,"APCM\1\1\1\0",8);track[8]=0x10;
}
static void settle(void) {while(q_count)finish_one();}
'''

def navigation_code():
    header = (ROOT/'include/dash_internal.h').read_text()
    inputs = header[header.rfind('enum {', 0, header.index('DASH_IN_UP')):
                    header.index('void dashInputPoll(DashInput')]
    ui = (ROOT/'src/dash_ui.c').read_text()
    start = ui.index('void dashInputPollEx(')
    end = ui.index('\n}\n', start)+3
    stubs = r'''
typedef uint64_t u64;
enum {PAD_SELECT=1,PAD_L3=2,PAD_R3=4,PAD_START=8,
      PAD_UP=16,PAD_RIGHT=32,PAD_DOWN=64,PAD_LEFT=128,
      PAD_L2=256,PAD_R2=512,PAD_L1=1024,PAD_R1=2048,
      PAD_TRIANGLE=4096,PAD_CIRCLE=8192,PAD_CROSS=16384,PAD_SQUARE=32768};
#define PAD_R3_V0 0x010000
#define PAD_R3_V1 0x020000
#define PAD_R3_H0 0x040000
#define PAD_R3_H1 0x080000
#define PAD_L3_V0 0x100000
#define PAD_L3_V1 0x200000
#define PAD_L3_H0 0x400000
#define PAD_L3_H1 0x800000
static u32 paddata,new_pad,held_prev,text_repeat_armed,shoulder_repeat_armed,shoulder_repeat;
static u64 last_input_ms;
static int swapKeys,navigation_events;
static u64 Timer(void) {return (u64)ui_steps*16;}
static void dashWorkerParkPoint(void) {}
static int readpad_no_KB(void) {new_pad=paddata=PAD_DOWN;return 1;}
static int readpad(void) {assert(!active);return readpad_no_KB();}
'''
    return inputs + stubs + ui[start:end]


def run(main, name, navigation=False):
    source = (ROOT / 'src/dash_sound.c').read_text()
    source = '\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
    compiler = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    assert compiler, 'Host C compiler required'
    with tempfile.TemporaryDirectory(prefix='audio-'+name+'-') as directory:
        path = Path(directory)
        (path/'test.c').write_text(PREFIX + source + (navigation_code() if navigation else '') + RESET + main)
        subprocess.run([compiler,'-std=c99','-Wall','-Wextra','-Werror',
                        '-Wno-misleading-indentation','-Wno-unused-function',
                        '-I',str(ROOT/'include'),'-I',str(ROOT/'packages/world/audsrv/include'),str(path/'test.c'),'-o',str(path/'test')],check=True)
        subprocess.run([str(path/'test')],check=True,timeout=10)
