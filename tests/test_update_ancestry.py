"""Exercise the actual updater comparison/confirmation code with mocked GitHub responses.

This covers stale, current, newer, divergent, malformed and unreachable releases.
It is a host-side regression test, not an HTTPS or console integration test.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "src/dash_tools.c").read_text()


def function(signature):
    start = src.index(signature)
    pos = src.index("{", start) + 1
    depth = 1
    while depth:
        depth += (src[pos] == "{") - (src[pos] == "}")
        pos += 1
    return src[start:pos] + "\n"


sources = "".join(function(signature) for signature in (
    "static int releaseJsonString(",
    "static int releaseAssetDigest(",
    "static int updateIsCommitId(",
    "static int updateCommitRelation(",
    "void dashToolsCheckUpdates(void)\n{",
))
enums = src[src.index("enum { UPDATE_RELATION_UNKNOWN"):src.index("static int updateIsCommitId(")]

program = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "self_update.h"
#define MAX_PATH 256
#define GIT_HASH "e70d903"
#define DI_CHECK 1
#define DI_WARNING 2
typedef struct {
    int status;
    char *body;
    int body_len;
} HttpsResponse;
static char comparison[32] = "ahead";
static char release_target[80] = "51e1e0c7bc1efcb5b51c6cc9de056ee858694a03";
static const char *last_title;
static char last_body[320];
static int requests, compares, confirmations, installs, response_status = 200;
static int worker_ready, ca_ready, network_ready;
static int waits, polls, ca_checks, network_checks;
static int dashWorkerAwaitAll(const char *title) {
    assert(title != NULL);waits++;return worker_ready;
}
static void filerRootMcPollIdle(void) {
    assert(waits==1 && worker_ready);polls++;
}
static int launchstationUpdateCaPath(char *path, int n) {
    assert(waits==1 && polls==1);ca_checks++;
    snprintf(path,n,"ca.pem");
    return ca_ready;
}
static int ensureDashboardIpNetworkReady(void) {
    assert(ca_checks==1 && ca_ready);network_checks++;return network_ready;
}
static const char *dashboardIpNetworkError(void) { return "Detailed network startup failure"; }
static void dashLoadingBegin(const char *s) { (void)s; }
static void dashLoadingEnd(void) {}
static void dashModalMessage(int kind,const char *title,const char *body,const char *detail) {
    (void)kind;(void)detail;
    last_title=title;
    snprintf(last_body,sizeof(last_body),"%s",body ? body : "");
}
static int dashModalConfirm(const char *title,const char *body,const char *action,int danger) {
    (void)title;(void)body;(void)action;(void)danger;
    confirmations++; return 1;
}
int selfUpdateInstall(const char *ca,const char *digest,char *result,int cap) {
    (void)ca;(void)digest;
    installs++;
    snprintf(result,cap,"installed");
    return 0;
}
static int httpsRequest(const char *method,const char *host,const char *path,
                            const char *headers,const void *body,int body_len,
                            const char *ca,HttpsResponse *out,char *err,int err_size) {
    char json[512];
    (void)headers;(void)body;(void)body_len;(void)ca;(void)err;(void)err_size;
    assert(!strcmp(method,"GET") && !strcmp(host,"api.github.com"));
    assert(network_checks==1 && network_ready);
    assert(!strncmp(path,"/repos/saildot4k/Launchstation/",
                    strlen("/repos/saildot4k/Launchstation/")));
    requests++;
    if (strstr(path,"/compare/")) {
        compares++;
        assert(strstr(path,"?per_page=1&page=2"));
        assert(strstr(path,"/compare/e70d903..."));
        snprintf(json,sizeof(json),"{\"status\":\"%s\"}",comparison);
        out->status=response_status;
    } else {
        assert(!strcmp(path,"/repos/saildot4k/Launchstation/releases/tags/latest"));
        snprintf(json,sizeof(json),"{\"target_commitish\":\"%s\",\"assets\":[{\"name\":\"%s\",\"digest\":\"sha256:%064d\"}]}",
                 release_target,SELF_UPDATE_ASSET,0);
        out->status=200;
    }
    out->body=malloc(strlen(json)+1);
    assert(out->body != NULL);
    strcpy(out->body,json);
    out->body_len=(int)strlen(json);
    return 0;
}
static void httpsResponseFree(HttpsResponse *r) {
    free(r->body);r->body=NULL;
}
'''
program += enums + sources
program += r'''
static void reset(const char *status,const char *release,int code) {
    requests=compares=confirmations=installs=0;
    waits=polls=ca_checks=network_checks=0;
    worker_ready=ca_ready=network_ready=1;
    last_title=NULL;
    last_body[0]='\0';
    snprintf(comparison,sizeof(comparison),"%s",status);
    snprintf(release_target,sizeof(release_target),"%s",release);
    response_status=code;
}
int main(void) {
    const char *old="51e1e0c7bc1efcb5b51c6cc9de056ee858694a03";
    reset("ahead",old,200);
    dashToolsCheckUpdates();
    assert(compares==1 && requests==2 && confirmations==1 && installs==1);
    assert(waits==1 && polls==1 && ca_checks==1 && network_checks==1);
    reset("ahead",old,200);worker_ready=0;
    dashToolsCheckUpdates();
    assert(waits==1 && !polls && !ca_checks && !network_checks && !requests && !installs);
    reset("ahead",old,200);ca_ready=0;
    dashToolsCheckUpdates();
    assert(!network_checks && !requests && !installs);
    assert(!strcmp(last_title,"Update check needs the CA bundle"));
    reset("ahead",old,200);network_ready=0;
    dashToolsCheckUpdates();
    assert(!requests && !installs);
    assert(!strcmp(last_title,"Update check unavailable"));
    assert(!strcmp(last_body,"Detailed network startup failure"));
    reset("behind",old,200);
    dashToolsCheckUpdates();
    assert(compares==1 && confirmations==0 && installs==0);
    assert(!strcmp(last_title,"No newer release available"));
    reset("identical",old,200);
    dashToolsCheckUpdates();
    assert(compares==1 && confirmations==0 && installs==0);
    reset("diverged",old,200);
    dashToolsCheckUpdates();
    assert(compares==1 && confirmations==0 && installs==0);
    assert(!strcmp(last_title,"Release is on another commit history"));
    reset("unrecognized",old,200);
    dashToolsCheckUpdates();
    assert(!strcmp(last_title,"Could not verify update order") && installs==0);
    reset("ahead",old,404);
    dashToolsCheckUpdates();
    assert(!strcmp(last_title,"Could not verify update order") && installs==0);
    reset("ahead","not-a-commit",200);
    dashToolsCheckUpdates();
    assert(compares==0 && confirmations==0 && installs==0);
    reset("ahead","e70d903c7811a1b95b95771fa6fd813f48f5ecd4",200);
    dashToolsCheckUpdates();
    assert(compares==0 && confirmations==0 && installs==0);
    assert(!strcmp(last_title,"Launchstation is up to date"));
    assert(!updateIsCommitId("local") && !updateIsCommitId("../malformed"));
    assert(updateIsCommitId("e70d903"));
    puts("PASS: updater only installs a proven descendant; stale/divergent/unknown builds are blocked");
}
'''
compiler=shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-update-order-") as temp:
    path=Path(temp)/"check.c"
    binary=Path(temp)/"check"
    path.write_text(program)
    for variant in ([], ["-DDS34"]):
        subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                        "-I",str(root/"include"),*variant,
                        str(path),"-o",str(binary)],check=True)
        subprocess.run([str(binary)],check=True,timeout=5)
