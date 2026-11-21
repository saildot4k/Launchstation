# HDD formatting

HDD Manager offers three destructive whole-drive formats. All formats erase
existing partitions and require the existing two confirmations, after the
format and its capacity summary have been selected.

| Format | Layout |
| --- | --- |
| APA | Existing APA formatter and PFS system partitions |
| exFAT | MBR, one partition starting at 1 MiB, label `PS2`, 32 KiB clusters |
| APA Jail (APA + exFAT) | A2 marker, MBR APA area, 32 MiB ext2 `RECOVERY`, then exFAT `PS2` with 32 KiB clusters |

The APA Jail size selector reserves **additional** space after the standard
APA system partitions. It uses 128 MiB increments and permits zero additional
space. The maximum keeps the APA area within half of the drive. The system
partition sizes follow the existing driver's capacity-dependent size cap;
on most drives they occupy 2 GiB. Creating APA layouts requires at least
8 GiB, so that the driver's cap does not fall below 128 MiB. Plain exFAT
requires at least a 64 MiB volume plus alignment and metadata space.

The formatter uses the ATA driver's existing 32-bit sector capacity. It rejects
the driver's saturated-capacity sentinel for larger drives; this is not a
formatter for disks beyond the current 2 TiB addressing limit. Disks whose
capacity cannot be distinguished from a driver error are also refused.
PSX/DESR internal-drive formatting remains unavailable.

## Driver lifetime

The HDD and ATA driver sources and ABIs are unchanged. The small, separately
loaded `iop/hdd_format` service provides checked raw transfers in 32 KiB chunks.
Before writing, Launchstation stops audio, checks VMC/PFS unmount results,
refuses an active FTP server, and detaches the ATA0 BDM root and its mounted
volumes. The normal runtime IOP reset reloads controllers and the storage stack
after the worker finishes, including after a failed format. This drops stale
APA and FAT caches before the drive is accessed again. Builds that disable
IOP reset cannot use this formatter.

The portable writer in `src/hdd_format.c` validates its plan before writing,
builds exFAT allocation metadata and both boot regions, checks the generated
boot regions and final MBR by reading them back, repairs the hybrid APA header
checksum, and flushes writes. Errors are reported as partial-format failures;
they never produce a success notification.

## APA allocation boundary

`src/hdd_apa_boundary.c` reads and validates the root APA header and MBR ranges.
The shared EE HDD library checks each main/subpartition allocation against the
APA boundary before asking the unmodified driver to allocate it. It follows
the driver's first eligible free-size slot, then its aligned append policy.
Both build systems use that library. Reported APA free space excludes recovery
and exFAT space. Unknown or damaged hybrid maps disable allocations rather
than treating the rest of the physical disk as available APA space.

This protects allocations made through Launchstation. Other applications and
drivers can still allocate beyond the reserved APA area. The
[PSBBN Definitive Project documentation](https://github.com/CosmicScale/PSBBN-Definitive-Project#apa-jail)
describes the same risk of overwriting exFAT when APA allocations exceed their
reserved space.

New partitions retain the **128 MiB minimum**. The boundary reader can inspect
existing 8 MiB partitions; it does not enable their creation. An append after
a tail that is not aligned to 128 MiB is refused because the stock allocator
cannot safely pad it. A suitably aligned existing free block can still be
reused. Supporting new mini partitions would also need a review of the
allocator, PFS overhead and compatibility with other PS2 software.

## Recovery volume

The A2 recovery partition contains a creation-time snapshot of the first
128 MiB (`apa_index.gz`), the cleared final 33 sectors (`gpt_2nd.bin`), and a
`README.txt`. These files do not track later APA changes or back up user files.
The snapshot uses the existing zlib dependency and gzip instead of PSBBN DP's
xz. Decompress it before using raw recovery tools; do not pass it to a tool
that specifically expects `apa_index.xz`.

The layout is based on the
[PSBBN DP installer](https://github.com/CosmicScale/PSBBN-Definitive-Project/blob/main/scripts/PSBBN-Installer.sh).
The filesystem writer follows the
[Microsoft exFAT specification](https://learn.microsoft.com/en-us/windows/win32/fileio/exfat-specification).
Unicode upper-case mappings are the standalone `ff_wtoupper` function and its
tables from ChaN's FatFs, under its permissive notice retained in
`src/hdd_format_upcase.c`; no code-page conversion tables are included.

## Verification

`tests/test_hdd_format.py` formats sparse host disk images and checks partition
bounds, exFAT boot/upcase checksums, metadata allocation, decompressed recovery
data, capacity limits and injected I/O failures. It runs `fsck.exfat` and
`e2fsck` when installed. `tests/test_hdd_format_ui.py` exercises the actual
format action, cancellation at both confirmations, failure handling and cache
reload. No test opens a physical disk. PS2 hardware validation is still needed.
