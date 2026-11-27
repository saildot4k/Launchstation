PS2SDKSRC ?= $(PS2SDK)

IOP_BIN ?= ata_bd.irx
IOP_OBJS = ps2atad.o imports.o exports.o
IOP_IMPORT_INCS += dev9/dev9 fs/bdm system/loadcore system/stdio system/sysclib system/threadman
IOP_CFLAGS += -DATA_ENABLE_BDM=1 -DATA_USE_DEV9=1 -DATA_GAMESTAR_WORKAROUND=1

include $(PS2SDKSRC)/Defs.make
include $(PS2SDKSRC)/iop/Rules.bin.make
include $(PS2SDKSRC)/iop/Rules.make
include $(PS2SDKSRC)/iop/Rules.release

$(IOP_OBJS): Makefile include/atad.h src/irx_imports.h
