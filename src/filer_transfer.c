#include "filer_transfer.h"
#include <stdlib.h>
#include <malloc.h>

int filerAllocateTransferBuffers(int size, void **first, void **second)
{
	*first = *second = NULL;
	if (size < 0) return 0;
	if (!size) return 1;
	*first = memalign(64, size);
	if (!*first) return 0;
	if (size == 0x100000) *second = memalign(64, size);
	return *second ? 2 : 1;
}
