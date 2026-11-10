#include "filer_saves.h"
#include "filer_shared.h"
#include "filer_actions.h"
#include "save_archive.h"
#include "init.h"
#include <ctype.h>

int filerCardInfo(const char *path, VmcInfo *info)
{
	int result, formatted = 0;
	char device[8];
	memset(info, 0, sizeof(*info));
	if (!strncmp(path, "vmc", 3) && (path[3] == '0' || path[3] == '1') && path[4] == ':') {
		if (!vmcMounted[path[3] - '0']) return 0;
		snprintf(device, sizeof(device), "vmc%c:", path[3]);
		result = fileXioDevctl(device, VMCCTL_GET_INFO, NULL, 0, info, sizeof(*info));
		return result == 0 && (info->type == 1 || info->type == 2) && info->free_units >= 0 &&
		       info->unit_bytes == (info->type == 1 ? 8192 : 1024);
	}
	if (strncmp(path, "mc", 2) || (path[2] != '0' && path[2] != '1') || path[3] != ':') return 0;
	if (filerPrepareMemoryCardRead(path[2] - '0') < 0) return 0;
	result = mcGetInfo(path[2] - '0', 0, &info->type, &info->free_units, &formatted);
	if (result < 0 || mcSync(0, NULL, &result) <= 0 || result < -1 || !formatted || info->free_units < 0) return 0;
	info->unit_bytes = info->type == 1 ? 8192 : 1024;
	return info->type == 1 || info->type == 2;
}

int filerIsPs1Image(const char *name)
{
	return genCmpFileExt(name, "VMC") || genCmpFileExt(name, "BIN") || genCmpFileExt(name, "MCR") ||
	       genCmpFileExt(name, "MCD") || genCmpFileExt(name, "MC") || genCmpFileExt(name, "MEM") ||
	       genCmpFileExt(name, "VM1") || genCmpFileExt(name, "SRM") ||
	       genCmpFileExt(name, "GME") || genCmpFileExt(name, "VGS") || genCmpFileExt(name, "VMP");
}

static uint8_t *readSource(const char *path, size_t *size)
{
	char fixed[MAX_PATH];
	uint8_t *data;
	s64 length;
	size_t done = 0;
	int fd, n;
	if (genFixPath(path, fixed) < 0) return NULL;
	fd = genOpen(fixed, FIO_O_RDONLY);
	if (fd < 0) return NULL;
	length = genLseek(fd, 0, SEEK_END);
	if (length < 0 || length > SAVE_ARCHIVE_LIMIT || genLseek(fd, 0, SEEK_SET) < 0) { genClose(fd); return NULL; }
	data = malloc(length ? (size_t)length : 1);
	if (!data) { genClose(fd); return NULL; }
	while (done < (size_t)length) {
		n = genRead(fd, data + done, (length - done > 65536) ? 65536 : (int)(length - done));
		if (n <= 0) { free(data); genClose(fd); return NULL; }
		done += n;
	}
	if (genClose(fd) < 0) { free(data); return NULL; }
	*size = done;
	return data;
}

static int exists(const char *path)
{
	char dir[MAX_PATH];
	int fd = genOpen(path, FIO_O_RDONLY);
	if (fd >= 0) { genClose(fd); return 1; }
	snprintf(dir, sizeof(dir), "%s", path);
	fd = genDopen(dir);
	if (fd >= 0) { genDclose(fd); return 1; }
	return 0;
}

static int saveWritable(const char *path)
{
	/* These transactions publish with a sibling rename. HOST has no such
	 * operation; reject it before creating any temporary file. */
	return genCanRenamePath(path) && strncmp(path, "host", 4);
}

static int uniquePath(const char *parent, char *out, size_t size, const char *suffix)
{
	for (int i = 0; i < 100; i++) {
		if (snprintf(out, size, "%sLSI%02d.%s", parent, i, suffix) >= (int)size) return 0;
		if (!exists(out)) return 1;
	}
	return 0;
}

static int writeFile(const char *path, const uint8_t *data, size_t size)
{
	size_t done = 0;
	int n, fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
	if (fd < 0) return 0;
	while (done < size) {
		n = genWrite(fd, (void *)(data + done), size - done > 65536 ? 65536 : (int)(size - done));
		if (n <= 0) { genClose(fd); return 0; }
		done += n;
	}
	return genClose(fd) >= 0;
}

static int metadata(const char *path, const SaveArchiveEntry *e, int folder)
{
	int result;
	sceMcTblGetDir info;
	if (strncmp(path, "mc", 2) && strncmp(path, "vmc", 3)) return 1;
	memset(&info, 0, sizeof(info));
	/* MAX has no timestamps: keep the card's newly assigned dates. */
	if (!strncmp(path, "mc", 2)) {
		result = mcGetDir(path[2] - '0', 0, path + 4, 0, 1, &info);
		if (result < 0 || mcSync(0, NULL, &result) <= 0 || result != 1) return 0;
		info.AttrFile = e->mode ? e->mode : folder ? 0x8427 : 0x8497;
		if (e->created[4]) memcpy(&info._Create, e->created, 8);
		if (e->modified[4]) memcpy(&info._Modify, e->modified, 8);
		result = mcSetFileInfo(path[2] - '0', 0, path + 4, &info, 0xFEED);
		if (result < 0 || mcSync(0, NULL, &result) <= 0) return 0;
		return result >= 0;
	} else {
		iox_stat_t stat;
		memset(&stat, 0, sizeof(stat));
		if (fileXioGetStat(path, &stat) < 0) return 0;
		stat.mode = folder ? FIO_S_IFDIR : FIO_S_IFREG;
		stat.private_0 = e->mode ? e->mode : folder ? 0x8427 : 0x8497;
		if (e->created[4]) memcpy(stat.ctime, e->created, 8);
		if (e->modified[4]) memcpy(stat.mtime, e->modified, 8);
		return fileXioChStat(path, &stat, 0xFEED) >= 0;
	}
}

static void removeStage(const char *stage, const SaveArchive *s, int folder)
{
	char path[MAX_PATH], mutable[MAX_PATH];
	if (folder) {
		for (unsigned i = 0; i < s->count; i++) {
			if (snprintf(path, sizeof(path), "%s/%s", stage, s->files[i].name) < (int)sizeof(path)) genRemove(path);
		}
		snprintf(mutable, sizeof(mutable), "%s", stage);
		genRmdir(mutable);
	} else {
		snprintf(mutable, sizeof(mutable), "%s", stage);
		genRemove(mutable);
	}
}

static int loadSaveSnapshot(const char *source, SaveArchive *save, uint8_t **data, size_t *length,
                            char *message, int size)
{
    *data = readSource(source, length);
    if (!*data) { snprintf(message, size, "Could not read save: %s", source); return 0; }
    if (!saveArchiveParse(save, *data, *length, source)) {
        free(*data); *data = NULL;
        snprintf(message, size, "Invalid, truncated or unsupported save: %s", source); return 0;
    }
    return 1;
}

int filerLoadSave(const char *source, SaveArchive *save, uint8_t **data, char *message, int size)
{
    size_t length;
    return loadSaveSnapshot(source, save, data, &length, message, size);
}

int filerImportSave(const char *source, const char *destination, char *message, int size)
{
    SaveArchive save;
    uint8_t *data;
    int result;
    if (!filerLoadSave(source, &save, &data, message, size)) return -1;
    result = filerExtractSave(&save, destination, message, size);
    saveArchiveFree(&save); free(data);
    return result;
}

int filerExtractSave(const SaveArchive *s, const char *destination, char *message, int size)
{
    VmcInfo card;
    char parent[MAX_PATH], target[MAX_PATH], stage[MAX_PATH], path[MAX_PATH];
    int is_card, folder = 0, result = -1, staged = 0;
	if (!saveWritable(destination) || prepareTransferDeviceStacks(destination, destination) < 0 || genFixPath(destination, parent) < 0) goto fail;
	is_card = !strncmp(destination, "mc", 2) || !strncmp(destination, "vmc", 3);
	if (is_card && !filerCardInfo(destination, &card)) goto fail;
	if (is_card && card.type == 1 && !s->ps1) {
		snprintf(message, size, "A PS2 save needs a PS2 card or a storage folder."); goto done;
	}
	if (!parent[0] || parent[strlen(parent) - 1] != '/' || !genCanRenamePath(parent)) goto fail;
	folder = !(s->ps1 && is_card && card.type == 1);
	const char *name = s->ps1 ? s->files[0].name : s->folder.name;
	if (snprintf(target, sizeof(target), "%s%s", parent, name) >= (int)sizeof(target)) goto fail;
	/* Keep existing saves intact. Importing under a different name would make
	 * most games unable to find them, so report the conflict explicitly. */
	if (exists(target)) {
		snprintf(message, size, "Save already exists: %s. Back it up and remove it before importing.", name); goto done;
	}
	if (is_card) {
		u64 needed = 0;
		for (unsigned i = 0; i < s->count; i++) needed += (s->files[i].size + card.unit_bytes - 1) / card.unit_bytes;
		if (folder) needed += s->count + 3; /* directory entries and directory growth */
		if (needed > (u64)card.free_units) { snprintf(message, size, "Not enough free space for this save."); goto done; }
	}
	if (!uniquePath(parent, stage, sizeof(stage), "TMP")) goto fail;
	if (folder && genMkdir(stage, 0x8427) < 0) goto fail;
	staged = 1;
	for (unsigned i = 0; i < s->count; i++) {
		if (folder) {
			if (snprintf(path, sizeof(path), "%s/%s", stage, s->files[i].name) >= (int)sizeof(path)) goto fail;
		} else snprintf(path, sizeof(path), "%s", stage);
		if (!writeFile(path, s->files[i].data, s->files[i].size)) goto fail;
		if (!s->ps1 && !metadata(path, &s->files[i], 0)) goto fail;
	}
	if (folder) {
		SaveArchiveEntry folder_info = s->folder;
		if (s->ps1) folder_info.mode = 0x9027;
		if (!metadata(stage, &folder_info, 1)) goto fail;
	}
	if (genRenameNoReplace(stage, target) < 0) goto fail;
	staged = 0;
	result = 1;
	snprintf(message, size, "Extracted %s", name);
	goto done;
fail:
	snprintf(message, size, "Could not extract save. Choose writable storage or a compatible memory card.");
done:
	if (staged) removeStage(stage, s, folder);
	return result;
}

int filerCanImportClipboard(void)
{
	if (nclipFiles <= 0) return 0;
	for (int i = 0; i < nclipFiles; i++) {
		u64 bytes = ((u64)clipFiles[i].stats.Reserve2 << 32) | clipFiles[i].stats.FileSizeByte;
		int raw_candidate = bytes > 0 && bytes <= 15 * PS1_BLOCK_SIZE && bytes % PS1_BLOCK_SIZE == 0 &&
		                    strlen(clipFiles[i].name) <= 20;
		if ((clipFiles[i].stats.AttrFile & sceMcFileAttrSubdir) ||
		    (!saveArchiveSupported(clipFiles[i].name) && !raw_candidate)) return 0;
	}
	return 1;
}

/* Describe the clipboard without opening a file or changing device stacks. */
void filerClipboardExtractLabel(char *label, int size)
{
	const char *dot = nclipFiles > 0 ? strrchr(clipFiles[0].name, '.') : NULL;
	int same = dot && strlen(dot + 1) == 3;
	for (int i = 1; same && i < nclipFiles; i++) {
		const char *other = strrchr(clipFiles[i].name, '.');
		if (!other || strlen(other + 1) != 3) { same = 0; break; }
		for (int j = 1; j <= 3; j++)
			if (toupper((unsigned char)dot[j]) != toupper((unsigned char)other[j])) same = 0;
	}
	if (same) filerExtractLabel(clipFiles[0].name, label, size);
	else snprintf(label, size, "Extract saves...");
}

/* Restore compatible source/destination drivers before verifying a Cut
 * source. Delete only an unchanged archive after successful publication. */
static int finishExtractCut(const char *destination, const char *source, const uint8_t *snapshot, size_t length, const FILEINFO *file)
{
	uint8_t *current;
	size_t current_length;
	int same;
	char message[160];
	if (filerPrepareClipboardTransfer(destination, message, sizeof(message)) < 0) return 0;
	current = readSource(source, &current_length);
	if (!current) return 0;
	same = current_length == length && !memcmp(current, snapshot, length);
	free(current);
	return same && clipIopResetGeneration == getIopResetGeneration() &&
	       filerConfirmExploitDelete(clipPath, file) >= 0 && delete(clipPath, file) >= 0;
}

int filerImportClipboard(const char *destination, char *message, int size)
{
	char source[MAX_PATH];
	int count = 0, kept = 0, cut = browser_cut;
	if (!filerCanImportClipboard()) {
		snprintf(message, size, "Copy or cut save archives first."); return -1;
	}
	for (int i = 0; i < nclipFiles;) {
		SaveArchive save = {0};
		uint8_t *snapshot = NULL;
		size_t length = 0;
		int result = -1;
		if (filerPrepareClipboardTransfer(destination, message, size) < 0) {
			/* Keep the source and destination readiness diagnostic. */
		} else if (snprintf(source, sizeof(source), "%s%s", clipPath, clipFiles[i].name) >= (int)sizeof(source))
			snprintf(message, size, "The copied archive path is too long.");
		else if (loadSaveSnapshot(source, &save, &snapshot, &length, message, size))
			result = filerExtractSave(&save, destination, message, size);
		saveArchiveFree(&save);
		if (result < 0) {
			free(snapshot);
			if (count) {
				char reason[192]; snprintf(reason, sizeof(reason), "%s", message);
				snprintf(message, size, "%d extracted; stopped: %s", count, reason);
			}
			return -1;
		}
		count++;
		if (cut && finishExtractCut(destination, source, snapshot, length, &clipFiles[i])) {
			memmove(&clipFiles[i], &clipFiles[i + 1], (nclipFiles - i - 1) * sizeof(clipFiles[0]));
			nclipFiles--;
		} else {
			if (cut) kept++;
			i++;
		}
		free(snapshot);
	}
	if (cut && !nclipFiles) {
		browser_cut = 0; clipPath[0] = 0;
		filerClearArchiveClipboard();
	}
	if (kept)
		snprintf(message, size, "Extracted %d save%s; %d source archive%s kept because removal could not be verified.",
		         count, count == 1 ? "" : "s", kept, kept == 1 ? "" : "s");
	else snprintf(message, size, "Extracted %d save%s", count, count == 1 ? "" : "s");
	return kept ? 0 : count;
}

unsigned char *filerReadPs1Card(const char *source, char *message, int size)
{
	uint8_t *data = NULL;
	VmcInfo info;
	size_t length = 0;
	int offset = 0;
	/* VMC snapshots include the full raw card, including deleted slots. */
	if (!strncmp(source, "vmc", 3)) {
		if (!filerCardInfo(source, &info) || info.type != 1) goto fail;
		data = malloc(PS1_CARD_SIZE);
		if (!data) goto fail;
		for (int page = 0; page < 1024; page++)
			if (fileXioDevctl(source, VMCCTL_READ_PS1_PAGE, &page, sizeof(page), data + page * 128, 128) < 0) goto fail;
	} else if (!strncmp(source, "mc", 2)) {
		FILEINFO *files;
		int count;
		if (!filerCardInfo(source, &info) || info.type != 1) goto fail;
		files = malloc(MAX_ENTRY * sizeof(*files));
		data = malloc(PS1_CARD_SIZE);
		if (!files || !data) { free(files); goto fail; }
		ps1CardFormat(data);
		count = getDir(source, files);
		if (count < 0) { free(files); goto fail; }
		for (int i = 0; i < count; i++) {
			uint8_t *save;
			char path[MAX_PATH];
			int ok;
			if (!strcmp(files[i].name, ".") || !strcmp(files[i].name, "..")) continue;
			if (snprintf(path, sizeof(path), "mc%c:/%s", source[2], files[i].name) >= (int)sizeof(path)) { free(files); goto fail; }
			save = readSource(path, &length);
			ok = save && ps1CardAppend(data, files[i].name, save, length);
			free(save);
			if (!ok) { free(files); goto fail; }
		}
		free(files);
	} else {
		data = readSource(source, &length);
		if (!data || (offset = ps1CardOffset(data, length)) < 0) {
			snprintf(message, size, "Choose a 128 KiB PS1 card (raw, GME, VGS or VMP)."); free(data); return NULL;
		}
	}
	if (offset) memmove(data, data + offset, PS1_CARD_SIZE);
	return data;
fail:
	free(data);
	snprintf(message, size, "Could not read a PS1 card from this source.");
	return NULL;
}

int filerSavePs1Card(const unsigned char *data, const char *destination, char *message, int size)
{
	char output[MAX_PATH], parent[MAX_PATH], stage[MAX_PATH];
	int staged = 0, result = -1;
	if (!data || memcmp(data, "MC", 2) || !saveWritable(destination)) goto fail;
	if (prepareTransferDeviceStacks(destination, destination) < 0 || genFixPath(destination, output) < 0) goto fail;
	snprintf(parent, sizeof(parent), "%s", output);
	char *leaf = strrchr(parent, '/');
	if (!leaf || !leaf[1]) goto fail;
	leaf[1] = 0;
	if (exists(output)) { snprintf(message, size, "Card already exists. Rename it or choose another folder."); goto done; }
	if (!uniquePath(parent, stage, sizeof(stage), "VMC")) goto fail;
	staged = 1;
	if (!writeFile(stage, data, PS1_CARD_SIZE) || genRenameNoReplace(stage, output) < 0) goto fail;
	staged = 0;
	snprintf(message, size, "Saved raw PS1 card: %s", destination);
	result = 1;
	goto done;
fail:
	snprintf(message, size, "Could not save the PS1 card. Check the destination and free space.");
done:
	if (staged) genRemove(stage);
	return result;
}

int filerExportPs1Card(const char *source, const char *destination, char *message, int size)
{
	unsigned char *data = filerReadPs1Card(source, message, size);
	int result;
	if (!data) return -1;
	result = filerSavePs1Card(data, destination, message, size);
	free(data);
	return result;
}

static int saveHeader(const char *path, uint8_t header[132], size_t *length)
{
	char fixed[MAX_PATH];
	int fd, got, used = 0;
	s64 bytes;
	memset(header, 0, 132);
	if (genFixPath(path, fixed) < 0 || (fd = genOpen(fixed, FIO_O_RDONLY)) < 0) return 0;
	bytes = genLseek(fd, 0, SEEK_END);
	if (bytes < 0 || bytes > SAVE_ARCHIVE_LIMIT || genLseek(fd, 0, SEEK_SET) < 0) { genClose(fd); return 0; }
	while (used < 132 && (got = genRead(fd, header + used, 132 - used)) > 0) used += got;
	if (genClose(fd) < 0) return 0;
	*length = bytes;
	return used;
}

int filerSaveKind(const char *folder, const FILEINFO *file, int card_type)
{
	char path[MAX_PATH], nested[MAX_PATH];
	uint8_t header[132];
	size_t length;
	int dir, card, n;
	if (!file || !file->name[0] || !strcmp(file->name, ".") || !strcmp(file->name, "..") ||
	    snprintf(path, sizeof(path), "%s%s", folder, file->name) >= (int)sizeof(path)) return FILER_SAVE_NONE;
	dir = !!(file->stats.AttrFile & sceMcFileAttrSubdir);
	card = !strncmp(folder, "mc", 2) || !strncmp(folder, "vmc", 3);
	if (card && card_type == 1) return dir ? FILER_SAVE_NONE : FILER_SAVE_PS1;
	if (dir) {
		if (card && card_type == 2) return file->stats.AttrFile & 0x1000 ? FILER_SAVE_PS1 : FILER_SAVE_PS2;
		if (snprintf(nested, sizeof(nested), "%s/icon.sys", path) < (int)sizeof(nested) &&
		    saveHeader(nested, header, &length) >= 4 && !memcmp(header, "PS2D", 4)) return FILER_SAVE_PS2;
		if (snprintf(nested, sizeof(nested), "%s/%s", path, file->name) >= (int)sizeof(nested)) return FILER_SAVE_NONE;
		n = saveHeader(nested, header, &length);
		return n >= 2 && !memcmp(header, "SC", 2) && length && length <= 15 * PS1_BLOCK_SIZE &&
		       !(length % PS1_BLOCK_SIZE) ? FILER_SAVE_PS1 : FILER_SAVE_NONE;
	}
	/* Only plausible saves/cards need a probe, and only when the menu opens. */
	length = file->stats.FileSizeByte;
	if (!saveArchiveSupported(file->name) && !filerIsPs1Image(file->name) &&
	    !(length && length <= 134976 && !(length % PS1_BLOCK_SIZE))) return FILER_SAVE_NONE;
	n = saveHeader(path, header, &length);
	if (n < 4) return FILER_SAVE_NONE;
	if ((length == 131072 && !memcmp(header, "MC", 2)) ||
	    (length == 131136 && !memcmp(header, "VgsM", 4)) ||
	    (length == 131200 && !memcmp(header, "\0PMV", 4)) ||
	    (length == 134976 && !memcmp(header, "123-456-STD", 11))) return FILER_CARD_PS1;
	if (!memcmp(header, "\0VSP", 4) && n >= 64) return header[60] == 1 ? FILER_ARCHIVE_PS1 : header[60] == 2 ? FILER_ARCHIVE_PS2 : FILER_SAVE_NONE;
	if (header[0] == 0x51 && length > 128 && !((length - 128) % PS1_BLOCK_SIZE)) return FILER_ARCHIVE_PS1;
	if (n >= 56 && !memcmp(header + 54, "SC", 2)) return FILER_ARCHIVE_PS1;
	if (toupper(header[0]) == 'S' && toupper(header[1]) == 'C' && strlen(file->name) <= 20 &&
	    length <= 15 * PS1_BLOCK_SIZE && !(length % PS1_BLOCK_SIZE)) return FILER_SAVE_PS1;
	if (!memcmp(header, "CFU\0", 4) || !memcmp(header, "Ps2PowerSave", 12) ||
	    !memcmp(header + 4, "SharkPortSave\0\0\0", 16) ||
	    (genCmpFileExt(file->name, "PSU") && (header[0] & 0x20))) return FILER_ARCHIVE_PS2;
	return FILER_SAVE_NONE;
}

void filerExtractLabel(const char *name, char *label, int size)
{
	const char *dot = strrchr(name, '.');
	char ext[4] = {0};
	if (dot && strlen(dot + 1) == 3) for (int i = 0; i < 3; i++) ext[i] = toupper((unsigned char)dot[i + 1]);
	snprintf(label, size, "Extract %s...", ext[0] ? ext : "save");
}

int filerCreateArchive(const char *source, const FILEINFO *file, int kind, int format,
					   uint8_t **data, size_t *length, char *name, int name_size, char *message, int size)
{
	SaveArchive save = {0};
	FILEINFO *files = NULL;
	uint8_t *raw = NULL;
	char folder[MAX_PATH], path[MAX_PATH];
	size_t bytes, accumulated = 0;
	int result = -1, count;
	*data = NULL; *length = 0;
	snprintf(folder, sizeof(folder), "%s", source);
	bytes = strlen(folder);
	if (bytes && folder[bytes - 1] == '/') folder[bytes - 1] = 0;
	if (kind == FILER_SAVE_PS1) {
		if (file->stats.AttrFile & sceMcFileAttrSubdir) {
			if (snprintf(path, sizeof(path), "%s/%s", folder, file->name) >= (int)sizeof(path)) goto done;
		} else snprintf(path, sizeof(path), "%s", folder);
		raw = readSource(path, &bytes);
		if (!raw || !saveArchiveParse(&save, raw, bytes, file->name) || !save.ps1) goto done;
	} else if (kind == FILER_SAVE_PS2) {
		if (snprintf(path, sizeof(path), "%s/", folder) >= (int)sizeof(path)) goto done;
		files = malloc(MAX_ENTRY * sizeof(*files));
		if (!files || (count = getDir(path, files)) <= 0 || count >= MAX_ENTRY - 2) goto done;
		save.files = calloc(count, sizeof(*save.files));
		if (!save.files) goto done;
		snprintf(save.folder.name, sizeof(save.folder.name), "%.32s", file->name);
		if (strlen(file->name) > 32) goto done;
		save.folder.mode = file->stats.AttrFile;
		memcpy(save.folder.created, &file->stats._Create, 8); memcpy(save.folder.modified, &file->stats._Modify, 8);
		for (int i = 0; i < count; i++) {
			SaveArchiveEntry *e = &save.files[save.count];
			if (!strcmp(files[i].name, ".") || !strcmp(files[i].name, "..")) continue;
			if ((files[i].stats.AttrFile & sceMcFileAttrSubdir) || strlen(files[i].name) > 32 ||
			    snprintf(path, sizeof(path), "%s/%s", folder, files[i].name) >= (int)sizeof(path)) goto done;
			e->data = readSource(path, &e->size);
			save.count++;
			if (!e->data || e->size > SAVE_ARCHIVE_LIMIT - accumulated) goto done;
			accumulated += e->size;
			strcpy(e->name, files[i].name); e->mode = files[i].stats.AttrFile;
			memcpy(e->created, &files[i].stats._Create, 8); memcpy(e->modified, &files[i].stats._Modify, 8);
		}
	} else goto done;
	if (!saveArchiveBuild(&save, format, data, length) || !saveArchiveFilename(&save, format, name, name_size)) {
		free(*data); *data = NULL; *length = 0; goto done;
	}
	result = 1;
done:
	if (kind == FILER_SAVE_PS2) for (unsigned i = 0; i < save.count; i++) free((void *)save.files[i].data);
	saveArchiveFree(&save); free(raw); free(files);
	if (result < 0) snprintf(message, size, format == SAVE_OUTPUT_PSV && kind == FILER_SAVE_PS2 ?
		"PSV needs a flat PS2 save with icon.sys and its referenced icons." : "Could not read or archive this save. Choose one complete save.");
	return result;
}

int filerWriteArchive(const uint8_t *data, size_t length, const char *destination, char *message, int size)
{
	char output[MAX_PATH], parent[MAX_PATH], stage[MAX_PATH];
	VmcInfo card;
	int staged = 0, result = -1;
	if (!data || !length || length > SAVE_ARCHIVE_LIMIT || !saveWritable(destination) ||
	    prepareTransferDeviceStacks(destination, destination) < 0 || genFixPath(destination, output) < 0) goto fail;
	if ((!strncmp(destination, "mc", 2) || !strncmp(destination, "vmc", 3)) &&
	    (!filerCardInfo(destination, &card) || card.type == 1)) {
		snprintf(message, size, "Choose storage or a PS2 card for archive files."); return -1;
	}
	snprintf(parent, sizeof(parent), "%s", output);
	char *leaf = strrchr(parent, '/');
	if (!leaf || !leaf[1]) goto fail;
	leaf[1] = 0;
	if (!genCanRenamePath(parent)) goto fail;
	if (exists(output)) { snprintf(message, size, "Archive already exists. Choose another filename or folder."); return -1; }
	if (!uniquePath(parent, stage, sizeof(stage), "ARC")) goto fail;
	staged = 1;
	if (!writeFile(stage, data, length) || genRenameNoReplace(stage, output) < 0) goto fail;
	staged = 0; result = 1;
	snprintf(message, size, "Archive created: %s", destination);
	return result;
fail:
	if (staged) genRemove(stage);
	snprintf(message, size, "Could not create archive. Check the destination and free space.");
	return result;
}

/* Copy/Cut stores metadata only. Canonical save data is temporary work for
 * an explicitly requested archive operation and its post-write Cut check. */
static uint8_t *archive_clip_data;
static size_t archive_clip_length;
static int archive_clip_kind, archive_clip_card_type, archive_clip_probed;
static FILEINFO archive_clip_file;
static char archive_clip_folder[MAX_PATH];

void filerClearArchiveClipboard(void)
{
	free(archive_clip_data);
	archive_clip_data = NULL;
	archive_clip_length = 0;
	archive_clip_kind = FILER_SAVE_NONE;
	archive_clip_probed = 0;
}

static int archiveClipboardMatches(void)
{
	return nclipFiles == 1 && !strcmp(clipPath, archive_clip_folder) &&
	       !strcmp(clipFiles[0].name, archive_clip_file.name) &&
	       !memcmp(&clipFiles[0].stats, &archive_clip_file.stats, sizeof(archive_clip_file.stats));
}

int filerArchiveClipboardKind(void)
{
	return archiveClipboardMatches() ? archive_clip_kind : FILER_SAVE_NONE;
}

void filerRememberArchiveClipboard(int card_type)
{
	filerClearArchiveClipboard();
	archive_clip_folder[0] = 0;
	if (nclipFiles != 1) return;
	archive_clip_file = clipFiles[0];
	snprintf(archive_clip_folder, sizeof(archive_clip_folder), "%s", clipPath);
	archive_clip_card_type = card_type;
}

/* A folder is eligible only after checking its complete immediate listing.
 * getDir() caps listings at MAX_ENTRY - 2; a full buffer cannot prove flatness. */
static int flatArchiveFolder(const char *source)
{
	FILEINFO *files;
	char path[MAX_PATH];
	int count, flat = 1, regular = 0;
	if (snprintf(path, sizeof(path), "%s/", source) >= (int)sizeof(path)) return 0;
	files = malloc(MAX_ENTRY * sizeof(*files));
	if (!files) return 0;
	count = getDir(path, files);
	if (count <= 0 || count >= MAX_ENTRY - 2) flat = 0;
	for (int i = 0; flat && i < count; i++) {
		if (!strcmp(files[i].name, ".") || !strcmp(files[i].name, "..")) continue;
		if (files[i].stats.AttrFile & sceMcFileAttrSubdir) flat = 0;
		else regular++;
	}
	free(files);
	return flat ? regular : 0;
}

int filerProbeArchiveClipboard(const char *destination)
{
	char source[MAX_PATH], message[160];
	VmcInfo card;
	int kind, files, type = archive_clip_card_type;
	u64 bytes;
	if (!archiveClipboardMatches() || !saveWritable(destination) || !clipFiles[0].name[0] ||
	    !strcmp(clipFiles[0].name, ".") || !strcmp(clipFiles[0].name, "..")) return FILER_SAVE_NONE;
	if (archive_clip_probed) return archive_clip_kind;
	bytes = ((u64)clipFiles[0].stats.Reserve2 << 32) | clipFiles[0].stats.FileSizeByte;
	if (!(clipFiles[0].stats.AttrFile & sceMcFileAttrSubdir) && type != 1 &&
	    !(bytes && bytes <= 15 * PS1_BLOCK_SIZE && !(bytes % PS1_BLOCK_SIZE) && strlen(clipFiles[0].name) <= 20))
		return FILER_SAVE_NONE;
	if (snprintf(source, sizeof(source), "%s%s", clipPath, clipFiles[0].name) >= (int)sizeof(source) ||
	    filerPrepareClipboardTransfer(destination, message, sizeof(message)) < 0) return FILER_SAVE_NONE;
	if (!strncmp(clipPath, "mc", 2) || !strncmp(clipPath, "vmc", 3)) {
		if (!filerCardInfo(clipPath, &card)) return FILER_SAVE_NONE;
		type = card.type;
	}
	kind = filerSaveKind(clipPath, &clipFiles[0], type);
	if (clipFiles[0].stats.AttrFile & sceMcFileAttrSubdir) {
		files = flatArchiveFolder(source);
		if (!files) kind = FILER_SAVE_NONE;
		else if (kind == FILER_SAVE_NONE || (kind == FILER_SAVE_PS1 && files != 1)) kind = FILER_SAVE_PS2;
	}
	archive_clip_kind = kind == FILER_SAVE_PS1 || kind == FILER_SAVE_PS2 ? kind : FILER_SAVE_NONE;
	archive_clip_probed = 1;
	return archive_clip_kind;
}

int filerCreateClipboardArchive(const char *destination, int format, uint8_t **data, size_t *length,
                               char *name, int name_size, char *message, int size)
{
	SaveArchive save = {0};
	char source[MAX_PATH], temporary_name[80];
	int result = -1, kind;
	*data = NULL; *length = 0;
	if (!archiveClipboardMatches()) {
		snprintf(message, size, "Copy or cut one complete PS1 save or flat folder first.");
		return -1;
	}
	if (filerPrepareClipboardTransfer(destination, message, size) < 0) return -1;
	/* Refresh eligibility after restoring drivers; cached menu metadata is not
	 * authority to archive a folder which acquired subdirectories meanwhile. */
	filerClearArchiveClipboard();
	kind = filerProbeArchiveClipboard(destination);
	if (!kind || snprintf(source, sizeof(source), "%s%s", clipPath, clipFiles[0].name) >= (int)sizeof(source)) {
		snprintf(message, size, "Choose one complete PS1 save or a folder with files and no subdirectories.");
		return -1;
	}
	if (filerCreateArchive(source, &clipFiles[0], kind, kind == FILER_SAVE_PS1 ? SAVE_OUTPUT_MCS : SAVE_OUTPUT_PSU,
	                       &archive_clip_data, &archive_clip_length, temporary_name, sizeof(temporary_name), message, size) < 0)
		return -1;
	if (saveArchiveParse(&save, archive_clip_data, archive_clip_length,
	                     archive_clip_kind == FILER_SAVE_PS1 ? "clipboard.mcs" : "clipboard.psu") &&
	    saveArchiveBuild(&save, format, data, length) && saveArchiveFilename(&save, format, name, name_size))
		result = 1;
	if (result < 0) {
		free(*data); *data = NULL; *length = 0;
		snprintf(message, size, format == SAVE_OUTPUT_PSV && archive_clip_kind == FILER_SAVE_PS2 ?
		         "PSV needs a flat PS2 save with icon.sys and its referenced icons." : "Could not create this save archive.");
	}
	saveArchiveFree(&save);
	if (result < 0) filerClearArchiveClipboard();
	return result;
}

int filerFinishArchiveClipboard(const char *destination, char *message, int size)
{
	char source[MAX_PATH], name[80], detail[160];
	uint8_t *current = NULL;
	size_t length = 0;
	int same;
	unsigned int generation;
	if (!browser_cut) { filerClearArchiveClipboard(); return 1; }
	if (!filerArchiveClipboardKind() || !archive_clip_data ||
	    snprintf(source, sizeof(source), "%s%s", archive_clip_folder, archive_clip_file.name) >= (int)sizeof(source)) goto kept;
	/* Do not delete an output created inside the original PS2 save folder. */
	length = strlen(source);
	if (!strncmp(destination, source, length) && destination[length] == '/') goto kept;
	if (filerPrepareClipboardTransfer(destination, detail, sizeof(detail)) < 0) goto kept;
	generation = getIopResetGeneration();
	/* A card may have been removed or a VMC replaced while browsing. Only
	 * remove a source whose complete data/metadata still match the snapshot. */
	if (filerCreateArchive(source, &archive_clip_file, archive_clip_kind,
	                       archive_clip_kind == FILER_SAVE_PS1 ? SAVE_OUTPUT_MCS : SAVE_OUTPUT_PSU,
	                       &current, &length, name, sizeof(name), detail, sizeof(detail)) < 0) goto kept;
	same = length == archive_clip_length && !memcmp(current, archive_clip_data, length);
	free(current); current = NULL;
	if (!same || generation != getIopResetGeneration() ||
	    filerConfirmExploitDelete(archive_clip_folder, &archive_clip_file) < 0 ||
	    delete(archive_clip_folder, &archive_clip_file) < 0) goto kept;
	nclipFiles = 0; browser_cut = 0; clipPath[0] = 0;
	filerClearArchiveClipboard();
	return 1;
kept:
	free(current);
	filerClearArchiveClipboard();
	snprintf(message, size, "Archive created; source save kept because it could not be safely removed.");
	return 0;
}
