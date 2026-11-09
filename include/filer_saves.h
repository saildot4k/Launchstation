#ifndef FILER_SAVES_H
#define FILER_SAVES_H

#include "launchelf.h"
#include "vmc_control.h"
#include "save_archive.h"

enum {
	FILER_SAVE_NONE, FILER_SAVE_PS1, FILER_SAVE_PS2,
	FILER_ARCHIVE_PS1, FILER_ARCHIVE_PS2, FILER_CARD_PS1
};
/* Inspect once when opening an action menu, never during frame rendering. */
int filerSaveKind(const char *folder, const FILEINFO *file, int card_type);
void filerExtractLabel(const char *name, char *label, int size);
int filerLoadSave(const char *source, SaveArchive *save, uint8_t **data, char *message, int size);
int filerExtractSave(const SaveArchive *save, const char *destination, char *message, int size);
int filerCreateArchive(const char *source, const FILEINFO *file, int kind, int format,
					   uint8_t **data, size_t *length, char *name, int name_size, char *message, int size);
int filerWriteArchive(const uint8_t *data, size_t length, const char *destination, char *message, int size);
/* Capture one copied/cut PS1 save or flat folder while its source is accessible.
 * Folders with subdirectories are ineligible. The snapshot survives destination
 * browsing and IOP stack changes; selection alone never enables Create archive. */
void filerClearArchiveClipboard(void);
int filerCaptureArchiveClipboard(int card_type, char *message, int size);
int filerArchiveClipboardKind(void);
int filerCreateClipboardArchive(int format, uint8_t **data, size_t *length,
                               char *name, int name_size, char *message, int size);
/* Call only after publishing the archive. Cut removes an unchanged source;
 * 0 means the archive exists but the source was retained, 1 means success. */
int filerFinishArchiveClipboard(const char *destination, char *message, int size);

/* Serialized device calls; invoke from the browser's listing worker or after
 * prepareOp(), never during a concurrent fileXio operation. */
int filerCardInfo(const char *path, VmcInfo *info);
int filerImportSave(const char *source, const char *destination, char *message, int size);
int filerImportClipboard(const char *destination, char *message, int size);
int filerCanImportClipboard(void);
int filerIsPs1Image(const char *name);
unsigned char *filerReadPs1Card(const char *source, char *message, int size);
int filerSavePs1Card(const unsigned char *data, const char *destination, char *message, int size);
int filerExportPs1Card(const char *source, const char *destination, char *message, int size);

#endif
