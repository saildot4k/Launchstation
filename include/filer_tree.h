#ifndef FILER_TREE_H
#define FILER_TREE_H
#include "launchelf.h"
/* Postorder visits; negative listing/visitor results abort. Listings which may
 * be truncated are rejected. Depth and retained metadata have fixed limits. */
typedef int (*FilerTreeVisit)(const char *, const FILEINFO *, void *);
int filerWalkTree(const char *path, const FILEINFO *file, FilerTreeVisit visit, void *context);
#endif
