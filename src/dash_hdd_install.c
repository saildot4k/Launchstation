#include "dash_internal.h"
#include "hdd_install.h"
#include "init.h"
#include "filer_shared.h"

int dashHddInstallChoose(HddInstall *in, int jail)
{
    memset(in, 0, sizeof(*in)); in->jail = jail;
#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
#ifndef EXFAT
    if (jail) return 1; /* no ATA filesystem driver in this build */
#endif
    {
        static const char *const profiles[] = {
            "Format only",
            "Install WLE-R3Z and R3CONFIGURATOR",
            "Install OSDMenu MBR and HOSDMenu",
            "Install MBR, HOSDMenu and included apps"
        };
        static const unsigned flags[] = {0, HDD_INSTALL_APPS, HDD_INSTALL_HOSD, HDD_INSTALL_HOSD | HDD_INSTALL_APPS};
        static const char *const jail_profiles[] = {
            "Format only", "Install PSBBN DP (English), MBR, HOSDMenu and apps"
        };
        int selected = dashModalChoice("Software after formatting", jail ? jail_profiles : profiles, jail ? 2 : 4, 0);
        if (selected < 0) return 0;
        in->flags = jail && selected ? HDD_INSTALL_PSBBN | HDD_INSTALL_HOSD | HDD_INSTALL_APPS : flags[selected];
        if (in->flags & HDD_INSTALL_PSBBN)
            dashModalMessage(DI_INFO, "PSBBN DP installation",
                "Requires a compatible Sony Network Adapter. Choose Music and Contents sizes next. Standalone PS2 Linux is optional; PSBBN always needs its own system partitions. Downloads are stored on the new HDD after formatting.", NULL);
    }
#endif
    return 1;
}

#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
static int installSize(const char *title, unsigned maximum)
{
    char labels[6][24];
    const char *items[6];
    int count = 0, selected;
    for (unsigned mb = 1024; mb <= maximum && count < 6; mb *= 2) {
        snprintf(labels[count], sizeof(labels[count]), "%u GiB", mb / 1024);
        items[count] = labels[count]; count++;
    }
    if (!count) return -1;
    selected = dashModalChoice(title, items, count, 0);
    return selected < 0 ? -1 : 1024 << selected;
}
#endif
int dashHddInstallConfigure(HddInstall *in, unsigned max_extent)
{
#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
    static const char *const linux[] = {"Off", "On"};
    int value;
    value = installSize("Music partition size", max_extent);
    if (value < 0) return 0;
    in->music_mb = value;
    value = installSize("Contents partition size", max_extent);
    if (value < 0) return 0;
    in->contents_mb = value;
    value = dashModalChoice("Install standalone PS2 Linux", linux, 2, 0);
    if (value < 0) return 0;
    in->flags &= ~HDD_INSTALL_PS2LINUX;
    in->linux_home_mb = 0;
    if (value) {
        unsigned maximum = max_extent < HDD_INSTALL_HOME_MAX_MB ? max_extent : HDD_INSTALL_HOME_MAX_MB;
        dashModalMessage(DI_INFO, "PS2 Linux space", "PS2 Linux needs a 2 GiB system partition plus the home size you choose next. A USB keyboard is required to use it.", NULL);
        value = installSize("PS2 Linux home size", maximum);
        if (value < 0) return 0;
        in->linux_home_mb = value;
        in->flags |= HDD_INSTALL_PS2LINUX;
    }
    return 1;
#else
    (void)in; (void)max_extent; return 0;
#endif
}

/* Preserve the CA file before formatting, including when Launchstation and
 * its settings were loaded from the drive that is about to be erased. */
int dashHddInstallPrepare(HddInstall *in)
{
#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
    if (!in->flags) return 1;
    if (!dashWorkerAwaitAll("Preparing installer")) return 0;
    if (!dashHttpsCaPath(in->ca_path, sizeof(in->ca_path)) || hddInstallLoadCa(in) < 0) {
        dashModalMessage(DI_WARNING, "Installer needs the CA bundle",
            "WLE-UPDATE-CA.PEM could not be read beside Launchstation or in its settings folder.", NULL);
        return 0;
    }
    hddInstallLog("Preparing network stack");
    if (!ensureDashboardIpNetworkReady()) {
        dashModalMessage(DI_WARNING, "Internet unavailable", dashboardIpNetworkError(), NULL);
        hddInstallRelease(in); return 0;
    }
    return 1;
#else
    (void)in;
    return 0;
#endif
}

int dashHddInstallPrepareStorage(HddInstall *in)
{
#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
    /* Formatting resets the IOP. Restore network/storage before the worker
     * mounts PFS or opens ata0; no external staging device is needed. */
    hddInstallLog("Preparing network stack");
    if (!ensureDashboardIpNetworkReady()) {
        snprintf(in->error, sizeof(in->error), "%s", dashboardIpNetworkError());
        return -EIO;
    }
    hddInstallLog("Loading HDD/PFS modules");
    if (!loadHddModules()) return -ENODEV;
#ifdef EXFAT
    hddInstallLog("Loading ATA filesystem modules (jail=%d)", in->jail);
    if (in->jail && !loadAtaModules()) return -ENODEV;
#endif
    snprintf(in->stage, sizeof(in->stage), "%s/PSBBN_DP_TEMP", in->jail ? "ata0:" : "pfs2:");
    return 0;
#else
    (void)in;
    return -ENOSYS;
#endif
}

/* Temporary verbose UI. The loading-view callback only draws; controller
 * polling belongs to the normal wait/review loops, never RPC wait frames. */
static DashLoadingView debug_previous_view;
static int debug_open, debug_review, debug_result, debug_rows = 8;
static int debug_top = -1;

static void debugInput(const DashInput *in)
{
    HddInstallLogSnapshot snapshot;
    int top, tail;
    hddInstallLogSnapshot(&snapshot);
    tail = (int)snapshot.next - debug_rows;
    if (tail < (int)snapshot.first) tail = snapshot.first;
    top = debug_top < 0 ? tail : debug_top;
    if (in->pressed & DASH_IN_UP) top--;
    if (in->pressed & DASH_IN_DOWN) top++;
    if (in->pressed & DASH_IN_LEFT) top -= debug_rows;
    if (in->pressed & DASH_IN_RIGHT) top += debug_rows;
    if (top < (int)snapshot.first) top = snapshot.first;
    debug_top = top >= tail || (in->pressed & DASH_IN_FAV) ? -1 : top;
}
static void debugDraw(const char *title)
{
    HddInstallLogSnapshot snapshot;
    const float x = 20, y = 20, w = DASH_VW - 40, h = DASH_VH - 40;
    const float log_y = y + 150, hints_y = y + h - 50;
    char line[HDD_INSTALL_LOG_COLS], counters[160];
    unsigned first, tail;
    float hx;
    hddInstallLogSnapshot(&snapshot);
    debug_rows = (int)((hints_y - 10 - log_y) / 24);
    if (debug_rows < 1) debug_rows = 1;
    tail = snapshot.next > (unsigned)debug_rows ? snapshot.next - debug_rows : 0;
    if (tail < snapshot.first) tail = snapshot.first;
    if (debug_top >= 0 && debug_top < (int)snapshot.first) debug_top = snapshot.first;
    first = debug_top < 0 ? tail : (unsigned)debug_top;
    dashRenderScene();
    dashModalBackdrop(1);
    dashModalPanel(x, y, w, h, 1);
    dashIcon(debug_review ? (debug_result < 0 ? DI_WARNING : DI_CHECK) : DI_HDD,
             x + 20, y + 18, 22, debug_result < 0 && debug_review ? DASH_C_DANGER : DASH_C_ACCENT);
    dashTextFit(x + 52, y + 18, w - 90, title, DASH_FS_LABEL, DASH_C_TEXT);
    if (!debug_review) dashDrawSpinner(x + w - 24, y + 29, 7, DASH_C_ACCENT);
    dashTextFit(x + 20, y + 48, w - 40, snapshot.status, DASH_FS_SMALL, DASH_C_TEXT2);
    if (snapshot.io[0]) dashTextFit(x + 20, y + 72, w - 40, snapshot.io, DASH_FS_SMALL, DASH_C_TEXT3);
    dashRect(x + 20, y + 100, w - 40, 5, dashColorA(DASH_C_TEXT3, 0.3f));
    if (snapshot.total > 0)
        dashRect(x + 20, y + 100, (w - 40) * dashClampf(snapshot.done / (float)snapshot.total, 0, 1), 5, DASH_C_ACCENT);
    snprintf(counters, sizeof(counters), "Elapsed %u:%02u | Last update %u s ago | %d / %d",
             (unsigned)(snapshot.elapsed / 60000), (unsigned)(snapshot.elapsed / 1000 % 60),
             (unsigned)(snapshot.idle / 1000), snapshot.done, snapshot.total);
    dashTextFit(x + 20, y + 112, w - 40, counters, DASH_FS_SMALL, DASH_C_TEXT2);
    snprintf(counters, sizeof(counters), "Diagnostic log: lines %u-%u of %u%s", first + 1,
             first + debug_rows < snapshot.next ? first + debug_rows : snapshot.next,
             snapshot.next, debug_top < 0 ? " (live)" : " (scrolling)");
    dashText(x + 20, y + 134, counters, DASH_FS_CAPTION, DASH_C_TEXT3);
    dashGfxScissorPush(x + 20, log_y, w - 40, debug_rows * 24);
    for (int row = 0; row < debug_rows && first + row < snapshot.next; row++) {
        if (!hddInstallLogRead(first + row, line)) continue;
        dashTextFit(x + 20, log_y + row * 24, w - 40, line, DASH_FS_SMALL,
                    strstr(line, "ERROR") || strstr(line, "FAILED") ? DASH_C_DANGER : DASH_C_TEXT);
    }
    dashGfxScissorPop();
    hx = x + 20;
    hx += dashDrawButton(hx, hints_y, DI_BTN_UP, NULL);
    hx += dashDrawButton(hx, hints_y, DI_BTN_DOWN, NULL) + 4;
    hx = dashTextS(hx, dashButtonTextY(hints_y, DASH_FS_SMALL), "Log", DASH_FS_SMALL, DASH_C_TEXT2) + 16;
    hx += dashDrawButton(hx, hints_y, -1, "LEFT/RIGHT") + 4;
    hx = dashTextS(hx, dashButtonTextY(hints_y, DASH_FS_SMALL), "Page", DASH_FS_SMALL, DASH_C_TEXT2) + 16;
    hx += dashDrawButton(hx, hints_y, DI_BTN_SQUARE, NULL) + 4;
    hx = dashTextS(hx, dashButtonTextY(hints_y, DASH_FS_SMALL), "Latest", DASH_FS_SMALL, DASH_C_TEXT2) + 16;
    if (debug_review) dashModalHintRow(hx, hints_y, dashOkIcon(), "Close", -1, NULL);
    if (snapshot.disk_error)
        snprintf(counters, sizeof(counters), "Log write error %d; messages remain in RAM", snapshot.disk_error);
    else if (snapshot.path[0]) snprintf(counters, sizeof(counters), "Log: %.150s", snapshot.path);
    else snprintf(counters, sizeof(counters), "RAM log; file will be saved when the HDD temporary folder is ready");
    dashTextFit(x + 20, y + h - 22, w - 40, counters, DASH_FS_CAPTION, DASH_C_TEXT3);
    dashGfxPresent();
}
void dashHddInstallDebugBegin(HddInstall *in, const HddFormatPlan *plan)
{
    if (!(in->flags & HDD_INSTALL_PSBBN)) return;
    hddInstallLogStart();
    if (!hddInstallLogEnabled()) return;
    debug_top = -1; debug_open = 1; debug_review = debug_result = 0;
    debug_previous_view = dashLoadingSetView(debugDraw);
    hddInstallLog("Launchstation build %s", GIT_HASH);
    hddInstallLog("Layout kind=%u sectors=%u APA=%u reserve=%u MiB", (unsigned)plan->kind, (unsigned)plan->sectors, (unsigned)plan->apa_sectors, (unsigned)plan->reserve_mb);
    hddInstallLog("exFAT first=%u sectors=%u recovery=%u", (unsigned)plan->exfat_start, (unsigned)plan->exfat_sectors, (unsigned)plan->recovery_start);
    hddInstallLog("Choices: Music=%u MiB Contents=%u MiB PS2 Linux=%s Home=%u MiB Free APA reserve=%u MiB",
                  in->music_mb, in->contents_mb, in->flags & HDD_INSTALL_PS2LINUX ? "On" : "Off", in->linux_home_mb, in->reserved_mb);
    hddInstallStatus("Preparing installer; the HDD has not been erased yet", 0, 0);
    dashLoadingBegin("PSBBN DP installer diagnostics");
}
int dashHddInstallAwait(int id, const char *title)
{
    int owns_loading = !dashLoadingActive();
    if (!debug_open) return dashWorkerAwait(id, title, 0);
    if (owns_loading) dashLoadingBegin(title);
    while (!dashWorkerDone(id)) {
        DashInput in;
        dashWorkerPump();
        if (dashWorkerDone(id)) break;
        dashInputPoll(&in); debugInput(&in);
        dashLoadingFrame(NULL, 0, 0);
    }
    if (owns_loading) dashLoadingEnd();
    return 1;
}
static void debugSave(void *context)
{
    HddInstall *in = context;
    int ret = hddInstallMountStage(in);
    if (ret >= 0) { hddInstallLogFlush(in); ret = hddInstallUnmountStage(in); }
    if (ret < 0) hddInstallLog("ERROR reopening log volume: %d", ret);
}
void dashHddInstallDebugEnd(HddInstall *in, int result)
{
    if (!debug_open) return;
    hddInstallLog("SESSION %s: result=%d", result == -ECANCELED ? "CANCELLED" : result < 0 ? "FAILED" : "COMPLETE", result);
    if (in->error[0]) hddInstallLog("ERROR detail: %s", in->error);
    if (in->owned) {
        int id = dashWorkerSubmit("Saving installer diagnostics", 0, debugSave, NULL, in);
        if (id > 0) dashHddInstallAwait(id, "Saving installer diagnostics");
        else hddInstallLog("ERROR log-save job could not be queued");
    }
    hddInstallLogStop();
    dashLoadingEnd();
    debug_review = 1; debug_result = result; debug_top = -1;
    if (result != -ECANCELED) {
        dashInputFlush();
        for (;;) {
            DashInput input;
            dashInputPoll(&input);
            if (input.pressed & (DASH_IN_OK | DASH_IN_BACK)) break;
            debugInput(&input);
            dashVisualUpdate();
            debugDraw(result < 0 ? "PSBBN DP installer failed" : "PSBBN DP installer complete");
        }
    }
    dashLoadingSetView(debug_previous_view); debug_open = 0;
    dashGfxSetPopup(0); dashInputFlush();
}
