"""Exercise the System clock chooser and its real manual/Internet handlers."""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/dash_settings.c").read_text()


def function(signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#define NITEMS(a) ((int)(sizeof(a)/sizeof((a)[0])))
enum { DI_CLOCK, DI_CHECK, DI_WARNING };
typedef struct { int icon; const char *label, *detail; int disabled; } DashMenuItem;
static int choice=-1, keyboard_ok, rtc_valid=1, manual_ok=1;
static int menus, keyboards, field_reads, manual_writes, messages, last_icon;
static const char *typed;
static char last_title[80], last_body[200];
static int dashModalMenu(const char *title,const char *subtitle,const DashMenuItem *items,int n,int initial) {
    assert(!strcmp(title,"Set PS2 Clock") && !subtitle && !initial);
#ifdef ETH
    assert(n==2 && !strcmp(items[1].label,"Sync from Internet"));
#else
    assert(n==1);
#endif
    assert(!strcmp(items[0].label,"Set manually..."));
    for(int i=0;i<n;i++) assert(items[i].icon==DI_CLOCK && !items[i].disabled);
    menus++;return choice;
}
static int menuTitleGetClockFields(int *y,int *m,int *d,int *h,int *mi,int *s,int *u,int *f) {
    field_reads++;*y=2026;*m=11;*d=8;*h=8;*mi=30;*s=15;*u=*f=0;return rtc_valid;
}
static int dashModalKeyboard(const char *title,char *text,int cap) {
    assert(strstr(title,"YYYY-MM-DD HH:MM:SS"));
    assert(!strcmp(text,rtc_valid?"2026-11-08 08:30:15":"2000-01-01 00:00:00"));
    keyboards++;if(typed)snprintf(text,cap,"%s",typed);return keyboard_ok;
}
static int dashClockSetManual(int y,int m,int d,int h,int mi,int s,char *result,int cap) {
    assert(y==2026 && m==11 && d==8 && h==13 && mi==14 && s==15);
    manual_writes++;snprintf(result,cap,"%s",manual_ok?"Clock verified":"RTC write failed");return manual_ok;
}
static void dashModalMessage(int icon,const char *title,const char *body,const char *detail) {
    (void)detail;messages++;last_icon=icon;
    snprintf(last_title,sizeof(last_title),"%s",title);snprintf(last_body,sizeof(last_body),"%s",body);
}
#ifdef ETH
static int allow_wait=1, waits, loading, begins, ends, syncs, sync_ok=1, empty_error;
static int dashWorkerAwaitAll(const char *title) { assert(title);waits++;return allow_wait; }
static void dashLoadingBegin(const char *title) { assert(title && waits && !loading);loading=1;begins++; }
static void dashLoadingEnd(void) { assert(loading);loading=0;ends++; }
static int dashClockSyncInternet(char *result,int cap) {
    assert(loading && waits);syncs++;
    snprintf(result,cap,"%s",empty_error?"":sync_ok?"Clock verified":"Server timeout");return sync_ok;
}
'''
code += function("static void syncClockFromInternet(") + "#endif\n"
code += function("static void setClockManually(") + function("static void setPs2Clock(")
code += r'''
static void reset(void) {
    choice=-1;keyboard_ok=0;rtc_valid=manual_ok=1;typed=NULL;
    menus=keyboards=field_reads=manual_writes=messages=0;
    last_title[0]=last_body[0]=0;
#ifdef ETH
    allow_wait=sync_ok=1;waits=loading=begins=ends=syncs=empty_error=0;
#endif
}
int main(void) {
    reset();setPs2Clock();assert(menus==1 && !keyboards && !field_reads && !manual_writes && !messages);
    reset();choice=0;setPs2Clock();assert(keyboards==1 && !manual_writes && !messages);
    reset();choice=0;keyboard_ok=1;typed="not a date";setPs2Clock();
    assert(!manual_writes && messages==1 && last_icon==DI_WARNING && !strcmp(last_title,"Invalid date / time"));
    reset();choice=0;keyboard_ok=1;typed="2026-11-08 13:14:15";setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_CHECK && !strcmp(last_title,"PS2 clock updated"));
#ifdef ETH
    assert(!waits && !syncs); /* Manual entry must never start the network. */
#endif
    reset();choice=0;keyboard_ok=1;manual_ok=0;rtc_valid=0;typed="2026-11-08 13:14:15";setPs2Clock();
    assert(manual_writes==1 && messages==1 && last_icon==DI_WARNING && !strcmp(last_body,"RTC write failed"));
#ifdef ETH
    reset();choice=1;allow_wait=0;setPs2Clock();assert(waits==1 && !begins && !syncs && !messages);
    reset();choice=1;setPs2Clock();
    assert(syncs==1 && begins==1 && ends==1 && !loading && !keyboards && !manual_writes);
    assert(messages==1 && last_icon==DI_CHECK && !strcmp(last_title,"PS2 clock synchronized"));
    reset();choice=1;sync_ok=0;setPs2Clock();
    assert(syncs==1 && ends==1 && !loading && last_icon==DI_WARNING && !strcmp(last_body,"Server timeout"));
    reset();choice=1;sync_ok=0;empty_error=1;setPs2Clock();
    assert(!strcmp(last_body,"No reliable Internet time was available."));
#endif
    puts("PASS: one clock chooser, safe cancellation, manual entry/readback feedback and Internet dispatch with background-IO drain");
}
'''

compiler = shutil.which("cc") or shutil.which("gcc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-settings-clock-") as tmp:
    src, binary = Path(tmp) / "clock.c", Path(tmp) / "clock"
    src.write_text(code)
    for flags in ([], ["-DETH"]):
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        *flags, str(src), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=5)
