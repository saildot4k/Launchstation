#ifndef WLE_HTTPS_CLIENT_H
#define WLE_HTTPS_CLIENT_H

#include <stddef.h>

#define HTTPS_BODY_MAX (64 * 1024)
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

void httpsResponseFree(HttpsResponse *response);
int httpsRequest(const char *method, const char *host, const char *path,
                 const char *headers, const void *body, int body_len,
                 const char *ca_path, HttpsResponse *response,
                 char *error, int error_size);

/* Stream an HTTPS response body directly to an already-open file descriptor.
 * Follows HTTPS redirects, enforces max_bytes and returns the SHA-256 of the
 * exact bytes written when digest is non-NULL. */
int httpsDownloadFd(const char *url, int fd, const char *ca_path,
                    int max_bytes, int *out_size,
                    unsigned char digest[32],
                    char *error, int error_size);

#endif
