#ifndef SAVE_ARCHIVE_H
#define SAVE_ARCHIVE_H

#include <stddef.h>
#include <stdint.h>

#define SAVE_ARCHIVE_LIMIT (16 * 1024 * 1024)
#define SAVE_ARCHIVE_FILES 1024
#define PS1_CARD_SIZE 131072
#define PS1_BLOCK_SIZE 8192

typedef struct {
	char name[33];
	uint16_t mode;
	uint8_t created[8], modified[8];
	const uint8_t *data;
	size_t size;
} SaveArchiveEntry;

/* Entry data borrows the input buffer until saveArchiveFree(). */
typedef struct {
	int ps1;
	SaveArchiveEntry folder;
	SaveArchiveEntry *files;
	unsigned count;
	uint8_t *decoded;
} SaveArchive;

int saveArchiveSupported(const char *name);
int saveArchiveParse(SaveArchive *save, uint8_t *data, size_t size, const char *filename);
void saveArchiveFree(SaveArchive *save);
enum { SAVE_OUTPUT_PSU, SAVE_OUTPUT_PSV, SAVE_OUTPUT_MCS, SAVE_OUTPUT_PSX };
/* Newly allocated output; caller owns it. Reject incompatible save/format pairs. */
int saveArchiveBuild(const SaveArchive *save, int format, uint8_t **output, size_t *length);
int saveArchiveFilename(const SaveArchive *save, int format, char *out, size_t size);
/* Locate a complete raw card inside raw, GME, VGS or VMP containers. */
int ps1CardOffset(const uint8_t *data, size_t size);
void ps1CardFormat(uint8_t *data);
int ps1CardAppend(uint8_t *card, const char *name, const uint8_t *data, size_t size);

#endif
