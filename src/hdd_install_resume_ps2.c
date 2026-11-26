#include "launchelf.h"
#include "hdd_install_resume.h"

static HddInstall *current;
static HddFormatPlan current_plan;
static unsigned current_sequence;
void hddInstallResumeBegin(HddInstall *in, const HddFormatPlan *plan, unsigned sequence)
{ current = in; current_plan = *plan; current_sequence = sequence; }
void hddInstallResumeEnd(void) { current = NULL; }
static int flush(void)
{
    /* HDD FLUSH alone does not write dirty PFS metadata to the device. */
    int ret = fileXioSync("pfs2:", 0);
    return ret < 0 ? ret : fileXioDevctl("hdd0:", HDIOC_FLUSH, NULL, 0, NULL, 0);
}
static int journalPath(char *path, unsigned size, const HddInstall *in, unsigned slot)
{ int n = snprintf(path, size, "%s/RESUME%u.BIN", in->stage, slot); return n > 0 && (unsigned)n < size ? 0 : -ENAMETOOLONG; }
int hddInstallResumeSave(HddInstall *in)
{
    char path[MAX_PATH]; int ret, fd;
    if (current != in || !in->stage_ready || !in->owned) return 0;
    if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
    unsigned char *bytes = malloc(HDD_INSTALL_RESUME_MAX);
    if (!bytes) return -ENOMEM;
    unsigned next = current_sequence + 1;
    int size = hddInstallResumeEncode(in, &current_plan, next, bytes, HDD_INSTALL_RESUME_MAX);
    if (size < 0) { free(bytes); return size; }
    /* Data and unmounted PFS volumes must precede the durable checkpoint. */
    ret = journalPath(path, sizeof(path), in, next & 1);
    if (ret >= 0) ret = flush();
    fd = ret < 0 ? ret : genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_TRUNC);
    if (fd < 0) ret = fd;
    else {
        unsigned done = 0;
        while (done < (unsigned)size) {
            int n = genWrite(fd, bytes + done, size - done);
            if (n <= 0 || (unsigned)n > (unsigned)size - done) { ret = n < 0 ? n : -EIO; break; }
            done += n;
        }
        if (!hddInstallRecoveryFault()) { int closed = genClose(fd); if (ret >= 0) ret = closed; }
        else ret = HDD_INSTALL_ATA_TIMEOUT;
        if (ret >= 0) ret = flush();
    }
    free(bytes);
    if (ret >= 0) current_sequence = next;
    else hddInstallLog("ERROR resume checkpoint rc=%d; previous checkpoint retained", ret);
    return ret;
}
static int readJournal(HddInstall *in, HddFormatPlan *plan, unsigned *sequence, const char *stage, unsigned slot)
{
    char path[MAX_PATH]; int fd, ret = 0;
    snprintf(path, sizeof(path), "%s/RESUME%u.BIN", stage, slot);
    fd = genOpen(path, FIO_O_RDONLY); if (fd < 0) return fd;
    s64 size = genLseek(fd, 0, SEEK_END);
    unsigned char *data = NULL;
    if (size < 24 || size > HDD_INSTALL_RESUME_MAX || genLseek(fd, 0, SEEK_SET) != 0) ret = -EINVAL;
    else if (!(data = malloc(size))) ret = -ENOMEM;
    else for (unsigned done = 0; done < (unsigned)size;) {
        int n = genRead(fd, data + done, size - done);
        if (n <= 0 || (unsigned)n > (unsigned)size - done) { ret = n < 0 ? n : -EIO; break; }
        done += n;
    }
    { int closed = genClose(fd); if (ret >= 0 && closed < 0) ret = closed; }
    if (ret >= 0) ret = hddInstallResumeDecode(in, plan, sequence, data, size);
    free(data); return ret;
}
static int sector(uint32_t lba, void *bytes)
{
    hddAtaTransfer_t request = {lba, 1};
    return fileXioDevctl("hdd0:", HDIOC_READSECTOR, &request, sizeof(request), bytes, 512);
}
static uint32_t le32(const unsigned char *p)
{ return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static int verifyDisk(HddInstall *in, const HddFormatPlan *plan)
{
    uint32_t limit;
    unsigned char boot[512] __attribute__((aligned(64)));
    int total = fileXioDevctl("hdd0:", HDIOC_TOTALSECTOR, NULL, 0, NULL, 0);
    if ((uint32_t)total != plan->sectors || hddGetApaCapacity(&limit) < 0 ||
        limit != (in->jail ? plan->apa_sectors : plan->sectors)) return -EINVAL;
    if (in->jail && (sector(plan->exfat_start, boot) < 0 || memcmp(boot + 3, "EXFAT   ", 8) ||
        le32(boot + 100) != plan->serial || le32(boot + 64) != plan->exfat_start ||
        le32(boot + 68) || le32(boot + 72) != plan->exfat_sectors || le32(boot + 76))) return -EINVAL;
    if (in->applied && (in->flags & HDD_INSTALL_PSBBN)) {
        static const char *const names[] = {"__linux.1", "__linux.2", "__linux.4", "__linux.5", "__linux.6", "__linux.7", "__linux.9", "__linux.8", "__linux.3", "__linux.10"};
        for (unsigned i = 0; i < HDD_INSTALL_LINUX_PARTITIONS; i++) {
            char path[64]; iox_stat_t st; unsigned mb = hddInstallPartitionMb(in, i);
            if (!mb) continue;
            snprintf(path, sizeof(path), "hdd0:%s", names[i]);
            if (fileXioGetStat(path, &st) < 0 || st.mode != (i == 1 ? 0x82u : 0x83u) || st.attr || st.private_0 ||
                st.size != mb * 2048u || st.private_5 != in->linux[i].start || st.size != in->linux[i].sectors ||
                st.private_5 < 2048 || st.size > limit || st.private_5 > limit - st.size) return -EINVAL;
        }
        static const char *const pfs[] = {"__contents", "PP.APP_WLE-R3Z", "PP.SYS_R3CONFIGURATOR", "PP.LAUNCHER"};
        for (unsigned i = 0; i < 4; i++) {
            char path[64]; iox_stat_t st; unsigned mb = i ? 128 : in->contents_mb;
            snprintf(path, sizeof(path), "hdd0:%s", pfs[i]);
            if (fileXioGetStat(path, &st) < 0 || st.mode != 0x100 || st.attr || st.private_0 || st.size != mb * 2048u ||
                st.size > limit || st.private_5 < 2048 || st.private_5 > limit - st.size) return -EINVAL;
        }
    }
    return 0;
}
static int incompleteLog(const char *stage)
{
    char path[MAX_PATH], tail[512];
    snprintf(path, sizeof(path), "%s/INSTALLER.LOG", stage);
    int fd = genOpen(path, FIO_O_RDONLY);
    if (fd < 0) return fd == -ENOENT ? 0 : fd;
    s64 size = genLseek(fd, 0, SEEK_END);
    unsigned count = size > (s64)sizeof(tail) ? sizeof(tail) : size > 0 ? (unsigned)size : 0;
    int ret = size < 0 ? (int)size : 0;
    if (ret >= 0 && genLseek(fd, size - count, SEEK_SET) < 0) ret = -EIO;
    for (unsigned done = 0; ret >= 0 && done < count;) {
        int n = genRead(fd, tail + done, count - done);
        if (n <= 0 || (unsigned)n > count - done) ret = n < 0 ? n : -EIO;
        else done += n;
    }
    if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
    int closed = genClose(fd);
    if (ret < 0 || closed < 0) return ret < 0 ? ret : closed;
    return !hddInstallLogComplete(tail, count);
}
int hddInstallResumeAvailable(int jail)
{
    char stage[64];
#ifndef EXFAT
    if (jail) return 0;
#endif
    /* Use the shared mount policy; never steal a fixed slot from a VMC. */
    int mount = mountParty("hdd0:__common");
    if (mount < 0) return mount;
    snprintf(stage, sizeof(stage), "pfs%d:/%s", mount, jail ? "tmp" : "PSBBN_DP_TEMP");
    int ret = incompleteLog(stage);
    if (ret <= 0) return ret;
    HddInstall *candidate = calloc(1, sizeof(*candidate));
    if (!candidate) return -ENOMEM;
    unsigned latest = 0;
    int available = 0;
    for (unsigned slot = 0; slot < 2; slot++) {
        HddFormatPlan plan; unsigned sequence;
        memset(candidate, 0, sizeof(*candidate));
        ret = readJournal(candidate, &plan, &sequence, stage, slot);
        if (ret >= 0 && candidate->jail == !!jail && sequence > latest) {
            latest = sequence;
            candidate->owned = 1; snprintf(candidate->stage, sizeof(candidate->stage), "%s", stage);
            available = !candidate->committed && hddInstallFindStage(candidate) >= 0;
        }
        hddInstallRelease(candidate);
        if (hddInstallRecoveryFault()) { available = HDD_INSTALL_ATA_TIMEOUT; break; }
    }
    free(candidate);
    return available;
}
int hddInstallResumeLoad(HddInstall *in, HddFormatPlan *plan, unsigned *sequence)
{
    HddInstall *candidate = calloc(1, sizeof(*candidate));
    if (!candidate) return -ENOMEM;
    int found = 0, ret = -ENOENT;
    /* Drivers are started on the UI thread. No network switch or write here. */
    for (unsigned jail = 0; jail < 2; jail++) {
#ifndef EXFAT
        if (jail) continue;
#endif
        int mounted = fileXioMount("pfs2:", "hdd0:__common", FIO_MT_RDONLY) >= 0;
        if (!mounted) continue;
        const char *stage = jail ? "pfs2:/tmp" : "pfs2:/PSBBN_DP_TEMP";
        for (unsigned slot = 0; slot < 2; slot++) {
            HddFormatPlan p; unsigned seq;
            memset(candidate, 0, sizeof(*candidate));
            int read = readJournal(candidate, &p, &seq, stage, slot);
            if (read >= 0 && candidate->jail == (int)jail) {
                candidate->owned = 1; snprintf(candidate->stage, sizeof(candidate->stage), "%s", stage);
                if (hddInstallFindStage(candidate) < 0 || verifyDisk(candidate, &p) < 0) ret = -EINVAL;
                else if (!found || seq > *sequence) {
                    hddInstallRelease(in); *in = *candidate; candidate->launcher_files = NULL;
                    *plan = p; *sequence = seq; found = 1;
                }
            } else if (read != -ENOENT) ret = -EINVAL;
            hddInstallRelease(candidate);
        }
        if (mounted) fileXioUmount("pfs2:");
    }
    free(candidate);
    if (!found) return ret;
    in->resumed = 1; in->recovery_attempts = 0;
    in->apa_sectors = in->jail ? plan->apa_sectors : plan->sectors;
    snprintf(in->ca_path, sizeof(in->ca_path), "pfs2:/%s/INSTALL_CA.PEM", in->jail ? "tmp" : "PSBBN_DP_TEMP");
    /* Read the staged CA before starting HTTPS, which can reset this stack. */
    int mounted = fileXioMount("pfs2:", "hdd0:__common", FIO_MT_RDONLY) >= 0;
    if (!mounted) ret = -EIO;
    else ret = in->committed ? 0 : hddInstallLoadCa(in);
    if (mounted) fileXioUmount("pfs2:");
    if (ret < 0) {
        snprintf(in->error, sizeof(in->error), "The checkpoint is valid, but its saved CA bundle could not be read (error %d).", ret);
        hddInstallRelease(in);
    }
    return ret;
}
int hddInstallResumeRemove(HddInstall *in)
{
    if (hddInstallRecoveryFault()) return HDD_INSTALL_ATA_TIMEOUT;
    for (unsigned i = 0; i < 2; i++) {
        char path[MAX_PATH];
        if (journalPath(path, sizeof(path), in, i) < 0) return -ENAMETOOLONG;
        int ret = genRemove(path);
        if (ret < 0 && ret != -ENOENT) return ret;
    }
    return flush();
}
