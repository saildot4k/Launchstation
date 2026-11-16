#ifndef FILER_TRANSFER_H
#define FILER_TRANSFER_H
/* 64-byte aligned caller-owned buffers. A second 1 MiB buffer is optional.
 * Returns the buffer count, or 0 if the required buffer could not be allocated.
 * Empty transfers allocate nothing and return one buffer position. */
int filerAllocateTransferBuffers(int size, void **first, void **second);
#endif
