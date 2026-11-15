#include "filer_shared.h"
#include "filer_saves.h"
#include "filer_actions.h"
#include "gui_texteditor.h"

static int isHddBrowserPath(const char *path)
{
	return (!strncmp(path, "hdd", 3) && path[3] >= '0' && path[3] <= '9' && path[4] == ':' && path[5] == '/');
}

static int isHddRootPath(const char *path)
{
	return (isHddBrowserPath(path) && path[6] == '\0');
}

static int isMcLikePath(const char *path)
{
	return (!strncmp(path, "mc", 2) || !strncmp(path, "vmc", 3));
}

static int isTitleCfgPathEligible(const char *path, int menu_disabled)
{
	return ((!strncmp(path, "mass", 4)) ||
	        (!strncmp(path, "usb", 3)) ||
	        (!strncmp(path, "mc0:", 4)) ||
	        (!strncmp(path, "mc1:", 4)) ||
#ifdef MMCE
	        (!strncmp(path, "mmce", 4)) ||
#endif
#ifdef MX4SIO
	        (!strncmp(path, "mx4sio", 6)) ||
#endif
#ifdef UDPFS
	        (!strncmp(path, "udpfs", 5)) ||
#endif
	        (!strncmp(path, "ata", 3)) ||
	        isPcCardCfPath(path) ||
	        (isHddBrowserPath(path) && !menu_disabled));
}

/* Filename eligibility only; VMCMAN validates the complete card on mount. */
static int isVmcImageName(const char *name)
{
	static const char *const extensions[] = {
		"VMC", "MCD", "MC2", "BIN", "MCR", "MC", "SRM", "VM1",
		"DDF", "PS", "PSM", "SAV", "PS2", "VM2", "RAW",
		"GME", "VGS", "MEM", "VMP"
	};

	for (unsigned int i = 0; i < sizeof(extensions) / sizeof(extensions[0]); i++)
		if (genCmpFileExt(name, extensions[i]))
			return TRUE;
	return FALSE;
}

/* Shared eligibility; rendering never probes devices or reads file contents. */
void filerMenuEnables(const char *path, const FILEINFO *file, int nmarked, int card_type, char enable[NUM_MENU])
{
	int menu_disabled = 0;
	int write_disabled = 0;

	memset(enable, TRUE, NUM_MENU);  //Assume that all menu items are legal by default

	if (isPcCardCfPath(path)) {
		if (!isPcCardCfOnline()) {
			menu_disabled = 1;
			write_disabled = 1;
		}
	}

	//identify cases where write access is illegal, and disable menu items accordingly
	if ((!strncmp(path, "cdfs", 4))  //Writing is always illegal for CDVD drive
#if defined(ETH) && defined(UDPFS)
	    || ((!strncmp(path, "host", 4) || !strncmp(path, "udpfs", 5))
#elif defined(ETH)
	    || ((!strncmp(path, "host", 4))
#elif defined(UDPFS)
	    || ((!strncmp(path, "udpfs", 5))
#endif
#if defined(ETH) || defined(UDPFS)
	        && ((!setting->HOSTwrite)                         //host/udpfs writing is illegal if not enabled in CNF
	            || (host_elflist && !strcmp(path, "host:/"))  //it's also illegal in elflist.txt
	            ))
#endif
				)
		write_disabled = 1;

	if ((isHddRootPath(path) || !strcmp(path, "dvr_hdd0:/")) || path[0] == 0)  //No menu cmds in partition/device lists
		menu_disabled = 1;

	if (menu_disabled) {
		enable[COPY] = FALSE;
		enable[MOUNTVMC0] = FALSE;
		enable[MOUNTVMC1] = FALSE;
		enable[GETSIZE] = FALSE;
	}
	enable[TIMEMANIP_CUSTOM] = filerCanOrganizeFolderTimestamps(path);
	if (genCmpFileExt(file->name, "ELF") && isTitleCfgPathEligible(path, menu_disabled))
		enable[TITLE_CFG] = TRUE;
	else
		enable[TITLE_CFG] = FALSE;

	enable[OPEN_TEXTEDITOR] = canOpenInTextEditor(path, file);

	if (isPcCardCfPath(path)) {
		enable[MOUNTVMC0] = FALSE;
		enable[MOUNTVMC1] = FALSE;
		if (!isPcCardCfOnline())
			enable[OPEN_TEXTEDITOR] = FALSE;
	}
	/* Argument files are read as text; they do not execute from this device. */
	enable[LAUNCH_ELF_ARGS] = enable[OPEN_TEXTEDITOR];


	if (write_disabled || menu_disabled) {
		enable[CUT] = FALSE;
		enable[PASTE] = FALSE;
		enable[DELETE] = FALSE;
		enable[RENAME] = FALSE;
		enable[NEWDIR] = FALSE;
		enable[NEWICON] = FALSE;
		enable[TITLE_CFG] = FALSE;
	}
	if (!genCanRenamePath(path))
		enable[RENAME] = FALSE;

	if (nmarked == 0) {
		if (!strcmp(file->name, "..")) {
			enable[COPY] = FALSE;
			enable[CUT] = FALSE;
			enable[DELETE] = FALSE;
			enable[RENAME] = FALSE;
			enable[GETSIZE] = FALSE;
		}
		if (filerIsExploitProtectedPath(path, file))
			enable[RENAME] = FALSE;
	} else {
		enable[RENAME] = FALSE;
	}

	if (!isVmcImageName(file->name) || (file->stats.AttrFile & sceMcFileAttrSubdir) ||
	    !strncmp(path, "vmc", 3) || !strncmp(path, "mc", 2)) {
		enable[MOUNTVMC0] = FALSE;  //forbid insane VMC mounting
		enable[MOUNTVMC1] = FALSE;  //forbid insane VMC mounting
	}

	enable[IMPORT_SAVE] = !write_disabled && !menu_disabled && genCanRenamePath(path) && filerCanImportClipboard();
	enable[EXPORT_PS1] = !menu_disabled &&
		((!(file->stats.AttrFile & sceMcFileAttrSubdir) && filerIsPs1Image(file->name)) ||
		 (card_type == 1 && isMcLikePath(path)));
	enable[CREATE_ARCHIVE] = !write_disabled && !menu_disabled && genCanRenamePath(path) &&
	                         strncmp(path, "host", 4) && filerArchiveClipboardKind() != FILER_SAVE_NONE &&
	                         !(card_type == 1 && isMcLikePath(path));
	if (nclipFiles == 0) enable[PASTE] = FALSE;

	/* PS1 cards are a flat list of save files, on both physical and VMC media. */
	if (card_type == 1 && isMcLikePath(path)) {
		enable[NEWDIR] = FALSE;
		enable[NEWICON] = FALSE;
		enable[OPEN_TEXTEDITOR] = FALSE;
		enable[LAUNCH_ELF_ARGS] = FALSE;
		enable[TITLE_CFG] = FALSE;
		enable[TIMEMANIP_CUSTOM] = FALSE;
		for (int i = 0; i < nclipFiles; i++)
			if (clipFiles[i].stats.AttrFile & sceMcFileAttrSubdir) enable[PASTE] = FALSE;
	}
}
