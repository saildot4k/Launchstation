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
| `src/filer_actions.c` | Validate the interactive request, enforce exploit-folder protection, prepare/resolve the parent once, handle HOST's descriptor protocol, and coordinate case-only rename staging/rollback. |
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

Interactive ASCII case-only changes, such as `GAME.ELF` to `game.elf`, now use
two native sibling renames through an unused temporary name. Both browsers use
this shared request handler. The copy engine retains its strict shared rename
backend; its staging/publication names do not require case-only handling.

Directory entries provide the actual stored spelling: stat/open alone resolve
both spellings to the same entry on a case-insensitive device. Before changing
anything, the code requires the exact original spelling and rejects another
entry with the requested or any other case-equivalent spelling. This preserves
distinct files/folders on case-sensitive filesystems. Directory open/read/close
errors abort; all listing handles close before HOST opens its rename handle.

Temporary candidates never exceed the original leaf length, preserving PS1/PS2
card limits, maximum-length USB names, and MMCE/HOST complete-path limits. The
code skips occupied candidates and their case aliases. Longer names use
`LSRN000.TMP` through `LSRN999.TMP`; names of 4–10 bytes use `R000` through
`R999`, and shorter names use decimal candidates of the same length.

After each hop the code checks actual directory spellings. If publication
fails with only the temporary entry present, it attempts to restore the original
name. Failed rollback leaves the temporary data intact. A directory error or
ambiguous state stops further mutation. An error reported after publication
actually applied is still reported, without repeating or undoing publication.
After a disconnect or failed rollback, refresh/reopen the directory and inspect
the original, requested and temporary names before retrying. This is a native
rename transaction, so payloads, children and card/application flags are not
copied or normalized. The two hops are not atomic across power loss or other
writers.

HOST has no stat operation, so its conflict and result checks use directory/file
probes. Server permissions, disconnects and concurrent PC changes need live
server testing. An RPC/close failure after a successful underlying rename is
reported as an error; the code does not blindly repeat the mutation.

## Evidence

`tests/test_rename_devices.py` compiles the actual request handler, shared rename
backend, conflict probes, HOST helper, HOST path formatter and HDD/DVR parsers.
Most driver I/O, `genFixPath`, module loading, mount slots and card RPC responses
use POSIX fixtures. With the case-only follow-up, the test exercises 1,309 counted rename cases plus input and
capability guards across 24 representative paths/aliases, covering:

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
- Case-only files/folders on all 24 device/alias paths with both case-sensitive
  and case-insensitive adapters; existing distinct case-equivalent targets.
- Temporary-name collisions/aliases and exhausted short-name candidates;
  maximum-length card/USB names and complete MMCE/HOST paths, including both
  HOST separator modes.
- Failure or false success at either hop or rollback; applied-but-reported-error
  operations; directory open/read/close errors and malformed names. Tests check
  surviving file identity, payload/children, metadata and closed descriptors.

The initial 715-case audit reproduced caller FILEINFO mutation after the first
MC rename with the earlier handler. The expanded test also compiles against the
handler immediately before the case-only follow-up and fails its case-only
success assertion. Existing tests also
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
