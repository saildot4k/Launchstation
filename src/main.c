//---------------------------------------------------------------------------
//File name:   main.c
//---------------------------------------------------------------------------
#include "launchelf.h"
#include "init.h"
#include "main_actions.h"
#include "main_boot.h"
#include "main_modules.h"
#include "main_startup.h"
#include "dash.h"
#include "filer_size_cache.h"

int TV_mode;
char LaunchElfDir[MAX_PATH], LaunchElfBootDir[MAX_PATH], mainMsg[MAX_PATH];
char LoadedConfigPath[MAX_PATH], LoadedIPConfigPath[MAX_PATH];
char CNF[MAX_NAME];
int swapKeys;

u64 WaitTime;

char if_conf[IPCONF_MAX_LEN];
int if_conf_len;

char ip[16] = "192.168.0.10";
char netmask[16] = "255.255.255.0";
char gw[16] = "192.168.0.1";

char netConfig[IPCONF_MAX_LEN + 64];  //Adjust size as needed

#ifdef MX4SIO
u8 mx4sio_driver_running = 0;
#endif

u8 console_is_PSX = 0;
u8 boot_show_all_devices = 0;
u8 boot_safe_mode = 0;

static int boot_argc;
static char *boot_argv[8];
static char boot_path[MAX_PATH];

const char *wleBootElfPath(void)
{
	return boot_path;
}

//Variables for SYSTEM.CNF processing
int BootDiscType = 0;
char SystemCnf_BOOT[MAX_PATH];
char SystemCnf_BOOT2[MAX_PATH];
char SystemCnf_VER[10];    //Arbitrary. Real value should always be shorter
char SystemCnf_VMODE[10];  //Arbitrary, same deal. As yet unused

char default_ESR_path[] = "mc:/BOOT/ESR.ELF";
char default_OSDSYS_path[30];
char default_OSDSYS_path2[30];

char ROMVER_data[16];  //16 byte file read from rom0:ROMVER at init
char rough_region;     //E==Europe, A==US, I==Japan, H==Asia, C==China

int cdmode;      //Last detected disc type
int old_cdmode;  //used for disc change detection
int uLE_cdmode;  //used for smart disc detection

int main(int argc, char *argv[])
{
	enum BOOT_DEVICE boot;
	int CNF_error = -1;  //assume error until CNF correctly loaded

	filerSizeCacheInit();
	captureBootArguments(argc, argv, &boot_argc, boot_argv, 8);
	boot = performEarlyBootInitialization((argc > 0) ? argv[0] : NULL, boot_path, sizeof(boot_path), mainMsg, CNF, sizeof(CNF), &CNF_error);

	initializeRuntimeInputModules(boot);
	initializeRuntimeDisplayModules(CNF_error, mainMsg);

	//Finish the startup configuration path before entering the dashboard.
	validateConfiguredCnfPath();

	cdmode = -1;     //flag unchecked cdmode state

	//The dashboard is the only shell; DashRun() does not return.
	{
		MainExecuteContext dash_ctx = {0};

		dash_ctx.boot_argc = boot_argc;
		dash_ctx.boot_argv = boot_argv;
		dash_ctx.boot_path = boot_path;
		dash_ctx.main_msg = mainMsg;
		dash_ctx.cnf_path = CNF;
		dash_ctx.default_esr_path = default_ESR_path;
		dash_ctx.default_osdsys_path = default_OSDSYS_path;
		dash_ctx.default_osdsys_path2 = default_OSDSYS_path2;
		dash_ctx.rough_region = rough_region;
		dash_ctx.romver_data = ROMVER_data;
		DashRun(&dash_ctx, 1);
	}
	return 0;
}
