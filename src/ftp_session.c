/* EE transport/lifecycle for the exclusive FTP file-transfer service. */
#ifdef ETH
#include "launchelf.h"
#include "init.h"
#include "ftp_session.h"
#include <delaythread.h>
#include <sifrpc.h>
#include <string.h>

static SifRpcClientData_t client __attribute__((aligned(64)));
static LsFtpStatus packet __attribute__((aligned(64)));
static unsigned int generation;
static int bound, owned;
static const char *error_text;

const char *ftpSessionError(void)
{
	return error_text ? error_text : "FTP could not be started.";
}

int ftpSessionBegin(void)
{
	bound = owned = 0;
	error_text = NULL;
	if (pcCardCfOwnsBus()) {
		error_text = "PC CARD CompactFlash is using the network adapter.";
		return 0;
	}
	/* Keep IPCONFIG cached in EE memory before removing its boot device. */
	getIpConfig();
	/* Quiesce MMCE/MX4SIO hooks and old PFS mounts. The existing reset path
	 * restores core I/O, PADMAN and both controller ports for Stop FTP. */
	generation = getIopResetGeneration();
	rebootIopAndReloadCoreStackSilent();
	if (generation == getIopResetGeneration()) {
		error_text = "FTP needs a fresh IOP session. IOP reboot was unavailable.";
		return 0;
	}
	owned = 1;
	generation = getIopResetGeneration();
	loadNetModules();
	if (!isFtpNetworkReady()) {
		error_text = dashboardIpNetworkError();
		return 0;
	}
	memset(&client, 0, sizeof(client));
	for (int attempt = 0; attempt < 1000; attempt++) {
		if (SifBindRpc(&client, LS_FTP_RPC_ID, 0) < 0)
			break;
		if (client.server) {
			bound = 1;
			return 1;
		}
		DelayThread(1000);
	}
	error_text = "FTP control service did not start.";
	return 0;
}

static int exchange(int command, LsFtpStatus *out)
{
	if (!bound || generation != getIopResetGeneration()) {
		error_text = "FTP's IOP session ended.";
		return 0;
	}
	memset(&packet, 0, sizeof(packet));
	if (SifCallRpc(&client, command, 0, NULL, 0, &packet, sizeof(packet), NULL, NULL) < 0 ||
		packet.version != LS_FTP_PROTOCOL_VERSION) {
		error_text = "Could not communicate with FTP.";
		return 0;
	}
	if (out)
		memcpy(out, &packet, sizeof(packet));
	return 1;
}
int ftpSessionQuery(LsFtpStatus *out)
{
	return exchange(LS_FTP_STATUS, out);
}
int ftpSessionStop(void)
{
	return exchange(LS_FTP_STOP, NULL);
}
void ftpSessionEnd(void)
{
	bound = 0;
	/* Also releases the control RPC thread and all eagerly loaded drivers. */
	if (owned)
		rebootIopAndReloadCoreStackSilent();
	owned = 0;
	memset(&client, 0, sizeof(client));
}
#endif
