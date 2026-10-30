// Extract the selected ELF from verified legacy (2-file) or sidecar-complete (4-file) app PSUs.
#include "launchelf.h"
#include "self_update.h"

static unsigned int psu32(const unsigned char *p)
{
    return p[0] | ((unsigned int)p[1] << 8) | ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

static int read_exact(int fd, unsigned char *buf, int size)
{
    while (size > 0) {
        int n = genRead(fd, buf, size);
        if (n <= 0 || n > size)
            return 0;
        buf += n;
        size -= n;
    }
    return 1;
}

static int record_is(const unsigned char *record, unsigned int mode, const char *name)
{
    return (record[0] | ((unsigned int)record[1] << 8)) == mode &&
           memchr(record + 64, 0, 448) != NULL && !strcmp((const char *)record + 64, name);
}

int selfUpdateExtractPsu(const char *package, const char *stage, int size)
{
    unsigned char directories[1536], entry[512], buffer[4096];
    int input = -1, output = -1, position = 1536, seen = 0, elf_size = -1, i, entries;
    char remove_path[MAX_PATH];

    if (size < 1536 || size > 16 * 1024 * 1024)
        return -1;
    input = genOpen(package, FIO_O_RDONLY);
    if (input < 0 || genLseek(input, 0, SEEK_END) != size ||
        genLseek(input, 0, SEEK_SET) != 0 || !read_exact(input, directories, 1536))
        goto done;
    entries = (int)psu32(directories + 4);
    /* A root entry counts itself, "." and ".." plus 2 or 4 files.
     * Preserve compatibility with older packages during migration. */
    if (!record_is(directories, 0x8027, SELF_UPDATE_FOLDER) ||
        (entries != 4 && entries != 6) ||
        !record_is(directories + 512, 0x8027, ".") ||
        !record_is(directories + 1024, 0x8027, ".."))
        goto done;

    for (i = 0; i < entries - 2; i++) {
        unsigned int length, padded;
        int is_elf;
        if (position > size - 512 || genLseek(input, position, SEEK_SET) != position ||
            !read_exact(input, entry, 512))
            goto done;
        position += 512;
        length = psu32(entry + 4);
        if (length == 0 || length > (unsigned int)(size - position))
            goto done;
        padded = (length + 1023) & ~1023u;
        if (padded > (unsigned int)(size - position))
            goto done;
        is_elf = record_is(entry, 0x8017, SELF_UPDATE_ELF);
        if (is_elf) {
            unsigned int remaining = length;
            if ((seen & 1) || length < 52)
                goto done;
            output = genOpen(stage, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
            if (output < 0)
                goto done;
            while (remaining) {
                int count = remaining > sizeof(buffer) ? sizeof(buffer) : remaining;
                int written = 0;
                if (!read_exact(input, buffer, count))
                    goto done;
                while (written < count) {
                    int n = genWrite(output, buffer + written, count - written);
                    if (n <= 0 || n > count - written)
                        goto done;
                    written += n;
                }
                remaining -= count;
            }
            if (genClose(output) < 0) {
                output = -1;
                goto done;
            }
            output = -1;
            seen |= 1;
            elf_size = length;
        } else if (record_is(entry, 0x8017, "title.cfg") && !(seen & 2) && length <= 4096) {
            seen |= 2;
        } else if (entries == 6 &&
                   record_is(entry, 0x8017, "WLE-UPDATE-CA.PEM") &&
                   !(seen & 4) && length <= 32768) {
            seen |= 4;
        } else if (entries == 6 &&
                   record_is(entry, 0x8017, "BGM.ADP") &&
                   !(seen & 8) && length >= 32 && length <= 1024 * 1024 &&
                   !(length & 15)) {
            seen |= 8;
        } else {
            goto done;
        }
        position += padded;
    }
    if (seen == (entries == 6 ? 15 : 3) && position == size) {
        if (genClose(input) < 0)
            goto remove_stage;
        return elf_size;
    }
done:
    if (output >= 0)
        genClose(output);
    if (input >= 0)
        genClose(input);
remove_stage:
    snprintf(remove_path, sizeof(remove_path), "%s", stage);
    genRemove(remove_path);
    return -1;
}


/* Update only the packaged boot entry when the installed ELF was renamed.
 * All other release metadata and line endings come from the verified PSU. */
static int write_title(int fd, const unsigned char *data, int size, const char *boot_leaf)
{
    int begin = -1, end = -1, i, count, written;
    const unsigned char *parts[3];
    int lengths[3];

    if (boot_leaf == NULL || !boot_leaf[0] || strlen(boot_leaf) >= MAX_NAME ||
        strpbrk(boot_leaf, "/\\:\r\n") != NULL || memchr(data, 0, size) != NULL)
        return -1;
    for (i = 0; i < size; i++) {
        if ((i == 0 || data[i - 1] == '\n') && size - i >= 5 &&
            !memcmp(data + i, "boot=", 5)) {
            if (begin >= 0)
                return -1;
            begin = i + 5;
            end = begin;
            while (end < size && data[end] != '\r' && data[end] != '\n')
                end++;
        }
    }
    if (begin < 0 || end - begin != (int)strlen(SELF_UPDATE_ELF) ||
        memcmp(data + begin, SELF_UPDATE_ELF, end - begin))
        return -1;
    parts[0] = data; lengths[0] = begin;
    parts[1] = (const unsigned char *)boot_leaf; lengths[1] = strlen(boot_leaf);
    parts[2] = data + end; lengths[2] = size - end;
    for (i = 0; i < 3; i++) {
        for (written = 0; written < lengths[i]; written += count) {
            count = genWrite(fd, (void *)(parts[i] + written), lengths[i] - written);
            if (count <= 0 || count > lengths[i] - written)
                return -1;
        }
    }
    return lengths[0] + lengths[1] + lengths[2];
}

/* Extract one app file from a package already verified with
 * its GitHub SHA-256 and selfUpdateExtractPsu(). Do not call on an unchecked
 * archive or overwrite an existing staging filename. Legacy packages still
 * contain title.cfg, but return 0 for absent runtime sidecars. */
static int extract_psu_file(const char *package, const char *name,
                            const char *stage, int size, const char *boot_leaf)
{
    unsigned char directories[1536], entry[512], buffer[4096];
    int input = -1, output = -1, position = 1536, i, entries;
    int result = -1, created = 0;
    unsigned int length = 0;
    char remove_path[MAX_PATH];
    int is_ca = name != NULL && !strcmp(name, "WLE-UPDATE-CA.PEM");
    int is_bgm = name != NULL && !strcmp(name, "BGM.ADP");
    int is_title = name != NULL && !strcmp(name, "title.cfg");

    if ((!is_ca && !is_bgm && !is_title) || package == NULL || stage == NULL ||
        size < 1536 || size > 16 * 1024 * 1024)
        return -1;

    input = genOpen(package, FIO_O_RDONLY);
    if (input < 0 || genLseek(input, 0, SEEK_END) != size ||
        genLseek(input, 0, SEEK_SET) != 0 ||
        !read_exact(input, directories, sizeof(directories)))
        goto done;
    entries = (int)psu32(directories + 4);
    if (!record_is(directories, 0x8027, SELF_UPDATE_FOLDER) ||
        !record_is(directories + 512, 0x8027, ".") ||
        !record_is(directories + 1024, 0x8027, ".."))
        goto done;
    if (entries == 4 && !is_title) {
        result = 0; /* compatible, older package without sidecars */
        goto done;
    }
    if (entries != 4 && entries != 6)
        goto done;

    for (i = 0; i < entries - 2; i++) {
        unsigned int padded;
        if (position > size - 512 ||
            genLseek(input, position, SEEK_SET) != position ||
            !read_exact(input, entry, sizeof(entry)))
            goto done;
        position += 512;
        length = psu32(entry + 4);
        if (length == 0 || length > (unsigned int)(size - position))
            goto done;
        padded = (length + 1023u) & ~1023u;
        if (padded > (unsigned int)(size - position))
            goto done;
        if (record_is(entry, 0x8017, name)) {
            unsigned int remaining = length;
            if ((is_title && length > sizeof(buffer)) ||
                (is_ca && (length < sizeof("-----BEGIN CERTIFICATE-----") - 1 ||
                           length > 32768)) ||
                (is_bgm && (length < 32 || length > 1024 * 1024 ||
                            (length & 15))))
                goto done;
            output = genOpen(stage, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
            if (output < 0)
                goto done;
            created = 1;
            if (is_title) {
                if (!read_exact(input, buffer, length))
                    goto done;
                result = write_title(output, buffer, length, boot_leaf);
                if (result < 0)
                    goto done;
                remaining = 0;
            }
            while (remaining > 0) {
                int count = remaining > sizeof(buffer) ? sizeof(buffer) : remaining;
                int written = 0;
                if (!read_exact(input, buffer, count))
                    goto done;
                if (remaining == length &&
                    ((is_ca && memcmp(buffer, "-----BEGIN CERTIFICATE-----", 27)) ||
                     (is_bgm && memcmp(buffer, "APCM\x01\x01\x01\x00", 8))))
                    goto done;
                while (written < count) {
                    int n = genWrite(output, buffer + written, count - written);
                    if (n <= 0 || n > count - written)
                        goto done;
                    written += n;
                }
                remaining -= count;
            }
            if (genClose(output) < 0) {
                output = -1;
                result = -1;
                goto done;
            }
            output = -1;
            if (!is_title)
                result = (int)length;
            goto done;
        }
        position += padded;
    }
done:
    if (output >= 0)
        genClose(output);
    if (input >= 0 && genClose(input) < 0)
        result = -1;
    if (result < 0 && created) {
        snprintf(remove_path, sizeof(remove_path), "%s", stage);
        genRemove(remove_path);
    }
    return result;
}

int selfUpdateExtractPsuSidecar(const char *package, const char *name,
                                const char *stage, int size)
{
    if (name == NULL || (strcmp(name, "WLE-UPDATE-CA.PEM") && strcmp(name, "BGM.ADP")))
        return -1;
    return extract_psu_file(package, name, stage, size, NULL);
}

int selfUpdateExtractPsuTitle(const char *package, const char *stage, int size,
                              const char *boot_leaf)
{
    return extract_psu_file(package, "title.cfg", stage, size, boot_leaf);
}
