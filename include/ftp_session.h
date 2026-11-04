#ifndef LAUNCHSTATION_FTP_SESSION_H
#define LAUNCHSTATION_FTP_SESSION_H
#include "ftp_protocol.h"
#ifdef ETH
/* Main thread only. Caller drains background IO before beginning. */
int ftpSessionBegin(void);
int ftpSessionQuery(LsFtpStatus *status);
int ftpSessionStop(void);
void ftpSessionEnd(void); /* Call after STOPPED: restore a clean dashboard IOP. */
const char *ftpSessionError(void);
#endif
#endif
