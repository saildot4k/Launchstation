#ifndef MMCE_PATH_H
#define MMCE_PATH_H

/* Firmware transports MMCE paths with a single u8 byte count including
 * NUL. Validate before narrowing size_t to u8, especially before write,
 * rename and remove commands. These helpers perform no device I/O. */
#include <stddef.h>

#define MMCE_FS_WIRE_NAME_MAX 254

static int mmce_fs_wire_name_ok(const char *name)
{
    size_t i;

    if (name == NULL || name[0] == '\0')
        return 0;
    for (i = 0; i < MMCE_FS_WIRE_NAME_MAX && name[i]; ++i)
        ;
    return name[i] == '\0';
}

#endif /* MMCE_PATH_H */
