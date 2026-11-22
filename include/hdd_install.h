#ifndef HDD_INSTALL_H
#define HDD_INSTALL_H

#include <stddef.h>
#include <stdint.h>
#include "hdd_format.h"

#define HDD_INSTALL_REPOSITORY "CosmicScale/PSBBN-Definitive-Project"
#define HDD_INSTALL_API "/repos/" HDD_INSTALL_REPOSITORY
#define HDD_INSTALL_BROWSER_ATTR 0xc4a7u
#define HDD_INSTALL_ASSETS 13
#define HDD_INSTALL_LINUX_PARTITIONS 10
#define HDD_INSTALL_HOME_MAX_MB 16384u

enum { HDD_INSTALL_HOSD = 1, HDD_INSTALL_APPS = 2, HDD_INSTALL_PSBBN = 4, HDD_INSTALL_PS2LINUX = 8 };
enum { HI_MBR, HI_HOSD, HI_WLE, HI_R3CONFIG, HI_EXTRAS, HI_VERSION, HI_SYSTEM, HI_LANGUAGE, HI_WLE_ART, HI_R3_ART,
       HI_PS2LINUX, HI_KERNEL_NTSC, HI_KERNEL_VGA };

typedef struct {
    unsigned flags;
    int jail;
    char commit[41];
    char stage[1024];
    char ca_path[1024];
    char error[256];
    uint32_t sizes[HDD_INSTALL_ASSETS];
    char hashes[HDD_INSTALL_ASSETS][41];
    char archives[2][128];
    struct { uint32_t start, sectors; } linux[HDD_INSTALL_LINUX_PARTITIONS];
    unsigned char owner[20];
    unsigned owned, ready;
    unsigned char *ca_data;
    unsigned ca_size;
    unsigned music_mb, contents_mb, linux_home_mb, reserved_mb;
} HddInstall;

unsigned hddInstallPartitionMb(const HddInstall *install, unsigned index);
/* Minimum additional APA allocation in MiB beyond the standard system partitions,
 * including allocator alignment, apps and explicitly reserved free space. */
int hddInstallRequiredMb(const HddInstall *install, unsigned base_mb);
int dashHddInstallConfigure(HddInstall *install, unsigned max_extent_mb);

const char *hddInstallAssetPath(unsigned asset);
const char *hddInstallAssetName(unsigned asset);
int hddInstallNeedsAsset(unsigned flags, unsigned asset);
int hddInstallHex(const char *text, unsigned length);
/* Strict, bounded JSON readers for authenticated upstream manifests. */
int hddInstallCommit(const char *json, char commit[41]);
int hddInstallAssetMetadata(const char *json, const char *name,
                             char hash[41], uint32_t *size);
int hddInstallArchiveMetadata(const char *json, const char *prefix,
                              char name[128], char hash[41], uint32_t *size);
int hddInstallLinuxMetadata(const char *json, char hash[41], uint32_t *size);
/* Config generation is based on installed components and the actual layout. */
int hddInstallConfig(const HddInstall *install, int mbr, char *text, size_t capacity);
extern const char *const hddInstallOsdFiles[7];

/* Native frontend/backend. No downloaded payload is embedded in the ELF. */
int dashHddInstallChoose(HddInstall *install, int jail);
int dashHddInstallPrepare(HddInstall *install);
int dashHddInstallPrepareStorage(HddInstall *install);
int hddInstallLoadCa(HddInstall *install);
void hddInstallRelease(HddInstall *install);
int hddInstallMountStage(HddInstall *install);
int hddInstallUnmountStage(HddInstall *install);
int hddInstallCreateStage(HddInstall *install);
int hddInstallDownload(HddInstall *install);
int hddInstallWriteConfigs(HddInstall *install);
int hddInstallApply(HddInstall *install);
int hddInstallPsbbnPreflight(HddInstall *install);
int hddInstallPsbbnPartitions(HddInstall *install);
int hddInstallPsbbnPayload(void *install, const HddFormatIo *io);
int hddInstallClaimStage(HddInstall *install);
int hddInstallFindStage(HddInstall *install);
void hddInstallCleanup(HddInstall *install);

/* Temporary verbose diagnostics: one serialized writer, UI snapshots, no
 * file I/O while the log lock is held. Times are elapsed milliseconds. */
#define HDD_INSTALL_LOG_ROWS 256
#define HDD_INSTALL_LOG_COLS 80
typedef struct {
    unsigned first, next;
    uint64_t elapsed, idle;
    char status[192], path[1024], io[112];
    int done, total, disk_error;
} HddInstallLogSnapshot;
void hddInstallLogStart(void);
void hddInstallLogStop(void);
int hddInstallLogEnabled(void);
void hddInstallLog(const char *format, ...) __attribute__((format(printf, 1, 2)));
void hddInstallStatus(const char *text, int done, int total);
void hddInstallRawTrace(int command, uint32_t lba, unsigned count, int pending, int result);
void hddInstallLogSnapshot(HddInstallLogSnapshot *snapshot);
int hddInstallLogRead(unsigned index, char line[HDD_INSTALL_LOG_COLS]);
void hddInstallLogFlush(HddInstall *install);
void dashHddInstallDebugBegin(HddInstall *install, const HddFormatPlan *plan);
void dashHddInstallDebugEnd(HddInstall *install, int result);
int dashHddInstallAwait(int id, const char *title);

#endif
