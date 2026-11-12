#ifndef MAIN_TITLE_H
#define MAIN_TITLE_H

#include <stddef.h>

typedef struct MenuClockSettings
{
	int timezone_minutes; /* Standard-time UTC offset; DST is separate. */
	int daylight_saving;
	int use_12h;
	int date_format;
} MenuClockSettings;

void menuTitleFormat(char *out, size_t out_size);
void menuTitleFormatClock(char *out, size_t out_size);
void menuTitleFormatTemperature(char *out, size_t out_size);
int menuTitleGetTemperatureRaw(int *raw); /* cached 1/128 C sample; no IOP calls */
int menuTitleUpdateAsync(int force);
void menuTitleGetClockFormat(int *use_12h, int *date_format);
/* Read saved OSD clock preferences without changing NVRAM. Serialized IOP access;
 * fall back to kernel settings if unavailable. Refreshes the local clock cache. */
int menuTitleLoadSavedClockSettings(void);
void menuTitleGetClockSettings(MenuClockSettings *settings);
/* Serialized IOP access. Returns 1 on verified success, 0 on failure with the
 * original configuration intact, -1 if restoring the original could not verify. */
int menuTitleSaveClockSettings(const MenuClockSettings *settings);
int menuTitleConvertTimestampForSettings(int fields[6], const MenuClockSettings *settings, int to_local);
void menuTitleFormatClockTime(char *dst, size_t dst_size, int hour, int minute, int second, int use_12h);
void menuTitleFormatClockDate(char *dst, size_t dst_size, int year, int month, int day, int date_format);
int menuTitleConvertTimestampToLocalTime(int *year, int *month, int *day, int *hour, int *minute, int *second);
int menuTitleConvertTimestampFromLocalTime(int *year, int *month, int *day, int *hour, int *minute, int *second);

#endif
