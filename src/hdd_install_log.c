/* Temporary installer diagnostics. Keep the UI responsive even when writing
 * the log blocks: snapshots only hold an EE semaphore for small RAM copies. */
#include "launchelf.h"
#include "dash_internal.h"
#include "hdd_install.h"
#include <stdarg.h>

static struct {
    char lines[HDD_INSTALL_LOG_ROWS][HDD_INSTALL_LOG_COLS];
    unsigned next, saved;
    u64 started, changed, sampled, stopped, io_started;
    unsigned io_lba, io_count;
    int io_command, io_pending, io_result;
    char status[192], path[1024];
    int done, total, disk_error, active;
} log_state;
static int log_sema = -1;

static void lock(void) { if (log_sema >= 0) WaitSema(log_sema); }
static void unlock(void) { if (log_sema >= 0) SignalSema(log_sema); }
int hddInstallLogEnabled(void) { return log_state.active; }
void hddInstallLogStart(void)
{
    if (log_sema < 0) {
        ee_sema_t sema;
        memset(&sema, 0, sizeof(sema)); sema.init_count = sema.max_count = 1;
        log_sema = CreateSema(&sema);
    }
    if (log_sema < 0) return;
    lock(); memset(&log_state, 0, sizeof(log_state));
    log_state.active = 1; log_state.started = log_state.changed = Timer(); unlock();
    hddInstallLog("Verbose PSBBN DP installer diagnostics enabled");
}
void hddInstallLogStop(void) { lock(); log_state.stopped = Timer(); log_state.active = 0; unlock(); }
void hddInstallLog(const char *format, ...)
{
    char text[1024];
    const char *p;
    va_list args;
    u64 elapsed;
    if (!log_state.active) return;
    va_start(args, format); vsnprintf(text, sizeof(text), format, args); va_end(args);
    text[sizeof(text) - 1] = 0;
    lock();
    log_state.changed = Timer();
    elapsed = log_state.changed - log_state.started;
    p = text;
    do {
        char *line = log_state.lines[log_state.next++ % HDD_INSTALL_LOG_ROWS];
        unsigned used = snprintf(line, HDD_INSTALL_LOG_COLS, "[%5u.%03u] %s",
                                  (unsigned)(elapsed / 1000), (unsigned)(elapsed % 1000), p == text ? "" : "  ");
        while (*p && *p != '\n' && used + 1 < HDD_INSTALL_LOG_COLS) {
            unsigned char c = (unsigned char)*p++;
            line[used++] = c < 32 ? ' ' : c;
        }
        line[used] = 0;
        if (*p == '\n') p++;
    } while (*p);
    unlock();
}
void hddInstallStatus(const char *text, int done, int total)
{
    int record = 0;
    u64 now;
    dashWorkerStatus(text, done, total);
    if (!log_state.active) return;
    now = Timer();
    lock();
    if (text && strcmp(log_state.status, text)) { record = 1; log_state.sampled = now; }
    else if (done != log_state.done && (now - log_state.sampled >= 2000 || (total > 0 && done >= total))) {
        record = 1; log_state.sampled = now;
    }
    if ((text && strcmp(log_state.status, text)) || done != log_state.done || total != log_state.total)
        log_state.changed = now;
    if (text) snprintf(log_state.status, sizeof(log_state.status), "%s", text);
    log_state.done = done; log_state.total = total;
    unlock();
    if (record) hddInstallLog("%s [done=%d total=%d]", text ? text : "", done, total);
}
void hddInstallRawTrace(int command, uint32_t lba, unsigned count, int pending, int result)
{
    if (!log_state.active) return;
    lock();
    log_state.io_command = command; log_state.io_lba = lba; log_state.io_count = count;
    log_state.io_pending = pending; log_state.io_result = result;
    log_state.changed = Timer();
    if (pending) log_state.io_started = log_state.changed;
    unlock();
}
void hddInstallLogSnapshot(HddInstallLogSnapshot *out)
{
    u64 now = Timer();
    lock();
    out->next = log_state.next;
    out->first = out->next > HDD_INSTALL_LOG_ROWS ? out->next - HDD_INSTALL_LOG_ROWS : 0;
    out->elapsed = (log_state.active ? now : log_state.stopped) - log_state.started;
    out->idle = now - log_state.changed;
    out->io[0] = 0;
    if (log_state.io_command) {
        if (log_state.io_pending)
            snprintf(out->io, sizeof(out->io), "RAW cmd=%d LBA=%u sectors=%u WAITING %u s", log_state.io_command,
                     log_state.io_lba, log_state.io_count, (unsigned)((now - log_state.io_started) / 1000));
        else snprintf(out->io, sizeof(out->io), "Last RAW cmd=%d LBA=%u sectors=%u rc=%d", log_state.io_command,
                      log_state.io_lba, log_state.io_count, log_state.io_result);
    }
    out->done = log_state.done; out->total = log_state.total; out->disk_error = log_state.disk_error;
    memcpy(out->status, log_state.status, sizeof(out->status)); memcpy(out->path, log_state.path, sizeof(out->path));
    unlock();
}
int hddInstallLogRead(unsigned index, char line[HDD_INSTALL_LOG_COLS])
{
    int exists;
    lock();
    exists = index < log_state.next && log_state.next - index <= HDD_INSTALL_LOG_ROWS;
    if (exists) memcpy(line, log_state.lines[index % HDD_INSTALL_LOG_ROWS], HDD_INSTALL_LOG_COLS);
    unlock(); return exists;
}
static int writeLog(int fd, const char *text, unsigned size)
{
    unsigned done = 0;
    while (done < size) {
        int n = genWrite(fd, (void *)(text + done), size - done);
        if (n <= 0 || (unsigned)n > size - done) return n < 0 ? n : -EIO;
        done += n;
    }
    return 0;
}
void hddInstallLogFlush(HddInstall *in)
{
    HddInstallLogSnapshot snap;
    char path[sizeof(log_state.path)], line[HDD_INSTALL_LOG_COLS + 1];
    unsigned next, written;
    int fd, ret = 0, previous;
    if (!log_state.active || !in->owned || !in->stage[0]) return;
    if (snprintf(path, sizeof(path), "%s/INSTALLER.LOG", in->stage) >= (int)sizeof(path)) return;
    hddInstallLogSnapshot(&snap);
    lock(); next = log_state.saved; unlock();
    if (next == snap.next) return;
    fd = genOpen(path, FIO_O_WRONLY | FIO_O_CREAT | FIO_O_APPEND);
    if (fd < 0) ret = fd;
    else {
        if (next < snap.first) {
            snprintf(line, sizeof(line), "[log] %u older lines left the RAM buffer before saving\n", snap.first - next);
            ret = writeLog(fd, line, strlen(line)); next = snap.first;
        }
        written = next;
        while (ret >= 0 && next < snap.next) {
            if (!hddInstallLogRead(next, line)) { ret = -EAGAIN; break; }
            { unsigned length = strlen(line); line[length] = '\n'; line[length + 1] = 0; }
            ret = writeLog(fd, line, strlen(line));
            if (ret >= 0) written = ++next;
        }
        { int closed = genClose(fd); if (ret >= 0) ret = closed; }
        if (ret >= 0) { lock(); log_state.saved = written; unlock(); }
    }
    lock(); previous = log_state.disk_error; log_state.disk_error = ret < 0 ? ret : 0;
    if (ret >= 0) snprintf(log_state.path, sizeof(log_state.path), "%s", path);
    unlock();
    if (ret < 0 && ret != previous) hddInstallLog("LOG WRITE ERROR %d; diagnostics remain in RAM", ret);
}
