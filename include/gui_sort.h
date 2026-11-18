#ifndef GUI_SORT_H
#define GUI_SORT_H

#include "launchelf.h"

/* Fixed system-partition order shared by HDD Manager and HDD browsing. */
int hddPartitionPriority(const char *name);

int cmpFile(FILEINFO *a, FILEINFO *b);
void sort(FILEINFO *a, int left, int right);

#endif
