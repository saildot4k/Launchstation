/* Keep GS rendering on its owner thread while the IOP processes a request.
 * Linker wrapping includes calls made inside PS2SDK clients (fileXio,
 * loadfile, libmc, audsrv, etc.), without changing their public blocking
 * contracts, result buffers, callbacks or fileXio's 64-bit seek results.
 *
 * Only the dashboard thread may cooperate, and only between complete frames.
 * A wait frame performs no input, audio, housekeeping, job dispatch or IO.
 * In particular it must never re-enter the client whose RPC buffer/lock is
 * in use. Original NOWAIT requests and background threads pass through.
 */
#include "dash_internal.h"
#include "save_archive.h"

static int io_owner = -1;
static int io_waiting;
static u64 io_next_frame;

extern int __real_sceSifCallRpc(SifRpcClientData_t *, int, int, void *, int,
                              void *, int, SifRpcEndFunc_t, void *);
extern int __real_sceSifBindRpc(SifRpcClientData_t *, int, int);
extern int __real_mcSync(int, int *, int *);
extern int __real_xfromSync(int, int *, int *);
extern int __real_SifIopReset(const char *, int);
extern int __real_SifIopSync(void);
extern s32 __real_DelayThread(s32);
extern int __real_saveArchiveParse(SaveArchive *, uint8_t *, size_t, const char *);
extern int __real_saveArchiveBuild(const SaveArchive *, int, uint8_t **, size_t *);

void dashIoInit(void)
{
	io_owner = GetThreadId();
	io_next_frame = Timer() + 16;
}

int dashIoBusy(void)
{
	return io_waiting;
}

int DashIoBusy(void)
{
	return io_waiting || dashWorkerIoBusy() || dashIopParked() ||
	       (io_owner >= 0 && DashIsActive() && !dashGfxCanYield());
}

static int canCooperate(void)
{
	return io_owner >= 0 && GetThreadId() == io_owner && DashIsActive() &&
	       !io_waiting && dashGfxCanYield();
}

static s32 waitFrame(void)
{
	u64 now = Timer();
	if (now >= io_next_frame) {
		io_next_frame = now + 16;
		dashLoadingRedraw();
	}
	/* Do not add a frame's latency to every small read or metadata request.
	 * Interrupts complete the RPC; short sleeps also give the worker time. */
	return __real_DelayThread(250);
}

static void rpcComplete(void *unused)
{
	(void)unused;
}

int __wrap_sceSifCallRpc(SifRpcClientData_t *cd, int number, int mode,
                       void *send, int send_size, void *receive, int receive_size,
                       SifRpcEndFunc_t complete, void *arg)
{
	int result;
	if ((mode & SIF_RPC_M_NOWAIT) || !canCooperate())
		return __real_sceSifCallRpc(cd, number, mode, send, send_size,
		                          receive, receive_size, complete, arg);
	io_waiting++;
	/* A callback forces the same RPC_END interrupt used by a blocking call.
	 * Keep SDK callbacks: fileXio/libmc finish unaligned reads there. */
	result = __real_sceSifCallRpc(cd, number, mode | SIF_RPC_M_NOWAIT,
	                            send, send_size, receive, receive_size,
	                            complete ? complete : rpcComplete, arg);
	if (result >= 0)
		while (SifCheckStatRpc(cd)) waitFrame();
	io_waiting--;
	return result;
}

int __wrap_sceSifBindRpc(SifRpcClientData_t *cd, int server, int mode)
{
	int result;
	if ((mode & SIF_RPC_M_NOWAIT) || !canCooperate())
		return __real_sceSifBindRpc(cd, server, mode);
	io_waiting++;
	result = __real_sceSifBindRpc(cd, server, mode | SIF_RPC_M_NOWAIT);
	if (result >= 0)
		while (SifCheckStatRpc(cd)) waitFrame();
	io_waiting--;
	return result;
}

static int cardSync(int (*sync)(int, int *, int *), int mode, int *command, int *result)
{
	int state;
	if (mode != 0 || !canCooperate()) return sync(mode, command, result);
	io_waiting++;
	while ((state = sync(1, command, result)) == 0) waitFrame();
	io_waiting--;
	return state; /* Preserve success, no-command and device error results. */
}

int __wrap_mcSync(int mode, int *command, int *result)
{
	return cardSync(__real_mcSync, mode, command, result);
}

int __wrap_xfromSync(int mode, int *command, int *result)
{
	return cardSync(__real_xfromSync, mode, command, result);
}

static void resetPoll(int ready)
{
	if (!ready && canCooperate()) {
		io_waiting++;
		waitFrame();
		io_waiting--;
	}
}

int __wrap_SifIopReset(const char *args, int mode)
{
	int ready = __real_SifIopReset(args, mode);
	resetPoll(ready);
	return ready;
}

int __wrap_SifIopSync(void)
{
	int ready = __real_SifIopSync();
	resetPoll(ready);
	return ready;
}

s32 __wrap_DelayThread(s32 usec)
{
	u64 deadline;
	int result = 0;
	if (usec < 1000 || !canCooperate()) return __real_DelayThread(usec);
	/* Timer has millisecond precision. Include the partial starting tick
	 * so a hardware settling delay never returns earlier than requested. */
	deadline = Timer() + ((u64)usec + 999) / 1000 + 1;
	io_waiting++;
	do {
		result = waitFrame();
		if (result < 0) break;
	} while (Timer() < deadline);
	io_waiting--;
	return result;
}

/* Archive codecs are EE work, independent of the IOP. They use bounded
 * stacks and never show dialogs or perform file IO. The caller's snapshot
 * remains alive until this job has finished; Cut/delete stays on the UI
 * thread, after encoding and writing have both succeeded. */
typedef struct {
	SaveArchive *save;
	uint8_t *data;
	size_t size;
	const char *filename;
	const SaveArchive *source;
	int format;
	uint8_t **output;
	size_t *length;
	int result;
} CodecJob;

static void codecRun(void *arg)
{
	CodecJob *job = arg;
	if (job->source)
		job->result = __real_saveArchiveBuild(job->source, job->format, job->output, job->length);
	else
		job->result = __real_saveArchiveParse(job->save, job->data, job->size, job->filename);
}

static int codecWait(CodecJob *job)
{
	int id;
	if (!canCooperate()) { codecRun(job); return job->result; }
	io_waiting++;
	/* Drain existing file jobs before handing over the snapshot. Applying
 * callbacks here is safe; an RPC wait never pumps or dispatches jobs. */
	while (dashWorkerBusy()) {
		dashWorkerPump();
		waitFrame();
	}
	id = dashWorkerSubmit("Processing save", 0, codecRun, NULL, job);
	if (id < 0) codecRun(job);
	else while (!dashWorkerDone(id)) {
		dashWorkerPump();
		waitFrame();
	}
	io_waiting--;
	return job->result;
}

int __wrap_saveArchiveParse(SaveArchive *save, uint8_t *data, size_t size, const char *filename)
{
	CodecJob job = {.save = save, .data = data, .size = size, .filename = filename};
	return codecWait(&job);
}

int __wrap_saveArchiveBuild(const SaveArchive *save, int format, uint8_t **output, size_t *length)
{
	CodecJob job = {.source = save, .format = format, .output = output, .length = length};
	return codecWait(&job);
}
