#ifndef FTP_EE_LAUNCHELF_H
#define FTP_EE_LAUNCHELF_H
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef unsigned long long u64;
extern char ip[16];
void filerRootMcPollIdle(void);
void getIpConfig(void);
#endif
