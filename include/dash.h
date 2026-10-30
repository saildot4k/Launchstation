//--------------------------------------------------------------
//File name:   dash.h
//Public entry points of the wLaunchELF dashboard shell.
//--------------------------------------------------------------
#ifndef DASH_H
#define DASH_H

#include <tamtypes.h>
#include "main_actions.h"

/* Runs the dashboard shell. Returns only when the user asks for the classic
 * launch-key menu; everything else (launching, tools, the FileBrowser) is
 * dispatched through ExecuteMainAction() exactly as the classic menu does. */
void DashRun(const MainExecuteContext *ctx, int from_boot);

/* Non-zero when the dashboard should replace the classic menu at boot.
 * Reads the dashboard settings file on first use; defaults to enabled. */
int DashIsEnabled(void);

/* Non-zero while DashRun() is on the call stack (guards re-entry). */
int DashIsActive(void);
/* Route Configure to Settings when the dashboard owns the screen. */
int DashOpenSettings(void);

/* Publish the next blocking storage operation before entering its RPC.
 * Worker callers only update status; UI callers draw an existing overlay. */
void DashStorageProbeStatus(const char *status);
/* Transfer values come from the copy engine's R3Z 4.80 calculations.
 * Speeds are bytes/second; negative speed/time means no estimate yet.
 * Remaining time covers this file; written total/average cover the paste batch. */
typedef struct
{
	u64 written_total;
	int current_speed;
	int average_speed;
	int remaining_seconds;
} DashTransferStats;

/* Main-thread file-operation progress. Returns zero in classic mode. */
int DashFileProgress(const char *action, const char *name, u64 remaining, u64 total);
/* NULL stats shows byte-counted progress without transfer speed/ETA. */
int DashFileTransferProgress(const char *action, const char *name, u64 remaining, u64 total,
                             const DashTransferStats *stats);
void DashFileDeleteProgress(const char *name);

/* Finish dashboard-owned IO/audio before a child ELF that deliberately
 * inherits the live IOP. Returns 0 if the user cancels the bounded wait. */
int DashPrepareKeepIopHandoff(const char *title);
/* Release Confirm for the saved mode, or hold one second to reverse it.
 * Does not edit configuration; callers retain the returned mode per launch. */
int DashChooseElfIopMode(int configured);

/* Path of the MISC pseudo-command that opens the dashboard. */
const char *DashMiscCommandName(void);

/* Legacy-screen theming (dash_theme.c). */
int DashThemeLegacyEnabled(void);
void DashThemeSetLegacyEnabled(int enabled);
void DashThemeBackgroundRect(int x1, int y1, int x2, int y2);
void DashThemePopupRect(int x1, int y1, int x2, int y2);
void DashThemeFrame(int x1, int y1, int x2, int y2, u64 color);
void DashThemeChar(unsigned int c, int x, int y, u64 colour);
void DashThemeSelectionBar(int x1, int y1, int x2, int y2);

#endif
