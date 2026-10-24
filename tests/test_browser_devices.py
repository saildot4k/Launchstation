"""Execute shared root labels and browser/picker row rendering on the host."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
browser = (root / 'src/filer_browser.c').read_text()
widgets = (root / 'src/dash_widgets.c').read_text()
devices = (root / 'src/dash_devices.c').read_text()
header = (root / 'include/dash_internal.h').read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end] + '\n'


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define LNG(x) #x
#define DASH_FS_SMALL 0.66f
#define DASH_C_TEXT3 3
#define DI_USB 1
#define MAX_PATH 1024
typedef int DashColor;
'''
code += header[header.index('enum DashDevState'):header.index('void dashDevicesInit(void)')]
code += function(browser, 'const char *filerRootDeviceDescription(')
code += function(browser, 'int filerFormatUsbPathForDisplay(')
code += function(browser, 'static void formatRootDeviceMountForDisplay(')
code += function(devices, 'const char *dashDeviceDisplayMount(')
code += r'''
typedef struct { float x,y,w,size;int color,scroll;char text[96]; } Text;
static Text texts[2];
static int ntexts,icon_calls;
static float icon_x,icon_y;
static DashColor dashItemColor(int selected) { return selected?9:7; }
static void dashIcon(int icon,float x,float y,float size,DashColor color) {
    (void)icon;(void)color;assert(size==16);icon_calls++;icon_x=x;icon_y=y;
}
static void record(float x,float y,float w,const char *text,float size,DashColor color,int scroll) {
    assert(ntexts<2 && w>0);
    Text *t=&texts[ntexts++];t->x=x;t->y=y;t->w=w;t->size=size;t->color=color;t->scroll=scroll;
    snprintf(t->text,sizeof(t->text),"%s",text);
}
static void dashTextFit(float x,float y,float w,const char *text,float size,DashColor color) {
    record(x,y,w,text,size,color,0);
}
static void dashTextScroll(float x,float y,float w,const char *text,float size,DashColor color) {
    record(x,y,w,text,size,color,1);
}
'''
code += function(widgets, 'void dashDrawDeviceRow(')
code += r'''
static void row(const char *mount,const char *path,const char *wanted,const char *description) {
    DashDevice d={.icon=DI_USB};
    snprintf(d.mount,sizeof(d.mount),"%s",mount);snprintf(d.browse,sizeof(d.browse),"%s",path);
    strcpy(d.name,"Fallback description");
    for(int picker=0;picker<2;picker++) for(int selected=0;selected<2;selected++) for(int ready=0;ready<2;ready++) {
        float x=picker?96:40,y=picker?81:100,w=picker?448:560;
        d.state=ready?DASH_DEV_READY:DASH_DEV_ABSENT;DashDevice original=d;
        ntexts=icon_calls=0;dashDrawDeviceRow(&d,x,y,w,selected);
        assert(ntexts==2 && icon_calls==1 && icon_x==x+10 && icon_y==y+2);
        assert(!memcmp(&d,&original,sizeof(d)));
        assert(!strcmp(texts[0].text,wanted) && !strcmp(texts[1].text,description));
        assert(texts[0].x==x+36 && texts[1].x==320 && texts[0].y==y && texts[1].y==y);
        assert(texts[0].x+texts[0].w+16==texts[1].x && texts[1].x+texts[1].w<=x+w-12);
        assert(texts[0].size==DASH_FS_SMALL && texts[1].size==DASH_FS_SMALL);
        assert(!texts[0].scroll && texts[1].scroll==selected);
        int color=selected?9:ready?7:DASH_C_TEXT3;
        assert(texts[0].color==color && texts[1].color==color);
    }
}
int main(void) {
    const struct { const char *mount,*description; } expected[] = {
        {"mc0:","Memory Card Slot 1"},{"mc1:","Memory Card Slot 2"},
        {"mmce0:","SD2PSX SD Card Slot 1"},{"mmce1:","SD2PSX SD Card Slot 2"},
        {"mx4sio:","MX4SIO SD Card"},{"hdd0:","APA HDD"},{"hdd1:","APA HDD 2"},
        {"ata0:","exFAT HDD"},{"ata1:","exFAT HDD 2"},
        {"dvr_hdd0:","PSX DVR"},{"xfrom0:","PSX Internal Flash"},
        {"cdfs:","CDVD Drive"},{"udpfs:","UDPFS Network Server"},{"host:","PC Host Server"},
        {"cf0:","PC CARD CF"},{"vmc0:","Virtual Memory Card 1"},{"vmc1:","Virtual Memory Card 2"},
    };
    for(unsigned i=0;i<sizeof(expected)/sizeof(expected[0]);i++) {
        const char *mount=expected[i].mount,*description=expected[i].description;
        char path[24],display[24];snprintf(path,sizeof(path),"%s/",mount);
        assert(!strcmp(filerRootDeviceDescription(mount),description));
        assert(!strcmp(filerRootDeviceDescription(path),description));
        formatRootDeviceMountForDisplay(mount,display,sizeof(display));assert(!strcmp(display,path));
        row(mount,path,path,description);row(mount,"",path,description);
    }
    for(int unit=0;unit<10;unit++) {
        char mass[24],usb[24],path[24],display[24];
        snprintf(mass,sizeof(mass),"mass%d:",unit);snprintf(usb,sizeof(usb),"usb%d:",unit);
        snprintf(path,sizeof(path),"usb%d:/",unit);
        assert(!strcmp(filerRootDeviceDescription(mass),"USB Storage"));
        assert(!strcmp(filerRootDeviceDescription(usb),"USB Storage"));
        formatRootDeviceMountForDisplay(mass,display,sizeof(display));assert(!strcmp(display,path));
        row(usb,path,path,"USB Storage");
    }
    row("usb:","usb:/","usb:/","USB Storage");
    row("","MISC/","MISC/","Built-in commands");
    row("custom:","custom:/","custom:/","Fallback description");
    assert(!strcmp(filerRootDeviceDescription("cf:/"),"PC CARD CF"));
    assert(!strcmp(filerRootDeviceDescription("ata:/"),"exFAT HDD"));
    assert(!strcmp(filerRootDeviceDescription("xfrom:/"),"PSX Internal Flash"));
    assert(!filerRootDeviceDescription(NULL) && !filerRootDeviceDescription("") && !filerRootDeviceDescription("mc0:/APPS/"));
    assert(!filerRootDeviceDescription("usb10:/") && !filerRootDeviceDescription("massBackup:/"));
    assert(!filerRootDeviceDescription("some_really_long_device_name:/"));
    DashDevice d={0};strcpy(d.mount,"mmce1:");char tiny[4];
    assert(!strcmp(dashDeviceDisplayMount(&d,tiny,sizeof(tiny)),"mmc"));
    assert(!strcmp(d.mount,"mmce1:") && !d.browse[0]);
    assert(!strcmp(dashDeviceDisplayMount(NULL,tiny,sizeof(tiny)),""));
    puts("PASS: device paths/descriptions in two left-aligned columns, common fonts, picker/browser sizing, readiness, selection and aliases");
}
'''
cc = shutil.which('gcc') or shutil.which('cc')
assert cc, 'Host C compiler required'
with tempfile.TemporaryDirectory(prefix='browser-devices-') as folder:
    path = Path(folder)
    (path / 'devices.c').write_text(code)
    for exfat in (False, True):
        exe = path / ('exfat' if exfat else 'classic')
        subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Werror',
                        *(['-DEXFAT'] if exfat else []), str(path / 'devices.c'), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
