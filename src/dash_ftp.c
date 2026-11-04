/* Exclusive FTP screen: status rendering and Stop; no dashboard storage work. */
#ifdef ETH
#include "dash_internal.h"
#include "dash_sound.h"
#include "ftp_session.h"
#include "init.h"

static void ftpFrame(const LsFtpStatus *status, int stopping)
{
	char line[160];
	const float w = 490, h = 260, x = (DASH_VW - w) * 0.5f, y = (DASH_VH - h) * 0.5f;
	dashVisualUpdate();
	dashGfxBeginFrame();
	dashBgDraw();
	dashModalBackdrop(1.0f);
	dashModalPanel(x, y, w, h, 1.0f);
	dashIcon(DI_NETWORK, x + 24, y + 22, 24, DASH_C_ACCENT);
	dashTextS(x + 60, y + 24, stopping ? "Stopping FTP" : "FTP server running", DASH_FS_LABEL, DASH_C_TEXT);
	snprintf(line, sizeof(line), "IP address: %s    Port: 21", ip);
	dashTextFit(x + 24, y + 65, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT);
	snprintf(line, sizeof(line), "Connected clients: %d    Active transfers: %d", status->clients,
			 status->transfers);
	dashTextFit(x + 24, y + 93, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT2);
	dashTextFit(x + 24, y + 125, w - 48,
				status->operation[0] ? status->operation : "Waiting for a connection", DASH_FS_SMALL,
				DASH_C_TEXT2);
	if (status->transfers) {
		u64 bytes = ((u64)status->bytes_high << 32) | status->bytes_low;
		snprintf(line, sizeof(line), "Transferred: %llu KB", (unsigned long long)(bytes / 1024));
		dashTextFit(x + 24, y + 150, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT2);
	}
	dashTextFit(x + 24, y + 181, w - 48,
				stopping ? "Closing files and connections..." : "Stop FTP to return to Launchstation.",
				DASH_FS_SMALL, DASH_C_TEXT3);
	if (!stopping)
		dashModalHintRow(x + 24, y + h - 42, dashOkIcon(), "Stop FTP", dashBackIcon(), "Stop FTP");
	dashGfxPresent();
}

int DashFtpServer(void)
{
	LsFtpStatus status;
	int stopping = 0, ok = 1;
	u64 next_poll = 0;
	/* No worker callbacks, device probes, artwork IO, remote launch commands
	 * or ISO receiver polling run inside this screen. Rendering and controller input remain. */
	if (!dashWorkerAwaitAll("Preparing FTP Server"))
		return 0;
	filerRootMcPollIdle();
	dashLoadingBegin("Starting FTP Server");
	dashLoadingFrame("Preparing supported devices and controllers", 0, 0);
	if (!ftpSessionBegin()) {
		ftpSessionEnd();
		dashLoadingEnd();
		dashModalMessage(DI_WARNING, "FTP Server", ftpSessionError(), NULL);
		return 0;
	}
	/* The FTP panel owns rendering, while this flag also prevents theme
	 * texture getters from submitting fresh disk work during background draws. */
	memset(&status, 0, sizeof(status));
	status.state = LS_FTP_RUNNING;
	dashInputFlush();
	while (status.state != LS_FTP_STOPPED) {
		DashInput input;
		dashInputPoll(&input);
		if (!stopping && (input.pressed & (DASH_IN_OK | DASH_IN_BACK))) {
			stopping = 1;
			dashSoundPlay(DASH_SND_CANCEL);
			if (!ftpSessionStop()) {
				ok = 0;
				break;
			}
			next_poll = 0;
		}
		if (Timer() >= next_poll) {
			if (!ftpSessionQuery(&status)) {
				ok = 0;
				break;
			}
			next_poll = Timer() + 100;
		}
		ftpFrame(&status, stopping);
	}
	/* The IOP owner acknowledges STOPPED only after files and PFS mounts close. */
	ftpSessionEnd();
	dashLoadingEnd();
	dashInputFlush();
	if (!ok)
		dashModalMessage(DI_WARNING, "FTP Server", ftpSessionError(), NULL);
	else if (status.error < 0)
		dashModalMessage(DI_WARNING, "FTP Server",
						 "FTP stopped, but a file or partition could not be closed.", NULL);
	return ok;
}
#else
int DashFtpServer(void)
{
	return 0;
}
#endif
