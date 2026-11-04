/* Exercise the production EE session and modal with a deterministic IOP peer. */
#include "dash_internal.h"
#include "dash_sound.h"
#include "ftp_session.h"
#include "init.h"
#include <assert.h>
#include <sifrpc.h>
char ip[16] = "192.168.1.10";
static unsigned int generation;
static int cf, can_reset = 1, ready, binds, calls, resets, server_state, stop_calls, frames, inputs, messages;
static int missing_rpc, bad_version, fail_calls, loading, worker_busy;
static unsigned int stop_button = DASH_IN_BACK;
static u64 clock_ms;
static void clear(void)
{
	cf = ready = binds = calls = resets = stop_calls = frames = inputs = messages = 0;
	missing_rpc = bad_version = fail_calls = loading = worker_busy = 0;
	server_state = LS_FTP_RUNNING;
	clock_ms = 0;
	can_reset = 1;
}
int pcCardCfOwnsBus(void)
{
	return cf;
}
unsigned int getIopResetGeneration(void)
{
	return generation;
}
void rebootIopAndReloadCoreStackSilent(void)
{
	if (can_reset) {
		resets++;
		generation++;
		ready = 0;
	}
}
void getIpConfig(void)
{
	assert(!resets);
}
void loadNetModules(void)
{
	ready = 1;
}
int isFtpNetworkReady(void)
{
	return ready;
}
const char *dashboardIpNetworkError(void)
{
	return "Network failed";
}
int DelayThread(unsigned int delay)
{
	clock_ms += delay / 1000;
	return 0;
}
int SifBindRpc(SifRpcClientData_t *c, int id, int mode)
{
	assert(id == LS_FTP_RPC_ID && mode == 0);
	binds++;
	if (!missing_rpc)
		c->server = c;
	return 0;
}
int SifCallRpc(SifRpcClientData_t *c, int command, int mode, void *in, int inlen, void *out, int outlen,
			   void (*done)(void *), void *arg)
{
	assert(c->server && mode == 0 && !in && !inlen && !done && !arg && outlen == sizeof(LsFtpStatus));
	calls++;
	if (fail_calls)
		return -1;
	if (command == LS_FTP_STOP) {
		stop_calls++;
		server_state = LS_FTP_STOPPING;
	} else {
		assert(command == LS_FTP_STATUS);
		if (server_state == LS_FTP_STOPPING)
			server_state = LS_FTP_STOPPED;
	}
	LsFtpStatus *s = out;
	memset(s, 0, sizeof(*s));
	s->version = bad_version ? 0 : LS_FTP_PROTOCOL_VERSION;
	s->state = server_state;
	return 0;
}
int dashWorkerAwaitAll(const char *s)
{
	(void)s;
	return !worker_busy;
}
void filerRootMcPollIdle(void) {}
float dashVisualUpdate(void)
{
	return 0.016f;
}
void dashGfxBeginFrame(void)
{
	assert(loading);
}
void dashBgDraw(void) {}
void dashModalBackdrop(float a)
{
	(void)a;
}
void dashModalPanel(float a, float b, float c, float d, float e)
{
	(void)a;
	(void)b;
	(void)c;
	(void)d;
	(void)e;
}
void dashIcon(int a, float b, float c, float d, int e)
{
	(void)a;
	(void)b;
	(void)c;
	(void)d;
	(void)e;
}
void dashTextS(float a, float b, const char *s, float c, int d)
{
	(void)a;
	(void)b;
	(void)s;
	(void)c;
	(void)d;
}
void dashTextFit(float a, float b, float c, const char *s, float d, int e)
{
	(void)a;
	(void)b;
	(void)c;
	(void)s;
	(void)d;
	(void)e;
}
void dashModalHintRow(float a, float b, int c, const char *d, int e, const char *f)
{
	(void)a;
	(void)b;
	(void)c;
	(void)d;
	(void)e;
	(void)f;
}
void dashGfxPresent(void)
{
	frames++;
	clock_ms += 100;
	assert(frames < 100);
}
int dashOkIcon(void)
{
	return 1;
}
int dashBackIcon(void)
{
	return 2;
}
void dashLoadingBegin(const char *s)
{
	(void)s;
	loading = 1;
}
void dashLoadingFrame(const char *s, int a, int b)
{
	(void)s;
	(void)a;
	(void)b;
}
void dashLoadingEnd(void)
{
	loading = 0;
}
void dashModalMessage(int a, const char *b, const char *c, const char *d)
{
	(void)a;
	(void)b;
	(void)c;
	(void)d;
	messages++;
}
void dashInputFlush(void) {}
void dashInputPoll(DashInput *in)
{
	in->pressed = ++inputs == 3 ? stop_button : 0;
}
u64 Timer(void)
{
	return clock_ms;
}
void dashSoundPlay(int s)
{
	assert(s == DASH_SND_CANCEL);
}
extern int DashFtpServer(void);
int main(void)
{
	LsFtpStatus status;
	clear();
	cf = 1;
	assert(!ftpSessionBegin());
	ftpSessionEnd();
	assert(!resets && !binds);
	clear();
	can_reset = 0;
	assert(!ftpSessionBegin());
	ftpSessionEnd();
	assert(!ready && !binds);
	clear();
	assert(ftpSessionBegin() && resets == 1 && binds == 1);
	assert(ftpSessionQuery(&status) && status.state == LS_FTP_RUNNING);
	assert(ftpSessionStop() && stop_calls == 1);
	assert(ftpSessionQuery(&status) && status.state == LS_FTP_STOPPED);
	ftpSessionEnd();
	assert(resets == 2);
	clear();
	assert(ftpSessionBegin());
	generation++;
	int before = calls;
	assert(!ftpSessionQuery(&status) && calls == before);
	ftpSessionEnd();
	clear();
	missing_rpc = 1;
	assert(!ftpSessionBegin() && binds == 1000);
	ftpSessionEnd();
	assert(resets == 2);
	clear();
	assert(ftpSessionBegin());
	bad_version = 1;
	assert(!ftpSessionQuery(&status));
	ftpSessionEnd();
	clear();
	worker_busy = 1;
	assert(!DashFtpServer() && !resets && !binds);
	clear();
	assert(DashFtpServer() && frames >= 3 && stop_calls == 1 && resets == 2 && !loading && !messages);
	clear();
	stop_button = DASH_IN_OK;
	assert(DashFtpServer() && stop_calls == 1 && resets == 2);
	clear();
	fail_calls = 1;
	assert(!DashFtpServer() && resets == 2 && messages == 1 && !loading);
	puts("PASS: EE FTP startup/reset gates, bounded bind, stale-session guard, protocol validation and "
		 "exclusive Stop screen");
}
