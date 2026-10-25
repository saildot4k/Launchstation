"""Check the IRX build contract and execute the socket server's RPC boundary."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
module = root / "iop/ps2ips_rpc"
yaml = (root / "ps2.yaml").read_text()
server = (module / "ps2ips.c").read_text()


def check_build_config(config):
    # An EE library named ps2ips is not a driver artifact. Resolve the explicit
    # embedding alias to a local IOP target, rather than accepting its spelling.
    alias = re.search(r"^      - ([\w-]+):ps2ips$", config, re.M)
    assert alias, "Socket server needs an explicit local IRX alias"
    target = re.search(r"^  - name: " + re.escape(alias[1]) +
                       r"\n(.*?)(?=^  - name:|\Z)", config, re.M | re.S)
    assert target, "Socket server target is missing"
    body = target[1]
    assert re.search(r"^    type: iop$", body, re.M), "Socket server must produce an IRX"
    assert "sources: [iop/ps2ips_rpc/ps2ips.c]" in body
    assert "imports_lst: iop/ps2ips_rpc/imports.lst" in body
    assert "defines: [PS2IP_DNS]" in body
    assert re.search(r"libs: \[[^\n]*\bps2ips, cglue\b", config)


check_build_config(yaml)
for broken in (yaml.replace("ps2ips_rpc:ps2ips", "ps2ips"),
               yaml.replace("name: ps2ips_rpc\n    type: iop",
                            "name: ps2ips_rpc\n    type: ee_lib")):
    try:
        check_build_config(broken)
    except AssertionError:
        pass
    else:
        raise AssertionError("The old library-as-IRX configuration must be rejected")

isolated = (module / "ps2.yaml").read_text()
assert "name: ps2ips_rpc\n    type: iop" in isolated
assert "sources: [ps2ips.c]" in isolated and "defines: [PS2IP_DNS]" in isolated
workflow = (root / ".github/workflows/compile.yml").read_text()
assert "python3 tests/test_ps2ips_rpc.py" in workflow
assert "ps2build build -c iop/ps2ips_rpc/ps2.yaml" in workflow
assert "I_DeleteThread" in (module / "imports.lst").read_text()


def function(name):
    match = re.search(r"(?:static )?(?:void \* |void \*|void |int )" +
                      name + r"\([^)]*\)\n\{", server)
    assert match, name
    end = server.index("{", match.start()) + 1
    depth = 1
    while depth:
        depth += (server[end] == "{") - (server[end] == "}")
        end += 1
    return server[match.start():end] + "\n"


code = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ps2ip_rpc.h"
#define MODULE_RESIDENT_END 0
#define MODULE_NO_RESIDENT_END 1
#define TH_C 2
#define _start ps2ips_start
typedef struct { int value; } SifRpcDataQueue_t;
typedef struct { int value; } SifRpcServerData_t;
typedef struct {
    int attr,option;void (*thread)(void *);int stacksize,priority;
} iop_thread_t;
static SifRpcDataQueue_t ps2ips_queue;
static SifRpcServerData_t ps2ips_server;
static u8 _rpc_buffer[2048];
static int create_result,start_result,starts,deletes,registrations,loops;
static void (*thread_entry)(void *);
static void *(*rpc_handler)(unsigned int,void *,int);
static u8 *registered_buffer;
static int CreateThread(const iop_thread_t *t) {
    assert(t->attr==TH_C && t->option==0 && t->stacksize>=0x800);
    thread_entry=t->thread;return create_result;
}
static int StartThread(int id,void *arg) {
    assert(id==42 && !arg);starts++;
    if(start_result<0)return start_result;
    thread_entry(arg);return 0;
}
static int DeleteThread(int id) { assert(id==42);deletes++;return 0; }
static int GetThreadId(void) { return 7; }
static void sceSifSetRpcQueue(SifRpcDataQueue_t *queue,int id) {
    assert(queue==&ps2ips_queue && id==7);
}
static void sceSifRegisterRpc(SifRpcServerData_t *rpc,unsigned id,void *handler,
                             u8 *buf,void *a,void *b,SifRpcDataQueue_t *queue) {
    assert(rpc==&ps2ips_server && id==PS2IP_IRX && !a && !b && queue==&ps2ips_queue);
    registrations++;rpc_handler=handler;registered_buffer=buf;
}
static void sceSifRpcLoop(SifRpcDataQueue_t *queue) {
    assert(queue==&ps2ips_queue);loops++;
}
struct hostent { int h_addrtype,h_length;char **h_addr_list; };
static int lookup_case;
static unsigned char resolved_ip[]={203,0,113,9};
static struct hostent *gethostbyname(const char *name) {
    static char *addresses[2];static struct hostent host;
    assert(!strcmp(name,"time.example.test"));
    if(lookup_case==1)return NULL;
    addresses[0]=lookup_case==3?NULL:(char *)resolved_ip;addresses[1]=NULL;
    host.h_addrtype=AF_INET;host.h_length=lookup_case==4?3:4;
    host.h_addr_list=lookup_case==2?NULL:addresses;return &host;
}
static ip_addr_t dns[2];
static void dns_setserver(u8 slot,const ip_addr_t *address) {
    assert(slot<2);dns[slot]=*address;
}
static const ip_addr_t *dns_getserver(u8 slot) { assert(slot<2);return &dns[slot]; }
'''
tested = {"do_gethostbyname", "do_dns_setserver", "do_dns_getserver"}
# Keep production dispatch and its tested endpoints. Other socket operations
# must never be invoked by these narrow registration/DNS scenarios.
for name in re.findall(r"static void (do_\w+)\(", server):
    if name not in tested:
        code += f"static void {name}(void *b,int n) {{ (void)b;(void)n;assert(0); }}\n"
for name in ("do_gethostbyname", "do_dns_setserver", "do_dns_getserver",
             "rpcHandlerFunction", "threadRpcFunction", "_start"):
    code += function(name)
code += r'''
static void reset(void) {
    create_result=42;start_result=starts=deletes=registrations=loops=0;
    rpc_handler=NULL;registered_buffer=NULL;
}
int main(void) {
    reset();create_result=-10;
    assert(ps2ips_start(0,NULL)==MODULE_NO_RESIDENT_END);
    assert(!starts && !deletes && !registrations);
    reset();start_result=-11;
    assert(ps2ips_start(0,NULL)==MODULE_NO_RESIDENT_END);
    assert(starts==1 && deletes==1 && !registrations);
    reset();assert(ps2ips_start(0,NULL)==MODULE_RESIDENT_END);
    assert(starts==1 && !deletes && registrations==1 && loops==1);
    assert(rpc_handler && registered_buffer==_rpc_buffer);
    for(lookup_case=0;lookup_case<5;lookup_case++) {
        memset(_rpc_buffer,0,sizeof(_rpc_buffer));strcpy((char *)_rpc_buffer,"time.example.test");
        assert(rpc_handler(PS2IPS_ID_GETHOSTBYNAME,_rpc_buffer,256)==_rpc_buffer);
        gethostbyname_res_pkt *reply=(void *)_rpc_buffer;
        if(!lookup_case) {
            assert(!reply->result && reply->hostent.h_addrtype==AF_INET && reply->hostent.h_length==4);
            /* Return IP bytes, never the address of an IOP-side pointer. */
            assert(!memcmp(&reply->hostent.h_addr,resolved_ip,4));
        } else assert(reply->result==-1);
    }
    dns_setserver_pkt *request=(void *)_rpc_buffer;
    unsigned char resolver[]={1,1,1,1};
    memset(_rpc_buffer,0,sizeof(_rpc_buffer));request->numdns=1;
    memcpy(&request->dnsserver,resolver,4);
    rpc_handler(PS2IPS_ID_DNS_SETSERVER,_rpc_buffer,sizeof(*request));
    assert(!memcmp(&dns[1],resolver,4));
    _rpc_buffer[0]=1;
    rpc_handler(PS2IPS_ID_DNS_GETSERVER,_rpc_buffer,1);
    assert(!memcmp(&((dns_getserver_res_pkt *)_rpc_buffer)->dnsserver,resolver,4));
    puts("PASS: IRX target/client distinction, RPC registration, thread failures, DNS IPv4 bytes and resolver RPCs");
}
'''
compiler = shutil.which("gcc") or shutil.which("cc")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="ps2ips-rpc-") as folder:
    path = Path(folder)
    (path / "tamtypes.h").write_text("#include <stdint.h>\ntypedef uint8_t u8;\n"
                                    "typedef int16_t s16;\ntypedef int32_t s32;\n"
                                    "typedef uint32_t u32;\n")
    (path / "tcpip.h").write_text("#include <sys/socket.h>\n#define MEMP_NUM_NETCONN 32\n"
                                 "typedef struct { u32 addr; } ip_addr_t;\n"
                                 "#define ip_addr_copy(d,s) ((d)=(s))\n")
    (path / "server.c").write_text(code)
    executable = path / "server"
    subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror","-DPS2IP_DNS",
                    "-I"+str(path),"-I"+str(module),str(path/"server.c"),
                    "-o",str(executable)],check=True)
    subprocess.run([str(executable)],check=True,timeout=10)
