#ifndef FILER_COPY_H
#define FILER_COPY_H

#include "launchelf.h"
#include "filer_transfer.h"

/* UI-thread paste diagnostics: one bounded record, no transfer-time I/O. */
void filerCopyDiagBegin(const char *source, const char *destination);
void filerCopyDiagStage(const char *stage);
void filerCopyDiagFormat(char *out, int size, int result);

/* Shared device presets; at most 1 MiB per buffer, optional second fast buffer. */
int filerTransferBufferSize(const char *source, const char *destination, u64 size);

/* Count payload files inside selected folders and PSU archives before a paste. */
int filerCopyProgressBegin(const char *path, const FILEINFO *files, int count);

int filerGetGameTitle(const char *path, const FILEINFO *file, unsigned char *out);

#endif
