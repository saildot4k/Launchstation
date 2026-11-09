/* PSP VMP signature layout and key derivation: dots_tb's Vita MCR2VMP,
 * also documented in Apollo PS2 source/psv_resign.c. This implementation
 * uses bounded streaming I/O and no heap or external crypto service.
 * AES-128 and SHA-1 here implement this legacy file-format checksum only.
 */
#include <stdint.h>
#include <string.h>
#include <iomanX.h>
#include "vmp_sign.h"
#include "../../../include/save_sign.h"

static int read_exact(int fd, uint8_t *data, unsigned n)
{
	while (n) {
		int got = iomanX_read(fd, data, n);
		if (got <= 0 || (unsigned)got > n) return -1;
		data += got; n -= got;
	}
	return 0;
}

int vmc_vmp_sign(int fd)
{
	uint8_t header[128], data[512], digest[20];
	SaveSigner signer;
	unsigned remaining = 131072, written = 0;
	if (iomanX_lseek(fd, 0, 0) != 0 || read_exact(fd, header, sizeof(header))) return -1;
	if (header[0] || header[1] != 'P' || header[2] != 'M' || header[3] != 'V') return -1;
	if (!saveSignInit(&signer, header + 12, 1)) return -1;
	memset(header + 32, 0, 20);
	saveSignUpdate(&signer, header, 128);
	while (remaining) {
		unsigned n = remaining < sizeof(data) ? remaining : sizeof(data);
		if (read_exact(fd, data, n)) return -1;
		saveSignUpdate(&signer, data, n); remaining -= n;
	}
	saveSignFinish(&signer, digest);
	if (iomanX_lseek(fd, 32, 0) != 32) return -1;
	while (written < 20) {
		int n = iomanX_write(fd, digest + written, 20 - written);
		if (n <= 0 || (unsigned)n > 20 - written) return -1;
		written += n;
	}
	return 0;
}
