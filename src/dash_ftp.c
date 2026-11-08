/* Exclusive FTP screen: status rendering and Stop; no dashboard storage work. */
#ifdef ETH
#include "dash_internal.h"
#include "dash_sound.h"
#include "ftp_session.h"
#include "init.h"
#include "main_title.h"

static void ftpFrame(const LsFtpStatus *status, int stopping)
{
	char line[160];
	const float w = 490, h = 330, x = (DASH_VW - w) * 0.5f, y = (DASH_VH - h) * 0.5f;
	dashVisualUpdate();
	dashGfxBeginFrame();
	dashBgDraw();
	dashModalBackdrop(1.0f);
	dashModalPanel(x, y, w, h, 1.0f);
	dashIcon(DI_NETWORK, x + 24, y + 22, 24, DASH_C_ACCENT);
	dashTextS(x + 60, y + 24, stopping ? "Stopping FTP" : "FTP server running", DASH_FS_LABEL, DASH_C_TEXT);
	snprintf(line, sizeof(line), "IP address: %s    Port: 21", ip);
	dashTextFit(x + 24, y + 65, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT);
	snprintf(line, sizeof(line), "FTP clients: %d    Active transfers: %d", status->clients,
			 status->transfers);
	dashTextFit(x + 24, y + 93, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT2);
	dashTextS(x + 24, y + 125, "Recent commands", DASH_FS_SMALL, DASH_C_TEXT3);
	if (!status->history[0].text[0])
		dashTextFit(x + 24, y + 150, w - 48,
					status->clients ? "Waiting for a command" : "Waiting for a connection",
					DASH_FS_SMALL, DASH_C_TEXT2);
	for (int i = 0; i < LS_FTP_HISTORY_COUNT; i++) {
		const LsFtpCommand *command = &status->history[i];
		int year = command->year, month = command->month, day = command->day;
		int hour = command->hour, minute = command->minute, second = command->second;
		if (!command->text[0])
			break;
		if (year && menuTitleConvertTimestampToLocalTime(&year, &month, &day, &hour, &minute, &second))
			snprintf(line, sizeof(line), "%02d:%02d:%02d  %s", hour, minute, second, command->text);
		else
			snprintf(line, sizeof(line), "--:--:--  %s", command->text);
		dashTextFit(x + 24, y + 150 + i * 24, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT2);
	}
	if (status->transfers) {
		u64 bytes = ((u64)status->bytes_high << 32) | status->bytes_low;
		snprintf(line, sizeof(line), "Transferred: %llu KB", (unsigned long long)(bytes / 1024));
		dashTextFit(x + 24, y + 228, w - 48, line, DASH_FS_SMALL, DASH_C_TEXT2);
	}
	dashTextFit(x + 24, y + 258, w - 48,
				stopping ? "Closing files and connections..." : "Stop FTP to return to Launchstation.",
				DASH_FS_SMALL, DASH_C_TEXT3);
	if (!stopping)
		dashModalHintRow(x + 24, y + h - 42, 0, NULL, dashBackIcon(), "Cancel");
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
		if (!stopping && (input.pressed & DASH_IN_BACK)) {
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
