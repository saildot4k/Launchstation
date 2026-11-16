#ifndef DASH_SETTINGS_THEME_H
#define DASH_SETTINGS_THEME_H
/* Return whether the active settings session acquired theme changes. */
int dashSettingsChoosePreset(void);
int dashSettingsLoadTheme(void);
void dashSettingsSaveTheme(void);
#endif
