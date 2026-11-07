#ifndef LAUNCHSTATION_FTP_PROTOCOL_H
#define LAUNCHSTATION_FTP_PROTOCOL_H
/* Fixed-width EE/IOP wire layout. No pointers or SDK-specific structures. */
#define LS_FTP_RPC_ID 0x4c534654
#define LS_FTP_PROTOCOL_VERSION 2
#define LS_FTP_HISTORY_COUNT 3
#define LS_FTP_STATUS 1
#define LS_FTP_STOP 2
#define LS_FTP_RUNNING 1
#define LS_FTP_STOPPING 2
#define LS_FTP_STOPPED 3
typedef struct {
	/* PS2 RTC date/time (JST); year == 0 means the clock was unavailable. */
	int year, month, day, hour, minute, second;
	char text[128];
} LsFtpCommand;
typedef struct {
	unsigned int version;
	/* Distinct source IPv4 addresses across live FTP control connections. */
	int state, error, clients, transfers;
	unsigned int bytes_low, bytes_high;
	LsFtpCommand history[LS_FTP_HISTORY_COUNT]; /* Newest first. */
	unsigned int reserved[7]; /* Whole 64-byte cache lines for SIF DMA. */
} LsFtpStatus;
#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(LsFtpStatus) == 512, "FTP status wire layout must be 512 bytes");
#endif
#endif
