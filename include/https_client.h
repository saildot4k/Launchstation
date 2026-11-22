#ifndef WLE_HTTPS_CLIENT_H
#define WLE_HTTPS_CLIENT_H

#include <stddef.h>

/* The upstream installer script used for language discovery exceeds 64 KiB. */
#define HTTPS_BODY_MAX (128 * 1024)
#define HTTPS_LOCATION_MAX 2048

typedef struct {
    int status;
    char *body;
    int body_len;
    char location[HTTPS_LOCATION_MAX];
} HttpsResponse;

/* Serialized transport observer, called on the request's thread. Set/clear
 * only between requests; observers must not draw or re-enter HTTPS. */
typedef void (*HttpsStatusCallback)(const char *status, void *arg);
void httpsSetStatusCallback(HttpsStatusCallback callback, void *arg);
/* Optional installer diagnostics; never emits headers, credentials or bodies. */
void httpsSetTraceCallback(HttpsStatusCallback callback, void *arg);
/* Serialized, scoped CA snapshot for requests across an IOP/storage reset.
 * Caller owns the bytes until cleared with (NULL, 0), between requests. */
void httpsSetCaBundle(const unsigned char *data, unsigned size);

/* Download progress runs on the caller's thread after bytes are written.
 * A zero total means the server has not supplied a body length. */
typedef void (*HttpsProgressCallback)(int done, int total, void *arg);

void httpsResponseFree(HttpsResponse *response);
int httpsRequest(const char *method, const char *host, const char *path,
                 const char *headers, const void *body, int body_len,
                 const char *ca_path, HttpsResponse *response,
                 char *error, int error_size);

/* Stream an HTTPS response body directly to an already-open file descriptor.
 * Follows HTTPS redirects, enforces max_bytes and returns the SHA-256 of the
 * exact bytes written when digest is non-NULL. A NULL digest skips hashing. */
int httpsDownloadFd(const char *url, int fd, const char *ca_path,
                    int max_bytes, int *out_size,
                    unsigned char digest[32],
                    HttpsProgressCallback progress, void *progress_arg,
                    char *error, int error_size);

#endif
