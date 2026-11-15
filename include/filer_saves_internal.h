#ifndef FILER_SAVES_INTERNAL_H
#define FILER_SAVES_INTERNAL_H
#include "filer_saves.h"
#include "filer_shared.h"
#include "filer_actions.h"
#include "filer_copy.h"
#include "dash.h"
#include "init.h"
#include "save_sign.h"
#include <ctype.h>

typedef struct {
	int active, verifying, classic_drawn, extracting, extract_complete;
	const char *action;
	char item[MAX_NAME], extract_name[MAX_NAME];
	u64 index, count, started, bytes, file_done, last_draw, extract_done, extract_total;
} FilerSaveProgress;
extern FilerSaveProgress save_progress;
void saveProgressBegin(int count);
void saveProgressEnd(void);
void saveProgressStage(const char *action, const char *name);
void saveProgressItem(int index, const char *name, const char *action);
void saveProgressBytes(const char *path, u64 done, u64 total);
void saveProgressFile(const char *path, size_t size);
void saveProgressExtractBegin(const SaveArchive *save, const char *name);
void saveProgressExtractEnd(int success);
uint8_t *filerSaveReadSource(const char *path, size_t *size);
int filerSaveExists(const char *path);
int filerSaveWritable(const char *path);
int filerSaveUniquePath(const char *parent, char *out, size_t size, const char *suffix);
int filerSaveWriteFileResult(const char *path, const uint8_t *data, size_t size, int *opened);
int filerSaveWriteFile(const char *path, const uint8_t *data, size_t size);
int filerSaveReadHeader(const char *path, uint8_t header[132], size_t *length);
int filerSaveClipboardIsPs1Card(void);
#endif
