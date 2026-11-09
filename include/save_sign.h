#ifndef SAVE_SIGN_H
#define SAVE_SIGN_H
#include <stdint.h>
#include <stddef.h>
/* Legacy PSV/VMP format checksums, shared by the EE exporter and IOP VMC. */
typedef struct {
    uint32_t hash[5], bytes;
    unsigned used;
    uint8_t block[64];
} SaveSha1;
typedef struct { SaveSha1 sha; uint8_t outer[64]; } SaveSigner;
int saveSignInit(SaveSigner *signer, const uint8_t seed[20], int type);
void saveSignUpdate(SaveSigner *signer, const uint8_t *data, unsigned length);
void saveSignFinish(SaveSigner *signer, uint8_t digest[20]);
#endif
