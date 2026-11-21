#include "launchelf.h"
#include "hdd_format.h"
#include "hdd_format_rpc.h"
#include "init.h"
#include "dash_internal.h"
#include <loadfile.h>
#include <sifrpc.h>

extern u8 hdd_format_irx[];
extern int size_hdd_format_irx;

static SifRpcClientData_t client __attribute__((aligned(64)));
static HddFormatPacket packet __attribute__((aligned(64)));
static unsigned generation;
static int loaded;

int hddFormatLoad(void)
{
    int ret, id, tries;
    unsigned gen = getIopResetGeneration();
    if (!loaded || generation != gen) {
        memset(&client, 0, sizeof(client));
        id = SifExecModuleBuffer(hdd_format_irx, size_hdd_format_irx, 0, NULL, &ret);
        if (id < 0 || ret != 0) return -EIO;
        loaded = 1; generation = gen;
    }
    for (tries = 0; tries < 200; tries++) {
        ret = SifBindRpc(&client, HDD_FORMAT_RPC, 0);
        if (ret < 0) return ret;
        if (client.server) return 0;
        DelayThread(10000);
    }
    return -ETIMEDOUT;
}

static int call(int command, uint32_t lba, unsigned count, unsigned send, unsigned receive)
{
    int ret;
    packet.lba = lba; packet.count = count;
    ret = SifCallRpc(&client, command, 0, &packet, send, &packet, receive, NULL, NULL);
    return ret < 0 ? ret : packet.result;
}

static int readDisk(void *ctx, uint32_t lba, unsigned count, void *data)
{
    int ret;
    (void)ctx;
    if (!count || count > HDD_FORMAT_CHUNK) return -EINVAL;
    ret = call(HF_READ, lba, count, 64, 64 + count * 512);
    if (ret >= 0) memcpy(data, packet.data, count * 512);
    return ret;
}

static int writeDisk(void *ctx, uint32_t lba, unsigned count, const void *data)
{
    (void)ctx;
    if (!count || count > HDD_FORMAT_CHUNK) return -EINVAL;
    memcpy(packet.data, data, count * 512);
    return call(HF_WRITE, lba, count, 64 + count * 512, 64);
}

static int zeroDisk(void *ctx, uint32_t lba, uint32_t count)
{ (void)ctx; return call(HF_ZERO, lba, count, 64, 64); }
static int flushDisk(void *ctx)
{ (void)ctx; return call(HF_FLUSH, 0, 0, 64, 64); }
static int apaDisk(void *ctx)
{ (void)ctx; return hddFormat(); }
static void progress(void *ctx, const char *stage, uint32_t done, uint32_t total)
{ (void)ctx; dashWorkerStatus(stage, done, total); }

int hddFormatDisk(const HddFormatPlan *plan, int *started)
{
    HddFormatIo io = {NULL, readDisk, writeDisk, zeroDisk, flushDisk, apaDisk, progress};
    int ret, finish;
    *started = 0;
    packet.sectors = plan->sectors;
    ret = call(HF_BEGIN, 0, 0, 64, 64);
    if (ret < 0) return ret;
    *started = 1;
    ret = hddFormatExecute(plan, &io);
    finish = call(HF_FINISH, 0, 0, 64, 64);
    return ret < 0 ? ret : finish;
}

static int readApa(void *context, uint32_t lba, void *sector)
{
    hddAtaTransfer_t transfer __attribute__((aligned(64)));
    memset(&transfer, 0, sizeof(transfer));
    transfer.lba = lba; transfer.size = 1;
    return fileXioDevctl(context, HDIOC_READSECTOR, &transfer, sizeof(transfer), sector, 512);
}

int hddGetApaCapacity(uint32_t *sectors)
{
    int total = fileXioDevctl("hdd0:", HDIOC_TOTALSECTOR, NULL, 0, NULL, 0);
    if (total >= -4095 && total <= 0) return total ? total : -ENODEV;
    return hddApaLimit(readApa, "hdd0:", (uint32_t)total, sectors);
}

int hddCheckAllocation(uint32_t sectors)
{
    int total = fileXioDevctl("hdd0:", HDIOC_TOTALSECTOR, NULL, 0, NULL, 0);
    if (total >= -4095 && total <= 0) return total ? total : -ENODEV;
    return hddApaCanAllocate(readApa, "hdd0:", (uint32_t)total, sectors);
}
