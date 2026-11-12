# Launchstation memory card drivers

This directory vendors the PS2SDK `mcman`/`vmcman` source used to build the
embedded physical `mcman.irx` and virtual `vmcman.irx` modules.

Base snapshot:

- Repository: `ps2dev/ps2sdk`
- Commit: `ff7c5f93763d90c8b10bc97fbce5d25939ed94fb`
- Source path: `iop/memorycard/mcman`

wLaunchELF keeps this as a local module because VMC support needs project
specific fixes and diagnostics. Building from a live PS2SDK source checkout and
patching it during every build made behavior dependent on whichever PS2SDK
revision happened to be in the container.

Local VMC changes include:

- Correct VMC backing geometry validation for no-ECC and ECC images.
- Preserve mounted VMC state so normal file operations do not keep re-probing
  physical memory card hardware.
- Add targeted diagnostics around mount, mkdir, create-file, and backing
  read/write paths.
- Register a startup marker: `vmcman: wLaunchELF patched VMC build active`.

## PS1 images and PS2 ECC

Mounting detects contents and geometry independently of suffix or case. PS1
raw cards have an exact 128 KiB payload with the `MC` header. VGS (64-byte
header), PSP VMP (128-byte header) and DexDrive GME (3904-byte header) mount
directly too. The common VMP/MCR/VM1/BIN/VMC/GME/VGS/SRM/MCD suffixes are
accepted, including names also used for PS2 cards. MC2 and arbitrary raw-image
suffixes work for PS2 as well.

PS1 routes 128-byte sector I/O through the existing PS1 filesystem, initializes
directory caches on mount, and retains its mounted type during detection.
Filesystem flushes update dirty VMP HMAC-SHA1 signatures using a bounded
streaming implementation shared with the EE PSV exporter (`src/save_sign.c`),
or GME directory-state/link tables, while retaining
other wrapper bytes. A failed wrapper update propagates as a flush error and
keeps the image dirty for retry.

PS2 superblocks specify 512-byte data pages and two pages per cache cluster.
File length distinguishes pages with and without 16-byte ECC/spare areas;
geometry, erase-block size, sector and slot bounds are validated before I/O.
Writes recompute the first twelve spare bytes from the page data, preserving
caller-supplied spare metadata or the existing tail for data-only writes.
Unmount flushes dirty caches and wrapper metadata before closing the backing
file, then clears cached handles/device information.

`include/vmc_control.h` defines the private EE/IOP devctl contract:
`VMCCTL_GET_INFO` returns the card type, free units and unit size (8192 for
PS1, 1024 for PS2); `VMCCTL_READ_PS1_PAGE` reads one bounded 128-byte sector
after flushing pending writes. Unsupported requests and short buffers fail.

Host coverage: `tests/test_ps1_vmc.py`, `tests/test_save_formats.py` and
`tests/test_save_import.py`. Physical PS2/card/storage testing is still required.

## Physical PS1 card rediscovery

The same vendored sources also build the physical `mcman` driver, without
`BUILDING_VMCMAN`. Both PS2BUILD (`mcman_physical:mcman`) and the legacy
Makefile embed that local module instead of the SDK's precompiled `mcman`.
The existing MCSERV, SIO2MAN, SIO2 1.2 import interface, and module-loading
order are retained.

A PS1 card can remain powered and return its already-accessed status after an
IOP reset discards the driver's geometry and directory cache. Full detection
now reads the header and directory again when that information is unknown or
belongs to a PS2 card. The fast detection path uses the same recovery when
needed. An already-accessed card needs no insertion-acknowledgement write; the
existing header/directory validation and new-card acknowledgement are retained. A known
unformatted PS1 card continues to report unformatted, and failed reads remain
errors. Recovery and cache invalidation apply only to the requested slot.
