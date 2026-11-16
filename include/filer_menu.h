#ifndef FILER_MENU_H
#define FILER_MENU_H
/* Stable action identifiers shared by both browser presentations. */
enum {
	COPY,
	CUT,
	PASTE,
	CREATE_ARCHIVE,
	DELETE,
	RENAME,
	NEWDIR,
	NEWICON,
	MOUNTVMC0,
	MOUNTVMC1,
	GETSIZE,
	OPEN_TEXTEDITOR,
	LAUNCH_ELF_ARGS,
	TIMEMANIP_CUSTOM,
	TITLE_CFG,
	IMPORT_SAVE,
	EXPORT_PS1,
	NUM_MENU
};
enum { FILER_MENU_CLASSIC, FILER_MENU_NATIVE };
/* Disabled legacy actions normally stay visible. Native menus omit actions
 * unavailable for this selection, while retaining core disabled operations. */
int filerMenuVisible(int command, const char enable[NUM_MENU], int presentation);
int filerMenuRowCount(const char enable[NUM_MENU], int presentation);
#endif
