"""Run the RTC display and manual date/time setter with mocked PS2 hardware."""
from pathlib import Path
import shutil
import subprocess
import tempfile

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
#include <string.h>
typedef uint64_t u64;
typedef int64_t s64;
typedef uint8_t u8;
typedef struct { u8 stat, second, minute, hour, pad, day, month, year; } sceCdCLOCK;
#define MENU_TITLE_CLOCK_YEAR_BASE 2000
#define MENU_TITLE_PS2_RTC_BASE_OFFSET_MINUTES 540
#define MENU_TITLE_CLOCK_POLL_MS 1000
'''
code += title[title.index("typedef struct"):title.index("} MenuTitleClockState;") + len("} MenuTitleClockState;")]
code += r'''
static MenuTitleClockState title_clock;
static int osd_local_offset_cached, osd_local_offset_minutes;
static int local_offset = -480, use_12h, date_format;
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
static void readOsdClockFormats(int *u, int *d, int *offset) {
    *u = use_12h; *d = date_format; *offset = local_offset;
}
'''
for signature in (
    "static int bcdToInt(", "static int daysInMonth(",
    "static void normalizeClockDate(", "static void advanceClockSeconds(",
    "static void shiftClockMinutes(", "static int isValidTimestamp(",
    "static int getOsdLocalOffsetMinutes(", "static int convertTimestampMinutes(",
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
    "static int manualLeap(", "static int manualDaysInMonth(",
    "static s64 manualSerialSeconds(", "int dashClockSetManual(",
):
    code += function(clock, signature)
code += r'''
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
    puts("PASS: RTC display, timezone/leap-day rollover, refresh/retry, manual date/time validation and hardware readback failures");
}
'''
with tempfile.TemporaryDirectory(prefix="hardware-clock-") as folder:
    path = Path(folder)
    (path / "clock.c").write_text(code)
    exe = path / "clock"
    subprocess.run([shutil.which("gcc") or shutil.which("cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(path / "clock.c"), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True, timeout=10)
