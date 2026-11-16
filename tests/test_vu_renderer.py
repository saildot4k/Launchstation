"""Run production VU1/gsKit ordering boundaries against DMA/GS ownership spies."""
from pathlib import Path
import os
import subprocess
import tempfile
root=Path(__file__).resolve().parents[1]
source=(root/'src/dash_gfx.c').read_text()
def function(signature):
 start=source.index(signature);end=source.index('{',start)+1;depth=1
 while depth:
  depth+=(source[end]=='{')-(source[end]=='}');end+=1
 return source[start:end]+'\n'
code=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "dash_vu1.h"
#define DASH_VU1_REFERENCE 0
static struct {int OffsetX,OffsetY,PrimContext;} screen={32768,32768,1},*gsGlobal=&screen;
static struct {int screen_x,screen_y;} settings={3,-2},*setting=&settings;
static float g_alpha=1,g_sy=512.0f/448.0f,g_ox=7,g_oy=9;
static int g_blend,gsScreenGeneration=4;
static int available=1,active,fail_begin,fail_end,fail_append,drained,idle;
static int submitted,finished,waits,resets,offsets,texture_resets,appended,states;
#define GS_ONESHOT 0
#define GS_ATEST_OFF 0
#define GS_CMODE_CLAMP 0
#define DASH_BLEND_NORMAL 0
static float SX(float value){return value+g_ox;}
static float SY(float value){return (value+g_oy)*g_sy;}
static void dashSpriteBatchEnd(void){}
static void gsKit_queue_exec(void *gs){assert(gs==gsGlobal&&!active);submitted++;drained=idle=0;}
static void dmaKit_wait_fast(void){assert(submitted);waits++;drained=1;}
static void gsKit_finish(void){assert(drained);idle=1;finished++;}
static void gsKit_init_screen(void *gs){assert(gs==gsGlobal&&!active);resets++;}
static void gsKit_set_display_offset(void *gs,int x,int y){assert(gs==gsGlobal&&x==3&&y==-2);offsets++;}
static void dashGfxCheckScreenChange(void){texture_resets++;}
static void dashGfxBlend(int value){assert(value==DASH_BLEND_NORMAL);states++;}
static void gsKit_set_test(void *gs,int value){assert(gs==gsGlobal&&!value);states++;}
static void gsKit_set_clamp(void *gs,int value){assert(gs==gsGlobal&&!value);states++;}
static void dashGfxScissorReset(void){states++;}
int dashVu1Available(void){return available;}
int dashVu1Begin(const DashVu1Screen *s,int generation){
 assert(drained&&idle&&!active&&generation==4);
 assert(s->cx==327&&s->cy==(224+9)*g_sy&&s->scale_x==1.18f&&s->scale_y==g_sy);
 assert(s->offset_x==32768&&s->offset_y==32768&&s->context==1);
 active=!fail_begin;return active;
}
int dashVu1Append(const DashVu1Vertex v[4]){
 assert(active);appended++;
 for(int i=0;i<4;i++){
  assert(v[i].direction[0]==(i&1?3:1)&&v[i].direction[1]==(i&1?4:2));
  assert(v[i].direction[2]==(i<2?5:6));
  assert(v[i].color[0]==(i<2?1:4)&&v[i].color[1]==(i<2?2:5)&&v[i].color[2]==(i<2?3:6)&&v[i].color[3]==128);
 }
 return !fail_append;
}
int dashVu1End(void){active=0;return !fail_end;}
'''
for signature in ('static void recoverVu1Screen(', 'int dashGfxVu1Begin(', 'int dashGfxVu1Quad(', 'int dashGfxVu1End('):
 code+=function(signature)
code+=r'''
int main(void){
 available=0;assert(!dashGfxVu1Begin(320,224)&&!submitted&&!resets);available=1;
 g_alpha=0.5f;assert(!dashGfxVu1Begin(320,224)&&!submitted&&!resets);g_alpha=1;
 assert(dashGfxVu1Begin(320,224)&&active&&submitted==1&&waits==1&&finished==1&&!resets);
 assert(dashGfxVu1Quad(1,2,3,4,5,6,0x80030201,0x80060504)&&appended==1);
 assert(dashGfxVu1End()&&!active&&!resets&&gsScreenGeneration==4);
 fail_begin=1;assert(dashGfxVu1Begin(320,224)==-1&&!active&&resets==1&&offsets==1&&texture_resets==1&&states==4&&gsScreenGeneration==5);
 fail_begin=0;gsScreenGeneration=4;
 assert(dashGfxVu1Begin(320,224));fail_end=1;
 assert(!dashGfxVu1End()&&!active&&resets==2&&offsets==2&&texture_resets==2&&gsScreenGeneration==5);
 puts("PASS: queued PATH3 clear/state drains before VU1, calibrated/scaled context and colors, no healthy-path screen reset, CPU fallback gates and complete texture/state recovery after faults");
}
'''
with tempfile.TemporaryDirectory(prefix='vu-renderer-') as folder:
 folder=Path(folder);(folder/'test.c').write_text(code)
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-I',str(root/'include'),
  str(folder/'test.c'),'-o',str(folder/'test')],check=True)
 subprocess.run([str(folder/'test')],check=True)
