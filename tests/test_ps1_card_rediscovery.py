"""Exercise physical MCMAN rediscovery with powered PS1 cards across IOP resets.

The real detection and header-validation functions run against simulated card
transport, including mixed PS1/PS2 slots and I/O errors. Physical SIO2 timing
is not emulated. An optional filename substitutes an older mcsio2.c snapshot.
"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sio = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else (root / 'iop/vmcman/src/mcsio2.c').read_text()
main = (root / 'iop/vmcman/src/main.c').read_text()
internal = (root / 'iop/vmcman/src/mcman-internal.h').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


start = internal.index('typedef struct {', internal.index('extern int mcman_iomanx_backing_'))
end = internal.index('MCDevInfo;', start) + len('MCDevInfo;')
code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
#define DPRINTF(...) ((void)0)
#define sceMcResSucceed 0
#define sceMcResChangedCard -1
#define sceMcResNoFormat -2
#define sceMcResDeniedPS1Permit -51
#define sceMcTypeNoCard 0
#define sceMcTypePS1 1
#define sceMcTypePS2 2
#define sceMcTypePDA 3
''' + internal[start:end] + r'''
static MCDevInfo mcman_devinfos[2][1];
static union {u8 byte[128];u32 word[32];} mcman_PS1PDApagebuf;
static struct {u32 regdata[16];int in_size,out_size;u32 stat6c;} mcman_sio2packet_PS1PDA;
static u8 mcman_sio2inbufs_PS1PDA[144];
static u8 mcman_sio2outbufs_PS1PDA[144] __attribute__((aligned(16)));
static u32 mcman_timercount,ticks;
static int mcman_timerthick,timer_ID,PS1CardFlag=1;
static u8 cards[2][131072],before[131072];
static int card_types[2],card_status[2],read_error[2],write_error[2],directory_error[2];
static int reads[2],writes[2],cached[2],invalidated[2],cleared[2],transfers[2],transport_error[2];
typedef struct {
 int mode,length;int16_t linked_block;char name[20];u8 field_1e,field_1f;
 u8 created[8];int field_28;u16 field_2c,field_2e;u8 modified[8];int field_38;
 u8 unused2[65],field_7d,field_7e,edc;
} McFsEntryPS1;
typedef struct {int wr_flag;} McCacheEntry;
static McCacheEntry directory_cache[2][2],*last_directory;
static u8 directory_data[2][2048] __attribute__((aligned(16)));
static int real_cachePS1dirs(int port,int slot);
static int mcman_readdirentryPS1(int port,int slot,int entry,McFsEntryPS1 **out){
 assert(!slot&&entry>=0&&entry<15);
 *out=(McFsEntryPS1 *)(directory_data[port]+(entry+1)*128);
 last_directory=&directory_cache[port][entry<7?0:1];return 0;
}
static McCacheEntry *mcman_get1stcacheEntp(void){return last_directory;}
static int mcman_probePS1Card(int port,int slot);
static int mcman_setPS1devinfos(int port,int slot);
static u32 GetTimerCounter(int timer){(void)timer;return ticks+=10000;}
static void long_multiply(u32 a,u32 b,u32 *hi,u32 *lo){uint64_t x=(uint64_t)a*b;*hi=x>>32;*lo=x;}
static void DelayThread(int us){(void)us;}
static void mcsio2_transfer(int port,int slot,void *packet){
 assert(port>=0&&port<2&&!slot&&packet==&mcman_sio2packet_PS1PDA);
 transfers[port]++;
 mcman_sio2packet_PS1PDA.stat6c=transport_error[port]?0:0x1000;
 mcman_sio2outbufs_PS1PDA[1]=card_status[port];
 mcman_sio2outbufs_PS1PDA[2]=card_types[port]==1?0x5a:0;
}
static int McReadPS1PDACard(int port,int slot,int page,void *out){
 assert(!slot&&page>=0&&page<1024);reads[port]++;
 if(read_error[port])return -4;
 memcpy(out,cards[port]+page*128,128);mcman_sio2outbufs_PS1PDA[1]=card_status[port];return 0;
}
static int McWritePS1PDACard(int port,int slot,int page,void *data){
 assert(!slot&&page==63);writes[port]++;
 if(write_error[port])return -4;
 memcpy(cards[port]+page*128,data,128);card_status[port]=0;return 0;
}
static int mcman_cachePS1dirs(int port,int slot){
 assert(!slot&&mcman_devinfos[port][slot].pagesize==128);
 assert(mcman_devinfos[port][slot].cluster_size==8192);
 cached[port]++;if(directory_error[port])return directory_error[port];
 memcpy(directory_data[port],cards[port],2048);return real_cachePS1dirs(port,slot);
}
static void mcman_clearcache(int port,int slot){assert(!slot);cleared[port]++;memset(directory_cache[port],0,sizeof(directory_cache[port]));}
static void mcman_invhandles(int port,int slot){assert(!slot);invalidated[port]++;}
static int mcman_probePS2Card(int port,int slot){
 assert(!slot);if(card_types[port]!=2)return -13;
 MCDevInfo *d=&mcman_devinfos[port][slot];
 if(d->cardtype==2&&d->cardform==1)return 0;
 memset(d,0,sizeof(*d));d->cardtype=2;d->cardform=1;d->cluster_size=1024;return -1;
}
static int mcman_probePS2Card2(int port,int slot){
 return card_types[port]==2&&mcman_devinfos[port][slot].cardform==1?0:-13;
}
static int mcman_probePDACard(int port,int slot){assert(!slot&&card_types[port]==1);return -1;}
''' + function(main, 'int mcman_calcEDC(')
code += '#define mcman_cachePS1dirs real_cachePS1dirs\n' + function(main, 'int mcman_cachePS1dirs(') + '#undef mcman_cachePS1dirs\n'
code += function(main, 'int mcman_setPS1devinfos(')
code += function(sio, 'int mcman_probePS1Card2(') + function(sio, 'int mcman_probePS1Card(')
code += function(main, 'int mcman_detectcard(') + function(main, 'int McDetectCard2(')
code += function(main, 'int McDetectCard(') + r'''
static void clear_driver(void){
 memset(mcman_devinfos,0,sizeof(mcman_devinfos));memset(directory_cache,0,sizeof(directory_cache));
 memset(reads,0,sizeof(reads));memset(writes,0,sizeof(writes));memset(cached,0,sizeof(cached));
 memset(invalidated,0,sizeof(invalidated));memset(cleared,0,sizeof(cleared));memset(transfers,0,sizeof(transfers));
}
static void make_card(int port){
 memset(cards[port],0xff,sizeof(cards[port]));cards[port][0]='M';cards[port][1]='C';
 for(int i=0;i<15;i++){
  McFsEntryPS1 entry;memset(&entry,0,sizeof(entry));assert(sizeof(entry)==128);
  entry.mode=i==0?0x51:i==1?0x53:0xa0;entry.linked_block=i==0?1:-1;
  if(!i){entry.length=16384;strcpy(entry.name,"BASLUS-TEST");}
  entry.edc=mcman_calcEDC(&entry,127);memcpy(cards[port]+(i+1)*128,&entry,128);
 }
 for(int i=8192;i<131072;i++)cards[port][i]=(u8)(i*17+port*31);
 cards[port][8192]='S';cards[port][8193]='C';
 card_types[port]=1;card_status[port]=0;
 read_error[port]=write_error[port]=directory_error[port]=transport_error[port]=0;
}
int main(void){
 int (*detect[])(int,int)={McDetectCard2,mcman_detectcard,McDetectCard};
 for(int reverse=0;reverse<2;reverse++)for(int cycle=0;cycle<12;cycle++) {
  int ps1=reverse,ps2=1-reverse;
  make_card(ps1);make_card(ps2);card_types[ps2]=2;
  for(unsigned path=0;path<sizeof(detect)/sizeof(*detect);path++){
   clear_driver();assert(McDetectCard2(ps2,0)==-1);
   MCDevInfo other=mcman_devinfos[ps2][0];
   memcpy(before,cards[ps1],sizeof(before));
   assert(detect[path](ps1,0)==sceMcResChangedCard);
   assert(mcman_devinfos[ps1][0].cardtype==1&&mcman_devinfos[ps1][0].cardform==1);
   assert(mcman_devinfos[ps1][0].clusters_per_card==16&&cached[ps1]==1&&reads[ps1]==21);
   assert(writes[ps1]==0&&!memcmp(cards[ps1],before,sizeof(before)));
   assert(!directory_cache[ps1][0].wr_flag&&!directory_cache[ps1][1].wr_flag);
   McFsEntryPS1 *first=(McFsEntryPS1 *)(directory_data[ps1]+128);
   McFsEntryPS1 *second=(McFsEntryPS1 *)(directory_data[ps1]+256);
   assert(first->mode==0x51&&first->length==16384&&first->linked_block==1&&second->mode==0x53);
   assert(!memcmp(&mcman_devinfos[ps2][0],&other,sizeof(other)));
   assert(!reads[ps2]&&!writes[ps2]&&!invalidated[ps2]&&!cleared[ps2]);
   int read_count=reads[ps1];
   for(int n=0;n<8;n++)assert(!detect[path](ps1,0)&&!McDetectCard2(ps2,0));
   assert(reads[ps1]==read_count&&cached[ps1]==1&&!writes[ps1]);
  }
 }
 puts("PASS: powered PS1 cards rediscover through full/fast/public detection after repeated resets, both slots with a PS2 card, without writes or cross-slot cache changes");
 for(int port=0;port<2;port++){
  make_card(port);clear_driver();card_status[port]=8;
  memcpy(before,cards[port],sizeof(before));
  /* Existing new-card handling acknowledges only the reserved page, then reads metadata. */
  assert(McDetectCard2(port,0)==-1&&writes[port]==1&&cached[port]==1);
  assert(!memcmp(before+8192,cards[port]+8192,sizeof(before)-8192));
  clear_driver();assert(mcman_detectcard(port,0)==-1&&cached[port]==1&&!writes[port]);
  assert(!McDetectCard2(port,0));
  /* An old PS2 cache cannot authorize PS1 access with PS2 geometry. */
  clear_driver();mcman_devinfos[port][0].cardtype=2;mcman_devinfos[port][0].cardform=1;
  assert(mcman_detectcard(port,0)==-1&&mcman_devinfos[port][0].cluster_size==8192&&!writes[port]);
  /* Header validation must distinguish a genuinely unformatted card. */
  clear_driver();cards[port][0]=0;
  assert(McDetectCard2(port,0)==sceMcResNoFormat&&mcman_devinfos[port][0].cardform==-1);
  int r=reads[port];assert(mcman_probePS1Card(port,0)==-2&&mcman_probePS1Card2(port,0)==-2&&reads[port]==r);
  cards[port][0]='M';clear_driver();read_error[port]=1;
  assert(McDetectCard2(port,0)<-9&&mcman_devinfos[port][0].cardform==0&&!writes[port]);
  read_error[port]=0;assert(McDetectCard2(port,0)==-1&&!writes[port]);
  clear_driver();directory_error[port]=-43;
  assert(mcman_detectcard(port,0)<-9&&mcman_devinfos[port][0].cardform==0&&!writes[port]);
  directory_error[port]=0;assert(mcman_detectcard(port,0)==-1);
  clear_driver();transport_error[port]=1;
  assert(mcman_probePS1Card(port,0)==-11&&transfers[port]==5&&!reads[port]&&!writes[port]);
  transport_error[port]=0;card_status[port]=3;
  assert(mcman_probePS1Card(port,0)==-12&&!writes[port]);
  card_status[port]=8;write_error[port]=1;
  assert(McDetectCard2(port,0)<-9&&mcman_devinfos[port][0].cardform==0);
  write_error[port]=0;card_status[port]=0;clear_driver();PS1CardFlag=0;
  assert(McDetectCard2(port,0)==sceMcResDeniedPS1Permit&&!writes[port]);PS1CardFlag=1;
 }
 puts("PASS: cold insertion acknowledgement, stale PS2 metadata, true unformatted cards, denied PS1 access and transport/header/directory errors retain their contracts");
}
'''

# Check that both build paths actually ship these physical-card branches.
project = (root / 'ps2.yaml').read_text()
physical = project[project.index('  - name: mcman_physical\n'):project.index('  - name: vmcman\n')]
assert 'iop/vmcman/src/mcsio2.c' in physical and 'BUILDING_VMCMAN' not in physical
assert 'defines: [BUILDING_XMCMAN]' in physical  # Same SIO2 1.2 imports as the prior SDK physical driver.
assert '      - mcman_physical:mcman\n' in project and '      - mcman\n' not in project
embed = (root / 'embed.make').read_text()
assert 'MCMAN_SOURCE := $(MCMAN_AUTOGEN)' in embed
assert 'MCMAN_BUILDING_VMCMAN=0' in embed and 'iop/__generated/mcman_obj' in embed
assert 'MCMAN_BUILDING_XMCMAN_V2=0' in embed

with tempfile.TemporaryDirectory(prefix='ps1-card-rediscovery-') as folder:
    folder = Path(folder)
    source = folder / 'test.c'
    source.write_text(code)
    flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if os.environ.get('SANITIZE') else []
    for variant in ([], ['-DBUILDING_XMCMAN=1']):
        executable = folder / 'test'
        subprocess.run([os.environ.get('CC', 'cc'), '-std=c99', '-Wall', '-Wextra', '-Werror',
                        *flags, *variant, str(source), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True, timeout=15, cwd=folder)
print('PASS: PS2BUILD and legacy Makefile embed the local physical-card driver')
