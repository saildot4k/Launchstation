# Launchstation FTP integration

The standard PS2BUILD target embeds this directory as `ps2ftpd.irx`.
FTP is an exclusive file-transfer mode. It has its own filesystem adapter;
the EE file browser's lazy-loading rules do not apply inside the FTP service.

| Source | Responsibility |
| --- | --- |
| `src/dash_ftp.c` | FTP screen, controller Stop action and exclusive rendering. |
| `src/ftp_session.c` | EE startup, control-RPC binding, status/stop calls and IOP restoration. |
| `include/ftp_protocol.h` | Fixed-width, versioned EE/IOP status and shutdown protocol. |
| `src/init.c:loadNetModules()` | Core, ATA, HDD/PFS, USB and network startup before FTP accepts clients. |
| `FtpControl.c` / `.h` | Independent IOP control thread: status snapshots and cooperative stop. |
| `FileSystem.c` / `.h` | Allowed paths/units, virtual HDD partitions, mount ownership and native file operations. |
| `FtpCommands.c` | FTP command replies and filesystem dispatch. |
| `FtpClient.c` / `.h` | Authentication, connection-local rename state, data sockets and exact transfer I/O. |
| `FtpServer.c` / `.h` | Socket ownership, bounded TCP command framing and select loop. |
| `main.c` | IOP server thread, control-service startup and final file/mount cleanup. |
| `imports.lst` / `irx_imports.h` | Explicit SDK imports and header dependencies. |

## Startup, exclusivity and stopping

`DashFtpServer()` drains background jobs and outstanding libmc status requests.
`ftpSessionBegin()` establishes a fresh IOP session through the normal reset path,
which restores PADMAN and controller ports and removes MMCE/MX4SIO hooks and old
PFS mounts. It rejects unavailable resets and conflicting PC CARD CF ownership.
`loadNetModules()` then prepares core memory-card services, ATA (EXFAT builds),
HDD/APA/PFS and USB before starting FTP. HDD/ATA startup uses the existing
`shouldHideHddAtaDevices()` console compatibility policy, independent of saved
visibility settings. Unsupported consoles skip those driver loads and pass
`-no-hdd` to the IOP service, which omits both families and rejects their direct
paths even if a driver is registered. Ethernet's shared DEV9 still starts.
Missing storage media on a compatible console does not prevent serving the other
devices. There is no driver loading triggered by FTP requests.
The FTP entry point does not start the separate netfs listener.

The modal owns its frame loop. It does not run dashboard device polling, scans,
artwork workers, remote-command dispatch or the staged ISO receiver. The loading
flag remains active to prevent theme texture getters from queuing fresh disk IO.
The regular background libmc poll also checks FTP module residency.
Confirm and Back both request Stop directly, using the user's button mapping.

The separate 4 KiB IOP control thread can report status while the 8 KiB FTP thread
is inside a driver or socket call. Stop marks the session stopping and shuts down
client sockets to wake pending sends/receives. It does not close filesystem handles
from the control thread. The FTP owner finishes its current driver call, closes
all clients/files, unmounts its idle PFS slots, and only then reports STOPPED.
Close/unmount errors are retained in the final status. The EE then resets the IOP
and returns to normal dashboard operation. An interrupted upload may be partial;
no transfer is declared successful by the stop path.

## Exported devices

| Virtual path | Accessible storage |
| --- | --- |
| `/mc/0/`, `/mc/1/` | Memory-card slots 1 and 2. |
| `/usb/0/`, `/usb/1/` | Typed USB filesystem units 0 and 1. |
| `/hdd/0/<partition>/` | Browsable PFS partitions on HDD0. |
| `/ata/0/` | ATA0 FAT/exFAT filesystem. |

The root lists these four device families once. Unit lists probe only their
allowed units and omit unavailable media. Path classification applies the same
limits to every operation, including absolute paths supplied without CWD.
`mass`, `pfs`, `mmce`, `mx4sio`, extra units and other device prefixes cannot be
accessed by spelling their paths manually. SITE mount management is unsupported.
Virtual device/partition roots cannot be renamed, overwritten or deleted.

Driver lookup uses `iomanX_GetDeviceList()` import 3, without module-memory offsets.
The supported PS2BUILD legacy-hook IOMANX table has 32 sparse slots; NULL entries
are holes. Recheck that bound when changing SDK packages. HDD advertises BLOCK,
not FS, so discovery accepts both types. A USB-only, non-extended legacy `mass`
driver may back `/usb/`; extended shared BDM `mass` is never guessed to be USB.

## HDD paths and mount ownership

HDD partition validation retains the browsable-PFS filter. Every operation maps
`/hdd/0/<partition>/...` to a private PFS mount, so CWD and PWD retain the virtual
HDD path. Absolute LIST, SIZE, upload/download, rename and nested paths use the
same translator; clients never need to manage `/pfs` aliases.

Four private mount slots match the PFS startup configuration. Open files and
directories pin their slots. A second connection can share a partition, while
only an unreferenced slot can be remounted. Exhaustion fails the request instead
of replacing an active transfer's partition. One-shot operations release their
references immediately, including errors. Pending renames retain mount generations
and reject a source whose original slot has since been repurposed.

## Transfer and rename contracts

`FileSystem_ReadDir()` returns 1 for an entry, 0 at end, or a negative error.
`FileSystem_Close()` clears handle ownership even on failure. Transfers check
close/flush results before reporting success. The server has blocking sockets
and one shared data buffer; each chunk is fully written/sent before another
client can reuse it. Short I/O loops preserve all bytes. Read/write/socket/list
errors abort the transfer. Failed REST seeks never reopen a file with truncation.
SIZE and restart offsets retain 64-bit sizes.

Each connection owns its RNFR source. Native rename is supported only within the
same device and unit. Cross-device requests and drivers without native extended
rename return errors. There is no copy/delete or temporary-name emulation.

TCP parsing supports split and coalesced commands, reserves its terminating NUL,
and rejects overlong lines. During a data transfer, unrelated commands cannot
replace that connection's filesystem handle. ABOR closes the handle/socket.
Operation status excludes authentication commands.

IOP formatting uses imported `sprintf` with bounded strings/buffers. Decimal
size conversion uses place subtraction, avoiding unresolved 64-bit division
helpers. Socket sends use mutable buffers to match the SDK API. Do not introduce
an unprovided IOP `snprintf` or global socket `errno` dependency.

## Validation

- `python3 tests/test_ftp_server.py`: actual IOP filesystem/command/socket/control
  units with preserved ABI headers and faulted drivers/sockets; fixed scope,
  legacy/extended cards, PFS pinning/eviction, native rename, short I/O, failures,
  cooperative shutdown, 64-bit sizes, command framing and freestanding 32-bit
  decimal formatting. Also compiles the IOP startup/control service branches.
- `python3 tests/test_ftp_session.py`: actual EE session and screen, covering
  reset/ownership gates, bounded bind, stale RPC sessions, version checks,
  exclusive frames, both Stop buttons and return to the dashboard.
- `python3 tests/test_ftp_network.py`: two real loopback clients, passive/active
  connections, resume, listings and exact payloads using the POSIX backend.
- `tests/test_dev9_transition.py`: storage-before-FTP ordering, shared DEV9,
  missing HDDs, network-mode transitions, failed startup and EXFAT builds.

Host tests do not simulate physical IOP scheduling, SIO2, Ethernet or storage.
Hardware checks should cover startup after MMCE/MX4SIO use, both controllers/card
slots, USB0/USB1, HDD/PFS and ATA0, multiple FileZilla connections, and Stop during
uploads/downloads as well as idle sessions.
