#ifndef HDD_INSTALL_RESUME_H
#define HDD_INSTALL_RESUME_H
#include "hdd_install.h"

/* Versioned, bounded little-endian journal. No pointers or native ABI data. */
#define HDD_INSTALL_RESUME_MAX 65536u
int hddInstallResumeEncode(const HddInstall *in, const HddFormatPlan *plan,
                          unsigned sequence, void *bytes, unsigned capacity);
int hddInstallResumeDecode(HddInstall *in, HddFormatPlan *plan, unsigned *sequence,
                          const void *bytes, unsigned size);
/* One serialized installer session; begin only after user confirmation. */
void hddInstallResumeBegin(HddInstall *in, const HddFormatPlan *plan, unsigned sequence);
void hddInstallResumeEnd(void);
int hddInstallResumeSave(HddInstall *in);
int hddInstallResumeLoad(HddInstall *in, HddFormatPlan *plan, unsigned *sequence);
/* Menu probe: existing incomplete log plus newest valid, uncommitted journal.
 * No CA/network preparation or full installation-layout validation. */
int hddInstallResumeAvailable(int jail);
int hddInstallLogComplete(const char *tail, unsigned size);
int hddInstallResumeRemove(HddInstall *in);
#endif
