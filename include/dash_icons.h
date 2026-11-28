#ifndef DASH_ICONS_H
#define DASH_ICONS_H

enum DashIcon {
	DI_HOME = 0,
	DI_APPS,
	DI_FOLDER,
	DI_DEVICES,
	DI_TOOLS,
	DI_SETTINGS,
	DI_MC,
	DI_USB,
	DI_HDD,
	DI_DISC,
	DI_NETWORK,
	DI_STAR,
	DI_CLOCK,
	DI_APP,
	DI_PLAY,
	DI_INFO,
	DI_WARNING,
	DI_POWER,
	DI_TEXT,
	DI_EDIT,
	DI_REFRESH,
	DI_PIN,
	DI_PLUS,
	DI_CHECK,
	DI_CLOSE,
	DI_SDCARD,
	DI_CHIP,
	DI_VIEW_GRID,
	DI_VIEW_LIST,
	DI_VIEW_CAROUSEL,
	DI_FILE,
	DI_BACK,
	DI_PAD_BADGE,   /* shared dark rounded-square tile drawn behind pad glyphs */
	DI_BTN_CROSS,
	DI_BTN_CIRCLE,
	DI_BTN_SQUARE,
	DI_BTN_TRIANGLE,
	DI_BTN_UP,
	DI_BTN_DOWN,
	DI_BTN_LEFT,
	DI_BTN_RIGHT,
	DI_BTN_START,
	DI_BTN_SELECT,
	DI_BTN_L1,
	DI_BTN_L2,
	DI_BTN_L3,
	DI_BTN_R1,
	DI_BTN_R2,
	DI_BTN_R3,
	DI_KEY,
	DI_GAMEPAD,
	DI_EXEC,    /* default application icon */
	DI_PALETTE, /* theme settings */
	DI_RECENT,  /* recently used */
	DI_IMAGE,   /* wallpaper / picture */
	DI_DPAD_UD, /* D-pad with up/down highlighted ("scroll") */
	DI_UPDATE,  /* package surrounded by circular arrows */
	DI_ARCHIVE_CREATE, /* closed package: create save archive */
	DI_ARCHIVE_EXTRACT, /* open package: extract/install archive */
	DI_SHOW,    /* open eye for showing hidden items */
	DI_BOOT_FLAG,
	DI_BOOT_FLAG_ENABLED,
	DI_CUT,     /* first small icon in the atlas margin, after the grid icons */
	DI_COPY,
	DI_PASTE_RENAME, /* pencil with a small upper-right plus */
	DI_SELECT_ALL,   /* checkmark with a small upper-left plus */
	DI_INVERT_SELECTION, /* filled rounded square with a checkmark cutout */
	DI_CLEAR_SELECTION, /* checkmark with a small upper-left minus */
	DI_LAUNCH_ARGS, /* rocket-launch: use a text file/buffer as launch arguments */
	DI_NEW_DOCUMENT, /* lined document with a small upper-right plus */
	DI_KEY_TAB,     /* keyboard right arrow ending at a vertical bar */
	DI_KEY_RETURN,  /* keyboard bent left arrow; arrowhead centered at y=0 */
	DI_SAVE,        /* upstream floppy disk: shutter on top, label below */
	DI_MICROSD,     /* notched microSD outline for MMCE and MX4SIO */
	DI_NETWORK_FOLDER, /* existing folder with a network bus and nodes below */
	DI_SOUND,       /* filled speaker with two sound waves */
	DI_KEYBOARD,    /* wired keyboard with keys and a space bar */
	DI_HIDE,        /* crossed-out eye for application visibility */
	DI_UNDO,        /* counterclockwise arrow for reset actions */
	DI_COMPACTFLASH, /* wide CF card with an inset connector/label panel */
	DI_PARTITION, /* stacked disk with separated pie-style partitions */
	DI_HDD_MANAGER, /* hard drive branching into two partition blocks */
	DI_COUNT
};

#endif
