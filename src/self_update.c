//--------------------------------------------------------------
// Native staged self-update for Launchstation.
//--------------------------------------------------------------
#include "launchelf.h"
#include "https_client.h"
#include "filer_shared.h"
#include "filer_actions.h"
#include "self_update.h"
#include "dash.h"

#include <ctype.h>

#define UPDATE_ELF_URL "https://github.com/" SELF_UPDATE_REPOSITORY "/releases/download/latest/" SELF_UPDATE_ASSET
#define UPDATE_MAX_ELF (16 * 1024 * 1024)
#define UPDATE_SPACE_MARGIN (100 * 1024)

/* Keep actual allocated space aside even on drivers with no free-space API.
 * All new files must fit alongside this reserve before any old file is deleted. */
static int reserve_update_space(const char *path)
{
    unsigned char zeros[4096] = {0};
    int fd, remaining = UPDATE_SPACE_MARGIN, ok = 1;

    fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_EXCL);
    if (fd < 0) return 0;
    while (remaining > 0) {
        int count = remaining > (int)sizeof(zeros) ? (int)sizeof(zeros) : remaining;
        int n = genWrite(fd, zeros, count);
        if (n <= 0 || n > count) { ok = 0; break; }
        remaining -= n;
    }
    if (genClose(fd) < 0) ok = 0;
    if (!ok) {
        char remove_path[MAX_PATH];
        snprintf(remove_path, sizeof(remove_path), "%s", path);
        genRemove(remove_path);
    }
    return ok;
}

static int device_path(const char *path, const char *name, int allow_bare)
{
    const char *p;
    size_t n;

    if (path == NULL || name == NULL)
        return 0;
    n = strlen(name);
    if (strncmp(path, name, n))
        return 0;
    p = path + n;
    if (allow_bare && *p == ':')
        return 1;
    if (!isdigit((unsigned char)*p))
        return 0;
    while (isdigit((unsigned char)*p))
        p++;
    return *p == ':';
}

static int supported_boot_path(const char *path)
{
    if (path == NULL || path[0] == '\0')
        return 0;

    /* Do not bake in mass0/mass1-style limits: BDM unit numbering depends on
     * attach order and the number of live devices. */
    return device_path(path, "mc", 0) ||
           device_path(path, "mass", 1) ||
           device_path(path, "usb", 1) ||
           device_path(path, "mmce", 0) ||
           device_path(path, "mx4sio", 0) ||
           device_path(path, "ata", 0) ||
           device_path(path, "hdd", 0);
}

static int split_parent_leaf(const char *path, char *parent, int parent_size,
                             char *leaf, int leaf_size)
{
    const char *slash, *colon;
    size_t n;

    if (path == NULL || parent == NULL || leaf == NULL ||
        parent_size <= 0 || leaf_size <= 0)
        return 0;

    slash = strrchr(path, '/');
    if (slash != NULL) {
        n = (size_t)(slash - path + 1);
        if (n >= (size_t)parent_size || strlen(slash + 1) >= (size_t)leaf_size)
            return 0;
        memcpy(parent, path, n);
        parent[n] = '\0';
        snprintf(leaf, leaf_size, "%s", slash + 1);
        return leaf[0] != '\0';
    }

    colon = strrchr(path, ':');
    if (colon == NULL)
        return 0;
    n = (size_t)(colon - path + 1);
    if (n >= (size_t)parent_size || strlen(colon + 1) >= (size_t)leaf_size)
        return 0;
    memcpy(parent, path, n);
    parent[n] = '\0';
    snprintf(leaf, leaf_size, "%s", colon + 1);
    return leaf[0] != '\0';
}

static int join_leaf(char *out, int out_size, const char *parent, const char *leaf)
{
    return snprintf(out, out_size, "%s%s", parent, leaf) < out_size;
}

static int find_file_info(const char *parent, const char *leaf, FILEINFO *out)
{
    char path[MAX_PATH], resolved[MAX_PATH];
    iox_stat_t stat;
    int ret;

    if (parent == NULL || leaf == NULL || out == NULL || !leaf[0])
        return -EINVAL;
    if (strlen(leaf) >= sizeof(out->name) ||
        !join_leaf(path, sizeof(path), parent, leaf))
        return -ENAMETOOLONG;
    if (genFixPath(path, resolved) < 0)
        return -ENODEV;

    /* Ask the filesystem to resolve the boot name, including FAT/exFAT case
     * aliases. A browser listing imposes exact spelling and needs a large
     * allocation just to recover the name of a file we already know. */
    ret = genGetStat(resolved, &stat);
    if (ret < 0)
        return ret;
    if (!FIO_S_ISREG(stat.mode))
        return FIO_S_ISDIR(stat.mode) ? -EISDIR : -EINVAL;
    memset(out, 0, sizeof(*out));
    snprintf(out->name, sizeof(out->name), "%s", leaf);
    out->stats.AttrFile = sceMcFileAttrFile;
    return 0;
}

static int rename_leaf(const char *parent, const char *old_leaf, const char *new_leaf)
{
    FILEINFO file;
    int ret = find_file_info(parent, old_leaf, &file);

    if (ret < 0)
        return ret;
    return Rename(parent, &file, new_leaf);
}

static int hex_nibble(int ch)
{
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

static int parse_expected_sha(const char *text, unsigned char expected[32])
{
    int i;

    if (text == NULL)
        return 0;
    if (!strncmp(text, "sha256:", 7))
        text += 7;
    if (strlen(text) != 64)
        return 0;

    for (i = 0; i < 32; i++) {
        int hi = hex_nibble((unsigned char)text[i * 2]);
        int lo = hex_nibble((unsigned char)text[i * 2 + 1]);
        if (hi < 0 || lo < 0)
            return 0;
        expected[i] = (unsigned char)((hi << 4) | lo);
    }
    return 1;
}

static void updateDownloadProgress(int done, int total, void *arg)
{
    (void)arg;
    if (total > 0)
        DashFileProgress("Downloading update", SELF_UPDATE_ASSET, total - done, total);
    else {
        char status[96];
        snprintf(status, sizeof(status), "Downloading update: %d KB received", done / 1024);
        DashStorageProbeStatus(status);
    }
}

static void updateCopyProgress(const char *name, int done, int total)
{
    DashFileProgress("Pasting update", name, total - done, total);
}

static int download_file(const char *url, const char *path, const char *ca_path,
                         int max_bytes, unsigned char digest[32],
                         char *error, int error_size)
{
    int fd, size = 0, r;

    fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
    if (fd < 0) {
        snprintf(error, error_size, "Could not create %.160s", path);
        return -1;
    }
    r = httpsDownloadFd(url, fd, ca_path, max_bytes, &size,
                            digest, updateDownloadProgress, NULL, error, error_size);
    if (genClose(fd) < 0 && r == 0) {
        snprintf(error, error_size, "Could not finalize %.160s", path);
        r = -1;
    }
    if (r < 0) {
        char remove_path[MAX_PATH];
        snprintf(remove_path, sizeof(remove_path), "%s", path);
        genRemove(remove_path);
        return -1;
    }
    return size;
}

#define UPDATE_ASSET_COUNT 8

static const char *update_asset_name(int index)
{
    static const char *const names[UPDATE_ASSET_COUNT] = {
        "title.cfg", "WLE-UPDATE-CA.PEM", "BGM.ADP", "icon.sys",
        "list.icn", "copy.icn", "del.icn", "APPINFO.PBT"
    };
    return names[index];
}

static int update_is_asset_name(const char *name)
{
    int i;
    for (i = 0; i < UPDATE_ASSET_COUNT; i++)
        if (!stricmp(name, update_asset_name(i))) return 1;
    return 0;
}

static int update_asset_paths(const char *parent, const char *name,
                               char *stage, char *stage_leaf)
{
    return snprintf(stage_leaf, MAX_NAME, "%s.UPDATE", name) < MAX_NAME &&
           join_leaf(stage, MAX_PATH, parent, stage_leaf);
}

static int publish_update_file(const char *parent, const char *name, const char *stage_leaf,
                                int *done, int total)
{
    char path[MAX_PATH], status[128];
    if (!join_leaf(path, sizeof(path), parent, name)) return -1;
    snprintf(status, sizeof(status), "Installing update: %s", name);
    DashStorageProgress(status, *done, total);
    if (wleExists(path) && genRemove(path) < 0 && wleExists(path)) return -1;
    if (rename_leaf(parent, stage_leaf, name) < 0) return -1;
    (*done)++;
    DashStorageProgress(status, *done, total);
    return 0;
}

static int install_update_files(const char *parent, const char *leaf,
                                 const char *ca_path, const char *expected_sha256,
                                 char *result, int result_size)
{
    char stage_leaf[MAX_NAME], stage[MAX_PATH], package_leaf[MAX_NAME], package[MAX_PATH];
    char asset_stage[MAX_PATH], asset_stage_leaf[MAX_NAME], folder_leaf[MAX_NAME];
    char error[256], remove_path[MAX_PATH];
    unsigned char expected[32], actual[32];
    int staged[UPDATE_ASSET_COUNT] = {0}, size, package_size, i, total = 1, done = 0;
    size_t end, begin;
    u64 free_bytes;

    if (snprintf(stage_leaf, sizeof(stage_leaf), "%s.UPDATE", leaf) >= (int)sizeof(stage_leaf) ||
        !join_leaf(stage, sizeof(stage), parent, stage_leaf) ||
        snprintf(package_leaf, sizeof(package_leaf), "%s.PACKAGE", leaf) >= (int)sizeof(package_leaf) ||
        !join_leaf(package, sizeof(package), parent, package_leaf)) {
        snprintf(result, result_size, "The running ELF path is too long for a staged update.");
        return -1;
    }
    /* Never truncate another attempt's download or recovery files. */
    if (wleExists(package) || wleExists(stage)) {
        snprintf(result, result_size,
                 "An earlier ELF .UPDATE or .PACKAGE file remains beside the app. Resolve it before retrying; no files were changed.");
        return -1;
    }
    for (i = 0; i < UPDATE_ASSET_COUNT; i++) {
        if (!update_asset_paths(parent, update_asset_name(i), asset_stage, asset_stage_leaf)) {
            snprintf(result, result_size, "The app folder path is too long for a staged asset update.");
            return -1;
        }
        if (wleExists(asset_stage)) {
            snprintf(result, result_size,
                     "An unfinished %s.UPDATE file remains. Resolve it before retrying; no files were changed.", update_asset_name(i));
            return -1;
        }
    }
    end = strlen(parent);
    while (end && parent[end - 1] == '/') end--;
    begin = end;
    while (begin && parent[begin - 1] != '/' && parent[begin - 1] != ':') begin--;
    if (end - begin >= sizeof(folder_leaf)) {
        snprintf(result, result_size, "The installed app folder name is too long.");
        return -1;
    }
    if (end > begin) {
        memcpy(folder_leaf, parent + begin, end - begin);
        folder_leaf[end - begin] = 0;
    } else snprintf(folder_leaf, sizeof(folder_leaf), "%s", SELF_UPDATE_FOLDER);

    if (!parse_expected_sha(expected_sha256, expected)) {
        snprintf(result, result_size, "GitHub did not provide a valid SHA-256 digest for the app package.");
        return -1;
    }
    error[0] = '\0';
    DashStorageProbeStatus("Downloading update package from GitHub");
    size = download_file(UPDATE_ELF_URL, package, ca_path, UPDATE_MAX_ELF,
                         actual, error, sizeof(error));
    if (size <= 0) {
        snprintf(result, result_size, "Update download failed: %s",
                 error[0] ? error : "no update data was received");
        return -1;
    }
    DashStorageProbeStatus("Verifying package SHA-256");
    if (memcmp(expected, actual, sizeof(expected)) != 0) {
        snprintf(result, result_size, "Downloaded update failed SHA-256 verification. Installed files were not changed.");
        goto discard_package;
    }
    package_size = size;
    DashStorageProbeStatus("Checking space for replacement files plus 100 KB");
    if (filerFreeSpace(parent, &free_bytes) && free_bytes < (u64)package_size) {
        snprintf(result, result_size,
                 "Not enough free space: need up to %d KB for replacement files, plus the reserved 100 KB. Installed files were not changed.",
                 (package_size + 1023) / 1024);
        goto discard_package;
    }
    DashStorageProbeStatus("Preparing and validating the new executable");
    size = selfUpdateExtractPsu(package, stage, package_size);
    if (size <= 0 || checkELFheader(stage) < 0) {
        snprintf(result, result_size, "The verified package does not contain a valid app ELF. Installed files were not changed.");
        goto discard_package;
    }
    /* Stage every release asset before replacing anything. Old 2-/4-file
     * packages return zero for absent assets and leave those files untouched. */
    for (i = 0; i < UPDATE_ASSET_COUNT; i++) {
        int extracted;
        const char *name = update_asset_name(i);
        update_asset_paths(parent, name, asset_stage, asset_stage_leaf);
        if (i == 0)
            extracted = selfUpdateExtractPsuTitle(package, asset_stage, package_size, leaf);
        else if (!strcmp(name, "APPINFO.PBT"))
            extracted = selfUpdateExtractPsuAppInfo(package, asset_stage, package_size, leaf, folder_leaf);
        else
            extracted = selfUpdateExtractPsuSidecar(package, name, asset_stage, package_size);
        if (extracted < 0 || (i == 0 && extracted == 0)) {
            snprintf(result, result_size, "Failed to prepare %s. Installed files were not changed.", name);
            goto discard_package;
        }
        staged[i] = extracted > 0;
        total += staged[i];
    }
    snprintf(remove_path, sizeof(remove_path), "%s", package);
    genRemove(remove_path);

    /* Publish assets first, then the ELF and its title metadata. All replacements
     * have finished writing; keep uncommitted stages if a rename/delete fails. */
    for (i = 1; i < UPDATE_ASSET_COUNT; i++) {
        if (!staged[i]) continue;
        update_asset_paths(parent, update_asset_name(i), asset_stage, asset_stage_leaf);
        if (publish_update_file(parent, update_asset_name(i), asset_stage_leaf, &done, total) < 0)
            goto install_failed;
    }
    if (publish_update_file(parent, leaf, stage_leaf, &done, total) < 0 ||
        publish_update_file(parent, "title.cfg", "title.cfg.UPDATE", &done, total) < 0)
        goto install_failed;
    snprintf(result, result_size,
             "Update installed and verified (%d bytes). Refreshed %d app files.",
             size, total);
    return 0;

install_failed:
    snprintf(result, result_size,
             "Could not finish replacing the app files. No backup was created. Keep any remaining .UPDATE files beside the app and finish copying them into place before restarting.");
    return -1;

discard_package:
    snprintf(remove_path, sizeof(remove_path), "%s", package);
    genRemove(remove_path);
    snprintf(remove_path, sizeof(remove_path), "%s", stage);
    genRemove(remove_path);
    for (i = 0; i < UPDATE_ASSET_COUNT; i++) {
        if (!staged[i]) continue;
        update_asset_paths(parent, update_asset_name(i), asset_stage, asset_stage_leaf);
        snprintf(remove_path, sizeof(remove_path), "%s", asset_stage);
        genRemove(remove_path);
    }
    return -1;
}

int selfUpdateInstall(const char *ca_path, const char *expected_sha256, char *result, int result_size)
{
    const char *boot = wleBootElfPath();
    char parent[MAX_PATH], leaf[MAX_NAME], reserve[MAX_PATH];
    sceMcStDateTime sas_timestamp;
    char warning[128];
    int preserve_sas, installed, timestamp_result;
    size_t prefix, kept;

    if (result == NULL || result_size <= 0)
        return -1;
    result[0] = '\0';
    if (!supported_boot_path(boot)) {
        snprintf(result, result_size,
                 "This boot location cannot be updated safely in place: %.160s",
                 boot != NULL ? boot : "(unknown)");
        return -1;
    }
    if (!split_parent_leaf(boot, parent, sizeof(parent), leaf, sizeof(leaf)) ||
        update_is_asset_name(leaf) ||
        !join_leaf(reserve, sizeof(reserve), parent, "WLE-UPDATE.SPACE")) {
        snprintf(result, result_size, "Could not resolve the running ELF path safely.");
        return -1;
    }
    if (!ensurePathDeviceStackReady(parent)) {
        snprintf(result, result_size, "The running ELF device is not writable right now.");
        return -1;
    }
    /* Read before the first reservation/download write changes the folder date.
     * Restore after every transaction outcome and all temporary-file cleanup. */
    preserve_sas = filerCaptureSasTimestamp(parent, &sas_timestamp);
    if (preserve_sas < 0) {
        snprintf(result, result_size,
                 "Could not read the app folder timestamp (error %d). No update files were changed.",
                 preserve_sas);
        return -1;
    }
    DashStorageProbeStatus("Checking free space and reserving 100 KB");
    if (wleExists(reserve)) {
        snprintf(result, result_size,
                 "An earlier WLE-UPDATE.SPACE file remains. Remove it before retrying. Installed files were not changed.");
        installed = -1;
    } else if (!reserve_update_space(reserve)) {
        snprintf(result, result_size,
                 "Could not reserve 100 KB of extra free space. Installed files were not changed.");
        installed = -1;
    } else {
        selfUpdateSetProgressCallback(updateCopyProgress);
        installed = install_update_files(parent, leaf, ca_path, expected_sha256,
                                         result, result_size);
        selfUpdateSetProgressCallback(NULL);
        if (genRemove(reserve) < 0 && wleExists(reserve)) {
            size_t used = strlen(result);
            snprintf(result + used, result_size - used,
                     " Remove WLE-UPDATE.SPACE to release the 100 KB reserve.");
        }
    }
    if (preserve_sas > 0) {
        timestamp_result = filerRestoreSasTimestamp(parent, &sas_timestamp);
        if (timestamp_result != 0) {
            snprintf(warning, sizeof(warning),
                     "Could not restore the app folder SAS date (error %d); run SAS timestamps again.\n",
                     timestamp_result);
            /* Keep this warning visible even if the transaction message filled
             * the caller's buffer; retain as much recovery detail as fits. */
            prefix = strlen(warning);
            if (prefix > (size_t)result_size - 1)
                prefix = result_size - 1;
            kept = strlen(result);
            if (kept > (size_t)result_size - prefix - 1)
                kept = result_size - prefix - 1;
            memmove(result + prefix, result, kept);
            memcpy(result, warning, prefix);
            result[prefix + kept] = '\0';
        }
    }
    return installed;
}
