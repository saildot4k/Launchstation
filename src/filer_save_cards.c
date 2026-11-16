#include "filer_saves_internal.h"

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

int filerPs1CardCandidate(const FILEINFO *file)
{
	u64 bytes;
	if (!file || (file->stats.AttrFile & sceMcFileAttrSubdir) || !filerIsPs1Image(file->name)) return 0;
	bytes = ((u64)file->stats.Reserve2 << 32) | file->stats.FileSizeByte;
	return bytes == 131072 || bytes == 131136 || bytes == 131200 || bytes == 134976;
}

int filerIsPs1Image(const char *name)
{
	return genCmpFileExt(name, "VMC") || genCmpFileExt(name, "BIN") || genCmpFileExt(name, "MCR") ||
	       genCmpFileExt(name, "MCD") || genCmpFileExt(name, "MC") || genCmpFileExt(name, "MEM") ||
	       genCmpFileExt(name, "VM1") || genCmpFileExt(name, "SRM") ||
	       genCmpFileExt(name, "GME") || genCmpFileExt(name, "VGS") || genCmpFileExt(name, "VMP");
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
			save = filerSaveReadSource(path, &length);
			ok = save && ps1CardAppend(data, files[i].name, save, length);
			free(save);
			if (!ok) { free(files); goto fail; }
		}
		free(files);
	} else {
		data = filerSaveReadSource(source, &length);
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
	if (!data || memcmp(data, "MC", 2) || !filerSaveWritable(destination)) goto fail;
	if (prepareTransferDeviceStacks(destination, destination) < 0 || genFixPath(destination, output) < 0) goto fail;
	snprintf(parent, sizeof(parent), "%s", output);
	char *leaf = strrchr(parent, '/');
	if (!leaf || !leaf[1]) goto fail;
	leaf[1] = 0;
	if (filerSaveExists(output)) { snprintf(message, size, "Card already exists. Rename it or choose another folder."); goto done; }
	if (!filerSaveUniquePath(parent, stage, sizeof(stage), "VMC")) goto fail;
	staged = 1;
	if (!filerSaveWriteFile(stage, data, PS1_CARD_SIZE) || genRenameNoReplace(stage, output) < 0) goto fail;
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
