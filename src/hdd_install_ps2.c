#include "launchelf.h"
#include "hdd_install.h"
#include "https_client.h"
#include "install_archive.h"
#include "save_archive.h"
#include "save_sign.h"
#include "hdd_header_injector.h"
#include "dash_internal.h"
#include "hdd_install_recovery.h"
#include "hdd_install_resume.h"

#include <time.h>
#define EXTRAS_URL "https://archive.org/download/psbbn-definitive-english-patch-v2/extras.zip"
/* Immutable archive referenced by DP's HOSDMenu-Installer.sh. Recorded from
 * https://archive.org/metadata/psbbn-definitive-english-patch-v2 . */
#define EXTRAS_SIZE 5034301u
#define EMBER_DEP_URL "https://archive.org/download/psbbn-definitive-project-dependencies/dep.zip"

static const char *const app_folders[] = {"APP_WLE-R3Z", "SYS_R3CONFIGURATOR"};
static const char *const app_boot[] = {"WLE-R3Z.ELF", "r3configurator.elf"};
static const char *const app_names[] = {"wLaunchELF-R3Z", "R3CONFIGURATOR"};
static const char *const app_partitions[] = {"PP.APP_WLE-R3Z", "PP.SYS_R3CONFIGURATOR"};

static int makeDirectory(const char *path, int visible);
static int makeParents(char *path);

static int pathJoin(char *out, size_t capacity, const char *parent, const char *leaf)
{
    size_t n = strlen(parent);
    return snprintf(out, capacity, "%s%s%s", parent, n && parent[n - 1] == '/' ? "" : "/", leaf) < (int)capacity ? 0 : -ENAMETOOLONG;
}
static int readAll(int fd, void *data, unsigned size)
{
    unsigned done = 0;
    while (done < size) {
        int n = genRead(fd, (unsigned char *)data + done, size - done);
        if (n <= 0 || (unsigned)n > size - done) return n < 0 ? n : -EIO;
        done += n;
    }
    return 0;
}
static int writeAll(int fd, const void *data, unsigned size)
{
    unsigned done = 0;
    while (done < size) {
        int n = genWrite(fd, (void *)((const unsigned char *)data + done), size - done);
        if (n <= 0 || (unsigned)n > size - done) return n < 0 ? n : -EIO;
        done += n;
    }
    return 0;
}
static int closeResult(int fd, int result)
{
    if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
    int closed = genClose(fd);
    return result < 0 ? result : closed < 0 ? closed : 0;
}
void hddInstallRelease(HddInstall *in)
{
    free(in->ca_data); in->ca_data = NULL; in->ca_size = 0;
    free(in->launcher_files); in->launcher_files = NULL; in->launcher_count = 0;
}
int hddInstallLoadCa(HddInstall *in)
{
    s64 size;
    int fd, ret;
    free(in->ca_data); in->ca_data = NULL; in->ca_size = 0;
    hddInstallLog("Reading CA bundle: %s", in->ca_path);
    fd = genOpen(in->ca_path, FIO_O_RDONLY);
    if (fd < 0) return fd;
    size = genLseek(fd, 0, SEEK_END);
    if (size <= 0 || size > 256 * 1024 || genLseek(fd, 0, SEEK_SET) != 0) return closeResult(fd, -EINVAL);
    in->ca_data = malloc((unsigned)size);
    if (!in->ca_data) return closeResult(fd, -ENOMEM);
    ret = closeResult(fd, readAll(fd, in->ca_data, (unsigned)size));
    if (ret < 0) { free(in->ca_data); in->ca_data = NULL; return ret; }
    in->ca_size = (unsigned)size;
    hddInstallLog("CA snapshot ready: %u bytes in EE memory", in->ca_size);
    return 0;
}
int hddInstallMountStage(HddInstall *in)
{ (void)in; return fileXioMount("pfs2:", "hdd0:__common", FIO_MT_RDWR); }
int hddInstallUnmountStage(HddInstall *in)
{ (void)in; return hddInstallRecoveryFault() ? HDD_INSTALL_ATA_TIMEOUT : fileXioUmount("pfs2:"); }
int hddInstallCreateStage(HddInstall *in)
{
    char path[MAX_PATH];
    int fd, ret;
    if (!in->ca_data || !in->ca_size || !in->stage[0]) return -EINVAL;
    /* Freshly formatted storage: refuse an existing directory rather than
     * overwrite unknown contents after a failed/changed workflow. */
    hddInstallLog("Creating download folder: %s", in->stage);
    ret = in->owned && (in->recovery_attempts || in->resumed) ? hddInstallFindStage(in) : genMkdir(in->stage, 0777);
    hddInstallLog("mkdir download folder rc=%d", ret);
    if (ret < 0) return ret;
    ret = in->owned && (in->recovery_attempts || in->resumed) ? 0 : hddInstallClaimStage(in);
    if (ret < 0) { genRmdir(in->stage); return ret; }
    if (pathJoin(path, sizeof(path), in->stage, "INSTALL_CA.PEM") < 0) return -ENAMETOOLONG;
    fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | ((in->recovery_attempts || in->resumed) ? FIO_O_TRUNC : FIO_O_EXCL));
    if (fd < 0) return fd;
    ret = closeResult(fd, writeAll(fd, in->ca_data, in->ca_size));
    if (ret >= 0) {
        if (strlen(path) >= sizeof(in->ca_path)) return -ENAMETOOLONG;
        strcpy(in->ca_path, path); in->stage_ready = 1; hddInstallRelease(in);
    }
    hddInstallLog("CA copy to %s rc=%d", path, ret);
    hddInstallLogFlush(in);
    return ret < 0 ? ret : hddInstallResumeSave(in);
}
static int checkFileSize(HddInstall *in, const char *name, uint32_t size)
{
    char path[MAX_PATH];
    int fd;
    if (pathJoin(path, sizeof(path), in->stage, name) < 0) return -ENAMETOOLONG;
    fd = genOpen(path, FIO_O_RDONLY);
    if (fd < 0) return fd;
    return closeResult(fd, genLseek(fd, 0, SEEK_END) == size ? 0 : -EIO);
}
static int launcherStageName(const char *source, char name[192])
{
    static const struct { const char *remote, *local; } roots[] = {
        {"scripts/assets/Ember/", "Ember/"}, {"scripts/assets/OPL/", "OPL/"}, {"scripts/assets/NHDDL/", "NHDDL/"},
        {"scripts/assets/neutrino/", "Neutrino/"}, {"icons/", "Icons/"},
        {"scripts/licenses/", "Licenses/"}
    };
    for (unsigned i = 0; i < sizeof(roots) / sizeof(roots[0]); i++) {
        size_t n = strlen(roots[i].remote);
        if (strncmp(source, roots[i].remote, n)) continue;
        const char *relative = source + n;
        if (!*relative || strspn(relative, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-/") != strlen(relative)) return -EINVAL;
        for (const char *p = relative; *p;) {
            const char *end = strchr(p, '/'); size_t length = end ? (size_t)(end - p) : strlen(p);
            if (!length || (length == 1 && *p == '.') || (length == 2 && !memcmp(p, "..", 2)) || (end && !end[1])) return -EINVAL;
            p += length + !!end;
        }
        return snprintf(name, 192, "%s%s", roots[i].local, relative) < 192 ? 0 : -ENAMETOOLONG;
    }
    return -EINVAL;
}
/* Only used to adopt/clean caches from builds with numbered staging files. */
static void legacyLauncherStageName(unsigned index, char name[32])
{ snprintf(name, 32, "launcher-%03u.bin", index); }
static int findLauncher(const HddInstall *in, const char *path)
{
    for (unsigned i = 0; i < in->launcher_count; i++) if (!strcmp(in->launcher_files[i].path, path)) return (int)i;
    return -ENOENT;
}
static const char *launcherIcon(const HddInstall *in)
{ return in->game_launcher >= HDD_GAME_RIPTOPL ? "icons/ico/APP_RIPTOPL_LST.ico" : in->game_launcher == HDD_GAME_NEUTRINO ? "icons/ico/APP_NHDDL_LST.ico" : "icons/ico/APP_OPL_LST.ico"; }
static const char *launcherArt(const HddInstall *in)
{ return in->game_launcher >= HDD_GAME_RIPTOPL ? "icons/art/APP_RIPTOPL.png" : in->game_launcher == HDD_GAME_NEUTRINO ? "icons/art/APP_NHDDL.png" : "icons/art/APP_OPL.png"; }
static const char *const launcher_required[] = {
        "scripts/assets/OPL/OPNPS2LD.ELF", "scripts/assets/NHDDL/nhddl.elf", "scripts/assets/neutrino/neutrino.elf",
        "scripts/assets/neutrino/config/system.toml", "scripts/assets/neutrino/version.txt",
        "scripts/assets/OPL/version.txt", "scripts/assets/NHDDL/version.txt",
        "scripts/licenses/OPL", "scripts/licenses/nhddl", "scripts/licenses/neutrino"
};
static const char *const riptopl_required[] = {
    "scripts/assets/OPL/RIPTOPL-RA-UNPAKT.ELF", "scripts/assets/Ember/ember.elf", "scripts/assets/neutrino/neutrino.elf",
    "scripts/assets/Ember/version.txt", "scripts/assets/OPL/version.txt", "scripts/assets/neutrino/version.txt",
    "scripts/assets/neutrino/config/system.toml", "scripts/licenses/EMBER-LICENSE-BETA.txt",
    "scripts/licenses/RiptOPL.txt", "scripts/licenses/neutrino.txt"
};
static int launcherManifest(HddInstall *in)
{
    if (!in->launcher_files || !in->launcher_count || in->launcher_count > HDD_INSTALL_LAUNCHER_FILES ||
        in->game_launcher > HDD_GAME_RIPTOPL_NEUTRINO) return -EINVAL;
    const char *const *required = in->game_launcher >= HDD_GAME_RIPTOPL ? riptopl_required : launcher_required;
    unsigned count = in->game_launcher >= HDD_GAME_RIPTOPL ? sizeof(riptopl_required) / sizeof(*riptopl_required) : sizeof(launcher_required) / sizeof(*launcher_required);
    for (unsigned i = 0; i < count; i++) {
        int index = findLauncher(in, required[i]);
        if (index < 0 || !in->launcher_files[index].size) {
            hddInstallLog("Missing/empty launcher asset: %s", required[i]); return -ENOENT;
        }
    }
    if (findLauncher(in, launcherIcon(in)) < 0 || findLauncher(in, launcherArt(in)) < 0) return -ENOENT;
    return 0;
}
static int checkLaunchers(HddInstall *in)
{
    int ready;
    if (!(in->flags & HDD_INSTALL_PSBBN)) return 0;
    ready = launcherManifest(in); if (ready < 0) return ready;
    for (unsigned i = 0; i < in->launcher_count; i++) {
        char name[192]; int ret = launcherStageName(in->launcher_files[i].path, name);
        if (ret < 0) return ret;
        ret = checkFileSize(in, name, in->launcher_files[i].size);
        if (ret < 0) return ret;
        if (!strcmp(in->launcher_files[i].path, launcher_required[0]) || !strcmp(in->launcher_files[i].path, launcher_required[1]) ||
            !strcmp(in->launcher_files[i].path, launcher_required[2]) ||
            !strcmp(in->launcher_files[i].path, riptopl_required[0]) || !strcmp(in->launcher_files[i].path, riptopl_required[1])) {
            char path[MAX_PATH]; unsigned char header[52]; int fd;
            if (in->launcher_files[i].size < sizeof(header) || pathJoin(path, sizeof(path), in->stage, name) < 0) return -EINVAL;
            fd = genOpen(path, FIO_O_RDONLY); if (fd < 0) return fd;
            ret = closeResult(fd, readAll(fd, header, sizeof(header)));
            if (ret < 0) return ret;
            if (memcmp(header, "\x7f" "ELF\x01\x01", 6) || header[18] != 8) return -EINVAL;
        }
    }
    return 0;
}
static int safeLeaf(const char *name)
{
    if (!name || !*name || !strcmp(name, ".") || !strcmp(name, "..")) return 0;
    for (; *name; name++) if ((unsigned char)*name < 32 || strchr("/\\:", *name)) return 0;
    return 1;
}
static int loadApp(HddInstall *in, unsigned index, SaveArchive *save, uint8_t **data)
{
    char path[MAX_PATH];
    int fd, ret, boot = 0, title = 0, icon = 0;
    unsigned asset = index ? HI_R3CONFIG : HI_WLE;
    memset(save, 0, sizeof(*save)); *data = NULL;
    if (pathJoin(path, sizeof(path), in->stage, hddInstallAssetName(asset)) < 0) return -ENAMETOOLONG;
    *data = malloc(in->sizes[asset]);
    if (!*data) return -ENOMEM;
    fd = genOpen(path, FIO_O_RDONLY);
    if (fd < 0) { free(*data); *data = NULL; return fd; }
    ret = closeResult(fd, readAll(fd, *data, in->sizes[asset]));
    if (ret < 0 || !saveArchiveParse(save, *data, in->sizes[asset], path) ||
        save->ps1 || strcmp(save->folder.name, app_folders[index])) goto invalid;
    for (unsigned i = 0; i < save->count; i++) {
        SaveArchiveEntry *entry = &save->files[i];
        if (!safeLeaf(entry->name)) goto invalid;
        for (unsigned j = 0; j < i; j++) if (!strcmp(entry->name, save->files[j].name)) goto invalid;
        if (!strcmp(entry->name, app_boot[index]))
            boot = entry->size >= 52 && !memcmp(entry->data, "\x7f" "ELF\x01\x01", 6) && entry->data[18] == 8;
        if (!strcmp(entry->name, "title.cfg")) title = entry->size > 0 && entry->size <= 16384;
        if (!strcmp(entry->name, "list.icn")) icon = entry->size > 0 && entry->size < 1024 * 1024;
    }
    if (boot && title && icon) return 0;
invalid:
    saveArchiveFree(save); free(*data); *data = NULL;
    return ret < 0 ? ret : -EINVAL;
}

typedef struct { int input, output; } ZipContext;
static int zipRead(void *ctx, uint32_t offset, void *data, unsigned size)
{
    ZipContext *z = ctx;
    if (genLseek(z->input, offset, SEEK_SET) != offset) return -EIO;
    return readAll(z->input, data, size);
}
static int zipWrite(void *ctx, const void *data, unsigned size)
{
    ZipContext *z = ctx;
    return z->output < 0 ? 0 : writeAll(z->output, data, size);
}
static int osdResources(HddInstall *in, const char *destination)
{
    char path[MAX_PATH], entry[128];
    ZipContext ctx = {-1, -1};
    InstallArchiveIo io = {&ctx, zipRead, zipWrite};
    int ret;
    if (pathJoin(path, sizeof(path), in->stage, "extras.zip") < 0) return -ENAMETOOLONG;
    ctx.input = genOpen(path, FIO_O_RDONLY);
    if (ctx.input < 0) return ctx.input;
    for (unsigned i = 0; i < 7; i++) {
        if (destination) {
            if (pathJoin(path, sizeof(path), destination, hddInstallOsdFiles[i]) < 0) { ret = -ENAMETOOLONG; goto done; }
            ctx.output = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | (in->owned && (in->recovery_attempts || in->resumed) ? FIO_O_TRUNC : FIO_O_EXCL));
            if (ctx.output < 0) { ret = ctx.output; goto done; }
        }
        snprintf(entry, sizeof(entry), "extras/%s", hddInstallOsdFiles[i]);
        hddInstallStatus(destination ? "Installing HDD-OSD resources" : "Checking HDD-OSD resources", i, 7);
        ret = installZipExtract(&io, in->sizes[HI_EXTRAS], entry, 4u * 1024 * 1024, NULL);
        if (ctx.output >= 0) { ret = closeResult(ctx.output, ret); ctx.output = -1; }
        if (ret < 0) { if (destination) genRemove(path); goto done; }
    }
    ret = 0;
done:
    return closeResult(ctx.input, ret);
}

#if defined(ETH) && defined(WLE_NATIVE_HTTPS)
typedef struct { const char *name; uint64_t completed, total; unsigned expected; } InstallTransfer;
static uint64_t downloadBytes(const HddInstall *in)
{
    uint64_t total = 0;
    for (unsigned i = 0; i < HDD_INSTALL_ASSETS; i++) if (hddInstallSelectedAsset(in, i)) total += in->sizes[i];
    for (unsigned i = 0; i < in->launcher_count; i++) total += in->launcher_files[i].size;
    return total;
}
static int prepareLauncherStage(HddInstall *in)
{
    unsigned moved = 0;
    for (unsigned i = 0; i < in->launcher_count; i++) {
        char name[192], local[MAX_PATH], old[32], previous[MAX_PATH];
        int ret = launcherStageName(in->launcher_files[i].path, name);
        if (ret < 0) return ret;
        ret = pathJoin(local, sizeof(local), in->stage, name); if (ret < 0) return ret;
        ret = makeParents(local); if (ret < 0) return ret;
        if (!in->owned || !(in->resumed || in->recovery_attempts) || i >= in->downloaded_launchers) continue;
        if (checkFileSize(in, name, in->launcher_files[i].size) == 0) continue;
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        legacyLauncherStageName(i, old);
        if (checkFileSize(in, old, in->launcher_files[i].size) < 0) {
            if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
            continue;
        }
        ret = pathJoin(previous, sizeof(previous), in->stage, old); if (ret < 0) return ret;
        ret = genRemove(local); if (ret < 0 && ret != -ENOENT) return ret;
        ret = fileXioRename(previous, local); if (ret < 0) return ret;
        moved++;
    }
    if (moved) hddInstallLog("Reorganized %u cached launcher files into app folders", moved);
    return 0;
}
/* Cached archives are streamed directly to their final filesystems. Only
 * compressed downloads, runtimes, journals and diagnostics occupy __common. */
static int stageSpace(HddInstall *in)
{
    int zones = fileXioDevctl("pfs2:", PDIOC_ZONEFREE, NULL, 0, NULL, 0);
    if (zones < 0) return zones;
    int zone_size = fileXioDevctl("pfs2:", PDIOC_ZONESZ, NULL, 0, NULL, 0);
    if (zone_size <= 0) return zone_size < 0 ? zone_size : -EIO;
    uint64_t needed = 4u * 1024 * 1024; /* Journal, log and inode headroom. */
    for (unsigned i = 0; i < HDD_INSTALL_ASSETS; i++) {
        if (!hddInstallSelectedAsset(in, i)) continue;
        if ((in->downloaded_assets & (1u << i)) && checkFileSize(in, hddInstallAssetName(i), in->sizes[i]) == 0) continue;
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        needed += ((uint64_t)in->sizes[i] + zone_size - 1) / zone_size * zone_size;
    }
    for (unsigned i = 0; i < in->launcher_count; i++) {
        char name[192]; int ret = launcherStageName(in->launcher_files[i].path, name);
        if (ret < 0) return ret;
        if (i < in->downloaded_launchers && checkFileSize(in, name, in->launcher_files[i].size) == 0) continue;
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        needed += ((uint64_t)in->launcher_files[i].size + zone_size - 1) / zone_size * zone_size;
    }
    uint64_t available = (uint64_t)zones * zone_size;
    hddInstallLog("PFS cache space: %llu bytes free; %llu bytes required", (unsigned long long)available, (unsigned long long)needed);
    if (needed <= available) return 0;
    snprintf(in->error, sizeof(in->error), "__common has %u MiB free; the remaining installer downloads need %u MiB. The HDD is formatted; installation is incomplete.",
             (unsigned)(available / (1024 * 1024)), (unsigned)((needed + 1024 * 1024 - 1) / (1024 * 1024)));
    return -ENOSPC;
}
static void transferProgress(int done, int total, void *context)
{
    InstallTransfer *transfer = context;
    (void)total; /* Repository metadata supplies a size even for chunked HTTP. */
    hddInstallProgress(transfer->name, done, transfer->expected);
    hddInstallOverall(transfer->completed + (unsigned)done, transfer->total);
}
/* Three file attempts: wait 2s before each retry. Reopen with TRUNC before retrying
 * a partial body; never append new bytes to an interrupted response. */
static int downloadFile(HddInstall *in, const char *url, const char *name,
                        uint32_t expected, InstallTransfer *transfer)
{
    char path[MAX_PATH];
    int ret = pathJoin(path, sizeof(path), in->stage, name);
    if (ret < 0) return ret;
    for (unsigned attempt = 1; attempt <= 3; attempt++) {
        int size = 0, retryable = 0, closed;
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        in->error[0] = 0;
        int fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT |
                        ((attempt > 1 || in->recovery_attempts || in->resumed) ? FIO_O_TRUNC : FIO_O_EXCL));
        if (fd < 0) {
            snprintf(in->error, sizeof(in->error), "Could not open download file (error %d).", fd);
            return fd;
        }
        ret = 0;
        if (expected) {
            ret = httpsDownloadFd(url, fd, in->ca_path, expected, &size, NULL,
                                  transferProgress, transfer, in->error, sizeof(in->error));
            retryable = ret < 0 && httpsFailureRetryable();
        }
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        closed = genClose(fd);
        hddInstallLog("DOWNLOAD attempt %u/3 rc=%d bytes=%d expected=%u", attempt, ret, size, (unsigned)expected);
        if (closed < 0) {
            snprintf(in->error, sizeof(in->error), "Could not close download file (error %d).", closed);
            return closed;
        }
        if (ret >= 0) {
            if ((uint32_t)size == expected) return 0;
            snprintf(in->error, sizeof(in->error), "Downloaded file has %d bytes; expected %u.", size, (unsigned)expected);
            return -EIO;
        }
        if (!retryable || attempt == 3) return ret;
        unsigned delay = 2;
        hddInstallLog("DOWNLOAD retry %u/3 in %u s: %s; %s", attempt + 1, delay, name, in->error);
        hddInstallLogFlush(in);
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        for (unsigned seconds = delay; seconds; seconds--) {
            char status[160];
            snprintf(status, sizeof(status), "Retry %u/3 in %u s: %.110s", attempt + 1, seconds, name);
            hddInstallProgress(status, 0, 0);
            DelayThread(1000000);
        }
    }
    return ret;
}
static int request(HddInstall *in, const char *path, HttpsResponse *response)
{
    const char headers[] = "User-Agent: Launchstation-PS2\r\nAccept: application/vnd.github+json\r\n";
    int ret;
    memset(response, 0, sizeof(*response));
    hddInstallLog("GET https://api.github.com%s", path);
    hddInstallLogFlush(in);
    ret = httpsRequest("GET", "api.github.com", path, headers, NULL, 0, in->ca_path,
                       response, in->error, sizeof(in->error));
    hddInstallLog("GitHub response: rc=%d HTTP=%d body=%d bytes", ret, response->status, response->body_len);
    hddInstallLogFlush(in);
    if (ret < 0 || response->status != 200 || !response->body) {
        if (ret >= 0) snprintf(in->error, sizeof(in->error), "GitHub returned HTTP %d. Try again later.", response->status);
        httpsResponseFree(response); return ret < 0 ? ret : -EIO;
    }
    return 0;
}
static int upstreamText(HddInstall *in, const char *file, HttpsResponse *response)
{
    char path[256]; int ret;
    memset(response, 0, sizeof(*response));
    snprintf(path, sizeof(path), "/" HDD_INSTALL_REPOSITORY "/%s/%s", in->commit, file);
    ret = httpsRequest("GET", "raw.githubusercontent.com", path, NULL, NULL, 0,
                       in->ca_path, response, in->error, sizeof(in->error));
    if (ret < 0 || response->status != 200 || !response->body) {
        httpsResponseFree(response); return ret < 0 ? ret : -EIO;
    }
    return 0;
}
static int archiveMetadata(HddInstall *in, HttpsResponse *response)
{
    char path[128]; int ret;
    memset(response, 0, sizeof(*response));
    if (!in->archive_item[0]) return -EINVAL;
    snprintf(path, sizeof(path), "/metadata/%s", in->archive_item);
    hddInstallLog("GET https://archive.org%s", path);
    ret = httpsRequest("GET", "archive.org", path, NULL, NULL, 0,
                       in->ca_path, response, in->error, sizeof(in->error));
    if (ret < 0 || response->status != 200 || !response->body) {
        httpsResponseFree(response); return ret < 0 ? ret : -EIO;
    }
    return 0;
}
int hddInstallLanguageChoices(HddInstall *in, HddInstallLanguage *languages, unsigned capacity)
{
    HttpsResponse response = {0}, script = {0}, english = {0};
    char prefix[32], name[128], hash[41]; uint32_t size;
    int ret, count, available = 0;
    /* The CA source can have been unmounted by network preparation. */
    httpsSetCaBundle(in->ca_data, in->ca_size);
    hddInstallStatus("Reading supported PSBBN languages", 0, 0);
    ret = request(in, HDD_INSTALL_API "/git/ref/heads/main", &response);
    if (ret >= 0 && !hddInstallCommit(response.body, in->commit)) ret = -EINVAL;
    httpsResponseFree(&response);
    if (ret >= 0) ret = upstreamText(in, "scripts/PSBBN-Installer.sh", &script);
    if (ret >= 0) ret = upstreamText(in, "scripts/assets/lang/eng.txt", &english);
    if (ret >= 0 && !hddInstallArchiveItem(script.body, in->archive_item)) ret = -EINVAL;
    if (ret >= 0) ret = hddInstallLanguages(script.body, english.body, languages, capacity);
    count = ret;
    httpsResponseFree(&script); httpsResponseFree(&english);
    if (ret >= 0) ret = archiveMetadata(in, &response);
    if (ret >= 0) {
        for (int i = 0; i < count; i++) {
            snprintf(prefix, sizeof(prefix), "language-pak-%s-v", languages[i].code);
            if (!hddInstallArchiveMetadata(response.body, prefix, name, hash, &size)) continue;
            if (!strcmp(languages[i].code, "jpn") &&
                !hddInstallArchiveMetadata(response.body, "channels-jpn-v", name, hash, &size)) continue;
            languages[available++] = languages[i];
        }
        ret = available ? available : -ENOENT;
    }
    httpsResponseFree(&response);
    if (ret < 0 && !in->error[0]) snprintf(in->error, sizeof(in->error), "Could not read supported PSBBN languages (error %d). The HDD has not been changed.", ret);
    httpsSetCaBundle(NULL, 0);
    return ret;
}
typedef struct {
    HddInstall *in;
    char dirs[16][192];
    unsigned count, current;
    uint32_t bytes;
} LauncherListing;
static int collectLauncher(void *context, const char *name, const char *hash, uint32_t size, int directory)
{
    LauncherListing *list = context;
    HddInstall *in = list->in;
    HddInstallFile *file;
    char path[192];
    const char *parent = list->dirs[list->current];
    if (name[0] == '.') return 0; /* Same hidden-file exclusion as DP's rsync. */
    if (snprintf(path, sizeof(path), "%s/%s", parent, name) >= (int)sizeof(path)) return -ENAMETOOLONG;
    if (!strncmp(parent, "icons/", 6)) {
        if (directory || (strcmp(path, launcherIcon(in)) && strcmp(path, launcherArt(in)))) return 0;
    } else if (!strcmp(parent, "scripts/licenses")) {
        if (directory || (strcmp(name, "OPL") && strcmp(name, "neutrino") && strcmp(name, "nhddl") &&
                          strcmp(name, "RiptOPL.txt") && strcmp(name, "neutrino.txt") && strcmp(name, "EMBER-LICENSE-BETA.txt"))) return 0;
    }
    /* These commit-pinned runtime trees use URL-safe names. Never follow
     * server-provided download URLs, symlinks or arbitrary repository roots. */
    if (strspn(name, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-") != strlen(name)) return -EINVAL;
    if (directory) {
        if (list->count >= 16) return -E2BIG;
        for (unsigned i = 0; i < list->count; i++) if (!strcmp(list->dirs[i], path)) return -EINVAL;
        strcpy(list->dirs[list->count++], path); return 0;
    }
    if (in->launcher_count >= HDD_INSTALL_LAUNCHER_FILES || list->bytes > 64u * 1024 * 1024 - size ||
        findLauncher(in, path) >= 0) return -EINVAL;
    file = &in->launcher_files[in->launcher_count++];
    strcpy(file->path, path); strcpy(file->hash, hash); file->size = size; list->bytes += size;
    return 0;
}
static int launcherMetadata(HddInstall *in)
{
    LauncherListing list = {.in = in, .count = 6};
    static const char *const roots[] = {"scripts/assets/OPL", "scripts/assets/NHDDL", "scripts/assets/neutrino",
                                       "icons/art", "icons/ico", "scripts/licenses"};
    free(in->launcher_files); in->launcher_count = 0;
    in->launcher_files = calloc(HDD_INSTALL_LAUNCHER_FILES, sizeof(*in->launcher_files));
    if (!in->launcher_files) return -ENOMEM;
    for (unsigned i = 0; i < 6; i++) strcpy(list.dirs[i], roots[i]);
    if (in->game_launcher >= HDD_GAME_RIPTOPL) strcpy(list.dirs[1], "scripts/assets/Ember");
    for (; list.current < list.count; list.current++) {
        HttpsResponse response; char path[320]; int ret;
        snprintf(path, sizeof(path), HDD_INSTALL_API "/contents/%s?ref=%s", list.dirs[list.current], in->commit);
        ret = request(in, path, &response); if (ret < 0) return ret;
        ret = hddInstallDirectory(response.body, collectLauncher, &list);
        httpsResponseFree(&response);
        if (ret < 0) return ret;
    }
    hddInstallLog("Launcher manifest: %u files, %u bytes; default %s", in->launcher_count, (unsigned)list.bytes, hddInstallGameName(in->game_launcher));
    return launcherManifest(in);
}
static int downloadLaunchers(HddInstall *in, const char **phase, uint64_t completed, uint64_t total)
{
    for (unsigned i = 0; i < in->launcher_count; i++) {
        HddInstallFile *file = &in->launcher_files[i];
        char name[192], url[512];
        int ret = launcherStageName(file->path, name);
        if (ret < 0) return ret;
        snprintf(url, sizeof(url), "https://raw.githubusercontent.com/" HDD_INSTALL_REPOSITORY "/%s/%s", in->commit, file->path);
        if (i < in->downloaded_launchers && checkFileSize(in, name, file->size) == 0) {
            completed += file->size; hddInstallOverall(completed, total); continue;
        }
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
        if (i < in->downloaded_launchers) in->downloaded_launchers = i;
        *phase = file->path;
        hddInstallLog("LAUNCHER download %u/%u: %s (%u bytes)", i + 1, in->launcher_count, file->path, (unsigned)file->size);
        hddInstallLogFlush(in);
        InstallTransfer transfer = {file->path, completed, total, file->size};
        ret = downloadFile(in, url, name, file->size, &transfer);
        if (ret < 0) return ret;
        in->downloaded_launchers = i + 1;
        ret = hddInstallResumeSave(in); if (ret < 0) return ret;
        completed += file->size;
    }
    return checkLaunchers(in);
}
static void installerHttpsStatus(const char *status, void *context)
{
    const char *const *phase = context;
    char text[128];
    snprintf(text, sizeof(text), "%.48s: %.72s", *phase, status);
    hddInstallProgress(text, 0, 0);
}
static int downloadInstaller(HddInstall *in, const char **phase)
{
    HttpsResponse response;
    char path[256], url[512], local[MAX_PATH];
    int ret, fd;
    uint64_t downloaded = 0, download_total;
    in->ready = 0; in->error[0] = 0;
    if (!in->manifest_ready) {
    hddInstallStatus("Reading PSBBN DP repository", 0, 0);
    ret = 0;
    if (!in->commit[0]) {
        ret = request(in, HDD_INSTALL_API "/git/ref/heads/main", &response);
        if (ret < 0) return ret;
        ret = hddInstallCommit(response.body, in->commit) ? 0 : -EINVAL;
        httpsResponseFree(&response);
    }
    hddInstallLog("Pinned PSBBN DP Git commit: %s rc=%d", in->commit, ret);
    if (ret < 0) goto invalid;
    /* Directory listings contain only metadata, avoiding GitHub's base64
     * file contents and keeping responses within the HTTPS client's limit. */
    for (unsigned directory = 0; directory < 4; directory++) {
        if (!(in->flags & (directory ? HDD_INSTALL_APPS : HDD_INSTALL_HOSD)) || (directory == 2 && !(in->flags & HDD_INSTALL_PSBBN)) || (directory == 3 && !(in->flags & HDD_INSTALL_PS2LINUX) && !hddInstallSelectedAsset(in, HI_KERNEL_JPN))) continue;
        snprintf(path, sizeof(path), HDD_INSTALL_API "/contents/%s?ref=%s",
                 directory == 3 ? "scripts/assets/kernel" : directory == 2 ? "icons/art" : directory ? "games/APPS" : "scripts/assets/osdmenu", in->commit);
        *phase = directory == 3 ? "PS2 Linux kernels" : directory ? "App metadata" : "OSDMenu metadata";
        ret = request(in, path, &response);
        if (ret < 0) return ret;
        for (unsigned asset = 0; asset < HDD_INSTALL_ASSETS; asset++) {
            if (!hddInstallSelectedAsset(in, asset) || !hddInstallAssetPath(asset) ||
                directory != (asset >= HI_KERNEL_NTSC ? 3u : asset == HI_WLE_ART || asset == HI_R3_ART ? 2u : (unsigned)(asset == HI_WLE || asset == HI_R3CONFIG))) continue;
            if (!hddInstallAssetMetadata(response.body, hddInstallAssetName(asset), in->hashes[asset], &in->sizes[asset])) {
                ret = -EINVAL; break;
            }
        }
        httpsResponseFree(&response);
        if (ret < 0) goto invalid;
    }
    if (in->flags & HDD_INSTALL_HOSD) {
        in->sizes[HI_EXTRAS] = EXTRAS_SIZE;
        if ((in->flags & HDD_INSTALL_PSBBN) && in->game_launcher >= HDD_GAME_RIPTOPL) {
            *phase = "Ember BIOS dependency metadata";
            memset(&response, 0, sizeof(response));
            hddInstallLog("GET https://archive.org/metadata/psbbn-definitive-project-dependencies");
            ret = httpsRequest("GET", "archive.org", "/metadata/psbbn-definitive-project-dependencies",
                               NULL, NULL, 0, in->ca_path, &response, in->error, sizeof(in->error));
            if (ret < 0 || response.status != 200 || !response.body) {
                httpsResponseFree(&response); return ret < 0 ? ret : -EIO;
            }
            ret = hddInstallDependencyMetadata(response.body, in->hashes[HI_EXTRAS], &in->sizes[HI_EXTRAS]) ? 0 : -EINVAL;
            httpsResponseFree(&response);
            if (ret < 0) goto invalid;
        }
    }
    if (in->flags & HDD_INSTALL_PSBBN) {
        *phase = "Game launcher package metadata";
        ret = launcherMetadata(in);
        if (ret < 0) goto invalid;
    }
    if (in->flags & HDD_INSTALL_PSBBN) {
        *phase = "PSBBN release metadata";
        ret = archiveMetadata(in, &response);
        if (ret >= 0) {
            char language_prefix[32];
            const char *prefixes[] = {"psbbn-definitive-patch-v", language_prefix};
            snprintf(language_prefix, sizeof(language_prefix), "language-pak-%s-v", in->language.code);
            for (unsigned i = 0; i < 2; i++)
                if (!hddInstallArchiveMetadata(response.body, prefixes[i], in->archives[i],
                                               in->hashes[HI_SYSTEM + i], &in->sizes[HI_SYSTEM + i])) ret = -EINVAL;
            if ((in->flags & HDD_INSTALL_PS2LINUX) && !hddInstallLinuxMetadata(response.body,
                    in->hashes[HI_PS2LINUX], &in->sizes[HI_PS2LINUX])) ret = -EINVAL;
            if (hddInstallSelectedAsset(in, HI_CHANNELS) && !hddInstallArchiveMetadata(response.body,
                    "channels-jpn-v", in->channels, in->hashes[HI_CHANNELS], &in->sizes[HI_CHANNELS])) ret = -EINVAL;
        }
        httpsResponseFree(&response);
        if (ret < 0) goto invalid;
    }
    in->manifest_ready = 1;
    }
    ret = hddInstallResumeSave(in); if (ret < 0) goto invalid;
    download_total = downloadBytes(in);
    *phase = "Preparing app download folders";
    ret = prepareLauncherStage(in); if (ret < 0) goto invalid;
    *phase = "Checking __common download space";
    ret = stageSpace(in); if (ret < 0) goto invalid;
    for (unsigned asset = 0; asset < HDD_INSTALL_ASSETS; asset++) {
        if (!hddInstallSelectedAsset(in, asset)) continue;
        if (pathJoin(local, sizeof(local), in->stage, hddInstallAssetName(asset)) < 0) { ret = -ENAMETOOLONG; goto invalid; }
        if ((in->downloaded_assets & (1u << asset)) && checkFileSize(in, hddInstallAssetName(asset), in->sizes[asset]) == 0) {
            downloaded += in->sizes[asset]; hddInstallOverall(downloaded, download_total); continue;
        }
        if (hddInstallRecoveryFault()) { ret = HDD_INSTALL_ATA_TIMEOUT; goto invalid; }
        in->downloaded_assets &= ~(1u << asset);
        if (asset == HI_EXTRAS) snprintf(url, sizeof(url), "%s", in->game_launcher >= HDD_GAME_RIPTOPL ? EMBER_DEP_URL : EXTRAS_URL);
        else if (asset == HI_PS2LINUX)
            snprintf(url, sizeof(url), "https://archive.org/download/%s/PS2Linux.tar.gz", in->archive_item);
        else if (asset == HI_SYSTEM || asset == HI_LANGUAGE || asset == HI_CHANNELS)
            snprintf(url, sizeof(url), "https://archive.org/download/%s/%s", in->archive_item,
                     asset == HI_CHANNELS ? in->channels : in->archives[asset - HI_SYSTEM]);
        else snprintf(url, sizeof(url), "https://raw.githubusercontent.com/" HDD_INSTALL_REPOSITORY "/%s/%s", in->commit, hddInstallAssetPath(asset));
        *phase = hddInstallAssetName(asset);
        hddInstallLog("DOWNLOAD %u/%u: %s", asset + 1, (unsigned)HDD_INSTALL_ASSETS, *phase);
        hddInstallLog("URL: %s", url);
        hddInstallLog("Destination: %s; expected=%u bytes", local, (unsigned)in->sizes[asset]);
        hddInstallLogFlush(in);
        {
            InstallTransfer transfer = {hddInstallAssetName(asset), downloaded, download_total, in->sizes[asset]};
            ret = downloadFile(in, url, hddInstallAssetName(asset), in->sizes[asset], &transfer);
        }
        hddInstallLogFlush(in);
        if (ret < 0) goto invalid;
        in->downloaded_assets |= 1u << asset;
        ret = hddInstallResumeSave(in); if (ret < 0) goto invalid;
        downloaded += in->sizes[asset];
    }
    if (in->flags & HDD_INSTALL_PSBBN) {
        ret = downloadLaunchers(in, phase, downloaded, download_total);
        if (ret < 0) goto invalid;
        *phase = "Checking installer files";
    }
    hddInstallPhase(HDD_INSTALL_PHASE_CHECK);
    if (in->flags & HDD_INSTALL_APPS) for (unsigned i = 0; i < 2; i++) {
        SaveArchive save; uint8_t *data;
        ret = loadApp(in, i, &save, &data);
        if (ret < 0) goto invalid;
        saveArchiveFree(&save); free(data);
    }
    if (in->flags & HDD_INSTALL_HOSD) {
        unsigned char header[52];
        for (unsigned i = HI_MBR; i <= HI_HOSD; i++) {
            pathJoin(local, sizeof(local), in->stage, hddInstallAssetName(i));
            fd = genOpen(local, FIO_O_RDONLY);
            if (fd < 0) { ret = fd; goto invalid; }
            ret = closeResult(fd, readAll(fd, header, sizeof(header)));
            if (ret < 0) goto invalid;
            if ((i == HI_MBR && (in->sizes[i] < 512 || in->sizes[i] > 1024 * 1024 || in->sizes[i] % 512 ||
                                memcmp(header, "\x01\x00\x00\x04", 4))) ||
                (i == HI_HOSD && (memcmp(header, "\x7f" "ELF\x01\x01", 6) || header[18] != 8))) { ret = -EINVAL; goto invalid; }
        }
        if (!(in->flags & HDD_INSTALL_PSBBN)) {
            ret = osdResources(in, NULL);
            if (ret < 0) goto invalid;
        }
    }
    in->ready = 1;
    return hddInstallResumeSave(in);
invalid:
    hddInstallLog("ERROR download/verification rc=%d detail=%s", ret, in->error);
    hddInstallLogFlush(in);
    if (!in->error[0]) snprintf(in->error, sizeof(in->error), "Downloaded installer files failed verification (error %d). The HDD is formatted; installation is incomplete.", ret);
    return ret;
}
int hddInstallDownload(HddInstall *in)
{
    const char *phase = "PSBBN DP repository";
    int ret;
    hddInstallPhase(HDD_INSTALL_PHASE_DOWNLOAD);
    httpsSetStatusCallback(installerHttpsStatus, &phase);
    httpsSetTraceCallback(NULL, NULL);
    httpsDownloadBatchBegin();
    ret = downloadInstaller(in, &phase);
    httpsDownloadBatchEnd();
    httpsSetStatusCallback(NULL, NULL);
    httpsSetTraceCallback(NULL, NULL);
    return ret;
}
#else
int hddInstallDownload(HddInstall *in)
{
    snprintf(in->error, sizeof(in->error), "This build does not include native HTTPS networking.");
    return -ENOSYS;
}
#endif

/* Only delete a temporary folder whose marker belongs to this install. */
int hddInstallClaimStage(HddInstall *in)
{
    char path[MAX_PATH];
    SaveSha1 hash;
    u64 ticks = Timer();
    time_t now = time(NULL);
    int fd, ret;
    if (in->owned) return -EEXIST;
    if (pathJoin(path, sizeof(path), in->stage, "owner.bin") < 0) return -ENAMETOOLONG;
    saveHashInit(&hash); saveHashUpdate(&hash, (const uint8_t *)&ticks, sizeof(ticks));
    saveHashUpdate(&hash, (const uint8_t *)&now, sizeof(now));
    saveHashUpdate(&hash, (const uint8_t *)in->stage, strlen(in->stage));
    saveHashFinish(&hash, in->owner);
    fd = genOpen(path, FIO_O_CREAT | FIO_O_EXCL | FIO_O_WRONLY);
    if (fd < 0) return fd;
    ret = closeResult(fd, writeAll(fd, in->owner, sizeof(in->owner)));
    if (ret < 0) { genRemove(path); return ret; }
    in->owned = 1; return 0;
}
static int stageMatches(HddInstall *in, const char *stage)
{
    char path[MAX_PATH];
    unsigned char owner[20];
    int fd, ret;
    if (pathJoin(path, sizeof(path), stage, "owner.bin") < 0) return 0;
    fd = genOpen(path, FIO_O_RDONLY); if (fd < 0) return 0;
    ret = genLseek(fd, 0, SEEK_END) == sizeof(owner) && genLseek(fd, 0, SEEK_SET) == 0 ? readAll(fd, owner, sizeof(owner)) : -EINVAL;
    ret = closeResult(fd, ret);
    return ret == 0 && !memcmp(owner, in->owner, sizeof(owner));
}
int hddInstallFindStage(HddInstall *in)
{
    return in->owned && in->stage[0] && stageMatches(in, in->stage) ? 0 : -ENOENT;
}

static void removeLauncherStage(HddInstall *in, const char *name)
{
    char path[MAX_PATH];
    if (pathJoin(path, sizeof(path), in->stage, name) < 0) return;
    genRemove(path);
    /* Remove only empty parents of manifest files, never unrelated contents. */
    char *slash;
    while (!hddInstallRecoveryFault() && (slash = strrchr(path, '/')) && slash > path + strlen(in->stage)) {
        *slash = 0;
        if (genRmdir(path) < 0) break;
    }
}
void hddInstallCleanup(HddInstall *in)
{
    char path[MAX_PATH];
    if (hddInstallRecoveryFault()) return;
    if (hddInstallFindStage(in) < 0) { if (!hddInstallRecoveryFault()) hddInstallRelease(in); return; }
    for (unsigned asset = 0; asset < HDD_INSTALL_ASSETS; asset++) {
        if (pathJoin(path, sizeof(path), in->stage, hddInstallAssetName(asset)) == 0) genRemove(path);
        if (hddInstallRecoveryFault()) return;
    }
    for (unsigned i = 0; i < in->launcher_count; i++) {
        char name[192];
        if (launcherStageName(in->launcher_files[i].path, name) == 0) removeLauncherStage(in, name);
        if (hddInstallRecoveryFault()) return;
        legacyLauncherStageName(i, name);
        if (pathJoin(path, sizeof(path), in->stage, name) == 0) genRemove(path);
        if (hddInstallRecoveryFault()) return;
    }
    if (pathJoin(path, sizeof(path), in->stage, "INSTALL_CA.PEM") == 0) genRemove(path);
    if (hddInstallRecoveryFault() || hddInstallResumeRemove(in) < 0) return;
    hddInstallRelease(in);
    if (hddInstallLogEnabled()) {
        hddInstallLog("Staged payloads cleaned; retaining owner marker and INSTALLER.LOG");
        hddInstallLogFlush(in); in->ready = 0;
    } else {
        if (pathJoin(path, sizeof(path), in->stage, "owner.bin") == 0) genRemove(path);
        snprintf(path, sizeof(path), "%s", in->stage); genRmdir(path);
        in->stage[0] = 0; in->owned = in->ready = 0;
    }
}

static int makeDirectory(const char *path, int visible)
{
    iox_stat_t stat;
    int ret = genMkdir(path, 0777);
    if (ret < 0) {
        if (fileXioGetStat(path, &stat) < 0 || !FIO_S_ISDIR(stat.mode)) return ret;
    }
    if (!visible) return 0;
    memset(&stat, 0, sizeof(stat)); stat.attr = HDD_INSTALL_BROWSER_ATTR;
    return fileXioChStat(path, &stat, FIO_CST_ATTR);
}
static int makeParents(char *path)
{
    for (char *p = strchr(path, ':'); p && *p; p++) if (*p == '/' && p[1] && p[-1] != ':') {
        *p = 0; int ret = makeDirectory(path, 0); *p = '/';
        if (ret < 0) return ret;
    }
    return 0;
}
static int writeNew(HddInstall *in, const char *path, const void *data, unsigned size)
{
    int fd, ret;
    unsigned done = 0;
    hddInstallLog("WRITE %s (%u bytes)", path, size);
    fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | (in->owned && (in->recovery_attempts || in->resumed) ? FIO_O_TRUNC : FIO_O_EXCL));
    if (fd < 0) return fd;
    hddInstallProgress(path, 0, size);
    ret = 0;
    while (done < size) {
        unsigned n = size - done > 32768 ? 32768 : size - done;
        ret = writeAll(fd, (const unsigned char *)data + done, n);
        if (ret < 0) break;
        done += n; hddInstallProgress(path, done, size);
    }
    ret = closeResult(fd, ret);
    if (ret < 0) { char remove[MAX_PATH]; snprintf(remove, sizeof(remove), "%s", path); genRemove(remove); }
    return ret;
}
static int copyFile(HddInstall *in, const char *name, uint32_t size, const char *destination, int replace)
{
    unsigned char *buffer;
    char source[MAX_PATH];
    uint32_t done = 0;
    int input, output, ret = 0;
    if (pathJoin(source, sizeof(source), in->stage, name) < 0) return -ENAMETOOLONG;
    buffer = malloc(32768);
    if (!buffer) return -ENOMEM;
    input = genOpen(source, FIO_O_RDONLY);
    if (input < 0) { free(buffer); return input; }
    hddInstallLog("COPY %s -> %s (%u bytes)", source, destination, (unsigned)size);
    output = genOpen(destination, FIO_O_WRONLY | FIO_O_CREAT | (replace ? FIO_O_TRUNC : FIO_O_EXCL));
    if (output < 0) { genClose(input); free(buffer); return output; }
    hddInstallProgress(destination, 0, size);
    while (done < size) {
        unsigned n = size - done > 32768 ? 32768 : size - done;
        ret = readAll(input, buffer, n);
        if (ret >= 0) ret = writeAll(output, buffer, n);
        if (ret < 0) break;
        done += n; hddInstallProgress(destination, done, size);
    }
    ret = closeResult(output, ret); ret = closeResult(input, ret); free(buffer);
    return ret;
}
static int copyAsset(HddInstall *in, unsigned asset, const char *destination)
{ return copyFile(in, hddInstallAssetName(asset), in->sizes[asset], destination, in->owned && (in->recovery_attempts || in->resumed)); }
int hddInstallPfsPartition(HddInstall *in, unsigned mb, const char *name)
{
    if (in->owned && (in->recovery_attempts || in->resumed)) {
        char path[96]; iox_stat_t st;
        snprintf(path, sizeof(path), "hdd0:%s", name);
        int ret = fileXioGetStat(path, &st);
        if (ret >= 0) {
            const int zone = 8192;
            if (st.mode != 0x100 || st.size != mb * 2048u || st.attr || st.private_0 ||
                in->apa_sectors < st.size || st.private_5 < 2048 || st.private_5 > in->apa_sectors - st.size) return -EINVAL;
            /* Apply has not completed. This new install owns this volume,
             * and an earlier timeout may have interrupted its PFS format. */
            hddInstallLog("RECOVERY reinitializing owned PFS %s (%u MiB)", name, mb);
            ret = fileXioFormat("pfs:", path, (const char *)&zone, sizeof(zone));
            return ret < 0 ? ret : (int)mb;
        }
        if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
    }
    return hddMakeFilesystem(mb, (char *)name, FS_GROUP_APPLICATION);
}
static int installApps(HddInstall *in)
{
    const char *base = in->jail ? "ata0:/APPS" : "pfs2:/APPS";
    char folder[MAX_PATH], path[MAX_PATH];
    int ret = makeDirectory(base, !in->jail);
    if (ret < 0) return ret;
    for (unsigned index = 0; index < 2; index++) {
        SaveArchive save; uint8_t *data;
        ret = loadApp(in, index, &save, &data);
        if (ret < 0) return ret;
        ret = pathJoin(folder, sizeof(folder), base, save.folder.name);
        if (ret >= 0) ret = makeDirectory(folder, !in->jail);
        for (unsigned i = 0; ret >= 0 && i < save.count; i++) {
            ret = pathJoin(path, sizeof(path), folder, save.files[i].name);
            if (ret >= 0) ret = writeNew(in, path, save.files[i].data, save.files[i].size);
        }
        if (ret >= 0 && in->jail) {
            char elf[MAX_PATH];
            const SaveArchiveEntry *icon = NULL;
            for (unsigned i = 0; i < save.count; i++) if (!strcmp(save.files[i].name, "list.icn")) icon = &save.files[i];
            hddInstallLog("Create app launcher: %s (128 MiB)", app_partitions[index]);
            hddInstallLogFlush(in);
            ret = hddInstallPfsPartition(in, 128, app_partitions[index]);
            if (ret != 128) ret = ret < 0 ? ret : -ENOSPC;
            else if (!icon || pathJoin(elf, sizeof(elf), folder, app_boot[index]) < 0) ret = -EINVAL;
            else ret = InjectHddAppLauncher(app_partitions[index], elf, app_names[index], icon->data, icon->size);
            if (ret >= 0 && (in->flags & HDD_INSTALL_PSBBN)) {
                char partition[64], info[1024];
                int n, closed;
                snprintf(partition, sizeof(partition), "hdd0:%s", app_partitions[index]);
                ret = fileXioMount("pfs3:", partition, FIO_MT_RDWR);
                if (ret >= 0) {
                    ret = makeDirectory("pfs3:/res", 0);
                    n = snprintf(info, sizeof(info),
                        "title = [APP] %s\ntitle_id = %s\ntitle_sub_id = 0\nrelease_date = \n"
                        "developer_id = \npublisher_id = Homebrew\nnote = \ncontent_web = \n"
                        "image_topviewflag = 0\nimage_type = 0\nimage_count = 1\nimage_viewsec = 600\n"
                        "copyright_viewflag = 0\ncopyright_imgcount = 0\ngenre = \nparental_lock = 1\n"
                        "effective_date = 0\nexpire_date = 0\nviolence_flag = 0\ncontent_type = 255\ncontent_subtype = 0\n",
                        app_names[index], index ? "SYS-R3CONFIG" : "APP-WLER3Z");
                    if (ret >= 0) ret = writeNew(in, "pfs3:/res/info.sys", info, n);
                    if (ret >= 0) ret = copyAsset(in, index ? HI_R3_ART : HI_WLE_ART, "pfs3:/res/jkt_001.png");
                    closed = fileXioUmount("pfs3:"); if (ret >= 0) ret = closed;
                }
            }
        }
        saveArchiveFree(&save); free(data);
        if (ret < 0) return ret;
    }
    return 0;
}

static int installEmberBios(HddInstall *in)
{
    char path[MAX_PATH];
    ZipContext ctx = {-1, -1};
    InstallArchiveIo io = {&ctx, zipRead, zipWrite};
    uint32_t size = 0;
    if (pathJoin(path, sizeof(path), in->stage, "extras.zip") < 0) return -ENAMETOOLONG;
    ctx.input = genOpen(path, FIO_O_RDONLY);
    if (ctx.input < 0) return ctx.input;
    ctx.output = genOpen("ata0:/Ember/bios.bin", FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
    if (ctx.output < 0) return closeResult(ctx.input, ctx.output);
    hddInstallStatus("Installing Ember BIOS", 0, 0);
    int ret = installZipExtract(&io, in->sizes[HI_EXTRAS], "dep/bios.bin", 512u * 1024, &size);
    ret = closeResult(ctx.output, ret); ret = closeResult(ctx.input, ret);
    return ret < 0 ? ret : size == 512u * 1024 ? 0 : -EINVAL;
}

/* Install commit-pinned launchers after system/language archive population.
 * Neutrino's complete runtime stays on
 * exFAT, matching NHDDL's ATA layout and DP's game installer. */
static int installLaunchers(HddInstall *in)
{
    static const char *const folders[] = {"APPS", "ART", "CFG", "CHT", "LNG", "THM", "VMC", "CD", "DVD", "POPS", "nhddl", "Ember", "Ember/games"};
    char target[MAX_PATH], name[192];
    int ret;
    uint64_t total = 0, copied = 0;
    if (!(in->flags & HDD_INSTALL_PSBBN)) return 0;
    if (!in->jail || !in->launcher_count || !in->launcher_files) return -EINVAL;
    for (unsigned i = 0; i < in->launcher_count; i++)
        if (strncmp(in->launcher_files[i].path, "icons/", 6)) total += in->launcher_files[i].size;
    for (unsigned i = 0; i < sizeof(folders) / sizeof(folders[0]); i++) {
        snprintf(target, sizeof(target), "ata0:/%s", folders[i]);
        ret = makeDirectory(target, 0); if (ret < 0) return ret;
    }
    for (unsigned i = 0; i < in->launcher_count; i++) {
        const HddInstallFile *file = &in->launcher_files[i];
        const char *source = file->path;
        if (!strncmp(source, "icons/", 6)) continue; /* PP.LAUNCHER metadata below. */
        if (!strcmp(source, "scripts/assets/OPL/OPNPS2LD.ELF")) strcpy(target, "pfs0:/launcher/OPNPS2LD.ELF");
        else if (!strcmp(source, "scripts/assets/OPL/RIPTOPL-RA-UNPAKT.ELF")) strcpy(target, "pfs0:/launcher/RIPTOPL-RA-UNPAKT.ELF");
        else if (!strncmp(source, "scripts/assets/Ember/", sizeof("scripts/assets/Ember/") - 1)) snprintf(target, sizeof(target), "ata0:/Ember/%s", source + sizeof("scripts/assets/Ember/") - 1);
        else if (!strcmp(source, "scripts/licenses/EMBER-LICENSE-BETA.txt")) strcpy(target, "ata0:/Ember/LICENSE.txt");
        else if (!strcmp(source, "scripts/assets/NHDDL/nhddl.elf")) strcpy(target, "pfs0:/launcher/nhddl.elf");
        else if (!strcmp(source, "scripts/assets/OPL/version.txt")) strcpy(target, "pfs0:/launcher/OPL-version.txt");
        else if (!strcmp(source, "scripts/assets/NHDDL/version.txt")) strcpy(target, "pfs0:/launcher/NHDDL-version.txt");
        else if (!strncmp(source, "scripts/assets/OPL/LNG/", sizeof("scripts/assets/OPL/LNG/") - 1)) snprintf(target, sizeof(target), "ata0:/LNG/%s", source + sizeof("scripts/assets/OPL/LNG/") - 1);
        else if (!strncmp(source, "scripts/assets/neutrino/", sizeof("scripts/assets/neutrino/") - 1)) snprintf(target, sizeof(target), "ata0:/neutrino/%s", source + sizeof("scripts/assets/neutrino/") - 1);
        else if (!strncmp(source, "scripts/licenses/", 17)) snprintf(target, sizeof(target), "pfs0:/launcher/licenses/%s", source + 17);
        else return -EINVAL;
        ret = makeParents(target); if (ret < 0) return ret;
        ret = launcherStageName(source, name); if (ret < 0) return ret;
        ret = copyFile(in, name, file->size, target, 1);
        if (ret < 0) return ret;
        copied += file->size;
        if (total) hddInstallOverall(900 + 80 * copied / total, 1000);
    }
    if (in->game_launcher >= HDD_GAME_RIPTOPL) {
        ret = installEmberBios(in); if (ret < 0) return ret;
        static const char credit[] = "Ember by Gageformer\nhttps://github.com/Gageformer/Ember/releases\n";
        ret = writeNew(in, "ata0:/Ember/README.txt", credit, sizeof(credit) - 1);
        if (ret < 0) return ret;
    }
    {
        char config[512], path[128];
        const char *language = !strcmp(in->language.code, "por") ? "Portuguese_BR" : in->language.name;
        snprintf(path, sizeof(path), "scripts/assets/OPL/LNG/lang_%s.lng", language);
        if (!*language || findLauncher(in, path) < 0) language = "English";
        int n = snprintf(config, sizeof(config), "enable_coverart=1\ndefault_device=0\nusb_mode=2\napp_mode=2\nenable_bdm_hdd=1\nlanguage_text=%s\nswap_select_btn=0\n", language);
        if (in->game_launcher >= HDD_GAME_RIPTOPL) {
            n = snprintf(config, sizeof(config),
                "enable_notifications=1\nenable_coverart=1\nenable_discart=0\nenable_logoart=1\nenable_bgart=1\n"
                "ps2logo=0\napply_gameid=1\nenable_rumble=0\ncfg_titles_in_lists=1\nigr_menu=1\nigr_alt_combo=0\n"
                "language_text=%s\nswap_select_btn=0\ndefault_device=0\nusb_mode=2\napp_mode=2\nenable_bdm_hdd=1\ndefault_core=%u\n",
                language, in->game_launcher == HDD_GAME_RIPTOPL_NEUTRINO ? 1u : 0u);
        }
        if (n < 0 || n >= (int)sizeof(config)) return -ENOSPC;
        return writeNew(in, in->game_launcher >= HDD_GAME_RIPTOPL ? "ata0:/settings_riptopl.cfg" : "ata0:/conf_opl.cfg", config, n);
    }
}

static int installGamePartition(HddInstall *in)
{
    const char *title = hddInstallGameName(in->game_launcher);
    const char *id = in->game_launcher >= HDD_GAME_RIPTOPL ? "APP_RIPTOPL" : in->game_launcher == HDD_GAME_NEUTRINO ? "APP_NHDDL" : "APP_OPL";
    char path[MAX_PATH], name[192], elf[128], info[1024];
    unsigned char *icon;
    int index, art, fd, ret, n;
    if (!(in->flags & HDD_INSTALL_PSBBN)) return 0;
    index = findLauncher(in, launcherIcon(in)); art = findLauncher(in, launcherArt(in));
    if (index < 0 || art < 0 || in->launcher_files[index].size > 1024 * 1024) return -EINVAL;
    icon = malloc(in->launcher_files[index].size); if (!icon) return -ENOMEM;
    ret = launcherStageName(in->launcher_files[index].path, name);
    if (ret < 0) { free(icon); return ret; }
    ret = pathJoin(path, sizeof(path), in->stage, name);
    if (ret >= 0) {
        fd = genOpen(path, FIO_O_RDONLY);
        ret = fd < 0 ? fd : closeResult(fd, readAll(fd, icon, in->launcher_files[index].size));
    }
    if (ret >= 0) {
        hddInstallLog("Creating PP.LAUNCHER (128 MiB): %s", title);
        ret = hddInstallPfsPartition(in, 128, "PP.LAUNCHER");
        ret = ret == 128 ? 0 : ret < 0 ? ret : -ENOSPC;
    }
    snprintf(elf, sizeof(elf), "hdd0:__system:pfs:/launcher/%s", hddInstallGameElf(in->game_launcher));
    if (ret >= 0) ret = InjectHddAppLauncherWithArg("PP.LAUNCHER", elf, title, icon, in->launcher_files[index].size,
                                        in->game_launcher == HDD_GAME_NEUTRINO ? "-mode=ata" : NULL);
    free(icon);
    if (ret < 0) return ret;
    ret = fileXioMount("pfs3:", "hdd0:PP.LAUNCHER", FIO_MT_RDWR); if (ret < 0) return ret;
    ret = makeDirectory("pfs3:/res", 0);
    n = snprintf(info, sizeof(info),
        "title = [LCH] %s\ntitle_id = %s\ntitle_sub_id = 0\nrelease_date = \n"
        "developer_id = \npublisher_id = Homebrew\nnote = \ncontent_web = \n"
        "image_topviewflag = 0\nimage_type = 0\nimage_count = 1\nimage_viewsec = 600\n"
        "copyright_viewflag = 0\ncopyright_imgcount = 0\ngenre = \nparental_lock = 1\n"
        "effective_date = 0\nexpire_date = 0\nviolence_flag = 0\ncontent_type = 255\ncontent_subtype = 0\n", title, id);
    if (ret >= 0) ret = writeNew(in, "pfs3:/res/info.sys", info, n);
    if (ret >= 0) ret = launcherStageName(in->launcher_files[art].path, name);
    if (ret >= 0) ret = copyFile(in, name, in->launcher_files[art].size, "pfs3:/res/jkt_001.png", in->owned && (in->recovery_attempts || in->resumed));
    { int closed = fileXioUmount("pfs3:"); if (ret >= 0) ret = closed; }
    return ret;
}

int hddInstallWriteConfigs(HddInstall *in)
{
    char config[4096];
    int installed = installLaunchers(in);
    if (installed < 0) return installed;
    for (unsigned i = 0; i < 2; i++) {
        int ret = hddInstallConfig(in, i == 0, config, sizeof(config));
        if (ret >= 0) ret = writeNew(in, i ? "pfs1:/osdmenu/OSDMENU.CNF" : "pfs1:/osdmenu/OSDMBR.CNF", config, ret);
        if (ret < 0) return ret;
    }
    /* Install kernels after the system archive, which may contain older copies. */
    if (hddInstallSelectedAsset(in, HI_KERNEL_JPN)) {
        int ret = copyAsset(in, HI_KERNEL_JPN, "pfs0:/p2lboot/vmlinux");
        if (ret < 0) return ret;
    }
    if (in->flags & HDD_INSTALL_PS2LINUX) {
        int ret = copyAsset(in, HI_KERNEL_NTSC, "pfs0:/p2lboot/ps2-linux-ntsc");
        if (ret < 0) return ret;
        ret = copyAsset(in, HI_KERNEL_VGA, "pfs0:/p2lboot/ps2-linux-vga");
        if (ret < 0) return ret;
    }
    hddInstallOverall(980, 1000);
    return 0;
}

int hddInstallApply(HddInstall *in)
{
    int ret = -EINVAL, mounts = 0, stage_mounted = 0;
    static const char *const partitions[] = {"hdd0:__system", "hdd0:__sysconf"};
    static const char *const pfs[] = {"pfs0:", "pfs1:"};
    hddInstallPhase(HDD_INSTALL_PHASE_INSTALL);
    if (!in->ready || !in->flags || (in->jail ? (in->flags & ~HDD_INSTALL_PS2LINUX) != (HDD_INSTALL_HOSD | HDD_INSTALL_APPS | HDD_INSTALL_PSBBN) :
        !!(in->flags & ~(HDD_INSTALL_HOSD | HDD_INSTALL_APPS)))) goto failed;
    ret = hddInstallMountStage(in);
    if (ret < 0) goto failed;
    stage_mounted = 1;
    ret = hddInstallFindStage(in);
    if (ret < 0) {
        hddInstallUnmountStage(in);
        snprintf(in->error, sizeof(in->error), "The temporary installer folder is missing or has a different owner. The HDD is formatted; software installation has not started.");
        return ret;
    }
    /* Size/format checks do not scan complete files or calculate hashes. */
    for (unsigned asset = 0; asset < HDD_INSTALL_ASSETS; asset++) {
        if (!hddInstallSelectedAsset(in, asset)) continue;
        ret = checkFileSize(in, hddInstallAssetName(asset), in->sizes[asset]);
        if (ret < 0) break;
    }
    if (ret >= 0) ret = checkLaunchers(in);
    if (ret < 0) goto failed;
    /* Keep common on pfs2 for staging and diagnostics during APA creation. */
    if (in->flags & HDD_INSTALL_PSBBN) {
        ret = hddInstallPsbbnPartitions(in);
        if (ret < 0) goto failed;
    }
    for (unsigned i = 0; i < 2; i++) {
        hddInstallLog("MOUNT %s -> %s", partitions[i], pfs[i]);
        ret = fileXioMount(pfs[i], partitions[i], FIO_MT_RDWR);
        hddInstallLog("MOUNT rc=%d", ret);
        if (ret < 0) goto failed;
        mounts++;
    }
    if (in->flags & HDD_INSTALL_APPS) {
        ret = installApps(in);
        if (ret < 0) goto failed;
    }
    ret = installGamePartition(in);
    if (ret < 0) goto failed;
    if (in->flags & HDD_INSTALL_HOSD) {
        const char *dirs[] = {"pfs0:/osdmenu", "pfs0:/osd100", "pfs1:/osdmenu"};
        for (unsigned i = 0; i < 3; i++) { ret = makeDirectory(dirs[i], 0); if (ret < 0) goto failed; }
        ret = copyAsset(in, HI_HOSD, "pfs0:/osdmenu/hosdmenu.elf");
        if (ret >= 0) ret = copyAsset(in, HI_VERSION, "pfs0:/osdmenu/version.txt");
        if (ret >= 0 && !(in->flags & HDD_INSTALL_PSBBN)) ret = osdResources(in, "pfs0:/osd100");
        if (ret < 0) goto failed;
        if (!(in->flags & HDD_INSTALL_PSBBN)) {
            ret = hddInstallWriteConfigs(in);
            if (ret < 0) goto failed;
        }
    }
    ret = 0;
failed:
    if (ret < 0) hddInstallLog("ERROR apply rc=%d", ret);
    while (mounts && !hddInstallRecoveryFault()) {
        int closed = fileXioUmount(pfs[--mounts]);
        if (ret >= 0 && closed < 0) ret = closed;
    }
    if (stage_mounted) {
        int closed = hddInstallUnmountStage(in);
        if (ret >= 0) ret = closed;
    }
    if (ret < 0) snprintf(in->error, sizeof(in->error), "Software installation failed (error %d). The HDD is formatted, but installation is incomplete.", ret);
    else hddInstallOverall(100, 1000);
    return ret;
}
