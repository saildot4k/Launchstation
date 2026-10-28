//--------------------------------------------------------------
//File name:   dash_tools.c
//TOOLS: every wLaunchELF function with a friendly name and a short
//description. Each entry dispatches the MISC command path through
//dashRunMisc(), which opens the native dashboard version of each tool or
//runs the command (disc, OSDSYS, network...) behind the loading overlay.
//--------------------------------------------------------------
#include "dash_internal.h"
#include "dash_sound.h"
#include "self_update.h"
#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
#include "https_client.h"
#endif
#include "init.h"
#include <stddef.h>
#include <stdlib.h>

enum ToolAction {
	TA_HEADER = 0,
	TA_MISC,
	TA_BROWSER,
	TA_BROWSER_AT,
	TA_MISC_MENU,
	TA_EDITOR,
	TA_USB_DIAG,
	TA_SOUND_DIAG
};

typedef struct
{
	int action;
	int icon;
	const char *name;
	const char *desc;
	const char *note; /* safety note shown in the detail panel */
	int confirm;      /* 1: ask before running, 2: dangerous or leaves Launchstation (red confirm) */
	size_t misc_offset;
	const char *path;
} Tool;

#define MISC(field) offsetof(SETTING, field)

static const Tool tools[] = {
    {TA_HEADER, -1, "ESSENTIALS", NULL, NULL, 0, 0, NULL},
    {TA_BROWSER, DI_FOLDER, "File Browser", "Browse every device, copy, move, rename, delete, create folders, build and extract PSU saves, mount VMC images and launch anything.", "Press Triangle inside the browser for file operations; Square selects.", 0, 0, NULL},
    {TA_EDITOR, DI_TEXT, "Text Editor", "Edit CNF, CFG, TXT, INI and argument files. Also used to launch an ELF with custom arguments.", NULL, 0, 0, NULL},
    {TA_MISC, DI_DISC, "Start disc", "Boot the disc in the drive: PS2 and PS1 games, DVD Video (with the console's player) and ESR discs.", NULL, 0, MISC(Misc_PS2Disc), NULL},
    {TA_BROWSER_AT, DI_DISC, "PS1 VCDs (POPStarter)", "Open the File Browser; select a .VCD image to start it through POPStarter.", "POPStarter and Ember coexist; the file format chooses the PS1 core automatically.", 0, 0, ""},
    {TA_BROWSER_AT, DI_DISC, "PS1 images (Ember)", "Open the File Browser; select a .CUE, .BIN or PS1 .EXE inside <Ember directory>/games/<Game>/ to start Ember.", "The umbrella can be named anything. Its 512 KB bios.bin stays local; if ember.elf is missing, Settings can supply it from another Ember directory.", 0, 0, ""},
    {TA_BROWSER_AT, DI_DISC, "PS2 ISOs (Neutrino)", "Open the File Browser; select a .ISO image to start it through Neutrino.", "Set Neutrino under Settings > Launching > Disc & image loaders. The game device is also searched automatically.", 0, 0, ""},
    {TA_HEADER, -1, "STORAGE", NULL, NULL, 0, 0, NULL},
    {TA_MISC_MENU, DI_TOOLS, "MISC commands", "Choose a built-in command from the popup menu.", NULL, 0, 0, NULL},
    {TA_USB_DIAG, DI_USB, "USB unit diagnostics", "Inspect the cached USB drive mask without IO, or manually probe logical USB unit 0 or 1 one at a time.", "Each manual probe is a synchronous IOP request and could freeze a failing console. Logical units may not match physical USB ports.", 0, 0, NULL},
    {TA_MISC, DI_HDD, "HDD Manager", "Create, remove, rename and expand APA partitions, view HDL game information and format the internal HDD.", "Partition changes and formatting are permanent.", 0, MISC(Misc_HddManager), NULL},
    {TA_MISC, DI_MC, "Memory card exploit installer", "Install a memory card system-update exploit for this console, another model or region, or PSX/DESR.", "Writes system folders to the memory card. Follow the on-screen checks carefully.", 0, MISC(Misc_Exploit_Installer), NULL},
    {TA_HEADER, -1, "SYSTEM", NULL, NULL, 0, 0, NULL},
    {TA_SOUND_DIAG, DI_PLAY, "Audio diagnostics", "View interface playback counters and the last rejected sound request.", "After reproducing missing sounds, open this page and report the requested, started and failed counts. Values cover this Launchstation session; accepted playback does not measure output at the speakers.", 0, 0, NULL},
    {TA_MISC, DI_APP, "PS2 system browser", "Leave Launchstation and open the console's own Browser.", NULL, 2, MISC(Misc_PS2Browser), NULL},
    {TA_MISC, DI_APP, "OSDSYS", "Start the console's OSD (or the OSDSYS path configured in Launchstation).", NULL, 2, MISC(Misc_OSDSYS), NULL},
#ifdef ETH
    {TA_MISC, DI_NETWORK, "FTP Server", "Start FTP on demand, accept remote commands, and receive staged/resumable ISO transfers from MrRexD-compatible PC tools.", "Switching to Host, UDPFS or Internet clock sync reboots the IOP and stops this server.", 0, MISC(Misc_PS2Net), NULL},
#endif
    {TA_MISC, DI_INFO, "System information", "Console model, ROM version, boot path, loaded configuration and debug details.", NULL, 0, MISC(Misc_Debug_Info), NULL},
    {TA_MISC, DI_CHIP, "Build information", "Features and drivers included in this build of Launchstation.", NULL, 0, MISC(Misc_Show_Build_Info), NULL},
    {TA_MISC, DI_TEXT, "Font viewer", "Show every glyph of the active font.", NULL, 0, MISC(Misc_ShowFont), NULL},
    {TA_MISC, DI_INFO, "About Launchstation", "Credits and version.", NULL, 0, MISC(Misc_About_uLE), NULL},
    {TA_HEADER, -1, "POWER", NULL, NULL, 0, 0, NULL},
    {TA_MISC, DI_REFRESH, "Reboot IOP", "Restart the I/O processor and all device drivers. Devices are detected again when used.", NULL, 2, MISC(Misc_Reboot_IOP), NULL},
    {TA_MISC, DI_POWER, "Power off", "Turn the console off.", NULL, 2, MISC(Misc_PS2PowerOff), NULL},
};

#define NTOOLS ((int)(sizeof(tools) / sizeof(tools[0])))

static int tsel = 1, ttop;
static float tsel_anim = 1.0f;

/* Report wrapping so a multi-step page move can snap its final selection. */
static int tMove(int d)
{
	int start, s, wrapped = 0;

	if (NTOOLS <= 0 || d == 0)
		return 0;
	start = s = tsel;
	do {
		s += d;
		wrapped |= s < 0 || s >= NTOOLS;
		if (s < 0)
			s = NTOOLS - 1;
		else if (s >= NTOOLS)
			s = 0;
		if (tools[s].action != TA_HEADER) {
			if (s != tsel)
				dashUiFocusPoke();
			tsel = s;
			if (wrapped)
				tsel_anim = (float)tsel;
			return wrapped;
		}
	} while (s != start);
	return 0;
}

static void toolsEnter(void)
{
	if (tools[tsel].action == TA_HEADER)
		tMove(1);
}

#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
static int releaseJsonString(const char *json, const char *key, char *out, int out_size)
{
	char needle[64];
	const char *p, *end;
	int n;

	if (json == NULL || key == NULL || out == NULL || out_size <= 0)
		return 0;
	snprintf(needle, sizeof(needle), "\"%s\"", key);
	p = strstr(json, needle);
	if (p == NULL)
		return 0;
	p = strchr(p + strlen(needle), ':');
	if (p == NULL)
		return 0;
	p++;
	while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')
		p++;
	if (*p != '\"')
		return 0;
	p++;
	end = strchr(p, '\"');
	if (end == NULL)
		return 0;
	n = (int)(end - p);
	if (n <= 0 || n >= out_size)
		return 0;
	memcpy(out, p, n);
	out[n] = '\0';
	return 1;
}

static int releaseAssetDigest(const char *json, const char *asset_name, char *out, int out_size)
{
	const char *p = json;
	char name[96], digest[96];

	if (json == NULL || asset_name == NULL || out == NULL || out_size < 72)
		return 0;

	while ((p = strstr(p, "\"name\"")) != NULL) {
		const char *next_name;
		const char *digest_key;

		if (!releaseJsonString(p, "name", name, sizeof(name))) {
			p += 6;
			continue;
		}
		if (strcmp(name, asset_name)) {
			p += 6;
			continue;
		}

		next_name = strstr(p + 6, "\"name\"");
		digest_key = strstr(p, "\"digest\"");
		if (digest_key == NULL || (next_name != NULL && digest_key > next_name) ||
		    !releaseJsonString(digest_key, "digest", digest, sizeof(digest)) ||
		    strncmp(digest, "sha256:", 7) != 0 || strlen(digest) != 71)
			return 0;

		snprintf(out, out_size, "%s", digest);
		return 1;
	}

	return 0;
}

/* Prefer the CA shipped with the running ELF. Existing installs may
 * still keep a user-provided CA in the dashboard configuration folder. */
static int launchstationUpdateCaPath(char *path, int path_size)
{
    const char *dir = LaunchElfBootDir[0] ? LaunchElfBootDir : LaunchElfDir;
    int n;

    if (dir[0]) {
        size_t len = strlen(dir);
        n = snprintf(path, path_size, "%s%sWLE-UPDATE-CA.PEM", dir,
                     dir[len - 1] == '/' ? "" : "/");
        if (n > 0 && n < path_size && wleExists(path))
            return 1;
    }
    return dashStoreBuildPath(path, path_size, "WLE-UPDATE-CA.PEM") == 0 &&
           wleExists(path);
}

/* Compare the installed commit to the published release before offering to
 * replace the running ELF. A different hash alone cannot prove an upgrade.
 * Page 2 suppresses the large first-page changed-files array in GitHub's
 * compare response, keeping the metadata within the PS2 HTTP body limit. */
enum { UPDATE_RELATION_UNKNOWN = -1, UPDATE_RELATION_SAME = 0,
       UPDATE_RELATION_NEWER = 1, UPDATE_RELATION_OLDER = 2,
       UPDATE_RELATION_DIVERGED = 3 };

static int updateIsCommitId(const char *value)
{
    int i, n;
    if (value == NULL)
        return 0;
    n = (int)strlen(value);
    if (n < 7 || n > 40)
        return 0;
    for (i = 0; i < n; i++) {
        char c = value[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
              (c >= 'A' && c <= 'F')))
            return 0;
    }
    return 1;
}

static int updateCommitRelation(const char *current, const char *latest,
                                const char *ca_path, const char *headers,
                                char *error, int error_size)
{
    HttpsResponse response;
    char path[256], status[24];
    int result = UPDATE_RELATION_UNKNOWN, n;

    if (!updateIsCommitId(current) || !updateIsCommitId(latest)) {
        snprintf(error, error_size,
                 "Cannot establish update order for an unrecognized or local build.");
        return result;
    }

    /* compare/base...head: ahead means the release is newer; behind
     * means the installed build is newer. Diverged is NOT an upgrade. */
    n = snprintf(path, sizeof(path),
                 SELF_UPDATE_API_PATH "/compare/%s...%s?per_page=1&page=2",
                 current, latest);
    if (n <= 0 || n >= (int)sizeof(path)) {
        snprintf(error, error_size, "Commit comparison URL was too long.");
        return result;
    }

    memset(&response, 0, sizeof(response));
    if (httpsRequest("GET", "api.github.com", path, headers, NULL, 0,
                         ca_path, &response, error, error_size) < 0)
        return result;
    if (response.status != 200 ||
        !releaseJsonString(response.body, "status", status, sizeof(status))) {
        snprintf(error, error_size,
                 "GitHub did not provide a valid commit ancestry comparison (HTTP %d).",
                 response.status);
    } else if (!strcmp(status, "ahead")) {
        result = UPDATE_RELATION_NEWER;
    } else if (!strcmp(status, "behind")) {
        result = UPDATE_RELATION_OLDER;
    } else if (!strcmp(status, "identical")) {
        result = UPDATE_RELATION_SAME;
    } else if (!strcmp(status, "diverged")) {
        result = UPDATE_RELATION_DIVERGED;
    } else {
        snprintf(error, error_size, "GitHub returned an unknown commit relationship.");
    }
    httpsResponseFree(&response);
    return result;
}

void dashToolsCheckUpdates(void)
{
	HttpsResponse response;
	char ca_path[MAX_PATH], error[192], latest[80], asset_digest[80], body[320];
	const char headers[] =
	    "User-Agent: Launchstation-PS2\r\n"
	    "Accept: application/vnd.github+json\r\n";
	int same = 0;

	if (!updateIsCommitId(GIT_HASH)) {
		snprintf(body, sizeof(body),
		         "This ELF identifies its commit as '%s'. Update checks need a usable Git commit ID.",
		         GIT_HASH);
		dashModalMessage(DI_WARNING, "Update check needs build information", body,
		                 "Install a complete release package built with commit information, then restart Launchstation.");
		return;
	}

	/* CA/device access and network stack changes use synchronous IOP RPCs.
	 * Finish queued IO and any root-card status request before starting. */
	if (!dashWorkerAwaitAll("Finishing background storage work"))
		return;
	filerRootMcPollIdle();

	if (!launchstationUpdateCaPath(ca_path, sizeof(ca_path))) {
		dashModalMessage(DI_WARNING, "Update check needs the CA bundle",
		                 "WLE-UPDATE-CA.PEM was not found beside the running ELF or in the dashboard settings folder.",
		                 "Install the complete Launchstation ZIP/PSU package, or copy res/WLE-UPDATE-CA.PEM beside the boot ELF.");
		return;
	}
	if (!ensureDashboardIpNetworkReady()) {
		dashModalMessage(DI_WARNING, "Update check unavailable",
		                 dashboardIpNetworkError(), NULL);
		return;
	}

	memset(&response, 0, sizeof(response));
	error[0] = latest[0] = asset_digest[0] = '\0';
	dashLoadingBegin("Checking for Launchstation updates");
	if (httpsRequest("GET", "api.github.com",
	                     SELF_UPDATE_API_PATH "/releases/tags/latest",
	                     headers, NULL, 0, ca_path, &response,
	                     error, sizeof(error)) < 0) {
		dashLoadingEnd();
		dashModalMessage(DI_WARNING, "Update check failed",
		                 error[0] ? error : "GitHub could not be reached.", NULL);
		return;
	}
	dashLoadingEnd();

	if (response.status != 200 ||
	    !releaseJsonString(response.body, "target_commitish", latest, sizeof(latest)) ||
	    !releaseAssetDigest(response.body, SELF_UPDATE_ASSET,
	                        asset_digest, sizeof(asset_digest))) {
		snprintf(body, sizeof(body), "GitHub returned HTTP %d or an unexpected release response.", response.status);
		httpsResponseFree(&response);
		dashModalMessage(DI_WARNING, "Update check failed", body, NULL);
		return;
	}
	httpsResponseFree(&response);

	if (strcmp(GIT_HASH, "local") != 0 && strlen(GIT_HASH) <= strlen(latest) &&
	    !strncmp(latest, GIT_HASH, strlen(GIT_HASH)))
		same = 1;

	if (same) {
		snprintf(body, sizeof(body), "This build (%s) matches the current latest release.", GIT_HASH);
		dashModalMessage(DI_CHECK, "Launchstation is up to date", body, NULL);
	} else {
		char install_result[384];
		int installed, relation;

		error[0] = '\0';
		dashLoadingBegin("Verifying release is newer");
		relation = updateCommitRelation(GIT_HASH, latest, ca_path, headers,
		                                error, sizeof(error));
		dashLoadingEnd();
		if (relation == UPDATE_RELATION_SAME || relation == UPDATE_RELATION_OLDER) {
			snprintf(body, sizeof(body),
			         "Installed: %s\nPublished: %.16s\n\nThe published release is not newer. No update is needed.",
			         GIT_HASH, latest);
			dashModalMessage(DI_CHECK, "No newer release available", body, NULL);
			return;
		}
		if (relation == UPDATE_RELATION_DIVERGED) {
			dashModalMessage(DI_WARNING, "Release is on another commit history",
			                 "The published release is not a verified descendant of this build. Automatic replacement was blocked.",
			                 "Use a complete ZIP/PSU package to change builds manually.");
			return;
		}
		if (relation != UPDATE_RELATION_NEWER) {
			dashModalMessage(DI_WARNING, "Could not verify update order",
			                 error[0] ? error : "Unable to compare installed and published commits.",
			                 "No files were changed. Update manually only after checking the release.");
			return;
		}

		snprintf(body, sizeof(body),
		         "Current: %s\nLatest: %.16s\n\nGitHub confirms this release is newer. Download and install the packed ELF?",
		         GIT_HASH, latest);
		if (!dashModalConfirm("A newer Launchstation build is available",
		                      body, "Install update", 0))
			return;

		install_result[0] = '\0';
		dashLoadingBegin("Downloading and verifying Launchstation update");
		installed = selfUpdateInstall(ca_path, asset_digest, install_result, sizeof(install_result));
		dashLoadingEnd();
		dashModalMessage(installed == 0 ? DI_CHECK : DI_WARNING,
		                 installed == 0 ? "Update installed" : "Update was not installed",
		                 install_result[0] ? install_result :
		                     (installed == 0 ? "The update was installed." : "The update failed."),
		                 installed == 0
		                     ? "The current session keeps running the old code until you restart. The previous ELF remains beside it as .BAK."
		                     : "The updater stages and verifies the complete download before changing the running ELF.");
	}
}
#else
void dashToolsCheckUpdates(void)
{
	dashModalMessage(DI_INFO, "Update checking unavailable",
	                 "This build does not include native HTTPS support.", NULL);
}
#endif


/* Explicit hardware diagnostic for two connected USB drives. Never called by
 * normal device discovery and never modifies global USB mount discovery.
 * A wedged IOP fileXio RPC cannot be cancelled; warn before every probe. */
static void dashToolsUsbUnitDiagnostics(void)
{
	static const char *const choices[] = {
		"Show cached units (no I/O)",
		"Probe logical unit 0 once",
		"Probe logical unit 1 once"
	};
	char path[12], status[96], body[240];
	iox_stat_t stat;
	int choice = dashModalChoice("USB unit diagnostics", choices, 3, 0);
	int mask, result;

	if (choice < 0 || choice > 2)
		return;
	if (choice == 0) {
		if (!filerUsbDriversLoaded()) {
			dashModalMessage(DI_INFO, "USB cache", "USB storage drivers are not loaded. No USB filesystem request was made.", NULL);
			return;
		}
		mask = filerUsbDriveMask();
		snprintf(body, sizeof(body),
		         "Last recorded units: %s%s%s. This is cached state only; no device I/O was performed.",
		         (mask & 1) ? "unit 0" : "",
		         ((mask & 3) == 3) ? ", " : "",
		         (mask & 2) ? "unit 1" : ((mask & 1) ? "" : "none confirmed"));
		dashModalMessage(DI_INFO, "USB cached units", body, NULL);
		return;
	}

	if (!dashModalConfirm("Probe one USB unit?",
	                      "A single synchronous USB filesystem request may freeze a failing console. No automatic IOP reset or timeout can interrupt it. Continue?",
	                      "Probe once", 0))
		return;
	if (!dashWorkerAwaitAll("Finishing background storage work"))
		return;
	/* Worker/file operations must finish before accessing synchronous IOP
	 * fileXio, and libmc may still have a pending EE-side status RPC. */
	filerRootMcPollIdle();
	dashLoadingBegin("Preparing USB diagnostic");
	if (!isUsbMassStackLoaded())
		loadUsbModules();
	if (!isUsbMassStackLoaded()) {
		dashLoadingEnd();
		dashModalMessage(DI_WARNING, "USB driver unavailable",
		                 "USB modules could not be started. No filesystem probe was issued.", NULL);
		return;
	}
#ifdef EXFAT
	snprintf(path, sizeof(path), "usb%c:/", (char)('0' + choice - 1));
#else
	snprintf(path, sizeof(path), "mass%c:/", (char)('0' + choice - 1));
#endif
	snprintf(status, sizeof(status), "Checking USB root %s", path);
	/* Present this exact unit before the blocking RPC, so the last frame
	 * identifies the stuck request even if the pad/IOP becomes unresponsive. */
	dashLoadingFrame(status, 0, 0);
	DPRINTF("[USB diagnostic] begin %s\n", path);
	memset(&stat, 0, sizeof(stat));
	result = fileXioGetStat(path, &stat);
	DPRINTF("[USB diagnostic] end %s result=%d\n", path, result);
	dashLoadingEnd();
	snprintf(body, sizeof(body),
	         "%s returned %d (%s). One logical unit was probed, not the other. A successful root stat does not prove file reads or power stability.",
	         path, result, result >= 0 ? "root responded" : "root unavailable / error");
	dashModalMessage(result >= 0 ? DI_CHECK : DI_WARNING,
	                 "Single-unit USB probe result", body,
	                 "Logical USB units are not guaranteed to match physical ports.");
}

/* Close the command popup before dispatching so native tab switches are
 * immediately visible. Labels follow the configured/localized MISC paths. */
static void showMiscCommands(void)
{
	const struct {
		const char *path;
		int icon;
	} commands[] = {
	    {setting->Misc_PS2Disc, DI_DISC},
	    {setting->Misc_FileBrowser, DI_FOLDER},
	    {setting->Misc_PS2Browser, DI_APP},
	    {setting->Misc_PS2Net, DI_NETWORK},
	    {setting->Misc_PS2PowerOff, DI_POWER},
	    {setting->Misc_HddManager, DI_HDD},
	    {setting->Misc_TextEditor, DI_TEXT},
	    {setting->Misc_Configure, DI_SETTINGS},
	    {setting->Misc_ShowFont, DI_TEXT},
	    {setting->Misc_Debug_Info, DI_INFO},
	    {setting->Misc_About_uLE, DI_INFO},
	    {setting->Misc_Show_Build_Info, DI_CHIP},
	    {setting->Misc_OSDSYS, DI_APP},
	    {setting->Misc_Exploit_Installer, DI_MC},
	    {setting->Misc_Reboot_IOP, DI_REFRESH}};
	DashMenuItem items[sizeof(commands) / sizeof(commands[0])];
	const char *paths[sizeof(commands) / sizeof(commands[0])];
	size_t prefix = strlen(setting->Misc);
	unsigned int i;
	int count = 0, selected;

	for (i = 0; i < sizeof(commands) / sizeof(commands[0]); i++) {
		const char *path = commands[i].path;

		if (strncmp(path, setting->Misc, prefix) || path[prefix] == '\0')
			continue;
		items[count].icon = commands[i].icon;
		items[count].label = getMiscEntryDisplayName(setting->Misc, path + prefix);
		items[count].detail = NULL;
		items[count].disabled = 0;
		paths[count++] = path;
	}
	if (count == 0)
		return;
	selected = dashModalMenu("MISC commands", NULL, items, count, 0);
	if (selected >= 0 && selected < count)
		dashRunMisc(paths[selected]);
}

static void showSoundDiagnostics(void)
{
	char status[512];

	dashSoundGetStatus(status, sizeof(status));
	dashModalMessage(DI_PLAY, "Audio diagnostics", status, NULL);
}

static void runTool(const Tool *t)
{
	if (t->confirm) {
		char body[200];
		const char *action_label = t->confirm == 2 ? t->name : "Continue";
		if (t->action == TA_MISC &&
		    (t->misc_offset == MISC(Misc_PS2Browser) || t->misc_offset == MISC(Misc_OSDSYS)))
			action_label = "Leave";
		snprintf(body, sizeof(body), "%s", t->desc);
		if (!dashModalConfirm(t->name, body, action_label, t->confirm == 2))
			return;
	}
	switch (t->action) {
		case TA_MISC:
			dashRunMisc((const char *)setting + t->misc_offset);
			break;
		case TA_BROWSER:
			dashNavigateFilesTab(NULL);
			break;
		case TA_BROWSER_AT:
			dashNavigateFilesTab(t->path);
			break;
		case TA_MISC_MENU:
			showMiscCommands();
			break;
		case TA_EDITOR:
			dashOpenTextEditor(NULL);
			break;
		case TA_USB_DIAG:
			dashToolsUsbUnitDiagnostics();
			break;
		case TA_SOUND_DIAG:
			showSoundDiagnostics();
			break;
	}
}

static void toolsInput(const DashInput *in)
{
	int i, wrapped = 0;

	if (in->pressed & DASH_IN_UP)
		wrapped |= tMove(-1);
	if (in->pressed & DASH_IN_DOWN)
		wrapped |= tMove(1);
	if (in->pressed & (DASH_IN_L2 | DASH_IN_LEFT))
		for (i = 0; i < 6; i++)
			wrapped |= tMove(-1);
	if (in->pressed & (DASH_IN_R2 | DASH_IN_RIGHT))
		for (i = 0; i < 6; i++)
			wrapped |= tMove(1);
	if (wrapped)
		tsel_anim = (float)tsel;
	if (in->pressed & DASH_IN_OK)
		runTool(&tools[tsel]);
}

static void toolsUpdate(float dt)
{
	tsel_anim = dashApproach(tsel_anim, (float)tsel, 16.0f * dashAnimSpeed(), dt);
}

static void toolsDraw(void)
{
	const float lx = DASH_SAFE_L, ly = 102, row_h = 29, lw = 300;
	const int rows = 10;
	const Tool *t = &tools[tsel];
	int i;

	dashDrawSectionTitle(lx, 68, "Tools", "everything Launchstation can do");
	ttop = listCenteredTop(tsel, NTOOLS, rows);
	if (tsel_anim < ttop || tsel_anim >= ttop + rows)
		tsel_anim = (float)tsel;

	dashDrawPanelBox(lx - 6, ly - 6, lw + 12, rows * row_h + 12, 14);
	dashGfxScissor(lx - 6, ly - 4, lw + 12, rows * row_h + 8);
	{
		float fy = ly + (tsel_anim - ttop) * row_h;
		dashDrawSelection(lx, fy, lw, row_h - 3, 9, 1.0f);
	}
	for (i = ttop; i < NTOOLS && i < ttop + rows; i++) {
		float y = ly + (i - ttop) * row_h;

		if (tools[i].action == TA_HEADER) {
			dashText(lx + 8, y + 7, tools[i].name, DASH_FS_CAPTION, DASH_C_ACCENT);
			continue;
		}
		dashIcon(tools[i].icon, lx + 10, y + 5, 16, dashItemColor(i == tsel));
		dashTextFit(lx + 34, y + 3.0f, lw - 44, tools[i].name, DASH_FS_SMALL, dashItemColor(i == tsel));
		if (tools[i].confirm == 2 || tools[i].note)
			dashGlow(lx + lw - 14, y + 13, 4, 4, tools[i].confirm == 2 ? DASH_C_DANGER : DASH_C_WARM);
	}
	dashGfxScissorReset();
	dashDrawScrollbar(lx + lw + 10, ly, rows * row_h, ttop, rows, NTOOLS);

	{
		float dx = lx + lw + 24, dy = 98, dw = DASH_PANE_R - dx, dh = 292;

		dashDrawCard(dx, dy, dw, dh, 16);
		dashAccentGlow(dx + dw * 0.5f, dy + 66, 80, 60, 1.0f);
		dashIcon(t->icon, dx + dw * 0.5f - 30, dy + 34, 60, DASH_C_TEXT);
		dashTextCenter(dx + dw * 0.5f, dy + 108, t->name, DASH_FS_BODY, DASH_C_TEXT);
		dashTextWrap(dx + 16, dy + 142, dw - 32, 4, t->desc, DASH_FS_CAPTION, DASH_C_TEXT2, 19);
		if (t->note) {
			DashColor wb = dashColorScale(DASH_C_WARM, 0.24f);
			wb.a = 130;
			dashPanel(dx + 12, dy + dh - 64, dw - 24, 52, 10, wb);
			dashRect(dx + 12, dy + dh - 64, 3, 52, dashColorA(DASH_C_WARM, 0.8f));
			dashIcon(DI_WARNING, dx + 20, dy + dh - 54, 16, DASH_C_WARM);
			dashTextWrapScrollTimed(dx + 42, dy + dh - 58, dw - 62, 36, t->note,
			                        DASH_FS_CAPTION * 0.95f, DASH_C_WARM, 18, dashUiFocusAge());
		}
	}
}

static void toolsHints(void)
{
	DashHint h[1];

	h[0].button = dashOkIcon(), h[0].key = NULL, h[0].label = "Open";
	dashDrawHints(h, 1);
}

const DashScreen dashToolsScreen = {toolsEnter, toolsInput, toolsUpdate, toolsDraw, toolsHints};
//--------------------------------------------------------------
//End of file: dash_tools.c
//--------------------------------------------------------------
