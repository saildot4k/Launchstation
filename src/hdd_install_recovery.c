#include "hdd_install_recovery.h"

static volatile int active, fault, reset_requested, reset_complete;
static volatile int reboot_pending, reboot_result;
void hddInstallRecoveryBegin(void)
{
    fault = reset_requested = reset_complete = 0;
    reboot_pending = reboot_result = 0;
    active = 1;
}
void hddInstallRecoveryEnd(void) { active = 0; }
int hddInstallRecoveryActive(void) { return active; }
int hddInstallRecoveryFault(void) { return active ? fault : 0; }
void hddInstallRecoveryObserve(int result)
{
    if (active && result == HDD_INSTALL_ATA_TIMEOUT) fault = result;
}
void hddInstallRecoveryRequestReset(void)
{
    if (active) { fault = HDD_INSTALL_ATA_TIMEOUT; reset_requested = 1; }
}
int hddInstallRecoveryResetRequested(void) { return active && reset_requested && !reset_complete; }
void hddInstallRecoveryResetComplete(void) { reset_complete = 1; }
int hddInstallRecoveryWasReset(void) { return reset_complete; }

void hddInstallRebootRequest(void) { reboot_pending = 1; }
int hddInstallRebootPending(void) { return reboot_pending; }
void hddInstallRebootComplete(int result)
{
    reboot_result = result;
    reboot_pending = 0;
}
int hddInstallRebootResult(void) { return reboot_result; }
