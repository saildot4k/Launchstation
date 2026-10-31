"""Run the production transfer layout, byte labels and rates with large files."""
from pathlib import Path
import shutil
import subprocess
import tempfile
root = Path(__file__).resolve().parents[1]
source = (root/'src/dash_ui.c').read_text()
a=source.index('static void loadingTransferBytes(')
b=source.index('void dashLoadingFrame(',a)
header=(root/'include/dash.h').read_text()
start=header.index('typedef struct\n{\n\tu64 written_total;')
stats_type=header[start:header.index('} DashTransferStats;',start)+len('} DashTransferStats;')]
start=source.index('static void loadingDraw(')
render_source=source[start:source.index('void dashLoadingBegin(',start)]
globals_source=source[source.index('static int loading_active;'):source.index('DashLoadingView dashLoadingSetView(')]
label_gap=next(line for line in source.splitlines() if line.startswith('#define STACKED_LABEL_GAP '))
code=label_gap+'\n'+r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint64_t u64;
typedef int DashColor;
typedef void (*DashLoadingView)(const char *);
'''+globals_source+r'''
static int active=1,worker,draws;
static u64 tick;
static int DashIsActive(void){return active;}
static int dashWorkerOnThread(void){return worker;}
static u64 Timer(void){return tick;}
static void dashStrCopy(char *a,const char *b,int cap){snprintf(a,cap,"%s",b);}
#define DASH_VW 640
#define DASH_VH 448
#define DASH_FS_LABEL 0.9f
#define DASH_FS_SMALL 0.66f
#define DASH_C_TEXT 1
#define DASH_C_TEXT2 2
#define DASH_C_TEXT3 3
#define DASH_C_ACCENT 4
#define DASH_BLEND_ADD 1
#define DASH_BLEND_NORMAL 0
static float panel_x,panel_y,panel_w,panel_h,bar_y,hint_y;
static int text_count,bars;
static struct {float x,y,w;int right;char text[128];} texts[16];
static float dashVisualUpdate(void){return 0.016f;}
static float dashApproach(float v,float target,float rate,float dt){(void)v;(void)rate;(void)dt;return target;}
static float dashClampf(float v,float lo,float hi){return v<lo?lo:v>hi?hi:v;}
static void dashRenderScene(void){text_count=bars=0;hint_y=0;}
static void modalBackdrop(float a){(void)a;}
static void dashGfxPushAlpha(float a){(void)a;}
static void modalPanel(float x,float y,float w,float h,float alpha){
 (void)alpha;panel_x=x;panel_y=y;panel_w=w;panel_h=h;
 assert(y>=0&&y+h<=DASH_VH);
}
static void dashGfxBlend(int mode){(void)mode;}
static void dashDrawSpinner(float x,float y,float r,DashColor c){(void)x;(void)y;(void)r;(void)c;}
static void dashTextFit(float x,float y,float w,const char *text,float scale,DashColor color){
 (void)scale;(void)color;assert(text_count<16&&x>=panel_x&&x+w<=panel_x+panel_w);
 assert(y>panel_y&&y+16<panel_y+panel_h);
 texts[text_count].x=x;texts[text_count].y=y;texts[text_count].w=w;texts[text_count].right=0;
 snprintf(texts[text_count++].text,128,"%s",text);
}
static void dashTextRight(float x,float y,const char *text,float scale,DashColor color){
 float width=strlen(text)*6.0f;dashTextFit(x-width,y,width,text,scale,color);texts[text_count-1].right=1;
}
static DashColor dashColorA(DashColor c,float a){(void)a;return c;}
static void loadingBarShape(float x,float y,float w,DashColor c){
 (void)x;(void)w;(void)c;if(!bars)bar_y=y;bars++;assert(y+8<panel_y+panel_h);
}
static int dashBackIcon(void){return 0;}
static void modalHintRow(float x,float y,int a,const char *s,int b,const char *t){
 (void)x;(void)a;(void)s;(void)b;(void)t;hint_y=y;
}
static void dashGfxPopAlpha(void){}
static void dashGfxPresent(void){draws++;}
static void dashLoadingBegin(const char *s){loading_active=1;snprintf(loading_title,sizeof(loading_title),"%s",s);}
'''+stats_type+'\n'+render_source+source[a:b]+r'''
int main(void){
 loading_active=1;
 assert(DashFileProgress("Pasting file","BOOT.ELF",8ULL<<30,8ULL<<30));
 assert(!strcmp(loading_status,"BOOT.ELF")&&!strcmp(loading_copied,"0.00 MB"));
 assert(!strcmp(loading_transfer[2],"8192.00 MB")&&loading_done==0&&loading_total==10000&&!draws);
 tick=20;DashFileProgress("Pasting file","BOOT.ELF",4ULL<<30,8ULL<<30);
 assert(loading_done==5000&&draws==1&&!strcmp(loading_copied,"4096.00 MB"));
 tick=21;DashFileProgress("Pasting file","BOOT.ELF",4ULL<<30,8ULL<<30);assert(draws==1);
 DashFileProgress("Pasting file","BOOT.ELF",0,8ULL<<30);assert(loading_done==10000&&draws==2);
 assert(!strcmp(loading_copied,"8192.00 MB"));
 loading_fraction=1;DashFileProgress("Pasting file","SECOND.ELF",1024,1024);
 assert(loading_fraction==0&&loading_done==0&&!strcmp(loading_copied,"0 KB"));
 assert(!strcmp(loading_transfer[2],"1 KB"));
 DashFileProgress("Pasting file","empty",0,0);assert(loading_done==10000);
 assert(!strcmp(loading_copied,"0 KB")&&!strcmp(loading_transfer[2],"0 KB"));
 DashFileProgress("Pasting file","bad count",200,100);assert(loading_done==0);
 assert(!strcmp(loading_copied,"0 KB"));
 char bytes[64];loadingTransferBytes(bytes,sizeof(bytes),1,1);assert(!strcmp(bytes,"0.00 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),2048,2048);assert(!strcmp(bytes,"2 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),512,512);assert(!strcmp(bytes,"0.50 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),1024,1024);assert(!strcmp(bytes,"1 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),1200ULL*1024+999,1200ULL*1024+999);assert(!strcmp(bytes,"1200 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),(1ULL<<20)-1,(1ULL<<20)-1);assert(!strcmp(bytes,"1023 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),1ULL<<20,1ULL<<20);assert(!strcmp(bytes,"1024 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),512,1ULL<<20);assert(!strcmp(bytes,"0.50 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),3ULL<<20,3ULL<<20);assert(!strcmp(bytes,"3072 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),0,(1ULL<<30)-1);assert(!strcmp(bytes,"0 KB"));
 loadingTransferBytes(bytes,sizeof(bytes),1ULL<<30,1ULL<<30);assert(!strcmp(bytes,"1024.00 MB"));
 loadingTransferBytes(bytes,sizeof(bytes),8ULL<<30,8ULL<<30);assert(!strcmp(bytes,"8192.00 MB"));
 loadingTransferBytes(bytes,sizeof(bytes),0,(1ULL<<40)-1);assert(!strcmp(bytes,"0.00 MB"));
 loadingTransferBytes(bytes,sizeof(bytes),1ULL<<40,1ULL<<40);assert(!strcmp(bytes,"1024.00 GB"));
 loadingTransferBytes(bytes,sizeof(bytes),UINT64_MAX,UINT64_MAX);assert(strstr(bytes,"GB"));
 DashTransferStats stats={8ULL<<30,2048,1024,3661,1,10};
 tick+=20;DashFileTransferProgress("Pasting file","BIG.ELF",4ULL<<30,8ULL<<30,&stats);
 assert(!strcmp(loading_title,"Pasting file 1 of 10"));
 assert(!strcmp(loading_transfer[0],"Average speed: 1024 B/s"));
 assert(!strcmp(loading_transfer[1],"Remaining time: 1 h 1 m 1 sec"));
 assert(!strcmp(loading_copied,"4096.00 MB")&&!strcmp(loading_transfer[2],"8192.00 MB"));
 assert(panel_w==420&&panel_h==210&&panel_x==110&&panel_y==119&&text_count==6);
 assert(!strcmp(texts[0].text,loading_title)&&!strcmp(texts[1].text,"BIG.ELF"));
 assert(texts[1].y+16<bar_y&&texts[2].y==bar_y+8+STACKED_LABEL_GAP);
 assert(texts[2].y==texts[3].y&&texts[2].x==panel_x+30&&!texts[2].right&&texts[3].right);
 assert(texts[2].x+texts[2].w<texts[3].x);
 assert(texts[3].x+texts[3].w==panel_x+panel_w-30);
 assert(texts[3].y+16<texts[4].y&&texts[4].y+16<texts[5].y&&texts[5].y+16<panel_y+panel_h);
 loading_cancel=1;loadingDraw();
 assert(panel_h==238&&hint_y>texts[5].y+16&&hint_y+16<panel_y+panel_h);loading_cancel=0;
 loading_fraction=0.5f;DashFileTransferProgress("Pasting file","BIG.ELF",2ULL<<30,8ULL<<30,&stats);
 assert(loading_fraction==0.5f&&!strcmp(loading_copied,"6144.00 MB"));
 stats.file_index=2;DashFileTransferProgress("Pasting file","BIG.ELF",8ULL<<30,8ULL<<30,&stats);
 assert(!strcmp(loading_title,"Pasting file 2 of 10")&&loading_fraction==0);
 char long_name[256];memset(long_name,'x',255);long_name[255]=0;
 DashFileTransferProgress("Pasting file",long_name,100,200,&stats);loading_fraction=0.5f;
 DashFileTransferProgress("Pasting file",long_name,50,200,&stats);assert(loading_fraction==0.5f);
 stats.current_speed=stats.average_speed=stats.remaining_seconds=-1;
 DashFileTransferProgress("Pasting file","BIG.ELF",100,100,&stats);
 assert(!strcmp(loading_transfer[0],"Average speed: Unknown"));
 assert(!strcmp(loading_transfer[1],"Remaining time: Unknown"));
 stats.average_speed=2147483647;stats.remaining_seconds=61;
 DashFileTransferProgress("Pasting file","BIG.ELF",10,100,&stats);
 assert(!strcmp(loading_transfer[0],"Average speed: 2097151 KB/s"));
 assert(!strcmp(loading_transfer[1],"Remaining time: 1 m 1 sec"));
 stats.remaining_seconds=59;DashFileTransferProgress("Pasting file","BIG.ELF",10,100,&stats);
 assert(!strcmp(loading_transfer[1],"Remaining time: 59 sec"));
 stats.remaining_seconds=0;DashFileTransferProgress("Pasting file","BIG.ELF",0,100,&stats);
 assert(!strcmp(loading_transfer[1],"Remaining time: 0 sec")&&loading_done==10000);
 DashFileProgress("Verifying file","BIG.ELF",10,100);loadingDraw();
 assert(!loading_transfer[0][0]&&text_count==4&&panel_h==154);
 assert(!strcmp(loading_copied,"0.09 KB")&&!strcmp(loading_transfer[2],"0.10 KB"));
 DashFileTransferProgress("Pasting file","BIG.ELF",10,100,&stats);
 loading_active=0;tick+=20;DashFileTransferProgress("Pasting file","SECOND.ELF",100,100,&stats);
 assert(loading_active&&loading_done==0&&loading_fraction==0);
 int old=draws;worker=1;assert(!DashFileProgress("Pasting file","unsafe",0,0));
 DashFileDeleteProgress("unsafe");assert(draws==old);worker=0;
 active=0;assert(!DashFileProgress("Pasting file","classic",0,0));active=1;
 tick+=20;DashFileDeleteProgress("nested.bin");
 assert(!strcmp(loading_title,"Deleting file")&&!strcmp(loading_status,"nested.bin"));
 assert(!loading_transfer[0][0]&&!loading_copied[0]&&!loading_total&&!loading_done&&loading_fraction==0);
 loading_total=10;loading_done=3;DashFileDeleteProgress("another.bin");assert(loading_total==10&&loading_done==3);
 puts("PASS: numbered file title, filename, bounded rounded bar and advancing size labels matching the tab icon/text gap, average/ETA order, sizes through 64-bit and modal ownership");
}
'''
# Renderer uses the scene tick once and bounds its fill to the track.
renderer=source[source.index('static void loadingDraw('):source.index('void dashLoadingBegin(')]
assert renderer.count('dashVisualUpdate()')==1
assert '(w - 60) * loading_fraction' in renderer and '* p + 8' not in renderer
assert 'dashTextFit(x + 84, y + 26' in renderer
copy=(root/'src/filer_copy.c').read_text()
assert 'if (!DashFileTransferProgress("Pasting file", file.name, size, original_size, &transfer_stats))' in copy
assert 'buffSize = 16384' in copy
assert 'DashFileDeleteProgress(file->name)' in (root/'src/filer_actions.c').read_text()
def function(text, signature):
 a=text.index(signature);b=text.index('{',a)+1;depth=1
 while depth:
  depth+=(text[b]=='{')-(text[b]=='}');b+=1
 return text[a:b]+'\n'
math_code=r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
typedef uint64_t u64;
#define TRANSFER_ETA_UPDATE_MS 1000
static u64 written_size,CurrentTime,OldTime,EtaOldTime,old_size,eta_old_size,SizeDiff,EtaSizeDiff,tick;
static int TimeDiff,EtaTimeDiff,speed,remain_time=-1,smooth_speed=-1,eta_sample_speed;
static u64 Timer(void){return tick;}
"""
for sig in ('static int calcTransferSpeed(', 'static int calcRemainingTime(', 'static int smoothTransferSpeed('):
 math_code+=function(copy,sig)
start=copy.index('\t\tCurrentTime = Timer();')
end=copy.index('\t\tsprintf(progress,',start)
math_code+='static void sample(u64 when,u64 written,u64 size) {\ntick=when;written_size=written;\n'+copy[start:end]+'}\n'
math_code+=r"""
int main(void) {
 assert(calcTransferSpeed(1024,1000)==1024);
 assert(calcTransferSpeed(1024,250)==4096);
 assert(calcTransferSpeed(8ULL<<30,1000)==INT_MAX);
 assert(calcTransferSpeed(0,1)==0 && calcTransferSpeed(1,0)==-1);
 assert(calcTransferSpeed(0,0)==-1 && calcTransferSpeed(1,-1)==-1);
 assert(calcRemainingTime(8192,1024)==8);
 assert(calcRemainingTime(8191,1024)==7); /* R3Z rounds down to whole seconds */
 assert(calcRemainingTime(8ULL<<30,1)==INT_MAX);
 assert(calcRemainingTime(1024,0)==-1 && calcRemainingTime(1024,-1)==-1);
 assert(smoothTransferSpeed(-1,1000)==1000 && smoothTransferSpeed(0,1000)==1000);
 assert(smoothTransferSpeed(1000,2000)==1250);
 assert(smoothTransferSpeed(1000,0)==0 && smoothTransferSpeed(1000,-1)==-1);
 assert(smoothTransferSpeed(INT_MAX,INT_MAX)==INT_MAX);
 OldTime=EtaOldTime=1000;
 sample(1000,0,1000);assert(speed==-1 && remain_time==-1);
 sample(1500,250,750);assert(speed==500 && remain_time==-1);
 sample(2000,500,500);assert(speed==500 && smooth_speed==500 && remain_time==1);
 sample(3000,1500,3500);assert(speed==1000 && smooth_speed==625 && remain_time==5);
 sample(4000,1500,3500);assert(speed==0 && smooth_speed==0 && remain_time==-1);
 sample(5000,2500,2500);assert(speed==1000 && smooth_speed==1000 && remain_time==2);
 sample(5010,2700,2300);assert(speed==20000 && remain_time==2); /* wait for next ETA window */
 puts("PASS: R3Z 4.80 chunk speed, 1-second ETA samples, 75/25 smoothing, stalls and 64-bit/clamped arithmetic");
}
"""
with tempfile.TemporaryDirectory(prefix='transfer-progress-') as folder:
 p=Path(folder);(p/'test.c').write_text(code)
 subprocess.run([shutil.which('gcc'),'-std=c99','-Wall','-Wextra','-Werror',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
 (p/'rates.c').write_text(math_code)
 subprocess.run([shutil.which('gcc'),'-std=c99','-Wall','-Wextra','-Werror',str(p/'rates.c'),'-o',str(p/'rates')],check=True)
 subprocess.run([str(p/'rates')],check=True)
