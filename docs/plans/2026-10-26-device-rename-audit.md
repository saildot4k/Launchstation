# Writable-device rename audit

Reviewed the interactive Rename operation for files and directories and its
relationship to the copy replacement transaction. CDFS remains read-only.
Host tests execute production C functions with filesystem/driver fixtures;
they do not establish physical PS2 or server reliability.

## Confirmed defects corrected

| Area | Before | After |
| --- | --- | --- |
| MC0/MC1 | Renamed through a cast of the caller's const FILEINFO, truncated the name to 31 bytes, submitted the rename twice, and checked a different variable from the RPC result. Failures could appear successful. | A separate initialized table carries the name with the rename-only mask. Check submission and completion, translate card results, enforce PS1/PS2 limits, and verify the resulting paths. The caller's FILEINFO stays unchanged. |
| VMC0/VMC1 | Interactive rename passed the full destination path to a driver that expects a sibling filename. | Pass the leaf through the shared rename implementation. The IOP also enforces the 20-byte PS1 limit, alongside the 32-byte PS2 limit. |
| HDD/PFS | The HDD branch bypassed the existing-name check used by other branches. | Existing files and folders are checked consistently; a failed stat is not treated as permission to replace. |
| DVR HDD | Manual string slicing could lose a directory separator or dereference a missing slash, and duplicated the partition mapping logic. | Resolve the parent once with `genFixPath`; both names use the same mapped/mounted parent. |
| XFROM | Used the same mutable-table/truncated-name structure as the MC branch and could repeat a rename. | Use the shared card RPC implementation and verify completion without changing the source entry. |
| HOST | Used unsupported standard `fileXioRename` despite the driver implementing rename through an ioctl. | Restore the handle ioctl, including full-path payload, correct file/directory closure, wire limits, and success checks. Preserve both slash and Windows backslash path modes. |
| UDPFS | Offered Rename even though its embedded driver has no rename operation. | Disable only Rename through the shared menu policy, and return `-ENOSYS` for direct calls. Other supported writes remain available. |
| Filename entry | Rename dialogs imposed a 36-character limit, and the classic keyboard separately imposed 33. | Rename dialogs allow the FILEINFO name-buffer limit; the backend rejects device-specific overflow instead of silently shortening it. |

The local HOST implementation in `iop/ps2host/net_fsys.c` accepts
`IOCTL_RENAME` (`0xFEEDC0DE`) only on the most recently opened handle.
`net_fio.c` always copies 256 argument bytes. Conflict probes must finish before
opening the source; no intervening open may occur before the ioctl. The new
caller zero-initializes the full EE `IOCTL_BUF_SIZE` argument (currently 1024
bytes), since fileXio copies that amount even though the peer uses only 256.
The complete mapped path after the `host:` prefix must fit the peer's 256-byte
field. A compatible PC-side HOST server is required. The EE buffer contract was
checked against PS2SDK's
[fileXio client](https://github.com/ps2dev/ps2sdk/blob/master/ee/rpc/filexio/src/fileXio_rpc.c)
and [packet header](https://github.com/ps2dev/ps2sdk/blob/master/common/include/fileXio.h).
This route also exists in
[upstream wLaunchELF](https://github.com/ps2homebrew/wLaunchELF/blob/master/filer.c)
(reviewed file blob `240c2aca0c48e5ac4829369e17890ea59b2e1aaa`).

## Ownership and behavior

| Source | Responsibility |
| --- | --- |
| `src/filer_actions.c` | Validate the interactive request, enforce exploit-folder protection, prepare/resolve the parent once, handle HOST's descriptor protocol, and verify native case-only rename results. |
| `src/filer_fileops.c` | `genCanRenamePath` advertises capability; `genRenameNoReplace` validates physical sibling paths, checks conflicts, dispatches card/VMC/standard operations and verifies success. |
| `src/filer_copy.c` | Replacement publication and rollback use the same shared local-device rename implementation. |
| `src/filer_browser.c` | Shared operation availability for classic and native browsers, including unsupported UDPFS rename. |
| `src/dash_browser.c`, `src/gui.c` | Native/classic name input, allowing the caller's buffer limit. |
| `iop/vmcman/src/mcdev.c` | Enforce card-format-specific leaf length before changing the entry. |

Renames use the native rename operation rather than copying and deleting data.
The MC/XFROM request changes only the entry name (`0x0010`); it does not
normalize application/save flags or rewrite timestamps. HDD-OSD attributes,
protection flags, reserved fields and child directory contents are preserved.
The [transfer audit](2026-10-26-device-transfer-audit.md) describes the separate
normalization required when copying between devices.

| Device family | Rename route / limits |
| --- | --- |
| MC0/1 | libmc rename-only SetFileInfo and checked Sync; PS1 names ≤20 bytes, PS2 names ≤32 bytes |
| VMC0/1 | fileXio rename with sibling leaf; IOP checks PS1/PS2 20/32-byte limits |
| USB/MASS, MX4SIO, ATA, CF | Mapped device paths and ordinary fileXio rename; CF aliases are normalized and offline media fails before mutation |
| MMCE0/1 | Ordinary fileXio rename; each complete relative wire path is limited to 254 bytes plus NUL |
| Logical HDD0/1, PFS, DVR partitions | Resolve/mount the logical parent, then rename physical siblings |
| PSX internal flash | XFROM rename-only RPC with checked completion |
| HOST | Last-opened-handle ioctl; complete peer path must fit 255 bytes plus NUL |
| UDPFS | Unsupported by the current driver; Rename disabled |
| CDFS | Read-only; Rename disabled |

Existing-name checks apply to both files and directories. Stat errors on local
devices propagate; only `-ENOENT` denotes an absent target. The operation
rejects empty/pseudo names, directory/device separators, control characters,
overlong names/paths, cross-parent requests to the shared backend, and protected
exploit-folder changes. Identical names are no-ops. The existence check is not
an atomic filesystem primitive for arbitrating concurrent writers.

### Case-only rename follow-up, 2026-10-27

Interactive ASCII case-only changes, such as `GAME.ELF` to `game.elf`, use only
the native driver operation in the shared request handler used by both browsers.
The final policy, updated on 2026-10-27, removes temporary-name emulation and
fallback retries entirely. An operation rejected by the driver returns its error.
A driver that reports success without changing the spelling returns
`-EOPNOTSUPP`; Launchstation does not emulate that missing capability.

| Route | Behavior |
| --- | --- |
| MC0/1, VMC0/1, XFROM, PFS and mounted HDD/DVR partitions | One normal checked native rename; no directory enumeration or temporary name. These filesystems compare exact names. |
| Other local devices and HOST where the new spelling is absent | One normal checked rename. HOST behavior follows the server filesystem rather than an assumed PC platform. |
| BDM/FatFs (USB/MASS, ATA, MX4SIO, CF), MMCE or HOST where lookup finds a case alias | Verify exact stored names, issue one direct native rename, then verify the resulting spelling. Reject an existing distinct destination before calling the driver. |
| MMCE with the reviewed SdFat-backed firmware | Ordinary renames are supported. Case-only changes are rejected by the firmware and that error is returned without emulation. The current protocol does not report FAT32 versus exFAT; both formats hit the same exclusive-create check. |
| Native case-alias attempt rejected, or returning success with the original spelling unchanged | Return the driver error, or `-EOPNOTSUPP` for unchanged spelling. No temporary name, second rename or rollback. |

On case-sensitive filesystems a third spelling such as `Game.elf` is a valid
separate entry and does not block renaming `GAME.ELF` to an unused `game.elf`.
The requested destination itself still must be absent. Case-sensitive driver
errors return immediately without staging or retrying the mutation.

For an alias lookup, stat/open alone cannot distinguish two spellings of the
same entry. Directory enumeration therefore requires the exact original name
and rejects an actual destination or another case-equivalent entry before any
native alias attempt. All listing handles close before a HOST rename handle
opens. Directory errors stop the operation. Every native driver error,
including collisions, is returned without retrying. An error after the
requested spelling actually appeared is reported without another rename.

This policy follows the reviewed driver sources:

- PS2SDK's [FatFs bridge](https://github.com/ps2dev/ps2sdk/blob/master/iop/fs/bdmfs_fatfs/src/fs_driver.c)
  calls `f_rename` and returns its negated result (reviewed file blob
  `290cf6375999fdf61e664fd403abe6829c97130f`).
- [FatFs `f_rename`](https://github.com/fjtrujy/FatFs/blob/iop-r0.16/source/ff.c)
  recognizes the same source entry when checking destination collisions on both
  FAT32 and exFAT, allowing direct case changes (file blob
  `04d1fd3b29903817ff2c11d6b41cd5989998492f`).
- The reviewed MMCE [firmware wrapper](https://github.com/sd2psXtd/firmware/blob/main/ext/ESP8266SdFatWrapper/src/sd.cpp)
  delegates to SdFat rename. Both its [FAT implementation](https://github.com/sd2psx/ESP8266SdFat/blob/rp2040/src/FatLib/FatFile.cpp)
  and [exFAT implementation](https://github.com/sd2psx/ESP8266SdFat/blob/rp2040/src/ExFatLib/ExFatFileWrite.cpp)
  create the destination with `O_EXCL`, rejecting the existing case alias.
  Reviewed blobs respectively: `2a42b2bb77b2b8df4b7ab56324250e3d3c705c9a`,
  `de099efc636720c2b5d28da5b2a44fa1e446487a`,
  `5e95a7c123f2f44e198d41e11e9022c23ea48a21`.

The copy engine retains its strict shared rename backend; its publication and
rollback names do not require case-alias handling.

The application neither copies payloads nor normalizes card/application flags
when renaming. Existing name/path limits still apply to the native request.
After an ambiguous driver error or disconnect, reopen the directory to check
the actual spelling before retrying. No application workaround can make the
driver's native operation atomic across power loss or other writers.

HOST has no stat operation, so its conflict and result checks use directory/file
probes. Server permissions, disconnects and concurrent PC changes need live
server testing. An RPC/close failure after a successful underlying rename is
reported as an error; the code does not blindly repeat the mutation.

## Evidence

`tests/test_rename_devices.py` compiles the actual request handler, shared rename
backend, conflict probes, HOST helper, HOST path formatter and HDD/DVR parsers.
Most driver I/O, `genFixPath`, module loading, mount slots and card RPC responses
use POSIX fixtures. With the native-only case policy, the test exercises
1,616 counted rename cases plus input and capability guards across 24
representative paths/aliases, covering:

- Files and folders at roots and in nested directories, including child data.
- MC0/1, VMC0/1, USB0/1, unnumbered/numbered MASS, ATA0/1, MX4SIO, MMCE0/1,
  CF aliases, PFS, logical HDD0/1, both DVR partition mappings, XFROM and HOST.
- File/file, file/folder, folder/file and folder/folder conflicts; no overwrite
  or mutation call is issued for a detected conflict.
- Complete payload, object identity, mode and modification-time preservation
  on host fixtures; caller FILEINFO immutability and no leaked descriptors.
- Exact PS1/PS2 20/32-byte names, overflow rejection, 255-byte ordinary names,
  HOST wire-path limits, and slash/backslash HOST formatting.
- MMCE relative paths of 254/255 bytes, including long parent directories,
  with overflowing requests rejected before mutation on both slots.
- Source/destination stat errors, false-success drivers, module/CF failures,
  card submission/completion errors and result translation, changed-card wakeup,
  ambiguous completion, and HOST close failure.
- CDFS and UDPFS capability rejection, invalid names, path bounds, cross-parent
  backend requests and exploit-folder protection.
- Direct case-only files/folders on all 24 paths with case-sensitive fixtures;
  case-insensitive fixtures on BDM, MMCE and HOST. Exact destination conflicts
  are preserved; a third spelling coexists on case-sensitive fixtures.
- One mutation and no directory reads on MC/VMC/PFS/XFROM, including driver
  failure, false success and applied-but-reported-error cases. Supporting
  case-insensitive FatFs/HOST adapters also receive only one native rename.
- Rejection without retry after a native collision, raw driver error, missing
  capability or successful no-op. MMCE errors leave the original intact on both
  slots. Fixtures for a hypothetical firmware supporting native case changes
  ensure the application does not hard-code a ban on MMCE capitalization.
- Existing entries named like the removed workaround's candidates remain
  untouched and do not block a supporting driver. Maximum-length card/USB names
  and complete MMCE/HOST paths cover native success and rejection, including
  both HOST separator modes.
- Applied-but-reported-error operations; directory open/read/close errors and
  malformed names. Tests check surviving file identity, payload/children,
  metadata and closed descriptors.

The initial 715-case audit reproduced caller FILEINFO mutation after the first
MC rename with the earlier handler. The current test also compiles against the
preceding fallback handler and fails when it emulates a rejected MMCE case-only
rename. Existing tests also
pass for replacement rollback/recovery, the full copy/PSU matrix (434 allowed
ordered pairs and 612 boundary transfers), MC/HDD-OSD copy flags, MMCE contracts,
CF guards and both keyboards. `tests/test_vmc_rename.py` runs the actual IOP
rename and bounded metadata receivers, including the added PS1 length checks.

No ELF/IRX build or physical-console test was possible without the PS2 toolchain.
Acceptance requires both controller builds, file/folder renames on available
devices, conflict checks, card metadata/OSD verification, and HOST testing with
the user's actual compatible server in both path-separator modes.
For the case-only follow-up, include real FAT32/exFAT USB files and folders,
maximum-length names, exact spelling after reopening the directory, and
unchanged contents/attributes. The host case-insensitive adapter validates
control flow and recovery; it does not run the console FAT/exFAT drivers.
