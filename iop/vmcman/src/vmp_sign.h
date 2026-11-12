#ifndef VMC_VMP_SIGN_H
#define VMC_VMP_SIGN_H

/* Re-sign a complete PSP VMP using its existing seed, preserving the header.
 * The only bytes changed here are the 20-byte HMAC at offset 0x20. */
int vmc_vmp_sign(int fd);

#endif
