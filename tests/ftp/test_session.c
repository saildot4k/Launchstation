/* Exercise the production EE session and modal with a deterministic IOP peer. */
#include "dash_internal.h"
#include "dash_sound.h"
#include "ftp_session.h"
#include "init.h"
#include "main_title.h"
#include <assert.h>
#include <sifrpc.h>
char ip[16] = "192.168.1.10";
static unsigned int generation;
static int cf, can_reset = 1, ready, binds, calls, resets, server_state, stop_calls, frames, inputs, messages;
static int missing_rpc, bad_version, fail_calls, loading, worker_busy;
static unsigned int stop_button = DASH_IN_BACK;
static u64 clock_ms;
static int history_mode, drawn_history, drawn_clients, history_frames;
static float history_y;
static void clear(void)
{
	cf = ready = binds = calls = resets = stop_calls = frames = inputs = messages = 0;
	missing_rpc = bad_version = fail_calls = loading = worker_busy = 0;
	server_state = LS_FTP_RUNNING;
	clock_ms = 0;
	can_reset = 1;
	history_mode = drawn_history = drawn_clients = history_frames = 0;
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
	s->version = bad_version ? LS_FTP_PROTOCOL_VERSION - 1 : LS_FTP_PROTOCOL_VERSION;
	s->state = server_state;
	if (history_mode) {
		s->clients = 1;
		s->transfers = 2;
		s->bytes_low = 4096;
		const char *commands[] = {"PWD", "CWD /usb0", "TYPE I"};
		for (int i = 0; i < LS_FTP_HISTORY_COUNT; i++) {
			LsFtpCommand *entry = &s->history[i];
			entry->year = history_mode == 1 ? 2026 : 0;
			entry->month = 10;
			entry->day = 31;
			entry->hour = 16;
			entry->minute = 59;
			entry->second = 58 - i;
			strcpy(entry->text, commands[i]);
		}
	}
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
	drawn_history = drawn_clients = 0;
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
int menuTitleConvertTimestampToLocalTime(int *year, int *month, int *day,
										int *hour, int *minute, int *second)
{
	assert(*year == 2026 && *month == 10 && *day == 31 && *hour == 16 && *minute == 59);
	assert(*second >= 56 && *second <= 58);
	/* A UTC-8 console displays the prior local day for this JST timestamp. */
	*day = 30;
	*hour = 23;
	return 1;
}
void dashTextFit(float a, float b, float c, const char *s, float d, int e)
{
	(void)a;
	(void)c;
	(void)d;
	(void)e;
	if (!history_mode)
		return;
	if (!strncmp(s, "FTP clients:", 12)) {
		assert(!strcmp(s, "FTP clients: 1    Active transfers: 2"));
		drawn_clients++;
	} else if (s[2] == ':' && s[5] == ':') {
		const char *expected[] = {"PWD", "CWD /usb0", "TYPE I"};
		char line[160];
		assert(drawn_history < LS_FTP_HISTORY_COUNT);
		if (history_mode == 1)
			snprintf(line, sizeof(line), "23:59:%02d  %s", 58 - drawn_history, expected[drawn_history]);
		else
			snprintf(line, sizeof(line), "--:--:--  %s", expected[drawn_history]);
		assert(!strcmp(s, line));
		if (drawn_history)
			assert(b >= history_y + 24);
		history_y = b;
		drawn_history++;
	} else if (!strncmp(s, "Transferred:", 12)) {
		assert(!strcmp(s, "Transferred: 4 KB") && drawn_history == LS_FTP_HISTORY_COUNT);
		assert(b >= history_y + 24);
	}
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
	if (history_mode) {
		assert(drawn_clients == 1 && drawn_history == LS_FTP_HISTORY_COUNT);
		history_frames++;
	}
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
	if (inputs == 4) {
		assert(!stop_calls && server_state == LS_FTP_RUNNING);
		in->pressed = DASH_IN_BACK;
	}
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
	assert(DashFtpServer() && inputs == 4 && stop_calls == 1 && resets == 2);
	clear();
	fail_calls = 1;
	assert(!DashFtpServer() && resets == 2 && messages == 1 && !loading);
	for (int mode = 1; mode <= 2; mode++) {
		clear();
		history_mode = mode;
		stop_button = DASH_IN_BACK;
		assert(DashFtpServer() && history_frames >= 3 && stop_calls == 1 && !loading && !messages);
	}
	puts("PASS: timestamped command rendering, local clock conversion, unknown-clock fallback and separate transfer status");
	puts("PASS: EE FTP startup/reset gates, bounded bind, stale-session guard, protocol validation and "
		 "exclusive Stop screen");
}
