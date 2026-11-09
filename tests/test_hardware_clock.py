"""Run the RTC display and manual date/time setter with mocked PS2 hardware."""
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta

root = Path(__file__).resolve().parents[1]
title = (root / "src/main_title.c").read_text()
clock = (root / "src/dash_clock_sync.c").read_text()


def function(source, signature):
    start = source.index(signature)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint64_t u64;
typedef int64_t s64;
typedef uint8_t u8;
typedef uint32_t u32;
typedef struct { u8 stat, second, minute, hour, pad, day, month, year; } sceCdCLOCK;
#define MENU_TITLE_CLOCK_YEAR_BASE 2000
#define MENU_TITLE_PS2_RTC_BASE_OFFSET_MINUTES 540
#define MENU_TITLE_CLOCK_POLL_MS 1000
'''
clock_header = (root / "include/main_title.h").read_text()
code += clock_header[clock_header.index("typedef struct MenuClockSettings"):clock_header.index("} MenuClockSettings;")+len("} MenuClockSettings;")] + "\n"
code += title[title.index("typedef struct"):title.index("} MenuTitleClockState;") + len("} MenuTitleClockState;")]
code += r'''
static MenuTitleClockState title_clock;
static int osd_local_offset_cached, osd_local_offset_minutes;
static int local_offset = -480, use_12h, date_format, daylight_saving, osd_version=1;
static int saved_clock_settings_valid, saved_clock_use12, saved_clock_datefmt, saved_clock_offset;
static int saved_clock_timezone,saved_clock_dst;
static int nvm_mode,nvm_writes,nvm_fail_write,nvm_bad_write,nvm_fail_read,kernel_writes;
static int nvm_available, nvm_read_ok=1, nvm_close_ok=1, nvm_status, nvm_open, nvm_reads, nvm_closes;
static u8 saved_nvm[30];
typedef struct {unsigned version,timezoneOffset;} ConfigParam;
typedef struct {unsigned timeFormat,dateFormat,daylightSaving;} Config2Param;
static void GetOsdConfigParam(ConfigParam *config) {config->version=osd_version;config->timezoneOffset=local_offset&0x7ff;}
static void GetOsdConfigParam2(Config2Param *config,int size,int offset) {
 assert(osd_version && size==sizeof(*config) && !offset);
 config->timeFormat=use_12h;config->dateFormat=date_format;config->daylightSaving=daylight_saving;
}
static void SetOsdConfigParam(const ConfigParam *config) {assert(osd_version);local_offset=(int)(config->timezoneOffset&0x7ff);kernel_writes++;}
static void SetOsdConfigParam2(const Config2Param *config,int size,int offset) {
 assert(osd_version && size==sizeof(*config) && !offset);
 use_12h=config->timeFormat;daylight_saving=config->daylightSaving;date_format=config->dateFormat;kernel_writes++;
}
static void DelayThread(int delay){assert(delay==1000);}
static int sceCdOpenConfig(int block,int mode,int count,u32 *status){
 assert(block==1 && (mode==0 || mode==1) && count==2);*status=nvm_available&&!nvm_open?0:0x80;
 if(!nvm_available || nvm_open)return 0;
 nvm_mode=mode;nvm_open=1;return 1;
}
static int sceCdReadConfig(void *data,u32 *status){
 assert(nvm_open && nvm_mode==0);nvm_reads++;memcpy(data,saved_nvm,30);*status=nvm_status;
 return nvm_read_ok && nvm_reads!=nvm_fail_read;
}
static int sceCdWriteConfig(const void *data,u32 *status){
 assert(nvm_open && nvm_mode==1);nvm_writes++;memcpy(saved_nvm,data,30);
 if(nvm_writes==nvm_bad_write)saved_nvm[18]^=0x40;
 *status=(nvm_fail_write==-1 || nvm_writes==nvm_fail_write)?8:0;
 return 1; /* Even an error response may have changed NVRAM. */
}
static int sceCdCloseConfig(u32 *status){
 assert(nvm_open);nvm_closes++;*status=nvm_close_ok?0:0x80;
 if(nvm_close_ok)nvm_open=0;
 return nvm_close_ok;
}
static u64 tick = 100;
static sceCdCLOCK rtc, written;
static int rtc_reads, rtc_writes, read_ok = 1, write_ok = 1, read_stat, second_delta;
static u64 Timer(void) { return tick; }
static int sceCdReadClock(sceCdCLOCK *out) {
    rtc_reads++; *out = rtc; out->stat = read_stat;
    /* These scenarios keep seconds below the next BCD decade. */
    out->second += second_delta;
    return read_ok;
}
static int sceCdWriteClock(sceCdCLOCK *in) {
    rtc_writes++; written = *in;
    if (write_ok) rtc = *in;
    return write_ok;
}
'''
for signature in (
    "static int decodeTimezoneOffsetMinutes(", "static int clockConfigAccess(",
    "static int decodeClockSettings(", "static void rememberClockSettings(",
    "int menuTitleLoadSavedClockSettings(", "void menuTitleGetClockSettings(",
    "int menuTitleSaveClockSettings(", "static void readOsdClockFormats(",
    "static int bcdToInt(", "static int daysInMonth(",
    "static void normalizeClockDate(", "static void advanceClockSeconds(",
    "static void shiftClockMinutes(", "static int isValidTimestamp(",
    "static int getOsdLocalOffsetMinutes(", "static int convertTimestampMinutes(",
    "int menuTitleConvertTimestampForSettings(",
    "int menuTitleConvertTimestampToLocalTime(", "int menuTitleConvertTimestampFromLocalTime(",
    "void menuTitleFormatClockTime(", "void menuTitleFormatClockDate(",
    "static int refreshClockText(", "static int seedClockFromPs2(",
    "static int updateClock(",
):
    code += function(title, signature)
code += "int menuTitleUpdateAsync(int force) { return updateClock(Timer(), force, 1, 1); }\n"
code += function(title, "int menuTitleGetClockFields(")
for signature in (
    "static u8 manualToBcd(", "static int manualFromBcd(",
    "static int manualLeap(", "int dashClockDaysInMonth(",
    "static s64 manualSerialSeconds(", "void dashClockManualLimitsForSettings(",
    "void dashClockManualLimits(", "static int setManualClock(",
    "int dashClockSetManualWithSettings(", "int dashClockSetManual(",
):
    code += function(clock, signature)
# Independent Gregorian arithmetic supplies expected RTC values and local limits.
zone_cases = []
for offset in (-720, -480, -420, 0, 60, 330, 345, 540, 570, 765, 840):
    for dst in (0, 1):
        shift = timedelta(minutes=offset + dst * 60 - 540)
        lo = datetime(2000, 1, 1) + shift
        hi = datetime(2099, 12, 31, 23, 59, 59) + shift
        local = datetime(2028, 2, 29, 23, 59, 58)
        raw = local - shift
        fields = lambda t: [t.year, t.month, t.day, t.hour, t.minute, t.second]
        zone_cases.append([offset, dst, *fields(lo), *fields(hi), *fields(local), *fields(raw)])
code += "static const int zone_cases[][26]={" + ",".join("{" + ",".join(map(str, row)) + "}" for row in zone_cases) + "};\n"
code += r'''
static void saveZone(int offset,int dst,int use12,int format) {
 memset(saved_nvm,0,sizeof(saved_nvm));
 saved_nvm[16]=0x22;
 saved_nvm[17]=0x80|((offset&0x7ff)>>8)|(dst?8:0)|(use12?0x10:0)|(format<<5);
 saved_nvm[18]=offset&0xff;
}
static void manualFields(const int *fields,const int *raw,char *result,int size) {
 assert(dashClockSetManual(fields[0],fields[1],fields[2],fields[3],fields[4],fields[5],result,size));
 assert(manualFromBcd(written.year)==raw[0]-2000 && manualFromBcd(written.month)==raw[1] && manualFromBcd(written.day)==raw[2]);
 assert(manualFromBcd(written.hour)==raw[3] && manualFromBcd(written.minute)==raw[4] && manualFromBcd(written.second)==raw[5]);
 int shown[6];assert(menuTitleGetClockFields(&shown[0],&shown[1],&shown[2],&shown[3],&shown[4],&shown[5],NULL,NULL));
 assert(!memcmp(shown,fields,sizeof(shown)));
}
int main(void) {
    /* RTC is in JST; the displayed local date crosses a leap-day boundary. */
    rtc = (sceCdCLOCK){.year=0x28, .month=0x03, .day=0x01,
                       .hour=0x16, .minute=0x59, .second=0x59};
    assert(menuTitleUpdateAsync(0) && rtc_reads == 1);
    assert(title_clock.year == 2028 && title_clock.month == 2 && title_clock.day == 29);
    assert(!strcmp(title_clock.time_text, "23:59:59"));
    tick=1100; assert(menuTitleUpdateAsync(0) && rtc_reads == 1);
    assert(title_clock.month == 3 && title_clock.day == 1 && title_clock.hour == 0);
    assert(!strcmp(title_clock.time_text, "00:00:00"));
    tick=1150; assert(!menuTitleUpdateAsync(0) && rtc_reads == 1);
    /* A forced refresh and a timer restart reread the hardware RTC. */
    rtc.hour=0x18; rtc.minute=0x01; rtc.second=0x20;
    use_12h=1; date_format=2;
    assert(menuTitleUpdateAsync(1) && rtc_reads == 2);
    assert(!strcmp(title_clock.time_text, "01:01:20 AM"));
    tick=0; menuTitleUpdateAsync(0); assert(rtc_reads == 3);
    int y,m,d,h,min,s,u,f;
    assert(menuTitleGetClockFields(&y,&m,&d,&h,&min,&s,&u,&f));
    assert(y==2028 && m==3 && d==1 && h==1 && min==1 && s==20 && u==1 && f==2);
    /* Hardware failures show an unavailable clock, then retry after a second. */
    read_ok=0; menuTitleUpdateAsync(1);
    assert(!menuTitleGetClockFields(NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL));
    assert(!strcmp(title_clock.time_text,"--:--:--"));
    read_ok=1; tick=1000; menuTitleUpdateAsync(0); assert(title_clock.valid);
    read_stat=1; menuTitleUpdateAsync(1); assert(!title_clock.valid);
    read_stat=0; menuTitleUpdateAsync(1); assert(title_clock.valid);

    /* Manual local date/time writes BCD hardware values and refreshes the display. */
    char result[160];
    int before=rtc_reads;
    assert(dashClockSetManual(2028,2,29,23,59,58,result,sizeof(result)));
    assert(rtc_reads==before+2 && rtc_writes==1);
    assert(written.year==0x28 && written.month==0x03 && written.day==0x01);
    assert(written.hour==0x16 && written.minute==0x59 && written.second==0x58);
    assert(strstr(result,"verified"));
    assert(menuTitleGetClockFields(&y,&m,&d,&h,&min,&s,&u,&f));
    assert(y==2028 && m==2 && d==29 && h==23 && min==59 && s==58);

    const int invalid[][6] = {
        {1999,1,1,0,0,0}, {2100,1,1,0,0,0}, {2026,0,1,0,0,0},
        {2026,13,1,0,0,0}, {2026,2,29,0,0,0}, {2028,2,30,0,0,0},
        {2026,4,31,0,0,0}, {2026,1,0,0,0,0}, {2026,1,1,24,0,0},
        {2026,1,1,-1,0,0}, {2026,1,1,0,60,0}, {2026,1,1,0,0,60}
    };
    before=rtc_writes;
    for (unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        const int *v=invalid[i];
        assert(!dashClockSetManual(v[0],v[1],v[2],v[3],v[4],v[5],result,sizeof(result)));
        assert(result[0] && rtc_writes==before);
    }
    write_ok=0; assert(!dashClockSetManual(2028,6,1,10,0,10,result,sizeof(result)));
    assert(strstr(result,"write failed")); write_ok=1;
    read_ok=0; assert(!dashClockSetManual(2028,6,1,10,0,10,result,sizeof(result)));
    assert(strstr(result,"read back")); read_ok=1;
    read_stat=1; assert(!dashClockSetManual(2028,6,1,10,0,10,result,sizeof(result)));
    read_stat=0; second_delta=3;
    assert(!dashClockSetManual(2028,6,1,10,0,10,result,sizeof(result)));
    assert(strstr(result,"did not verify")); second_delta=2;
    assert(dashClockSetManual(2028,6,1,10,0,10,NULL,0));
    second_delta=0;local_offset=540;daylight_saving=0;osd_version=1;nvm_available=1;
    for(unsigned i=0;i<sizeof(zone_cases)/sizeof(zone_cases[0]);i++) {
        const int *c=zone_cases[i];
        saveZone(c[0],c[1],i%2,i%3);
        assert(menuTitleLoadSavedClockSettings() && !nvm_open);
        int minimum[6],maximum[6];dashClockManualLimits(minimum,maximum);
        assert(!memcmp(minimum,c+2,sizeof(minimum)) && !memcmp(maximum,c+8,sizeof(maximum)));
        manualFields(c+14,c+20,result,sizeof(result));
        assert(title_clock.use_12h==(int)(i%2) && title_clock.date_format==(int)(i%3));
        const int rtc_min[]={2000,1,1,0,0,0},rtc_max[]={2099,12,31,23,59,59};
        manualFields(minimum,rtc_min,result,sizeof(result));manualFields(maximum,rtc_max,result,sizeof(result));
    }
    // Changing the saved DST choice invalidates the old offset before writing.
    saveZone(-480,0,1,1);assert(menuTitleLoadSavedClockSettings());menuTitleUpdateAsync(1);
    saveZone(-480,1,1,1);
    const int summer_local[]={2028,6,1,10,0,0},summer_raw[]={2028,6,2,2,0,0};
    manualFields(summer_local,summer_raw,result,sizeof(result));
    // Invalid dates at either converted boundary never reach sceCdWriteClock.
    saveZone(-480,0,0,0);before=rtc_writes;
    assert(!dashClockSetManual(1999,12,31,6,59,59,result,sizeof(result)) && rtc_writes==before);
    assert(!dashClockSetManual(2099,12,31,7,0,0,result,sizeof(result)) && rtc_writes==before);
    saveZone(840,0,0,0);
    assert(!dashClockSetManual(2000,1,1,4,59,59,result,sizeof(result)) && rtc_writes==before);
    assert(!dashClockSetManual(2100,1,1,5,0,0,result,sizeof(result)) && rtc_writes==before);
    // Preview boundaries follow staged settings, without changing active preferences.
    MenuClockSettings preferences={345,1,1,2},prior;
    assert(menuTitleLoadSavedClockSettings());menuTitleGetClockSettings(&prior);
    int preview_min[6],preview_max[6];
    dashClockManualLimitsForSettings(preview_min,preview_max,&preferences);
    assert(preview_min[0]==1999 && preview_min[3]==21 && preview_min[4]==45);
    assert(saved_clock_timezone==prior.timezone_minutes && saved_clock_dst==prior.daylight_saving);
    // Read-modify-write changes just clock bits; PS1, language, date and location ID survive.
    for(int i=0;i<30;i++)saved_nvm[i]=(u8)(i*7+3);
    saved_nvm[17]=0xc0|2;saved_nvm[18]=0x1c; // Valid saved date format 2, JST.
    u8 preserved[30];memcpy(preserved,saved_nvm,30);before=nvm_writes;
    assert(menuTitleSaveClockSettings(&preferences)==1 && nvm_writes==before+1 && !nvm_open);
    for(int i=0;i<30;i++)if(i!=17 && i!=18)assert(saved_nvm[i]==preserved[i]);
    assert((saved_nvm[17]&0xe0)==(preserved[17]&0xe0));
    assert((saved_nvm[17]&0x1f)==0x19 && saved_nvm[18]==0x59);
    menuTitleGetClockSettings(&prior);
    assert(prior.timezone_minutes==345 && prior.daylight_saving==1 && prior.use_12h==1 && prior.date_format==2);
    assert(kernel_writes>=2 && use_12h==1 && daylight_saving==1);
    before=nvm_writes;assert(menuTitleSaveClockSettings(&preferences)==1 && nvm_writes==before);
    // Persistent write/verification failures restore every original byte and retain cached values.
    for(int failure=0;failure<3;failure++) {
        memcpy(preserved,saved_nvm,30);preferences.timezone_minutes=330;
        if(failure==0)nvm_fail_write=nvm_writes+1;
        if(failure==1)nvm_bad_write=nvm_writes+1;
        if(failure==2)nvm_fail_read=nvm_reads+2;
        assert(menuTitleSaveClockSettings(&preferences)==0 && !memcmp(saved_nvm,preserved,30));
        assert(saved_clock_timezone==345 && !nvm_open);
        nvm_fail_write=nvm_bad_write=nvm_fail_read=0;
    }
    preferences.timezone_minutes=900;before=nvm_writes;
    assert(menuTitleSaveClockSettings(&preferences)==0 && nvm_writes==before);
    preferences.timezone_minutes=330;nvm_fail_write=-1;
    assert(menuTitleSaveClockSettings(&preferences)==-1);nvm_fail_write=0;
    // The early kernel never calls unsupported configuration syscalls while NVRAM still works.
    osd_version=0;before=kernel_writes;preferences.timezone_minutes=-210;preferences.use_12h=0;
    assert(menuTitleSaveClockSettings(&preferences)==1 && kernel_writes==before);
    osd_version=1;
    // Apply uses the chosen offset, commits preferences, and refreshes immediately.
    const int requested[]={2028,2,29,23,59,58};preferences=(MenuClockSettings){345,1,1,2};
    assert(dashClockSetManualWithSettings(requested,&preferences,result,sizeof(result)));
    assert(rtc.hour==0x02 && rtc.minute==0x14 && rtc.day==0x01 && rtc.month==0x03);
    assert(title_clock.hour==23 && title_clock.minute==59 && title_clock.use_12h && saved_clock_dst);
    // An unavailable NVRAM service leaves preferences intact and restores the previous RTC.
    sceCdCLOCK original_rtc=rtc;nvm_available=0;preferences.timezone_minutes=540;
    assert(!dashClockSetManualWithSettings(requested,&preferences,result,sizeof(result)));
    assert(!memcmp(&rtc,&original_rtc,sizeof(rtc)) && strstr(result,"Previous RTC restored"));
    assert(saved_clock_timezone==345);nvm_available=1;
    // Failed/uninitialized/invalid reads are bounded and close every acquired session.
    for(int failure=0;failure<5;failure++) {
        saveZone(-480,0,0,0);nvm_read_ok=1;nvm_status=0;nvm_available=1;
        if(failure==0)nvm_available=0;
        if(failure==1)nvm_read_ok=0;
        if(failure==2)nvm_status=0x81;
        if(failure==3)saved_nvm[17]&=~0x80;
        if(failure==4)saved_nvm[17]|=0x60;
        assert(!menuTitleLoadSavedClockSettings() && !nvm_open);
    }
    nvm_available=1;nvm_read_ok=1;nvm_status=0;saveZone(-480,0,0,0);
    nvm_close_ok=0;before=nvm_closes;assert(!menuTitleLoadSavedClockSettings() && nvm_closes==before+3);
    nvm_close_ok=1;nvm_open=0;
    saved_clock_settings_valid=0;osd_version=0;local_offset=-480;
    int format,offset;readOsdClockFormats(&u,&format,&offset);assert(!u && !format && offset==540);
    assert(nvm_reads && nvm_closes);
    puts("PASS: saved NVRAM time-zone/DST/date formats, local/RTC conversions, 1999/2100 bounds, stale DST refresh, verified preference writes, unrelated NVRAM preservation, failure restoration and hardware readback");
}
'''
with tempfile.TemporaryDirectory(prefix="hardware-clock-") as folder:
    path = Path(folder)
    (path / "clock.c").write_text(code)
    exe = path / "clock"
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "clock.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
