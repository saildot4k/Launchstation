/* FTP status and cooperative shutdown, independently of blocked data sockets. */
#include "FtpControl.h"
#include "FtpServer.h"
#include "irx_imports.h"
#ifndef FTP_CONTROL_TEST
#include <sifrpc.h>
#endif
#include <errno.h>
static FtpServer *server;
static volatile int state, last_error;
static LsFtpCommand history[LS_FTP_HISTORY_COUNT];
static LsFtpStatus reply __attribute__((aligned(64)));
int FtpControl_Stopping(void)
{
	return state != LS_FTP_RUNNING;
}
static int clockByte(unsigned char value)
{
	if ((value & 15) > 9 || (value >> 4) > 9)
		return -1;
	return (value >> 4) * 10 + (value & 15);
}
void FtpControl_Operation(const char *text)
{
	LsFtpCommand entry;
	sceCdCLOCK clock;
	int intr;
	memset(&entry, 0, sizeof(entry));
	strncpy(entry.text, text, sizeof(entry.text) - 1);
	/* Clock reads can yield. Capture the event before entering the short
	 * critical section that publishes the complete history atomically. */
	if (sceCdReadClock(&clock) && !clock.stat) {
		entry.year = 2000 + clockByte(clock.year);
		entry.month = clockByte(clock.month & 0x7f);
		entry.day = clockByte(clock.day);
		entry.hour = clockByte(clock.hour);
		entry.minute = clockByte(clock.minute);
		entry.second = clockByte(clock.second);
		if (entry.year < 2000 || entry.month < 1 || entry.month > 12 ||
			entry.day < 1 || entry.day > 31 || entry.hour < 0 || entry.hour > 23 ||
			entry.minute < 0 || entry.minute > 59 || entry.second < 0 || entry.second > 59)
			entry.year = 0;
	}
	CpuSuspendIntr(&intr);
	memmove(&history[1], &history[0], (LS_FTP_HISTORY_COUNT - 1) * sizeof(history[0]));
	history[0] = entry;
	CpuResumeIntr(intr);
}
void *FtpControl_Exchange(int command, void *data, int size)
{
	int intr;
	CpuSuspendIntr(&intr);
	if (command == LS_FTP_STOP && state == LS_FTP_RUNNING)
		state = LS_FTP_STOPPING;
	(void)data;
	(void)size;
	memset(&reply, 0, sizeof(reply));
	reply.version = LS_FTP_PROTOCOL_VERSION;
	reply.state = state;
	reply.error = last_error;
	memcpy(reply.history, history, sizeof(history));
	if (server)
		for (int i = 0; i < MAX_CLIENTS; i++) {
			FtpClient *client = &server->m_kClientArray[i];
			if (!client->m_pServer)
				continue;
			int unique = 1;
			for (int j = 0; j < i; j++) {
				FtpClient *other = &server->m_kClientArray[j];
				if (other->m_pServer && other->m_uiPeerAddress == client->m_uiPeerAddress) {
					unique = 0;
					break;
				}
			}
			reply.clients += unique;
			if (client->m_eDataMode != DATAMODE_IDLE) {
				u64 bytes = ((u64)reply.bytes_high << 32) | reply.bytes_low;
				reply.transfers++;
				bytes += client->m_uiDataOffset;
				reply.bytes_low = (unsigned int)bytes;
				reply.bytes_high = (unsigned int)(bytes >> 32);
			}
		}
	CpuResumeIntr(intr);
	/* Socket APIs may yield; never call them with interrupts disabled. Only
	 * the FTP owner closes files/clients, after the current driver call. */
	if (command == LS_FTP_STOP && server)
		for (int i = 0; i < MAX_CLIENTS; i++) {
			FtpClient *client = &server->m_kClientArray[i];
			if (!client->m_pServer)
				continue;
			if (client->m_iControlSocket >= 0)
				lwip_shutdown(client->m_iControlSocket, 2);
			if (client->m_iDataSocket >= 0)
				lwip_shutdown(client->m_iDataSocket, 2);
		}
	return &reply;
}
void FtpControl_Stopped(void)
{
	state = LS_FTP_STOPPED;
}
void FtpControl_Error(int error)
{
	if (error < 0)
		last_error = error;
}
#ifndef FTP_CONTROL_TEST
static SifRpcDataQueue_t queue;
static SifRpcServerData_t rpc;
static unsigned char rpc_buffer[sizeof(LsFtpStatus)] __attribute__((aligned(64)));
static void control_thread(void *arg)
{
	(void)arg;
	sceSifSetRpcQueue(&queue, GetThreadId());
	sceSifRegisterRpc(&rpc, LS_FTP_RPC_ID, FtpControl_Exchange, rpc_buffer, NULL, NULL, &queue);
	sceSifRpcLoop(&queue);
}
#endif
int FtpControl_Init(FtpServer *owner)
{
	server = owner;
	state = LS_FTP_RUNNING;
	last_error = 0;
	memset(history, 0, sizeof(history));
#ifndef FTP_CONTROL_TEST
	iop_thread_t thread;
	int id;
	memset(&thread, 0, sizeof(thread));
	thread.attr = TH_C;
	thread.thread = control_thread;
	thread.stacksize = 0x1000;
	thread.priority = 0x42;
	id = CreateThread(&thread);
	if (id < 0)
		return id;
	if (StartThread(id, NULL) < 0) {
		DeleteThread(id);
		return -EIO;
	}
#endif
	return 0;
}
