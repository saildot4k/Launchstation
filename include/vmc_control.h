#ifndef VMC_CONTROL_H
#define VMC_CONTROL_H

/* Private, fixed-width EE/IOP devctl interface. */
#define VMCCTL_GET_INFO 0x564d4301
#define VMCCTL_READ_PS1_PAGE 0x564d4302
typedef struct {
	int type;
	int free_units;
	int unit_bytes;
} VmcInfo;

#endif
