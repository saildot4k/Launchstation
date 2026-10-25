"""Execute DEV9 and ATA loaders across refused/successful variant resets."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / "src/init.c").read_text()
yaml = (root / "ps2.yaml").read_text()
clock = (root / "src/dash_clock_sync.c").read_text()
make = (root / "Makefile").read_text()
embed = (root / "embed.make").read_text()
assert "      - WLE_NETMAN_IP\n" in yaml
for module in ("netman", "smap:ps2smap", "ps2ip-nm:ps2ip", "ps2ips_rpc:ps2ips"):
    assert "      - " + module + "\n" in yaml, module
assert "      - smap-ps2ip:ps2smap\n" not in yaml
assert "ps2ips_irx.o" in make and "iop/irx/ps2ips.irx" in embed
assert "have_ps2ips = 0;" in source[source.index("static void clearIopModuleState(void)\n{"):]
assert "have_netman = 0;" in source[source.index("static void clearIopModuleState(void)\n{"):]
blobs = (root / "src/embed_blobs.S").read_text()
assert 'EMBED_FILE(ps2smap_legacy_irx, "iop/__precompiled/ps2smap.irx")' in blobs

def function(name, source=source):
    match = re.search(r"(?:static )?(?:int |void |const char \*)" + name + r"\([^)]*\)\n\{", source)
    assert match, name
    pos = source.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[match.start():pos] + "\n"

code = r'''
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
#include <string.h>
#define ETH 1
#ifndef TEST_ETH_ONLY
#define UDPFS 1
#endif
/* NETWORK_MODE_DECLARATIONS */
#define TRUE 1
#define DEV9_VARIANT_NONE 0
#define DEV9_VARIANT_CURRENT 1
#define DEV9_VARIANT_PS2SDK_V10 2
#define DPRINTF(...) ((void)0)
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
/* CLOCK_QUERY_DECLARATIONS */
static u64 Timer(void) { return 1000; }
static int query_calls, clock_writes;
static void dashLoadingFrame(const char *text,int done,int total) { (void)text;(void)done;assert(total==SNTP_ATTEMPTS); }
static int sntpQuery(const char *host,SntpSample *out) {
    assert(!strcmp(host,"0.pool.ntp.org"));query_calls++;out->unix_ms=1700000000000ULL;out->received_ms=1000;return SNTP_OK;
}
static int writePs2Clock(u64 stamp) { assert(stamp==1700000000ULL);clock_writes++;return 1; }
static int menuTitleUpdateAsync(int force) { assert(force==1);return 0; }
typedef struct { u32 addr; } DashboardDnsAddress;
static DashboardDnsAddress dns_servers[2];
static const char *dashboard_ip_error;
static int dns_writes, client_result, socket_calls;
static const void *failed_module;
static int failed_id, failed_result;
static char gw[32] = "192.168.1.1";
#ifdef WLE_NETMAN_IP
static int have_netman;
static u8 netman_irx[1], ps2smap_legacy_irx[1];
static int size_netman_irx=1, size_ps2smap_legacy_irx=1;
#define BASE_NETWORK_CALLS 4
#else
#define BASE_NETWORK_CALLS 3
#endif
static const DashboardDnsAddress *ps2ipc_dns_getserver(u8 n) { assert(n<2); return &dns_servers[n]; }
static void ps2ipc_dns_setserver(u8 n, const DashboardDnsAddress *ip) {
    assert(n<2); dns_servers[n]=*ip; dns_writes++;
}
static u8 ps2dev9_irx[1], ps2dev9_v10_irx[1], ata_bd_irx[1];
static int size_ps2dev9_irx=1, size_ps2dev9_v10_irx=1, size_ata_bd_irx=1;
static u8 ps2ip_irx[1], ps2ip_v10_irx[1], ps2ips_irx[1], ps2smap_irx[1], ps2host_irx[1], ps2ftpd_irx[1], ps2netfs_irx[1];
static int size_ps2ip_irx=1, size_ps2ip_v10_irx=1, size_ps2ips_irx=1, size_ps2smap_irx=1, size_ps2host_irx=1, size_ps2ftpd_irx=1, size_ps2netfs_irx=1;
static int have_ps2ip, have_ps2ips, have_ps2smap, have_ps2host, have_ps2ftpd, have_ps2netfs, network_calls;
static int client_calls, if_conf_len, have_NetModules;
static unsigned int generation;
#ifdef UDPFS
static int have_udpfs_smap, have_udpfs_ministack, have_udpfs_ioman;
static u8 udpfs_smap_irx[1], udpfs_ministack_irx[1], udpfs_ioman_irx[1];
static int size_udpfs_smap_irx=1, size_udpfs_ministack_irx=1, size_udpfs_ioman_irx=1;
static char ip[]="192.168.1.10";
#endif
static int console_is_PSX, have_Flash_modules, xfromserv_loaded, power_calls, flash_calls;
static char if_conf[1];
static struct Config { int legacy_net_drivers; } config;
static struct Config *setting = &config;
static int ps2dev9_loaded, have_ps2dev9, ps2dev9_variant, have_ata_bd;
static int cf_owned, allow_reset, resets, bdm_live, bdm_ok, bdm_calls, ata_calls, dev9_calls, settle_calls;
static int module_id=1, module_result;
static int pcCardCfOwnsBus(void) { return cf_owned; }
#ifdef UDPFS
static unsigned int getIopResetGeneration(void) { return generation; }
#endif
static void showLoadingModulesMsg(const char *name) { (void)name; }
static void ensureCoreIoStackReady(void) {}
static void setupPowerOff(void) { power_calls++; }
static void load_pflash(void) { flash_calls++; xfromserv_loaded=1; }
static void getIpConfig(void) {}
static int ps2ip_init(void) {
    /* Binding without this IOP RPC server can wait forever on hardware. */
    assert(have_ps2ip && have_ps2smap && have_ps2ips);
    client_calls++; return client_result;
}
static void resetRuntimeDeviceState(int show) {
    assert(show == TRUE); resets++;
    if (allow_reset) {
        generation++;have_NetModules=0;
#ifdef UDPFS
        have_udpfs_smap=have_udpfs_ministack=have_udpfs_ioman=0;
#endif
        have_ps2dev9=ps2dev9_loaded=have_ata_bd=bdm_live=0;
        have_ps2ip=have_ps2ips=have_ps2smap=have_ps2host=have_ps2ftpd=have_ps2netfs=0;
        ps2dev9_variant=DEV9_VARIANT_NONE;network_stack_mode=0;
        memset(dns_servers,0,sizeof(dns_servers));
#ifdef WLE_NETMAN_IP
        have_netman=0;
#endif
    }
}
static int loadBdmCoreModules(void) { bdm_calls++; bdm_live=bdm_ok; return bdm_live; }
static int SifExecModuleBuffer(const void *module, int size, int len, const void *args, int *ret) {
    assert(size==1);
    if(module==ps2ip_irx) {
#ifdef WLE_NETMAN_IP
        assert(have_netman && have_ps2smap && len==if_conf_len && args==if_conf);
#else
        assert(!len && !args);
#endif
    }
    if(module==ps2ip_v10_irx) assert(!len && !args);
    if(module==ps2smap_irx) {
#ifdef WLE_NETMAN_IP
        assert(have_netman && !len && !args);
#else
        assert(have_ps2ip && len==if_conf_len && args==if_conf);
#endif
    }
#ifdef WLE_NETMAN_IP
    if(module==netman_irx) assert(!have_ps2ip && !have_ps2smap && !len && !args);
    if(module==ps2smap_legacy_irx) assert(have_ps2ip && !have_netman && len==if_conf_len && args==if_conf);
#endif
    if (module==ata_bd_irx) { ata_calls++; if (!bdm_live) return -1; }
    else if (module==ps2dev9_irx || module==ps2dev9_v10_irx) dev9_calls++;
    else {
        if(module==ps2ips_irx) {
            assert(have_ps2ip && have_ps2smap);
            socket_calls++;
        }
        network_calls++;
    }
    if(module==failed_module) { *ret=failed_result;return failed_id; }
    *ret=module_result; return module_id;
}
static void pauseAfterAtaBlockDriverLoad(void) { settle_calls++; }
'''
# Preserve the real feature guard: Ethernet-only builds need the gate too.
enum_start = source.rfind("#if", 0, source.index("enum network_stack_mode {"))
enum_lines = []
guard_depth = 0
for line in source[enum_start:].splitlines(keepends=True):
    enum_lines.append(line)
    if re.match(r"\s*#if(?:def|ndef)?\b", line):
        guard_depth += 1
    elif re.match(r"\s*#endif\b", line):
        guard_depth -= 1
        if guard_depth == 0:
            break
code = code.replace("/* NETWORK_MODE_DECLARATIONS */", "".join(enum_lines))
switch_source = function("switchNetworkStack")
switch_pos = source.index(switch_source.rstrip())
switch_guard = source[source.rfind("#if", 0, switch_pos):switch_pos].strip()
code += switch_guard + "\n" + switch_source + "#endif\n"
for name in ("load_ps2dev9", "loadAtaBlockDriver", "load_ps2ip", "load_ps2host",
             "load_ps2ftpd", "load_ps2netfs", "loadNetModules", "isFtpNetworkReady", "configureDashboardDns", "dashboardIpNetworkError", "ensureDashboardIpNetworkReady", "loadFlashModules"):
    code += function(name)
code += "#ifdef UDPFS\n"
for name in ("load_udpfs_stack", "load_udpfs", "reloadUdpfsModules"):
    code += function(name)
code += "#endif\n"
# This integration fixture mocks only the query; the packet/elapsed-time path
# is exercised by test_clock_sync.py against the production socket functions.
sample_end = clock.index("} SntpSample;") + len("} SntpSample;")
sample = clock[clock.rfind("typedef struct", 0, sample_end):sample_end] + "\n"
status_start = clock.index("enum {", sample_end)
query_types = sample + clock[status_start:clock.index("};", status_start) + 2] + "\n"
for constant in ("SNTP_ATTEMPTS",):
    query_types += re.search(r"^#define " + constant + r" .+$", clock, re.M).group() + "\n"
code = code.replace("/* CLOCK_QUERY_DECLARATIONS */", query_types)
code += function("sntpStatusText", clock)
code += function("dashClockSyncInternet", clock)
code += r'''
static void reset(void) {
    config.legacy_net_drivers=0;
    ps2dev9_loaded=have_ps2dev9=have_ata_bd=cf_owned=resets=bdm_live=0;
    bdm_calls=ata_calls=dev9_calls=settle_calls=module_result=0;
    ps2dev9_variant=DEV9_VARIANT_NONE; allow_reset=bdm_ok=module_id=1;
    have_ps2ip=have_ps2ips=have_ps2smap=have_ps2host=have_ps2ftpd=have_ps2netfs=network_calls=client_calls=0;
    network_stack_mode=0;generation=0;have_NetModules=0;
#ifdef UDPFS
    have_udpfs_smap=have_udpfs_ministack=have_udpfs_ioman=0;
#endif
    client_result=socket_calls=dns_writes=query_calls=clock_writes=0;
    if_conf_len=1;
#ifdef WLE_NETMAN_IP
    have_netman=0;
#endif
    failed_module=NULL;failed_id=-1;failed_result=0;
    dashboard_ip_error=NULL;
    memset(dns_servers,0,sizeof(dns_servers));
    strcpy(gw,"192.168.1.1");
    console_is_PSX=have_Flash_modules=xfromserv_loaded=power_calls=flash_calls=0;
}
static int startNetworkMode(int mode) {
    switch(mode) {
        case NETWORK_STACK_FTP: loadNetModules();return isFtpNetworkReady();
        case NETWORK_STACK_HOST: load_ps2host();return have_ps2host;
#ifdef UDPFS
        case NETWORK_STACK_UDPFS: return load_udpfs();
#endif
        case NETWORK_STACK_CLIENT: return ensureDashboardIpNetworkReady();
    }
    assert(0);return 0;
}
static void assertOnlyMode(int mode) {
    assert(network_stack_mode==mode);
    assert(!!have_NetModules==(mode==NETWORK_STACK_FTP));
    assert(!!have_ps2ftpd==(mode==NETWORK_STACK_FTP));
    assert(!!have_ps2netfs==(mode==NETWORK_STACK_FTP));
    assert(!!have_ps2host==(mode==NETWORK_STACK_HOST));
    assert(!!have_ps2ips==(mode==NETWORK_STACK_CLIENT));
    assert(!!have_ps2ip==(mode!=NETWORK_STACK_UDPFS));
    assert(!!have_ps2smap==(mode!=NETWORK_STACK_UDPFS));
#ifdef UDPFS
    assert(!!have_udpfs_smap==(mode==NETWORK_STACK_UDPFS));
    assert(!!have_udpfs_ministack==(mode==NETWORK_STACK_UDPFS));
    assert(!!have_udpfs_ioman==(mode==NETWORK_STACK_UDPFS));
#endif
}
int main(void) {
    /* Refused reset must preserve ownership and perform no dependent load. */
    reset(); have_ps2dev9=ps2dev9_loaded=1;
    ps2dev9_variant=DEV9_VARIANT_CURRENT; config.legacy_net_drivers=1;
    allow_reset=0;
    assert(!loadAtaBlockDriver());
    assert(resets==1 && !ata_calls && !dev9_calls && !bdm_calls);
    assert(ps2dev9_loaded && ps2dev9_variant==DEV9_VARIANT_CURRENT);
    reset(); have_ps2dev9=ps2dev9_loaded=1;
    ps2dev9_variant=DEV9_VARIANT_PS2SDK_V10; allow_reset=0;
    assert(!loadAtaBlockDriver() && resets==1 && !ata_calls && !dev9_calls && !bdm_calls);
    assert(ps2dev9_variant==DEV9_VARIANT_PS2SDK_V10);
    /* Successful reset clears BDM; restore it before the ATA module runs. */
    reset(); have_ps2dev9=ps2dev9_loaded=bdm_live=1;
    ps2dev9_variant=DEV9_VARIANT_CURRENT; config.legacy_net_drivers=1;
    assert(loadAtaBlockDriver());
    assert(resets==1 && dev9_calls==1 && bdm_calls==1 && ata_calls==1 && settle_calls==1);
    assert(ps2dev9_variant==DEV9_VARIANT_PS2SDK_V10 && bdm_live);
    assert(loadAtaBlockDriver());
    assert(resets==1 && dev9_calls==1 && ata_calls==1 && settle_calls==1);
    /* CF ownership, module rejection and BDM failure stop dependent loads. */
    reset(); cf_owned=1; assert(!loadAtaBlockDriver());
    assert(!dev9_calls && !bdm_calls && !ata_calls);
    reset(); module_id=-1; assert(!loadAtaBlockDriver() && !bdm_calls && !ata_calls);
    reset(); module_result=-1; assert(!loadAtaBlockDriver() && !bdm_calls && !ata_calls);
    reset(); bdm_ok=0; assert(!loadAtaBlockDriver() && !ata_calls);
    /* Existing IP flags do not override a refused DEV9 transition. */
    reset(); have_ps2dev9=ps2dev9_loaded=have_ps2ip=have_ps2ips=have_ps2smap=1;
    ps2dev9_variant=DEV9_VARIANT_CURRENT; config.legacy_net_drivers=1; allow_reset=0;
    load_ps2host(); load_ps2ftpd(); load_ps2netfs();
    assert(!ensureDashboardIpNetworkReady());
    assert(resets==4 && have_ps2ip && have_ps2smap);
    assert(!network_calls && !client_calls && !dev9_calls);
    assert(!have_ps2host && !have_ps2ftpd && !have_ps2netfs);
    reset(); network_stack_mode=NETWORK_STACK_UDPFS;allow_reset=0;
    load_ps2host(); load_ps2ftpd(); load_ps2netfs();
    assert(!ensureDashboardIpNetworkReady() && !network_calls && !dev9_calls && !client_calls);
    char clock_result[160];
    reset(); assert(dashClockSyncInternet(clock_result,sizeof(clock_result)));
    assert(query_calls==1 && clock_writes==1 && strstr(clock_result,"synchronized"));
    assert(dev9_calls==1 && network_calls==BASE_NETWORK_CALLS && client_calls==1 && socket_calls==1);
    /* Repeated clients share resident modules and preserve configured DNS. */
    assert(dns_writes==2 && !memcmp(&dns_servers[0].addr,"\xC0\xA8\x01\x01",4));
    assert(!memcmp(&dns_servers[1].addr,"\x01\x01\x01\x01",4));
    assert(ensureDashboardIpNetworkReady());
    assert(socket_calls==1 && network_calls==BASE_NETWORK_CALLS && dns_writes==2);
    /* Module failures stop before binding, including positive nonresident returns. */
    const void *modules[]={ps2ip_irx,ps2smap_irx,ps2ips_irx,
#ifdef WLE_NETMAN_IP
        netman_irx,
#endif
    };
    const char *errors[]={"PS2IP","SMAP","PS2IPS","NetMan"};
    for(unsigned i=0;i<sizeof(modules)/sizeof(modules[0]);i++) for(int nonresident=0;nonresident<2;nonresident++) {
        reset();failed_module=modules[i];failed_id=nonresident?1:-1;failed_result=nonresident;
        assert(!dashClockSyncInternet(clock_result,sizeof(clock_result)) && !client_calls && !dns_writes);
        assert(!query_calls && !clock_writes && strstr(clock_result,errors[i]));
        assert(strstr(dashboardIpNetworkError(),errors[i]));
        assert(!have_ps2host && !have_ps2ftpd && !have_ps2netfs);
        failed_module=NULL;assert(ensureDashboardIpNetworkReady());
        assert(client_calls==1 && socket_calls==(i==2?2:1) && dns_writes==2);
    }
    /* A failed RPC bind is retryable without loading another server. */
    reset();client_result=-1;assert(!ensureDashboardIpNetworkReady());
    assert(strstr(dashboardIpNetworkError(),"connect") && !dns_writes && socket_calls==1);
    client_result=0;assert(ensureDashboardIpNetworkReady() && socket_calls==1 && dns_writes==2);
    /* An IOP reset discards server residency and resolver state. */
    resetRuntimeDeviceState(TRUE);assert(!have_ps2ips);
    assert(ensureDashboardIpNetworkReady() && socket_calls==2 && dns_writes==4);
    /* Fresh static-IP stacks get DNS, but an existing resolver is retained. */
    reset();dns_servers[0].addr=123;assert(ensureDashboardIpNetworkReady() && !dns_writes);
    const char *invalid_gateways[]={"0.0.0.0","999.1.1.1","bad","192.168.1.1oops","224.0.0.1"};
    for(unsigned i=0;i<sizeof(invalid_gateways)/sizeof(invalid_gateways[0]);i++) {
        reset();strcpy(gw,invalid_gateways[i]);assert(ensureDashboardIpNetworkReady());
        assert(!memcmp(&dns_servers[0].addr,"\x01\x01\x01\x01",4));
        assert(!memcmp(&dns_servers[1].addr,"\x08\x08\x08\x08",4));
    }
    reset();cf_owned=1;assert(!ensureDashboardIpNetworkReady());
    assert(strstr(dashboardIpNetworkError(),"CompactFlash") && !network_calls);
    reset();network_stack_mode=NETWORK_STACK_UDPFS;allow_reset=0;assert(!ensureDashboardIpNetworkReady());
    assert(strstr(dashboardIpNetworkError(),"Internet"));
    reset();module_id=-1;assert(!ensureDashboardIpNetworkReady());
    assert(strstr(dashboardIpNetworkError(),"DEV9"));
#ifdef WLE_NETMAN_IP
    /* Switching to/from legacy networking must use the matching SMAP too. */
    reset();config.legacy_net_drivers=1;assert(ensureDashboardIpNetworkReady());
    assert(ps2dev9_variant==DEV9_VARIANT_PS2SDK_V10 && !have_netman && network_calls==3);
    config.legacy_net_drivers=0;assert(ensureDashboardIpNetworkReady());
    assert(ps2dev9_variant==DEV9_VARIANT_CURRENT && have_netman && resets==1);
    assert(network_calls==3+BASE_NETWORK_CALLS && socket_calls==2 && network_stack_mode==NETWORK_STACK_CLIENT);
#endif
    /* Exercise the real entry points and reset gate for every mode pair. */
    const int modes[]={NETWORK_STACK_FTP,NETWORK_STACK_HOST,NETWORK_STACK_CLIENT,
#ifdef UDPFS
        NETWORK_STACK_UDPFS,
#endif
    };
    for(unsigned from=0;from<sizeof(modes)/sizeof(modes[0]);from++) {
        for(unsigned to=0;to<sizeof(modes)/sizeof(modes[0]);to++) {
            reset();assert(startNetworkMode(modes[from]));assertOnlyMode(modes[from]);
            assert(!resets);int modules_before=network_calls,dev9_before=dev9_calls;
            allow_reset=0;
            if(from==to) {
                assert(startNetworkMode(modes[to]));assertOnlyMode(modes[to]);
                assert(!resets && network_calls==modules_before && dev9_calls==dev9_before);
            } else {
                assert(!startNetworkMode(modes[to]));assertOnlyMode(modes[from]);
                assert(resets==1 && !generation && network_calls==modules_before && dev9_calls==dev9_before);
                allow_reset=1;assert(startNetworkMode(modes[to]));assertOnlyMode(modes[to]);
                assert(resets==2 && generation==1 && network_calls>modules_before);
                int modules_after=network_calls;
                assert(startNetworkMode(modes[to]));assertOnlyMode(modes[to]);
                assert(resets==2 && network_calls==modules_after);
            }
        }
        reset();cf_owned=1;assert(!startNetworkMode(modes[from]));
        assert(!resets && !network_calls && !dev9_calls);
    }
#ifdef UDPFS
    reset();assert(load_udpfs());allow_reset=0;
    assert(!reloadUdpfsModules());assertOnlyMode(NETWORK_STACK_UDPFS);
    assert(!generation);allow_reset=1;
    assert(reloadUdpfsModules() && generation==1);assertOnlyMode(NETWORK_STACK_UDPFS);
    reset();cf_owned=1;assert(!reloadUdpfsModules() && !resets && !network_calls);
#endif
    /* XFROM boot registers power-off even if DEV9 rejects initialization. */
    reset(); console_is_PSX=1; module_id=-1;
    assert(!loadFlashModules() && power_calls==1 && !flash_calls);
    reset(); console_is_PSX=1;
    assert(loadFlashModules() && power_calls==1 && flash_calls==1);
    puts("PASS: lazy socket-server startup, DNS, module failures, retries, IOP resets, refused DEV9/IP transitions, BDM ordering, dependent services, XFROM power-off and CF ownership");
}
'''
with tempfile.TemporaryDirectory(prefix="dev9-transition-") as folder:
    path = Path(folder)
    (path / "test.c").write_text(code)
    exe = path / "test.exe"
    cc = shutil.which("gcc") or shutil.which("clang")
    assert cc, "Host C compiler required"
    for flags in ([], ["-DWLE_NETMAN_IP"], ["-DTEST_ETH_ONLY"],
                  ["-DTEST_ETH_ONLY", "-DWLE_NETMAN_IP"], ["-DUDPTTY"]):
        subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror", *flags,
                        str(path / "test.c"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True, timeout=10)
print("PASS: exclusive FTP/Host/UDPFS/Internet sessions, refused reboots, same-mode reuse, direct/NetMan and Ethernet-only builds")
