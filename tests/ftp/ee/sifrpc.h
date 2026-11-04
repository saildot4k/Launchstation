#ifndef FTP_EE_SIFRPC_H
#define FTP_EE_SIFRPC_H
/* Pointer is opaque to the EE client; the transport checks command/wire sizes. */
typedef struct {
	void *server;
} SifRpcClientData_t;
int SifBindRpc(SifRpcClientData_t *, int, int);
int SifCallRpc(SifRpcClientData_t *, int, int, void *, int, void *, int, void (*)(void *), void *);
#endif
