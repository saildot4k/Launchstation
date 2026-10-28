# Device transfer comparison with wLaunchELF_R3Z

Reviewed against saildot4k/wLaunchELF_R3Z `master` at
[`06b06d000072d358c93d98104d64d2f081e47ba7`](https://github.com/saildot4k/wLaunchELF_R3Z/tree/06b06d000072d358c93d98104d64d2f081e47ba7).
This records source comparison and host regression evidence. Physical PS2,
adapter, server and filesystem reliability require console testing.

## Source ownership

| Source | Responsibility |
| --- | --- |
| `src/filer_browser.c` | Clipboard, paste orchestration, source availability after IOP reset, deletion after a successful Cut/Paste |
| `src/filer_copy.c` | Recursive copy, exact transfer lengths, replacement staging/readback/publication, metadata, transfer diagnostics |
| `src/filer_device.c` | Device initialization and rejection of incompatible driver pairs before opening handles |
| `src/filer_fileops.c` | Device path adjustments and fileXio wrappers, including 64-bit seek with legacy fallback |
| `src/gui_hdd0_format.c` | Logical HDD/DVR partition paths to PFS paths |
| `src/filer_mount.c` | HDD/DVR mount ownership and mount slots |
| `iop/mmceman/src/mmce_fs.c` | MMCE protocol requests, response decoding and errno translation |
| `iop/vmcman/src/mcdev.c` | Mounted card filesystem operations, including sibling renames |
| `iop/vmcman/src/ps1mc_fio.c`, `ps2mc_fio.c` | Card metadata receivers; bound fixed-width entry names before string lookup |
| `iop/udpfs_smap/src/xfer.c` | UDPFS receive FIFO and final partial-word handling |

## Findings and changes

R3Z removes an existing destination and opens a new truncated file. Launchstation
added staged replacements that need GetStat, readback and rename support.
Those extra requirements exposed driver differences which the R3Z write path
does not encounter.

The [interactive rename follow-up](2026-10-26-device-rename-audit.md) consolidates
the local-device rename implementation into `genRenameNoReplace` in
`filer_fileops.c`. HOST lacks standard rename and stat operations, but does
implement a handle-based rename ioctl; that route is restored for interactive
renaming and remains unsuitable for this stat/rename replacement transaction.

| Destination | Finding | Result |
| --- | --- | --- |
| MMCE0/1 | Firmware GETSTAT reports a missing path as status 1; the old IOP wrapper returned generic `-1`. Added destination checks rejected new files. | The preceding fix maps that completed firmware response to `-ENOENT`; transport errors and unknown statuses remain failures. |
| UDPFS | The embedded IOP module does not implement rename. Staging can write successfully but cannot publish a replacement. | Retain R3Z's direct truncated writes, like legacy HOST. Failed copies retain Cut sources; the old destination cannot be retained transactionally on this driver. |
| VMC0/1 | VMCMAN rename expects a leaf name. Passing a full relative path fails or introduces a slash into the card entry. Its length check also rejected a valid 32-byte name. | Pass the sibling leaf; accept all 32 entry bytes, initialize the table, and terminate bounded working copies in the PS1/PS2 metadata receivers before string lookup. |
| PSX internal flash | XFROM uses its dedicated card RPC for rename, as in R3Z's interactive rename operation. Ordinary fileXio rename is insufficient. | Use `xfromSetFileInfo` with the rename mask and check RPC completion, then verify the old/new paths. |
| MC0/1, USB/MASS, MX4SIO, ATA, PFS, DVR PFS, CF | No additional ordinary-copy regression established in this review. | Retain staged replacements, rollback and existing driver-specific initialization/metadata behavior. |

HOST and UDPFS writes remain subject to the browser's existing network-write
setting and server permissions. Optical media is a copy source only.
PSU extraction retains R3Z's direct entry writes into the prepared restore
folder; it does not use ordinary-file replacement transactions.

The production driver policy rejects MX4SIO ↔ MC1, MX4SIO ↔ MMCE,
HOST ↔ UDPFS, and PC CARD CF ↔ DEV9-backed storage/network devices.
The first two restrictions are also present in the compared R3Z policy.
The latter guards account for Launchstation's network mode resets and shared
CF/DEV9 ownership. These are not routes to enable by bypassing preflight.

## UDPFS final byte

The historical precompiled SMAP, ministack and IOMAN files have the same Git
blob IDs as R3Z:

| Historical module | Git blob |
| --- | --- |
| `udpfs_smap.irx` | `a8ad1bf35a0ab57c4119dce82ee5ca39402cd3aa` |
| `udpfs_ministack.irx` | `7696096abf3df9fe56ec7ef0f28d27b3d533985e` |
| `udpfs_ioman.irx` | `638f0ab4527ee5b806ee5fe3f965922a27959015` |

The old SMAP tail copies whole words and an optional halfword, leaving an odd
final byte stale despite reporting the complete read length. Launchstation
already replaces that historical SMAP blob with the source-built fix described
in [`iop/udpfs_smap/ORIGIN.md`](../../iop/udpfs_smap/ORIGIN.md). Both build routes
must use that output. The legacy blob is only a reference.

The receive test checks 70,080 combinations: lengths 1–1460, two frame starts,
four payload offsets, three DMA sizes and two destination fills. It requires
the old algorithm to fail and verifies the fixed algorithm's byte content and
buffer bounds. This is a specific explanation for the reported final-byte
concern, not evidence that every UDPFS server/network failure is resolved.

UDPFS rename support was also checked against the IOP operation table in the
embedded blob: rename returns `-EIO`. The
[pinned Neutrino wrapper](https://github.com/ps2max32/neutrino/blob/06188cce7cd07d2a158cb4b2646c5719fc16a565/iop/udpfs/src/udpfs_ioman.c)
has the same unsupported operation. IOMAN and ministack remain unchanged.

## HDD-OSD and memory-card attributes

The production constants and copy branches match
[R3Z's copier](https://github.com/saildot4k/wLaunchELF_R3Z/blob/06b06d000072d358c93d98104d64d2f081e47ba7/src/filer_copy.c).
The transfer changes preserve them:

| Operation | Metadata behavior |
| --- | --- |
| Non-card source → MC0/MC1 | Normalize folders to `0x8427` and files to `0x8497`. Network sources use the attribute-only request rather than importing server dates. |
| Card-like source → MC0/MC1 | Preserve the source table, including application/PDA, copy-protection and reserved metadata, and timestamps. |
| Folder → HDD `__common` | Set the second-level save-folder attribute to `0xC4A7`, or `0xC4AF` when copy-protected, through `FIO_CST_ATTR`. Preserve the R3Z PDA-executable exclusion. |

The HDD condition is deliberately the original second-folder-level rule:
`hdd0:/__common/GROUP/SAVE/` maps to `pfsN:/GROUP/SAVE/` and receives the flag.
It does not tag every folder directly under `__common`, folders outside that
partition, or PDA-executable folders. The same partition check accepts hdd1.
Setting these attributes alone does not create missing icons or application
launch metadata.

Host tests execute the actual copy paths and capture the MC/fileXio metadata
requests. They check normalization for both MC slots, full card-to-card table
preservation, both HDD flag values, repeated pastes, both HDD units, and the
depth/partition/PDA exclusions. Production constants are compiled into the
harness and checked against the expected values. Console readback and HDD-OSD
visibility remain hardware acceptance checks.

## Regression evidence

`tests/test_copy_pipeline.py` now compiles the actual copier, clipboard paste,
device preflight and HDD/DVR path parsers. It executes:

- 22 representative paths: MC0/1, USB0/1, MASS0, ATA0, MMCE0/1, MX4SIO,
  VMC0/1, PFS0/1, logical HDD0/1, both DVR partition mappings, XFROM0, CF0,
  HOST, UDPFS and CDFS.
- 434 ordered path pairs allowed by the production policy and 28 rejected
  pairs; CDFS destinations are excluded. This includes transfers within one
  device between distinct directories.
- 1,715 file operations: new copies, shorter replacements, empty replacements
  and Cut/Paste. Also 847 folder operations covering a file, an empty child
  directory and moves over existing folders.
- 612 additional transfers across 34 sizes and nine destinations, from zero
  through 1 MiB + 1. Sizes surround FIFO, alignment and all copy buffer
  boundaries. Tests compare the complete file contents and exact length.
- Last-byte read/write stalls on new and existing destinations, plus a later
  item failing in a multi-item move. Sources remain present after failure.
- The reported 15,523,560-byte APOLLO folder copy to both MMCE slots, including
  replacement and real MMCE GETSTAT packet decoding.
- Existing source/load/read/write/close/cancel/verification/publication error
  cases, ordinary recursion, same-directory no-op and PSU restore behavior.
- Nested replacements with 32-byte filenames on both MC/VMC slots and XFROM.

Three isolated negative controls restore the old UDPFS, VMC and XFROM rename
behavior individually. The matrix fails at replacement publication with
`-EIO`, `-ENAMETOOLONG` and `-ENOSYS`, respectively. The fixed paths pass.
`tests/test_vmc_rename.py` separately compiles the production IOP rename and
checks lengths 1–32, overflow rejection, initialized metadata, semaphore
release and mapped card errors; the previous length check fails its boundary.
The receiver checks put nonzero guard bytes after a full-width entry, then run
the production PS2 name validation and PS1 lookup dispatch. This prevents a
32-byte name from depending on incidental stack padding for termination.

Supporting tests cover positive short I/O, replacement rollback, transfer
preflight/progress, MMCE protocol/path guards, USB path mapping, CF filesystem
guards and the SMAP receive/startup algorithms.

## Validation limits and console acceptance

File operations and most driver/module/RPC responses in the matrix use POSIX
fixtures. This exercises production orchestration and driver contracts, not
the physical devices. VMC backing media, actual mount exhaustion, filesystem
case/alias behavior, server permissions, device capacity and real IOP/module
timing are not established by these tests. Existing best-effort metadata calls
also need console readback to establish persistence.

No ELF or IRX was built during this audit because this workspace lacks the
PS2 toolchain. Before release, build both controller variants and run the
following acceptance on available hardware:

1. Use `scripts/copy_test_pack.py --output /tmp/LS-COPY-TEST.zip` to generate
   deterministic fixtures, then copy the scratch folder in both directions
   between available devices. Repeat over existing files.
2. Copy results to a new PC directory and run
   `scripts/copy_test_pack.py --verify <returned-folder>`. Include odd-sized
   UDPFS files, a server reconnect, and the original APOLLO folder transfer.
3. Use Cut/Paste only on disposable duplicates; check successful source
   removal and retained sources when the destination is full/disconnected.
4. Copy a known-good application/save folder to both MC slots and the same
   `__common` layout used in R3Z. Read back attributes and verify HDD-OSD
   listing/launch, icons, protection flags and timestamps.
