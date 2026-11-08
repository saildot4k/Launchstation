#ifndef FTP_EE_DASH_INTERNAL_H
#define FTP_EE_DASH_INTERNAL_H
#include "launchelf.h"
#define DASH_VW 640
#define DASH_VH 448
#define DI_NETWORK 1
#define DI_WARNING 2
#define DASH_FS_LABEL 0.86f
#define DASH_FS_SMALL 0.66f
#define DASH_C_ACCENT 1
#define DASH_C_TEXT 2
#define DASH_C_TEXT2 3
#define DASH_C_TEXT3 4
#define DASH_IN_OK 1
#define DASH_IN_BACK 2
typedef struct {
	unsigned int pressed;
} DashInput;
float dashVisualUpdate(void);
void dashGfxBeginFrame(void);
void dashBgDraw(void);
void dashModalBackdrop(float);
void dashModalPanel(float, float, float, float, float);
void dashIcon(int, float, float, float, int);
void dashTextS(float, float, const char *, float, int);
void dashTextFit(float, float, float, const char *, float, int);
void dashModalHintRow(float, float, int, const char *, int, const char *);
void dashGfxPresent(void);
int dashOkIcon(void);
int dashBackIcon(void);
int dashWorkerAwaitAll(const char *);
void dashLoadingBegin(const char *);
void dashLoadingFrame(const char *, int, int);
void dashLoadingEnd(void);
void dashModalMessage(int, const char *, const char *, const char *);
void dashInputFlush(void);
void dashInputPoll(DashInput *);
u64 Timer(void);
#endif
