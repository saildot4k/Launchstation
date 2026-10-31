"""Exercise the actual updater comparison/confirmation code with mocked GitHub responses.

This covers stale, current, newer, divergent, malformed and unreachable releases.
It is a host-side regression test, not an HTTPS or console integration test.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
src = (root / "src/dash_tools.c").read_text()


def function(signature):
    start = src.index(signature)
    # Ignore braces inside strings, character literals and comments.
    tokens = re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|/\*.*?\*/|//[^\n]*|[{}]',
                         src[start:], re.S)
    depth = 0
    for token in tokens:
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return src[start:start + token.end()] + '\n'
    raise AssertionError('Unclosed function: ' + signature)


sources = "".join(function(signature) for signature in (
    "static int releaseJsonString(",
    "static const char *releaseObjectEnd(",
    "static int releaseObjectString(",
    "static int releaseAssetString(",
    "static int releaseAssetDigest(",
    "static void releaseUpdateTime(",
    "static int updateIsCommitId(",
    "static void updateHttpsStatus(",
    "static void updateRequestRun(",
    "static int updateRequest(",
    "static int updateCommitRelation(",
    "void dashToolsCheckUpdates(void)\n{",
))
enums = src[src.index("enum { UPDATE_RELATION_UNKNOWN"):src.index("static int updateIsCommitId(")]

request_type = re.search(r"typedef struct\s*\{[^}]+\} UpdateRequestJob;", src).group()

program = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "self_update.h"
#define MAX_PATH 256
#ifndef GIT_HASH
#define GIT_HASH "e70d903"
#endif
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
static int in_worker, submits, job_waits, rendered_frames, status_updates, reject_submit, request_failure;
static char release_stamp[32]="2026-10-30T01:02:03Z", confirmation_body[320];
static void (*pending_run)(void *);
static void *pending_arg;
typedef void (*HttpsStatusCallback)(const char *,void *);
static HttpsStatusCallback status_callback;
static void *status_arg;
#define DASH_JOB_VISIBLE 1
static void httpsSetStatusCallback(HttpsStatusCallback callback,void *arg) {
    assert(in_worker);status_callback=callback;status_arg=arg;
}
static void dashWorkerStatus(const char *text,int done,int total) {
    assert(in_worker && text && *text && !done && !total);status_updates++;
}
static int dashWorkerSubmit(const char *title,int flags,void (*run)(void *),void (*done)(void *),void *arg) {
    assert(!in_worker && !pending_run && !done && title && flags==DASH_JOB_VISIBLE);
    submits++;if(reject_submit==submits)return -1;
    pending_run=run;pending_arg=arg;return submits;
}
static int dashWorkerAwait(int id,const char *title,int cancelable) {
    assert(id==submits && title && !cancelable && !in_worker && pending_run);
    rendered_frames++;job_waits++;in_worker=1;pending_run(pending_arg);in_worker=0;
    pending_run=NULL;pending_arg=NULL;rendered_frames++;
    assert(!status_callback);return 1;
}
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
    assert(!in_worker);(void)kind;(void)detail;
    last_title=title;
    snprintf(last_body,sizeof(last_body),"%s",body ? body : "");
}
static int dashModalConfirm(const char *title,const char *body,const char *action,int danger) {
    assert(!in_worker);(void)title;(void)action;(void)danger;
    snprintf(confirmation_body,sizeof(confirmation_body),"%s",body);
    confirmations++; return 1;
}
int selfUpdateInstall(const char *ca,const char *digest,char *result,int cap) {
    assert(!in_worker && !status_callback);(void)ca;(void)digest;
    installs++;
    snprintf(result,cap,"installed");
    return 0;
}
static int httpsRequest(const char *method,const char *host,const char *path,
                            const char *headers,const void *body,int body_len,
                            const char *ca,HttpsResponse *out,char *err,int err_size) {
    char json[1024];
    (void)headers;(void)body;(void)body_len;(void)ca;(void)err;(void)err_size;
    assert(!strcmp(method,"GET") && !strcmp(host,"api.github.com"));
    assert(network_checks==1 && network_ready && in_worker && status_callback);
    status_callback("Connecting to server",status_arg);
    status_callback("Verifying secure connection",status_arg);
    status_callback("Receiving server response",status_arg);
    if(request_failure) { snprintf(err,err_size,"network timeout");return -1; }
    assert(!strncmp(path,"/repos/saildot4k/Launchstation/",
                    strlen("/repos/saildot4k/Launchstation/")));
    requests++;
    if (strstr(path,"/compare/")) {
        compares++;
        assert(strstr(path,"?per_page=1&page=2"));
        assert(strstr(path,"/compare/" GIT_HASH "..."));
        snprintf(json,sizeof(json),"{\"status\":\"%s\"}",comparison);
        out->status=response_status;
    } else {
        assert(!strcmp(path,"/repos/saildot4k/Launchstation/releases/tags/latest"));
        snprintf(json,sizeof(json),"{\"target_commitish\":\"%s\",\"published_at\":\"2020-01-01T00:00:00Z\",\"assets\":[{\"name\":\"unrelated.zip\",\"updated_at\":\"2030-01-01T00:00:00Z\"},{\"updated_at\":\"%s\",\"name\":\"%s\",\"digest\":\"sha256:%064d\"}],\"updated_at\":\"2035-01-01T00:00:00Z\"}",
                 release_target,release_stamp,SELF_UPDATE_ASSET,0);
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
program += request_type + "\n" + enums + sources
program += r'''
static void reset(const char *status,const char *release,int code) {
    requests=compares=confirmations=installs=0;
    assert(!in_worker && !pending_run && !status_callback);
    submits=job_waits=rendered_frames=status_updates=reject_submit=request_failure=0;
    strcpy(release_stamp,"2026-10-30T01:02:03Z");confirmation_body[0]='\0';
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
    char parsed[80];
    const char *nested_json = "{\"assets\": [{\"name\": \"other.psu\", \"updated_at\": \"2000-01-01T00:00:00Z\"}, {\"uploader\": {\"name\": \"wrong.psu\", \"updated_at\": \"2099-01-01T00:00:00Z\"}, \"label\": \"braces } { and escaped \\\" quote\", \"name\": \"wanted.psu\", \"updated_at\": \"2026-10-30T01:02:03Z\"}], \"updated_at\": \"2098-01-01T00:00:00Z\"}";
    assert(releaseAssetString(nested_json,"wanted.psu","updated_at",parsed,sizeof(parsed)));
    assert(!strcmp(parsed,"2026-10-30T01:02:03Z"));
    assert(!releaseAssetString(nested_json,"wrong.psu","updated_at",parsed,sizeof(parsed)));
    assert(!releaseAssetString(nested_json,"wanted.psu","digest",parsed,sizeof(parsed)));

    if (!updateIsCommitId(GIT_HASH)) {
        reset("ahead",old,200);
        dashToolsCheckUpdates();
        assert(!waits && !requests && !confirmations && !installs);
        assert(!strcmp(last_title,"Update check needs build information"));
        assert(strstr(last_body,GIT_HASH));
        puts("PASS: missing installed commit gets a specific diagnostic without network or installation");
        return 0;
    }
    reset("ahead",old,200);
    dashToolsCheckUpdates();
    assert(compares==1 && requests==2 && confirmations==1 && installs==1);
    assert(waits==1 && polls==1 && ca_checks==1 && network_checks==1);
    assert(submits==2 && job_waits==2 && rendered_frames==4 && status_updates==6);
    assert(strstr(confirmation_body,"Updated: 2026-10-30 01:02:03 UTC"));
    assert(!strstr(confirmation_body,"2020-") && !strstr(confirmation_body,"2030-") && !strstr(confirmation_body,"2035-"));
    reset("ahead",old,200);reject_submit=1;dashToolsCheckUpdates();
    assert(!requests && !job_waits && !installs && !strcmp(last_title,"Update check failed"));
    reset("ahead",old,200);reject_submit=2;dashToolsCheckUpdates();
    assert(requests==1 && job_waits==1 && !installs && !strcmp(last_title,"Could not verify update order"));
    reset("ahead",old,200);request_failure=1;dashToolsCheckUpdates();
    assert(job_waits==1 && !installs && !strcmp(last_body,"network timeout") && !status_callback);
    reset("ahead",old,200);strcpy(release_stamp,"2026-02-30T01:02:03Z");dashToolsCheckUpdates();
    assert(installs==1 && strstr(confirmation_body,"Updated: Unavailable"));
    reset("ahead",old,200);release_stamp[0]='\0';dashToolsCheckUpdates();
    assert(installs==1 && strstr(confirmation_body,"Updated: Unavailable"));
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
    puts("PASS: live worker status, callback cleanup, matching-package UTC dates and only verified descendants; stale/divergent/unknown builds are blocked");
}
'''
compiler=shutil.which("gcc") or shutil.which("clang")
assert compiler, "Host C compiler required"
with tempfile.TemporaryDirectory(prefix="launchstation-update-order-") as temp:
    path=Path(temp)/"check.c"
    binary=Path(temp)/"check"
    path.write_text(program)
    for variant in ([], ["-DDS34"],
                    ['-DGIT_HASH="local"'], ["-DDS34", '-DGIT_HASH="local"'],
                    ['-DGIT_HASH="e70d903c7811a1b95b95771fa6fd813f48f5ecd4"'],
                    ["-DDS34", '-DGIT_HASH="e70d903c7811a1b95b95771fa6fd813f48f5ecd4"']):
        subprocess.run([compiler,"-std=c11","-Wall","-Wextra","-Werror",
                        "-I",str(root/"include"),*variant,
                        str(path),"-o",str(binary)],check=True)
        subprocess.run([str(binary)],check=True,timeout=5)
