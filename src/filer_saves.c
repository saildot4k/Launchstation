#include "filer_saves_internal.h"

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
    *data = filerSaveReadSource(source, length);
    if (!*data) { snprintf(message, size, "Could not read save: %s", source); return 0; }
	saveProgressStage("Opening archive", save_progress.item);
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

/* PS2 directories store two 512-byte entries per 1 KiB cluster. Count only
 * live entries plus . and ..: old holes/extra allocation can reclaim more,
 * never less. The parent entry's storage remains allocated and is not credited.
 * Walk one directory record at a time; do not load save contents or retain
 * MAX_ENTRY-sized listings on the EE stack at every recursive level. */
static int saveDirectoryUnits(char *path, int unit_bytes, u64 *units, int depth)
{
	iox_dirent_t entry;
	char child[MAX_PATH];
	u64 reclaimed = 0, children = 0;
	int fd, read_result = -1, result = 0;
	if (depth >= 16 || (fd = genDopen(path)) < 0) return 0;
	while ((read_result = fileXioDread(fd, &entry)) > 0) {
		if (!memchr(entry.name, '\0', sizeof(entry.name)) || !entry.name[0]) goto done;
		if (!strcmp(entry.name, ".") || !strcmp(entry.name, "..")) continue;
		/* The legacy delete path cannot prove a capped listing complete. */
		if (++children >= MAX_ENTRY - 2 || strchr(entry.name, '/') || strchr(entry.name, '\\') ||
		    snprintf(child, sizeof(child), "%s/%s", path, entry.name) >= (int)sizeof(child)) goto done;
		if (FIO_S_ISDIR(entry.stat.mode)) {
			u64 nested;
			if (!saveDirectoryUnits(child, unit_bytes, &nested, depth + 1)) goto done;
			reclaimed += nested;
		} else if (FIO_S_ISREG(entry.stat.mode) && !entry.stat.hisize) {
			reclaimed += ((u64)entry.stat.size + unit_bytes - 1) / unit_bytes;
		} else goto done;
	}
	if (read_result < 0) goto done;
	reclaimed += (children + 3) / 2;
	*units = reclaimed;
	result = 1;
done:
	if (genDclose(fd) < 0) result = 0;
	return result;
}

static int saveReclaimableUnits(char *target, const VmcInfo *card, u64 *units)
{
	iox_stat_t stat;
	*units = 0;
	if (fileXioGetStat(target, &stat) < 0) return 0;
	if (FIO_S_ISDIR(stat.mode))
		return card->type == 2 && saveDirectoryUnits(target, card->unit_bytes, units, 0);
	if (!FIO_S_ISREG(stat.mode) || stat.hisize) return 0;
	*units = ((u64)stat.size + card->unit_bytes - 1) / card->unit_bytes;
	return 1;
}

int filerExtractSave(const SaveArchive *s, const char *destination, char *message, int size)
{
	VmcInfo card;
	char parent[MAX_PATH], target[MAX_PATH], path[MAX_PATH];
	int is_card, replacing, folder = 0, result = -1, created = 0, error = -EIO;
	const char *action = "open the destination";
	saveProgressStage("Preparing destination", save_progress.item);
	if (!filerSaveWritable(destination) || prepareTransferDeviceStacks(destination, destination) < 0 || genFixPath(destination, parent) < 0) goto fail;
	is_card = !strncmp(destination, "mc", 2) || !strncmp(destination, "vmc", 3);
	if (is_card && !filerCardInfo(destination, &card)) goto fail;
	if (is_card && card.type == 1 && !s->ps1) {
		snprintf(message, size, "A PS2 save needs a PS2 card or a storage folder."); goto done;
	}
	/* genFixPath may turn a storage root into dev: without a slash. */
	size_t used = strlen(parent);
	if (!used) goto fail;
	if (parent[used - 1] != '/') {
		if (used + 1 >= sizeof(parent)) goto fail;
		strcat(parent, "/");
	}
	folder = !(s->ps1 && is_card && card.type == 1);
	const char *name = s->ps1 ? s->files[0].name : s->folder.name;
	if (snprintf(target, sizeof(target), "%s%s", parent, name) >= (int)sizeof(target)) goto fail;
	replacing = filerSaveExists(target);
	if (replacing) {
		int choice;
		snprintf(message, size, "Save already exists: %s\n\nDo you wish to overwrite it?", name);
		choice = save_progress.active && save_progress.count > 1 ? filerConfirmSaveOverwrite(name) : ynDialog(message);
		if (choice == 0) {
			snprintf(message, size, "Skipped %s", name); result = 0; goto done;
		}
		if (choice < 0) {
			snprintf(message, size, "Save already exists: %s. Extraction canceled.", name); goto done;
		}
	}
	if (is_card) {
		u64 needed = 0, available = card.free_units;
		for (unsigned i = 0; i < s->count; i++) needed += ((u64)s->files[i].size + card.unit_bytes - 1) / card.unit_bytes;
		/* A fresh PS2 save directory contains . and .. plus one entry per file.
		 * Replacement reuses the parent's old entry; a new save may expand it. */
		if (folder) needed += (s->count + 3) / 2 + (replacing ? 0 : 1);
		if (replacing && needed > available) {
			u64 reclaimed;
			if (!saveReclaimableUnits(target, &card, &reclaimed)) {
				snprintf(message, size, "Could not measure the existing save. Extraction canceled."); goto done;
			}
			available += reclaimed;
		}
		if (needed > available) { snprintf(message, size, "Not enough free space for this save."); goto done; }
	}
	if (replacing) {
		FILEINFO existing = {0};
		snprintf(existing.name, sizeof(existing.name), "%s", name);
		existing.stats.AttrFile = folder ? 0x8427 : 0x8497;
		if (filerConfirmExploitDelete(destination, &existing) < 0) {
			snprintf(message, size, "Extraction canceled."); goto done;
		}
		/* Match PSU restore: replace the whole save, including stale files.
		 * Confirm and check free space before removing the old destination. */
		action = "remove the existing save";
		if ((error = delete(parent, &existing)) < 0) goto fail;
	}
	if (folder) {
		action = "create the save folder";
		if ((error = genMkdir(target, 0x8427)) < 0) goto fail;
		created = 1;
	}
	saveProgressStage("Extracting save", name);
	saveProgressExtractBegin(s, name);
	for (unsigned i = 0; i < s->count; i++) {
		if (folder) {
			if (snprintf(path, sizeof(path), "%s/%s", target, s->files[i].name) >= (int)sizeof(path)) { error = -ENAMETOOLONG; goto fail; }
		} else snprintf(path, sizeof(path), "%s", target);
		action = "write a save file";
		if ((error = filerSaveWriteFileResult(path, s->files[i].data, s->files[i].size, folder ? NULL : &created)) < 0) goto fail;
		action = "restore save metadata";
		if (!s->ps1 && !metadata(path, &s->files[i], 0)) { error = -EIO; goto fail; }
	}
	if (folder) {
		SaveArchiveEntry folder_info = s->folder;
		if (s->ps1) folder_info.mode = 0x9027;
		action = "restore folder metadata";
		if (!metadata(target, &folder_info, 1)) { error = -EIO; goto fail; }
	}
	created = 0;
	result = 1;
	snprintf(message, size, "Extracted %s", name);
	goto done;
fail:
	snprintf(message, size, "Could not %s (%d): %s", action, error, destination);
done:
	saveProgressExtractEnd(result > 0);
	if (created) removeStage(target, s, folder);
	return result;
}

int filerCanImportClipboard(void)
{
	/* Native PS1 saves are already files: Paste transfers them, and Create
	 * archive exports them. Only recognized save containers need Extract. */
	if (nclipFiles <= 0 || filerSaveClipboardIsPs1Card()) return 0;
	for (int i = 0; i < nclipFiles; i++) {
		if ((clipFiles[i].stats.AttrFile & sceMcFileAttrSubdir) ||
		    !saveArchiveSupported(clipFiles[i].name)) return 0;
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

/* Compare archive bytes with bounded transfer storage. The decoded save and
 * archive snapshot may already occupy several MiB; never allocate a second
 * archive just to authorize deleting its source. */
static int finishExtractCut(const char *destination, const char *source, const uint8_t *snapshot, size_t length, const FILEINFO *file)
{
	SaveSha1 hash;
	uint8_t expected[20], actual[20], *buffer = NULL;
	char fixed[MAX_PATH], message[160];
	size_t done = 0, capacity;
	int fd = -1, same = 0;
	unsigned int generation;
	if (filerPrepareClipboardTransfer(destination, message, sizeof(message)) < 0) return 0;
	generation = getIopResetGeneration();
	saveProgressStage("Verifying source", file->name);
	saveHashInit(&hash);
	while (done < length) {
		size_t block = length - done > 65536 ? 65536 : length - done;
		saveHashUpdate(&hash, snapshot + done, block); done += block;
		DashIoYield();
	}
	saveHashFinish(&hash, expected);
	capacity = filerTransferBufferSize(source, destination, length);
	if (!capacity || !(buffer = memalign(64, capacity)) || genFixPath(source, fixed) < 0 ||
	    (fd = genOpen(fixed, FIO_O_RDONLY)) < 0) goto done;
	if (genLseek(fd, 0, SEEK_END) != (s64)length || genLseek(fd, 0, SEEK_SET) != 0) goto done;
	saveHashInit(&hash); saveProgressFile(source, length);
	done = 0;
	while (done < length) {
		size_t block = length - done > capacity ? capacity : length - done;
		int count = genRead(fd, buffer, block);
		if (count <= 0 || (size_t)count > block) goto done;
		/* Bound cooperative work even when a fast device selected a 1 MiB buffer. */
		for (size_t offset = 0; offset < (size_t)count;) {
			size_t chunk = count - offset > 65536 ? 65536 : count - offset;
			saveHashUpdate(&hash, buffer + offset, chunk); offset += chunk; DashIoYield();
		}
		done += count;
		if (done < length) saveProgressBytes(source, done, length);
	}
	if (genLseek(fd, 0, SEEK_END) != (s64)length) goto done;
	saveHashFinish(&hash, actual);
	same = !memcmp(actual, expected, sizeof(actual));
done:
	if (fd >= 0 && genClose(fd) < 0) same = 0;
	free(buffer);
	if (same) saveProgressBytes(source, length, length);
	return same && generation == getIopResetGeneration() && clipIopResetGeneration == generation &&
	       filerConfirmExploitDelete(clipPath, file) >= 0 && delete(clipPath, file) >= 0;
}

int filerImportClipboard(const char *destination, char *message, int size)
{
	char source[MAX_PATH];
	int count = 0, skipped = 0, kept = 0, cut = browser_cut, total = nclipFiles;
	if (!filerCanImportClipboard()) {
		snprintf(message, size, "Copy or cut save archives first."); return -1;
	}
	saveProgressBegin(total);
	for (int i = 0; i < nclipFiles;) {
		SaveArchive save = {0};
		uint8_t *snapshot = NULL;
		size_t length = 0;
		int result = -1;
		saveProgressItem(count + skipped + 1, clipFiles[i].name, "Reading archive");
		if (filerPrepareClipboardTransfer(destination, message, size) < 0) {
			/* Keep the source and destination readiness diagnostic. */
		} else if (snprintf(source, sizeof(source), "%s%s", clipPath, clipFiles[i].name) >= (int)sizeof(source))
			snprintf(message, size, "The copied archive path is too long.");
		else if (loadSaveSnapshot(source, &save, &snapshot, &length, message, size))
			result = filerExtractSave(&save, destination, message, size);
		saveArchiveFree(&save);
		if (result < 0) {
			free(snapshot);
			if (count || skipped) {
				char reason[192]; snprintf(reason, sizeof(reason), "%s", message);
				if (skipped) snprintf(message, size, "%d extracted; %d skipped; stopped: %s", count, skipped, reason);
				else snprintf(message, size, "%d extracted; stopped: %s", count, reason);
			}
			saveProgressEnd(); return -1;
		}
		if (result == 0) {
			/* Skip never publishes or removes a Cut source. Keep its clipboard
			 * entry and advance independently of the extracted-save count. */
			skipped++; i++; free(snapshot); continue;
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
	snprintf(message, size, "Extracted %d save%s", count, count == 1 ? "" : "s");
	if (skipped && (int)strlen(message) < size) {
		int used = strlen(message);
		snprintf(message + used, size - used, "; %d skipped", skipped);
	}
	if (kept && (int)strlen(message) < size) {
		int used = strlen(message);
		snprintf(message + used, size - used, "; %d source archive%s kept because removal could not be verified.",
		         kept, kept == 1 ? "" : "s");
	}
	saveProgressEnd();
	return kept ? 0 : count;
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
		    filerSaveReadHeader(nested, header, &length) >= 4 && !memcmp(header, "PS2D", 4)) return FILER_SAVE_PS2;
		if (snprintf(nested, sizeof(nested), "%s/%s", path, file->name) >= (int)sizeof(nested)) return FILER_SAVE_NONE;
		n = filerSaveReadHeader(nested, header, &length);
		return n >= 2 && !memcmp(header, "SC", 2) && length && length <= 15 * PS1_BLOCK_SIZE &&
		       !(length % PS1_BLOCK_SIZE) ? FILER_SAVE_PS1 : FILER_SAVE_NONE;
	}
	/* Only plausible saves/cards need a probe, and only when the menu opens. */
	length = file->stats.FileSizeByte;
	if (!saveArchiveSupported(file->name) && !filerIsPs1Image(file->name) &&
	    !(length && length <= 134976 && !(length % PS1_BLOCK_SIZE))) return FILER_SAVE_NONE;
	n = filerSaveReadHeader(path, header, &length);
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
