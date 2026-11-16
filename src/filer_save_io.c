#include "filer_saves_internal.h"

uint8_t *filerSaveReadSource(const char *path, size_t *size)
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
	saveProgressFile(path, length);
	while (done < (size_t)length) {
		int count = (length - done > 65536) ? 65536 : (int)(length - done);
		n = genRead(fd, data + done, count);
		if (n <= 0 || n > count) { free(data); genClose(fd); return NULL; }
		done += n;
		if (done < (size_t)length) saveProgressBytes(path, done, length);
	}
	if (genClose(fd) < 0) { free(data); return NULL; }
	saveProgressBytes(path, done, length);
	*size = done;
	return data;
}

int filerSaveExists(const char *path)
{
	char dir[MAX_PATH];
	int fd = genOpen(path, FIO_O_RDONLY);
	if (fd >= 0) { genClose(fd); return 1; }
	snprintf(dir, sizeof(dir), "%s", path);
	fd = genDopen(dir);
	if (fd >= 0) { genDclose(fd); return 1; }
	return 0;
}

int filerSaveWritable(const char *path)
{
	/* Keep the existing save-action destination policy. Archive writes do
	 * not depend on the device actually implementing native rename. */
	return genCanRenamePath(path) && strncmp(path, "host", 4);
}

int filerSaveUniquePath(const char *parent, char *out, size_t size, const char *suffix)
{
	for (int i = 0; i < 100; i++) {
		if (snprintf(out, size, "%sLSI%02d.%s", parent, i, suffix) >= (int)size) return 0;
		if (!filerSaveExists(out)) return 1;
	}
	return 0;
}

int filerSaveWriteFileResult(const char *path, const uint8_t *data, size_t size, int *opened)
{
	size_t done = 0;
	int n, result = 0, closed, fd;
	if (opened) *opened = 0;
	fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
	if (fd < 0) return fd;
	if (opened) *opened = 1;
	saveProgressFile(path, size);
	while (done < size) {
		int count = size - done > 65536 ? 65536 : (int)(size - done);
		n = genWrite(fd, (void *)(data + done), count);
		if (n <= 0 || n > count) { result = n < 0 ? n : -EIO; break; }
		done += n;
		if (done < size) saveProgressBytes(path, done, size);
	}
	closed = genClose(fd);
	if (result >= 0 && closed >= 0) saveProgressBytes(path, done, size);
	return result < 0 ? result : closed < 0 ? closed : 0;
}

int filerSaveWriteFile(const char *path, const uint8_t *data, size_t size)
{
	return filerSaveWriteFileResult(path, data, size, NULL) >= 0;
}

int filerSaveReadHeader(const char *path, uint8_t header[132], size_t *length)
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
