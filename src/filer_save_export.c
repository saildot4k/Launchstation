#include "filer_saves_internal.h"

static int sameArchiveName(const char *left, const char *right);

/* Copy/Cut stores metadata only; archive creation retains a digest for the
 * post-write Cut check. No payload snapshot survives publication. */
static int archive_stream_valid, archive_stream_format;
static size_t archive_stream_length;
static uint8_t archive_stream_digest[20];
static int archive_clip_kind, archive_clip_card_type, archive_clip_probed;
static int archive_clip_count, archive_clip_index;
static FILEINFO archive_clip_file;
static char archive_clip_folder[MAX_PATH];

/* The listing's captured card type avoids probing the source in Options.
 * A native save can contain a dot and resemble an archive filename. */
int filerSaveClipboardIsPs1Card(void)
{
	return archive_clip_card_type == 1 && !strcmp(clipPath, archive_clip_folder) &&
	       (!strncmp(clipPath, "mc", 2) || !strncmp(clipPath, "vmc", 3));
}

void filerClearArchiveClipboard(void)
{
	archive_stream_valid = 0;
	archive_clip_kind = FILER_SAVE_NONE;
	archive_clip_probed = 0;
}

static int archiveClipboardMatches(void)
{
	return nclipFiles > 0 && nclipFiles == archive_clip_count && archive_clip_index < nclipFiles &&
	       !strcmp(clipPath, archive_clip_folder) &&
	       !strcmp(clipFiles[archive_clip_index].name, archive_clip_file.name) &&
	       !memcmp(&clipFiles[archive_clip_index].stats, &archive_clip_file.stats, sizeof(archive_clip_file.stats));
}

static int archiveCandidate(const FILEINFO *file)
{
	u64 bytes = ((u64)file->stats.Reserve2 << 32) | file->stats.FileSizeByte;
	if (!file->name[0] || !strcmp(file->name, ".") || !strcmp(file->name, ".."))
		return FILER_SAVE_NONE;
	/* Opening Options uses listing metadata only. Resolve a candidate's
	 * contents and folder flatness after the user chooses Create archive. */
	if (file->stats.AttrFile & sceMcFileAttrSubdir)
		return archive_clip_card_type == 2 && (file->stats.AttrFile & 0x1000) ? FILER_SAVE_PS1 : FILER_SAVE_PS2;
	if (archive_clip_card_type == 1 || (bytes && bytes <= 15 * PS1_BLOCK_SIZE &&
	    !(bytes % PS1_BLOCK_SIZE) && strlen(file->name) <= 20)) return FILER_SAVE_PS1;
	return FILER_SAVE_NONE;
}

int filerArchiveClipboardKind(void)
{
	int kind = FILER_SAVE_NONE;
	if (!archiveClipboardMatches()) return FILER_SAVE_NONE;
	if (nclipFiles == 1 && archive_clip_probed) return archive_clip_kind;
	for (int i = 0; i < nclipFiles; i++) {
		int candidate = archiveCandidate(&clipFiles[i]);
		if (!candidate) return FILER_SAVE_NONE;
		kind = !kind || kind == candidate ? candidate : FILER_SAVE_MIXED;
	}
	return kind;
}

void filerRememberArchiveClipboard(int card_type)
{
	filerClearArchiveClipboard();
	archive_clip_folder[0] = 0;
	archive_clip_count = 0; archive_clip_index = 0;
	if (nclipFiles <= 0 || nclipFiles > MAX_ENTRY) return;
	archive_clip_count = nclipFiles;
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

static int probeArchiveItem(const FILEINFO *file)
{
	char source[MAX_PATH];
	VmcInfo card;
	int kind, files, type = archive_clip_card_type;
	if (!archiveCandidate(file) ||
	    snprintf(source, sizeof(source), "%s%s", clipPath, file->name) >= (int)sizeof(source)) return FILER_SAVE_NONE;
	if (!strncmp(clipPath, "mc", 2) || !strncmp(clipPath, "vmc", 3)) {
		if (!filerCardInfo(clipPath, &card)) return FILER_SAVE_NONE;
		type = card.type;
	}
	kind = filerSaveKind(clipPath, file, type);
	if (file->stats.AttrFile & sceMcFileAttrSubdir) {
		files = flatArchiveFolder(source);
		if (!files) kind = FILER_SAVE_NONE;
		else if (kind == FILER_SAVE_NONE || (kind == FILER_SAVE_PS1 && files != 1)) kind = FILER_SAVE_PS2;
	}
	return kind == FILER_SAVE_PS1 || kind == FILER_SAVE_PS2 ? kind : FILER_SAVE_NONE;
}

int filerProbeArchiveClipboard(const char *destination)
{
	char message[160];
	int kind = FILER_SAVE_NONE;
	if (!archiveClipboardMatches() || !filerSaveWritable(destination) ||
	    filerPrepareClipboardTransfer(destination, message, sizeof(message)) < 0) return FILER_SAVE_NONE;
	for (int i = 0; i < nclipFiles; i++) {
		int candidate = probeArchiveItem(&clipFiles[i]);
		if (!candidate) { kind = FILER_SAVE_NONE; break; }
		kind = !kind || kind == candidate ? candidate : FILER_SAVE_MIXED;
	}
	if (nclipFiles == 1) { archive_clip_kind = kind; archive_clip_probed = 1; }
	return kind;
}

/* Apply the existing PSU backup policy only to the final output name.
 * Canonical clipboard snapshots and their Cut comparisons stay independent
 * of naming preferences. Reuse R3Z's title conversion and device name limits. */
static int clipboardArchiveFilename(const SaveArchive *save, int format, const char *source,
                                    const char *destination, char *out, int size)
{
	char parent[MAX_PATH], path[MAX_PATH], name[MAX_NAME], title[66] = {0};
	unsigned char sjis[66];
	const uint8_t *date = save->folder.modified;
	int count;
	if (format != SAVE_OUTPUT_PSU) return saveArchiveFilename(save, format, out, size);
	if (setting->PSU_HugeNames || fileShowTitles()) {
		snprintf(parent, sizeof(parent), "%s", source);
		char *leaf = strrchr(parent, '/');
		if (leaf) {
			leaf[1] = 0;
			if (filerGetGameTitle(parent, &archive_clip_file, sjis) == 0 && sjis[0]) transcpy_sjis(title, sjis);
		}
	}
	if (title[0] && setting->PSU_HugeNames)
		count = snprintf(name, sizeof(name), "%s_%s", save->folder.name, title);
	else count = snprintf(name, sizeof(name), "%s", title[0] ? title : save->folder.name);
	if (count < 0 || count >= (int)sizeof(name)) return 0;
	for (int i = 0; name[i]; i++) if (strchr("\"\\/:*?<>|", name[i])) name[i] = '_';
	if (setting->PSU_DateNames) {
		count += snprintf(name + count, sizeof(name) - count, "_%04d-%02d-%02d_%02d-%02d-%02d",
		                  date[6] | (date[7] << 8), date[5], date[4], date[3], date[2], date[1]);
		if (count >= (int)sizeof(name)) return 0;
	}
	if (snprintf(path, sizeof(path), "%s%s", destination, name) >= (int)sizeof(path)) return 0;
	genLimObjName(path, 4);
	if (strlen(path) + 4 >= sizeof(path)) return 0;
	strcat(path, ".psu");
	const char *leaf = strrchr(path, '/');
	return leaf && snprintf(out, size, "%s", leaf + 1) < size;
}

/* One source listing and two bounded transfer buffers; payloads are never
 * retained between entries or between archive creation and Cut verification. */
typedef struct {
	SaveArchive save;
	char source[MAX_PATH];
	int input, output, entry;
	size_t input_pos, output_pos, length, buffer_size;
	uint8_t *buffer, *buffer2;
	SaveSha1 hash;
} ArchiveStream;

static int archiveStreamCloseInput(ArchiveStream *stream)
{
	int result = 0;
	if (stream->input >= 0) result = genClose(stream->input);
	stream->input = -1;
	return result >= 0;
}

static void archiveStreamFree(ArchiveStream *stream)
{
	archiveStreamCloseInput(stream);
	if (stream->output >= 0) genClose(stream->output);
	stream->output = -1;
	free(stream->buffer2); free(stream->buffer);
	stream->buffer = stream->buffer2 = NULL;
	saveArchiveFree(&stream->save);
}

static int archiveStreamPath(const ArchiveStream *stream, unsigned entry, char *out)
{
	return (stream->save.ps1 ? snprintf(out, MAX_PATH, "%s", stream->source) :
	        snprintf(out, MAX_PATH, "%s/%s", stream->source, stream->save.files[entry].name)) < MAX_PATH;
}

static int archiveStreamRead(void *context, unsigned entry, size_t offset, void *data, size_t length)
{
	ArchiveStream *stream = context;
	char path[MAX_PATH], fixed[MAX_PATH];
	size_t done = 0;
	if (entry >= stream->save.count || offset > stream->save.files[entry].size ||
	    length > stream->save.files[entry].size - offset) return 0;
	if (stream->input < 0 || stream->entry != (int)entry) {
		if (!archiveStreamCloseInput(stream) || !archiveStreamPath(stream, entry, path) ||
		    genFixPath(path, fixed) < 0 || (stream->input = genOpen(fixed, FIO_O_RDONLY)) < 0) return 0;
		stream->entry = entry;
		if (genLseek(stream->input, 0, SEEK_END) != (s64)stream->save.files[entry].size ||
		    genLseek(stream->input, 0, SEEK_SET) != 0) return 0;
		stream->input_pos = 0;
	}
	if (stream->input_pos != offset && genLseek(stream->input, offset, SEEK_SET) != (s64)offset) return 0;
	while (done < length) {
		int n = genRead(stream->input, (uint8_t *)data + done, length - done);
		if (n <= 0 || (size_t)n > length - done) return 0;
		done += n;
	}
	stream->input_pos = offset + done;
	return 1;
}

static int archiveStreamWrite(void *context, size_t offset, const void *data, size_t length)
{
	ArchiveStream *stream = context;
	size_t done = 0;
	/* Hash the deterministic header/data emission, including PSV's final patch.
	 * The same encoder is replayed into this digest sink before a Cut deletes. */
	for (size_t hashed = 0; hashed < length;) {
		size_t block = length - hashed;
		if (block > 65536) block = 65536;
		saveHashUpdate(&stream->hash, (const uint8_t *)data + hashed, block); hashed += block;
		DashIoYield();
	}
	if (stream->output >= 0) {
		if (stream->output_pos != offset && genLseek(stream->output, offset, SEEK_SET) != (s64)offset) return 0;
		while (done < length) {
			int n = genWrite(stream->output, (uint8_t *)data + done, length - done);
			if (n <= 0 || (size_t)n > length - done) return 0;
			done += n;
		}
	}
	stream->output_pos = offset + length;
	/* 100% is published only after both descriptors have closed successfully. */
	if (offset + length < stream->length && offset != 28)
		saveProgressBytes(save_progress.item, offset + length, stream->length);
	return 1;
}

static int archiveStreamLoad(ArchiveStream *stream, const char *source, const FILEINFO *file, int kind)
{
	SaveArchive *save = &stream->save;
	FILEINFO *files = NULL;
	char path[MAX_PATH];
	int count;
	memset(stream, 0, sizeof(*stream)); stream->input = stream->output = stream->entry = -1;
	if (snprintf(stream->source, sizeof(stream->source), "%s", source) >= (int)sizeof(stream->source)) return 0;
	size_t used = strlen(stream->source);
	if (used && stream->source[used - 1] == '/') stream->source[used - 1] = 0;
	if (kind == FILER_SAVE_PS1) {
		uint8_t header[132];
		size_t length;
		if (file->stats.AttrFile & sceMcFileAttrSubdir) {
			if (snprintf(path, sizeof(path), "%s/%s", stream->source, file->name) >= (int)sizeof(path)) return 0;
			snprintf(stream->source, sizeof(stream->source), "%s", path);
		}
		if (filerSaveReadHeader(stream->source, header, &length) < 2 || length > 15 * PS1_BLOCK_SIZE ||
		    !length || length % PS1_BLOCK_SIZE || toupper(header[0]) != 'S' || toupper(header[1]) != 'C' ||
		    strlen(file->name) > 20) return 0;
		save->files = calloc(1, sizeof(*save->files));
		if (!save->files) return 0;
		save->ps1 = save->count = 1;
		strcpy(save->files[0].name, file->name); save->files[0].size = length; save->files[0].mode = 0x8497;
		return 1;
	}
	if (kind != FILER_SAVE_PS2 || strlen(file->name) > 32 ||
	    snprintf(path, sizeof(path), "%s/", stream->source) >= (int)sizeof(path)) return 0;
	files = malloc(MAX_ENTRY * sizeof(*files));
	if (!files) return 0;
	count = getDir(path, files);
	if (count <= 0 || count >= MAX_ENTRY - 2 ||
	    !(save->files = calloc(count, sizeof(*save->files)))) { free(files); return 0; }
	strcpy(save->folder.name, file->name); save->folder.mode = file->stats.AttrFile;
	memcpy(save->folder.created, &file->stats._Create, 8); memcpy(save->folder.modified, &file->stats._Modify, 8);
	for (int i = 0; i < count; i++) {
		SaveArchiveEntry *e = &save->files[save->count];
		if (!strcmp(files[i].name, ".") || !strcmp(files[i].name, "..")) continue;
		if ((files[i].stats.AttrFile & sceMcFileAttrSubdir) || strlen(files[i].name) > 32 ||
		    files[i].stats.Reserve2 || files[i].stats.FileSizeByte > SAVE_ARCHIVE_LIMIT) { free(files); return 0; }
		strcpy(e->name, files[i].name); e->size = files[i].stats.FileSizeByte; e->mode = files[i].stats.AttrFile;
		memcpy(e->created, &files[i].stats._Create, 8); memcpy(e->modified, &files[i].stats._Modify, 8);
		save->count++;
	}
	free(files);
	return save->count != 0;
}

static int archiveStreamBuffers(ArchiveStream *stream, const char *destination)
{
	void *first, *second;
	if (stream->buffer) return 1;
	stream->buffer_size = filerTransferBufferSize(stream->source, destination, stream->length);
	if (!stream->buffer_size || !filerAllocateTransferBuffers(stream->buffer_size, &first, &second)) return 0;
	stream->buffer = first; stream->buffer2 = second;
	return 1;
}

static void archiveStreamYield(void *context)
{
	(void)context;
	DashIoYield();
}

static int archiveStreamRun(ArchiveStream *stream, int format, const char *destination, uint8_t digest[20])
{
	SaveArchiveStreamIo io = {archiveStreamRead, archiveStreamWrite, stream, NULL, NULL, 0, archiveStreamYield};
	int result;
	if (!archiveStreamBuffers(stream, destination)) return 0;
	io.buffer = stream->buffer; io.buffer2 = stream->buffer2; io.buffer_size = stream->buffer_size;
	saveHashInit(&stream->hash);
	result = saveArchiveStream(&stream->save, format, &io, &stream->length);
	if (!archiveStreamCloseInput(stream)) result = 0;
	if (result) saveHashFinish(&stream->hash, digest);
	return result;
}

static int archiveStreamPrepare(const char *destination, int format, ArchiveStream *stream,
                                char *name, int name_size, char *message, int size)
{
	char source[MAX_PATH];
	SaveArchiveStreamIo io = {archiveStreamRead, NULL, stream, NULL, NULL, 0, NULL};
	memset(stream, 0, sizeof(*stream)); stream->input = stream->output = stream->entry = -1;
	if (!archiveClipboardMatches() || !filerSaveWritable(destination) ||
	    filerPrepareClipboardTransfer(destination, message, size) < 0) return 0;
	archive_clip_kind = probeArchiveItem(&archive_clip_file); archive_clip_probed = 1;
	if (!archive_clip_kind || snprintf(source, sizeof(source), "%s%s", clipPath, archive_clip_file.name) >= (int)sizeof(source) ||
	    !archiveStreamLoad(stream, source, &archive_clip_file, archive_clip_kind) ||
	    !saveArchiveStream(&stream->save, format, &io, &stream->length) ||
	    !archiveStreamCloseInput(stream) ||
	    !clipboardArchiveFilename(&stream->save, format, source, destination, name, name_size)) {
		snprintf(message, size, format == SAVE_OUTPUT_PSV && archive_clip_kind == FILER_SAVE_PS2 ?
		         "PSV needs a flat PS2 save with icon.sys and its referenced icons." : "Could not read or archive this save. Choose one complete save.");
		return 0;
	}
	return 1;
}

static int archiveStreamPublish(ArchiveStream *stream, int format, const char *destination, char *message, int size)
{
	char output[MAX_PATH], path[MAX_PATH], fixed[MAX_PATH];
	VmcInfo card;
	int replace, result, closed;
	uint8_t digest[20];
	if (genFixPath(destination, output) < 0) goto fail;
	if ((!strncmp(destination, "mc", 2) || !strncmp(destination, "vmc", 3)) &&
	    (!filerCardInfo(destination, &card) || card.type == 1)) {
		snprintf(message, size, "Choose storage or a PS2 card for archive files."); return -1;
	}
	/* Streaming must never truncate one of its own inputs. */
	for (unsigned i = 0; i < stream->save.count; i++) {
		if (!archiveStreamPath(stream, i, path) || genFixPath(path, fixed) < 0) goto fail;
		if (sameArchiveName(fixed, output)) {
			snprintf(message, size, "The archive destination is one of the source files."); return -1;
		}
	}
	replace = filerSaveExists(output);
	if (replace) {
		if (format != SAVE_OUTPUT_PSU) {
			snprintf(message, size, "Archive already exists. Rename it or choose another folder."); return -1;
		}
		if (setting->PSU_NoOverwrite) {
			snprintf(message, size, "PSU archive already exists; skipped because never overwrite is enabled."); return 0;
		}
	}
	/* Allocate before opening/truncating the destination; a second fast buffer
	 * is optional, exactly as in ordinary transfers. */
	if (!archiveStreamBuffers(stream, destination)) goto fail;
	stream->output = genOpen(output, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
	if (stream->output < 0) goto fail;
	saveProgressFile(save_progress.item, stream->length);
	result = archiveStreamRun(stream, format, destination, digest);
	closed = genClose(stream->output); stream->output = -1;
	if (!result || closed < 0) {
		if (!replace) genRemove(output);
		goto fail;
	}
	archive_stream_valid = 1; archive_stream_format = format; archive_stream_length = stream->length;
	memcpy(archive_stream_digest, digest, sizeof(archive_stream_digest));
	saveProgressBytes(save_progress.item, stream->length, stream->length);
	snprintf(message, size, "Archive created: %s", destination);
	return 1;
fail:
	snprintf(message, size, "Could not write archive: %s", destination);
	return -1;
}

static int archiveStreamVerify(const char *source, const char *destination)
{
	ArchiveStream stream;
	uint8_t digest[20];
	int same = 0;
	if (archiveStreamLoad(&stream, source, &archive_clip_file, archive_clip_kind)) {
		SaveArchiveStreamIo io = {archiveStreamRead, NULL, &stream, NULL, NULL, 0, NULL};
		if (saveArchiveStream(&stream.save, archive_stream_format, &io, &stream.length) &&
		    stream.length == archive_stream_length) {
			saveProgressFile(save_progress.item, stream.length);
			same = archiveStreamRun(&stream, archive_stream_format, destination, digest) &&
			       !memcmp(digest, archive_stream_digest, sizeof(digest));
			if (same) saveProgressBytes(save_progress.item, stream.length, stream.length);
		}
	}
	archiveStreamFree(&stream);
	return same;
}

static int filerFinishArchiveClipboard(const char *destination, char *message, int size)
{
	char source[MAX_PATH], detail[160];
	size_t length = 0;
	int same;
	unsigned int generation;
	if (!browser_cut) { filerClearArchiveClipboard(); return 1; }
	if (!archiveClipboardMatches() || !archive_clip_kind || !archive_stream_valid ||
	    snprintf(source, sizeof(source), "%s%s", archive_clip_folder, archive_clip_file.name) >= (int)sizeof(source)) goto kept;
	/* Do not delete an output created inside the original PS2 save folder. */
	length = strlen(source);
	if (!strncmp(destination, source, length) && destination[length] == '/') goto kept;
	if (filerPrepareClipboardTransfer(destination, detail, sizeof(detail)) < 0) goto kept;
	generation = getIopResetGeneration();
	if (save_progress.active) save_progress.verifying = 1;
	saveProgressStage("Verifying source", archive_clip_file.name);
	/* Confirm the complete data and metadata still match before deleting. */
	same = archiveStreamVerify(source, destination);
	if (!same || generation != getIopResetGeneration() ||
	    filerConfirmExploitDelete(archive_clip_folder, &archive_clip_file) < 0 ||
	    delete(archive_clip_folder, &archive_clip_file) < 0) goto kept;
	memmove(&clipFiles[archive_clip_index], &clipFiles[archive_clip_index + 1],
	        (nclipFiles - archive_clip_index - 1) * sizeof(clipFiles[0]));
	archive_clip_count = --nclipFiles;
	archive_clip_index = 0;
	if (!nclipFiles) { browser_cut = 0; clipPath[0] = 0; }
	else archive_clip_file = clipFiles[0];
	filerClearArchiveClipboard();
	return 1;
kept:
	filerClearArchiveClipboard();
	snprintf(message, size, "Archive created; source save kept because it could not be safely removed.");
	return 0;
}

static int sameArchiveName(const char *left, const char *right)
{
	while (*left && toupper((unsigned char)*left) == toupper((unsigned char)*right)) { left++; right++; }
	return *left == *right;
}

int filerCreateClipboardArchives(const char *destination, int format, char *message, int size)
{
	char output[MAX_PATH], name[MAX_NAME], detail[MAX_PATH];
	char (*created)[MAX_NAME];
	int count = 0, skipped = 0, kept = 0, total = nclipFiles, cut = browser_cut;
	if (!archiveClipboardMatches() || !total) {
		snprintf(message, size, "Copy or cut complete PS1 saves or flat folders first."); return -1;
	}
	/* Retain only output names across items, never an entire batch of saves.
	 * Detect duplicate generated names before an overwrite could discard a
	 * previous Cut item's only backup (including case-insensitive devices). */
	created = calloc(total, sizeof(*created));
	if (!created) { snprintf(message, size, "Not enough memory to create archives."); return -1; }
	saveProgressBegin(total);
	for (int i = 0; i < nclipFiles;) {
		ArchiveStream stream;
		int result, before = nclipFiles;
		filerClearArchiveClipboard();
		archive_clip_index = i; archive_clip_file = clipFiles[i];
		saveProgressItem(count + skipped + 1, clipFiles[i].name, "Preparing archive");
		if (!archiveStreamPrepare(destination, format, &stream, name, sizeof(name), message, size)) {
			archiveStreamFree(&stream); goto fail;
		}
		if (!name[0] || snprintf(output, sizeof(output), "%s%s", destination, name) >= (int)sizeof(output)) {
			archiveStreamFree(&stream); snprintf(message, size, "The archive destination path is too long."); goto fail;
		}
		for (int j = 0; j < count; j++) if (sameArchiveName(name, created[j])) {
			archiveStreamFree(&stream);
			snprintf(message, size, "Two saves produce the same archive name: %s", name); goto fail;
		}
		saveProgressStage("Creating archive", name);
		result = archiveStreamPublish(&stream, format, output, message, size);
		archiveStreamFree(&stream);
		if (result < 0) goto fail;
		if (!result) skipped++;
		else {
			snprintf(created[count++], MAX_NAME, "%s", name);
			if (!filerFinishArchiveClipboard(output, message, size) && cut) kept++;
		}
		if (nclipFiles == before) i++;
	}
	saveProgressEnd(); free(created); filerClearArchiveClipboard();
	if (total == 1 && !skipped && !kept) snprintf(message, size, "Archive created: %s", output);
	else snprintf(message, size, "%d archive%s created; %d skipped; %d source save%s kept.",
	              count, count == 1 ? "" : "s", skipped, cut ? skipped + kept : total,
	              (cut ? skipped + kept : total) == 1 ? "" : "s");
	return skipped || kept ? 0 : count;
fail:
	snprintf(detail, sizeof(detail), "%s", message);
	snprintf(message, size, "%d archive%s created; stopped at %s: %s", count, count == 1 ? "" : "s",
	         archive_clip_file.name, detail);
	saveProgressEnd(); free(created); filerClearArchiveClipboard();
	return -1;
}
