"""Exercise normal MMCE path/command handling after removing card-image backups."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'iop/mmceman/src/mmce_fs.c').read_text()
header = root / 'iop/mmceman/include/mmce_path.h'
commands = (root / 'iop/mmceman/include/mmce_cmds.h').read_text()


def function(signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


# Keep firmware byte-length checks on ordinary filesystem mutations.
for signature, guard in (
    ('int mmce_fs_open(', 'if (!mmce_fs_wire_name_ok(name))'),
    ('int mmce_fs_remove(', 'if (!mmce_fs_wire_name_ok(name))'),
    ('int mmce_fs_mkdir(', 'if (!mmce_fs_wire_name_ok(name))'),
    ('int mmce_fs_rmdir(', 'if (!mmce_fs_wire_name_ok(name))'),
    ('int mmce_fs_getstat(', 'if (!mmce_fs_wire_name_ok(name))'),
    ('int\tmmce_fs_rename(', 'if (!mmce_fs_wire_name_ok(old_name) ||'),
):
    body = function(signature)
    assert body.index(guard) < body.index('mmce_fs_update_unit(file->unit)')
assert 'rdbuf[0x1] < MMCE_FS_MAX_FD' in source
assert 'MMCE_FS_ACTIVE_HANDLE' not in source
assert 'mmce_fs_discover_active_fd' not in source

# Removed workflow has no remaining UI/build/runtime dependency.
for path in ('src/dash_browser.c', 'src/dash_tools.c', 'src/dash_settings.c',
             'src/dash_store.c', 'include/dash_internal.h', 'ps2.yaml', 'Makefile'):
    text = (root / path).read_text()
    for removed in ('mmce_backup', 'mc_card_export', 'MmceBackup',
                    'dashToolsMmceStatus', 'dashBrowserRecoverCardPath',
                    'WLE-MMCE-Backups', 'WLE-Recovered', 'S_MMCE_', 'P_MMCE_BACKUP',
                    'wle_igr', 'mmce_igr', 'igr_auto_backup', 'igr_after'):
        assert removed not in text, (path, removed)
settings = (root / 'src/dash_settings.c').read_text()
system = settings[settings.index('static const SetItem system_items[]'):]
system = system[:system.index('\n};')]
assert 'S_ABOUT_PROJECT' in system
browser = (root / 'src/dash_browser.c').read_text()
assert 'Mount as vmc0:' in browser and 'Mount as vmc1:' in browser
assert 'opPaste(PASTE_PSU);' in browser

code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "mmce_path.h"
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef struct {int unit;} iomanX_iop_file_t;
#define DPRINTF(...) ((void)0)
'''
code += commands.replace('#include <tamtypes.h>', '')
code += r'''
static int last_unit=-1,port,port_changes,command,reply=7,resets;
static int card_type,card_mode,card_number,channel_number;
static const char game_id[]="SLUS_123.45";
static void mmce_sio2_set_port(int n){port=n;port_changes++;}
static void mmce_sio2_update_ack_wait_cycles(int n){command=MMCE_SETTINGS_ACK_WAIT_CYCLES;assert(n==12);}
static void mmce_sio2_set_use_alarm(int n){command=MMCE_SETTINGS_SET_ALARMS;assert(n==1);}
int mmce_cmd_ping(void){command=MMCE_CMD_PING;return reply;}
int mmce_cmd_get_status(void){command=MMCE_CMD_GET_STATUS;return reply;}
int mmce_cmd_get_card(void){command=MMCE_CMD_GET_CARD;return reply;}
int mmce_cmd_get_channel(void){command=MMCE_CMD_GET_CHANNEL;return reply;}
int mmce_cmd_reset(void){command=MMCE_CMD_RESET;resets++;return reply;}
int mmce_cmd_unmount_bootcard(void){command=MMCE_CMD_UNMOUNT_BOOTCARD;return reply;}
int mmce_cmd_set_card(u8 t,u8 m,u16 n){
    command=MMCE_CMD_SET_CARD;card_type=t;card_mode=m;card_number=n;return reply;
}
int mmce_cmd_set_channel(u8 m,u16 n){
    command=MMCE_CMD_SET_CHANNEL;card_mode=m;channel_number=n;return reply;
}
int mmce_cmd_set_card_channel(u8 t,u16 n,u16 c){
    command=MMCE_CMD_SET_CARD_CHANNEL;card_type=t;card_number=n;channel_number=c;return reply;
}
int mmce_cmd_get_gameid(void *p){command=MMCE_CMD_GET_GAMEID;strcpy(p,game_id);return reply;}
int mmce_cmd_set_gameid(void *p){command=MMCE_CMD_SET_GAMEID;assert(!strcmp(p,game_id));return reply;}
'''
code += function('static int mmce_fs_update_unit(')
code += function('int mmce_fs_devctl(')
code += r'''
int main(void) {
    char name[256],id[12];
    memset(name,'a',sizeof(name));name[254]=0;
    assert(mmce_fs_wire_name_ok(name));
    name[254]='a';name[255]=0;assert(!mmce_fs_wire_name_ok(name));
    assert(!mmce_fs_wire_name_ok("") && !mmce_fs_wire_name_ok(NULL));
    assert(mmce_fs_wire_name_ok("/games/example.iso"));
    assert(mmce_fs_wire_name_ok("/MemoryCards/PS2/Card0/Card0-1.mcd"));
    for(int unit=0;unit<2;unit++) {
        iomanX_iop_file_t f={unit};
        int commands[]={MMCE_CMD_PING,MMCE_CMD_GET_STATUS,MMCE_CMD_GET_CARD,MMCE_CMD_GET_CHANNEL};
        for(unsigned i=0;i<sizeof(commands)/sizeof(*commands);i++) {
            command=0;
            assert(mmce_fs_devctl(&f,"",commands[i],NULL,0,NULL,0)==reply);
            assert(command==commands[i] && port==unit+2);
        }
        assert(mmce_fs_devctl(&f,"",MMCE_CMD_SET_GAMEID,(void *)game_id,sizeof(game_id),NULL,0)==reply);
        assert(command==MMCE_CMD_SET_GAMEID && !resets);
        assert(mmce_fs_devctl(&f,"",MMCE_CMD_GET_GAMEID,NULL,0,id,sizeof(id))==reply);
        assert(!strcmp(id,game_id) && !resets);
        u8 packed[]={1,0x12,0x34,0x56,0x78};
        command=0;
        assert(mmce_fs_devctl(&f,"",MMCE_CMD_SET_CARD_CHANNEL,packed,4,NULL,0)<0 && !command);
        assert(mmce_fs_devctl(&f,"",MMCE_CMD_SET_CARD_CHANNEL,packed,5,NULL,0)==reply);
        assert(card_type==1 && card_number==0x1234 && channel_number==0x5678);
        reply=-1;
        assert(mmce_fs_devctl(&f,"",MMCE_CMD_SET_GAMEID,(void *)game_id,sizeof(game_id),NULL,0)==-1);
        reply=7;
    }
    assert(port_changes==2 && !resets);
    puts("PASS: MMCE path bounds and both-slot ping/status/Game ID/card commands survive backup removal without resetting the card");
}
'''
compiler = shutil.which('gcc') or shutil.which('cc')
assert compiler, 'Host C compiler required'
with tempfile.TemporaryDirectory(prefix='launchstation-mmce-paths-') as tmp:
    src, exe = Path(tmp) / 'test.c', Path(tmp) / 'test'
    src.write_text(code)
    subprocess.run([compiler, '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-I', str(header.parent), str(src), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
