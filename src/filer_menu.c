#include "filer_menu.h"

enum { HIDE_CLASSIC = 1, HIDE_NATIVE = 2 };
typedef struct { unsigned char hidden_when_disabled; } FilerActionDescriptor;
static const FilerActionDescriptor actions[NUM_MENU] = {
	[CREATE_ARCHIVE] = {HIDE_NATIVE}, [IMPORT_SAVE] = {HIDE_NATIVE},
	[NEWICON] = {HIDE_NATIVE}, [OPEN_TEXTEDITOR] = {HIDE_NATIVE},
	[MOUNTVMC0] = {HIDE_CLASSIC | HIDE_NATIVE}, [MOUNTVMC1] = {HIDE_CLASSIC | HIDE_NATIVE},
	[LAUNCH_ELF_ARGS] = {HIDE_CLASSIC | HIDE_NATIVE},
	[TIMEMANIP_CUSTOM] = {HIDE_NATIVE}, [TITLE_CFG] = {HIDE_NATIVE}, [EXPORT_PS1] = {HIDE_NATIVE}
};

int filerMenuVisible(int command, const char enable[NUM_MENU], int presentation)
{
	unsigned mask = presentation == FILER_MENU_CLASSIC ? HIDE_CLASSIC : HIDE_NATIVE;
	if (command < 0 || command >= NUM_MENU) return 0;
	return enable[command] || !(actions[command].hidden_when_disabled & mask);
}

int filerMenuRowCount(const char enable[NUM_MENU], int presentation)
{
	int count = 0;
	for (int i = 0; i < NUM_MENU; i++) count += filerMenuVisible(i, enable, presentation);
	return count;
}
