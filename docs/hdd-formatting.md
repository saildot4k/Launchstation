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

Formatting preserves the HDD and ATA driver ABIs. The HDD driver also enables
its existing 8 MiB allocation mode while retaining the OSD access policy. The small, separately
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
APA boundary before asking the HDD driver to allocate it. It follows
the driver's first eligible free-size slot, then its aligned append policy.
Both build systems use that library. Reported APA free space excludes recovery
and exFAT space. Unknown or damaged hybrid maps disable allocations rather
than treating the rest of the physical disk as available APA space.

This protects allocations made through Launchstation. Other applications and
drivers can still allocate beyond the reserved APA area. The
[PSBBN Definitive Project documentation](https://github.com/CosmicScale/PSBBN-Definitive-Project#apa-jail)
describes the same risk of overwriting exFAT when APA allocations exceed their
reserved space.

New PFS partitions can be as small as **8 MiB**. Each physical APA extent is a
power of two and aligned to its own size; mixed 8/16/32/64/128 MiB extents do
not require groups of sixteen mini partitions. Appending a larger extent
creates appropriately sized free alignment blocks. Allocation first reuses
an eligible free extent, splitting it as necessary. Occupied PFS partitions
are never split based on their filesystem free space. The size picker offers
8 MiB, then 128/256/384 MiB and larger in 128 MiB steps. Its 1/10 GiB jump
buttons use the same choices; a non-aligned free-space limit is rounded down
to a selectable size. Existing volumes retain their original size as the
minimum when expanding them. Internal create/grow requests still support
8 MiB increments so allocation can split/reuse smaller free extents without
exposing those details in the picker. The APA Jail outer reservation and
system partition layout retain their existing 128 MiB alignment. Other apps
must also support mini APA layouts before managing these disks.

## Install an app PSU

On an APA Jail HDD with HOSDMenu installed, choose **Install apps from PSU...**
in HDD Manager Options, or **Install app to HDD...** on a PSU in File Browser.
HDD Manager's **Install apps from PSU...** picker accepts several PSUs: Square
or Confirm toggles a file, and Start begins the selected queue (or the focused
file if none are selected). Selections survive folder/device navigation.
Apps are read and installed one at a time, with their own boot choice and
review table. An error or cancellation stops the queue and reports how many
apps completed; completed installs remain in place. Progress opens before
starting the source device and shows the app number, current task and transfer
progress throughout preparation, downloads and installation.
The HDD Manager entry is shown only when PSBBN DP's
`hdd0:__system:pfs:/p2lboot/osdboot.elf` exists.
The installer announces the required Internet connection before reading the
package. It snapshots the PSU and CA bundle before network preparation can
reset the launch device (including UDPFS).

The PSU must contain a little-endian PS2 MIPS executable. `title.cfg` can
provide its title and boot filename; multiple candidate ELFs require a choice.
`APPINFO.PBT` is not interpreted and is copied as an ordinary package file.
Dot-prefixed configuration files such as POPSLOADER's `.pldrs` are preserved.
Memory-card `icon.sys`, `list.icn` and `del.icn` are not used as HDD header
metadata/models. Matching HDD models come from DP's `icons/ico` directory or
its HDD-OSD Icon Database source, falling back to DP's generic app models.
Artwork is checked in DP's `icons/art` directory, then in
`CosmicScale/psbbn-art-database/apps`, before using DP's generic `APP.png`.
Each repository is pinned to a commit for that app's asset downloads.
The PS2X header settings are extracted from DP's pinned `Game-Installer.sh`
template as text. Downloaded scripts are never executed. Only HTTP 404 permits
an asset fallback; network/TLS errors stop the operation.

All assets are downloaded to `ata0:/LAUNCHSTATION_APP_TEMP/<identity>-<PSU-CRC>`
before the review table and installation confirmation. New app files are
staged privately and then published under `ata0:/APPS/<PSU-folder>`; a hidden
8 MiB PFS launcher partition is published as `PP.<folder>` after installing
its PATINFO `SYSTEM.CNF`, separate list/delete HDD models, `/res/info.sys`
and `/res/jkt_001.png`. The header points directly to the ATA ELF, following
HOSDMenu's PATINFO path handling. No per-app OSDMenu ELF is necessary.

Managed updates require ownership markers in both the ATA folder and PFS
partition. They retain the partition size and preserve user files absent
from the replacement PSU. The previous app folder remains in the private
staging area until the new folder and launcher are committed. Unrelated
folders/partitions with matching names are refused. Active VMCs or FTP also
prevent installation.

Two alternating CRC-protected journals record publication intents and completed
steps. If interrupted, select the same original PSU, or navigate to its staged
`PACKAGE.PSU`, to resume. A failed download is downloaded again; an unpublished
owned partition can be reformatted after an interrupted create, but a published
partition is never reformatted. The existing ATA timeout watchdog resets a
stalled IOP and retains staging for an explicit resume. A power loss before the
PSU cache finishes requires the original PSU. Successful installation removes
its private cache and old app backup. These journals do not replace a disk
backup, and hardware testing of mixed mini layouts remains necessary.

APA metadata writes now propagate failures, retain failed dirty cache entries
and preserve the on-disk journal until all headers have been written. Failed
journal replay also preserves the recovery record. The app installer reloads
the IOP and storage drivers after a create/format I/O error so the HDD driver
can replay that record before an explicit retry. If an older false-success
checkpoint outlived its missing launcher, resume validates the complete APA
chain and the package ownership of staged or published app files before
recreating only that new install's 8 MiB launcher. Existing managed updates
never recreate or reformat their published partition. Temporary `+LSAPP.*`
names still keep incomplete launchers hidden until their headers are ready.
`tests/test_hdd_metadata.py` exercises the production cache, journal and
allocator with 223 partitions and injected link/journal I/O failures;
`tests/test_hdd_app_install.py` covers interrupted missing-launcher recovery
and refusal of foreign app files or an invalid chain.

Fresh installs create their own app folder, launcher partition and ownership
markers. If the initial journal was interrupted, staging containing only
installer downloads/journals can be reused automatically. Unknown files or
staged app/backup directories are retained when no valid journal survives.
Failures identify the operation, error code and affected device/path instead
of combining PSU validation, HDD detection and ownership into one message.

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


## Online software installer

Native HTTPS builds offer software installation as part of formatting. All
application binaries, icons and system resources are downloaded; none are
bundled in Launchstation. A working network connection is required. Launchstation
uses its embedded HTTPS CA bundle unless `WLE-UPDATE-CA.PEM` is beside the ELF. After the two erase confirmations the HDD is
formatted, then installer files are downloaded to `hdd0:__common:pfs:/tmp`
for APA Jail (mounted as `pfs2:/tmp`). Pure APA uses
`hdd0:__common:pfs:/PSBBN_DP_TEMP` on the same temporary PFS mount.
Archives stream from this cache directly into their final filesystems; no
second uncompressed archive copy is staged. Metadata is fetched first, then
free PFS zones are checked against the remaining downloads plus 4 MiB for
metadata, logs and journals. Completed cached downloads are excluded. This
test keeps the standard `__common` size: selections that do not fit report
the required/free space instead of switching to exFAT or filling the partition.
The `__contents` extraction target uses `pfs3:` so that the `__common` cache,
log and checkpoints remain mounted on `pfs2:` throughout extraction.
Installed APA Jail apps and launcher runtimes still go to their configured
`ata0:` destinations. Both filesystems still share the existing ATA backend;
this change removes exFAT staging I/O, not the resident BDM/ATA modules.
No USB or MMCE download folder is needed. The CA bundle is held in EE memory
before erasing and written to the new temporary folder, so it also works when
the original CA file was on the formatted HDD. Use the matching release CA
bundle; it includes the Go Daddy G2 root required by Archive.org.

Installer file downloads make up to three attempts for transient TCP/TLS
transport failures, interrupted responses, and HTTP 408/502/503/504. Delays are
2 seconds before attempt 2 and another 2 seconds before attempt 3, shown as a GUI
countdown and logged with the file and error. Each attempt reconnects and
reopens only that file with truncation; completed downloads remain cached.
Certificate, malformed-response, size-limit and storage errors stop immediately.
These network retries do not reset the IOP. Metadata requests retain their
existing behavior.

The HTTPS downloader combines arbitrary TLS/HTTP fragments into 16 KiB file
writes from a 64-byte-aligned buffer. Writes start at sector boundaries and use
DMA-aligned source buffers for direct FatFs/ATA transfers; the filesystem handles
the final partial sector. Short writes finish the current sector before continuing.
This avoids the one-to-three-byte shifts caused by unaligned ATA DMA pointers.
Progress counts bytes accepted by storage, including the final buffered flush.

- **Pure APA:** **No software, format only** or **Install HOSDMenu and supporting
  apps**. The software option installs OSDMenu MBR, HOSDMenu, WLE-R3Z and
  R3CONFIGURATOR. App files share `__common/APPS`, with the HDD-OSD
  visibility attribute `0xc4a7` on APPS and each application folder. Each app
  also gets an **8 MiB PFS launcher partition** with PATINFO and its HDD icon,
  using persistent `hdd0:__common:pfs:/APPS/...` paths. The two launchers add
  16 MiB of APA allocation. No PSBBN/Linux partitions are created.
- **APA Jail:** format only, or install English PSBBN DP, OSDMenu MBR,
  HOSDMenu, WLE-R3Z, R3CONFIGURATOR, RiptOPL, Neutrino, and Ember. Apps live on exFAT under `ata0:/APPS`.
  WLE-R3Z, R3CONFIGURATOR and the game frontend each get an **8 MiB PFS
  launcher partition** with PATINFO, HDD icons and PSBBN browser metadata.
  Their executables remain on exFAT or `__system`; they are not copied into
  these small launcher partitions.

APA-Jail software installs create DP's required Linux system/swap/data partitions.
The user chooses Music and Contents sizes (both default to 1 GiB), whether to
install standalone PS2 Linux (default Off), and additional APA space to leave
free for future use (default zero). The required allocation is calculated from
the selected volumes, app launchers and standard APA allocator alignment, then
the future reserve is added. The default PSBBN/media/apps layout requires
**6272 MiB beyond the standard APA system partitions**, before any future reserve.
The APA region is capped at 128 GiB for PSBBN. The existing driver must support a
single 2 GiB APA extent (checked before download/format); smaller-capacity
configurations are refused rather than inventing a subpartition mapping.
PSBBN needs a compatible Sony Network Adapter. Before the erase confirmations,
the installer resolves the DP Git revision and reads its language choices and
English display names from the upstream installer and UI data. It offers only
languages with a published pack in the Archive.org item referenced by that
installer. English is selected initially when available. New language entries
in the same upstream format appear without rebuilding Launchstation; unavailable
packs are omitted. A network or metadata failure stops before formatting.
Downloaded scripts are parsed as data and are never executed.

Music and Contents offer power-of-two sizes from 1 GiB up to the driver's
single-extent limit (at most 32 GiB). Optional PS2 Linux adds a fixed 2 GiB
`__linux.3` root and a user-selected `__linux.10` home partition from 1 GiB up
to the lesser of 16 GiB and the driver's single-extent limit. The limits keep
the PS2 Linux mapping to one validated APA extent per filesystem. Oversized
combinations return to the size choices before any erase confirmation.
The review is a borderless two-column table containing the format, capacity,
software, language, default launcher, media/Linux sizes and future reserve.
It uses 24-pixel rows and scrolls with Up/Down or Left/Right for a visible page
when the current video mode cannot fit every row. The separate final erase
confirmation remains.

Japanese also installs DP's Japanese PSBBN kernel and latest Japanese channel
archive into `__linux.9`. Its download can approach 1 GiB and is included in
overall/file progress and streaming archive validation. The metadata and tar
reader share a 1 GiB compressed-archive limit for the Japanese channels.
OSDMenu uses DP's corresponding
supported language code (Japanese maps to `jap`; unsupported OSD languages use
English). OPL selects the matching installed language file when available.

Enabling PS2 Linux downloads `PS2Linux.tar.gz` from the same Archive.org item,
checks its metadata size and validates it during extraction along with
the PSBBN and language archives. Both Linux kernels come from the pinned DP
Git revision. Permissions, links and device nodes are preserved; the home
filesystem is prepared for first boot. Holding Circle boots the installed NTSC
Linux kernel, matching DP's default configuration. Linux requires a USB keyboard.
With Linux Off, its archive/kernels and both extra partitions are omitted.

The system archive's Unix permissions, owners, hard links, symlinks and device
nodes are preserved in ext2. The music volume is FAT32, matching DP's Linux
layout; the external-facing APA-Jail partition remains exFAT with label `PS2`.
Boot configuration is generated for the actual installed components and paths.
Pure APA boots HOSDMenu; PSBBN installs boot PSBBN with `-dev9=NICHDD` and offer
HOSDMenu on Cross. Start/Select hotkeys launch the included apps when present.

New PSBBN installations follow DP's November 2026 runtime layout. RiptOPL
is the game frontend, with **Neutrino (RiptOPL)** listed first/default and
**OPL (RiptOPL)** as the alternative PS2 core. Both selections install the same
commit-pinned RiptOPL, Neutrino and Ember packages. RiptOPL's ELF goes to
`__system/launcher/RIPTOPL-RA-UNPAKT.ELF`; Neutrino's complete runtime goes to
`ata0:/neutrino`, language assets to `ata0:/LNG`, and Ember to `ata0:/Ember`,
with `ata0:/Ember/games` created for PS1 titles. `settings_riptopl.cfg` enables
BDM HDD, apps and cover art, selects the installed language, and sets
`default_core=1` for Neutrino or `0` for OPL.

Ember's unmodified ELF and version come from DP's pinned commit, with a README crediting
[Gageformer and linking the official releases](https://github.com/Gageformer/Ember/releases).
Like DP, the installer downloads `dep.zip` from the
`psbbn-definitive-project-dependencies` Archive.org item and extracts only
`dep/bios.bin` to `ata0:/Ember/bios.bin`. Metadata supplies the bounded archive
size; extraction checks ZIP CRC and requires a 512 KiB BIOS. The shared dependency
asset retains its legacy `extras.zip` cache filename, but contains `dep.zip`
for this profile. Pure APA profiles retain their HDD-OSD resources and do not
install these game runtimes. No game images or PS1 save conversions are installed.

Launcher downloads retain their original names and subfolders under
`__common:/tmp/OPL`, `Ember` and `Neutrino`. Shared artwork/icons use
`tmp/Icons/art` and `tmp/Icons/ico`. License files are not downloaded or installed.
Old checkpoints may still list them; those entries are skipped without changing
runtime indices or requiring the cached license files to exist. Retries adopt
completed numbered files from older caches by renaming them into the app folders.
Cleanup removes manifest files and their empty parents, leaving unrelated files
and retained diagnostics alone.

Square boot, the first HOSDMenu launcher entry, and DP's `PP.LAUNCHER` partition
all launch RiptOPL with matching DP artwork, icon, title ID and Navigator shortcut.
The launcher uses an 8 MiB APA partition included in allocation calculations.
The installer reuses/splits free APA extents through the existing mini-partition
allocator, and rounds the outer APA reservation to 128 MiB. Recovery accepts
existing installer-owned 8 MiB launchers and preserves older 128 MiB launchers
without resizing their extents; other unexpected sizes are rejected. Existing journals preserve their older OPL/NHDDL enum values,
runtime paths and configuration generation; newly prepared installations no
longer request those removed upstream assets.

### Download and failure behavior

Repository assets come from
[PSBBN DP](https://github.com/CosmicScale/PSBBN-Definitive-Project) at one
resolved Git commit. File content hashes are not calculated or compared. HDD-OSD-only installs
fetch DP's referenced `extras.zip`. PSBBN installations fetch the newest
complete system and selected language versions from DP's
[Archive.org collection](https://archive.org/details/psbbn-definitive-patch-v4.1),
using its published sizes. Archive decompression, CRCs, paths,
required boot files and capacity bounds are checked during installation. Each
archive is decompressed once, with no separate preflight option. Invalid archives
can leave a partial installation; boot activation remains conditional on complete
success. Staged file sizes are checked immediately before
copying installed files. Downloads and verification report file progress; DNS,
connection, TLS and response-header stages are also shown so connection setup
does not appear as an unexplained static download screen. The HTTPS idle
budget also bounds repeated ready-but-no-progress socket retries; actual
transferred bytes reset that budget.

Installer file downloads reuse one TLS connection for consecutive requests to
the same host and CA context. The batch is closed before the worker returns or
the IOP is reset. Redirects, explicit server closes and host/CA changes discard
the connection; responses must have a complete Content-Length body or complete
chunk framing including trailers before reuse. A stale reused connection gets
one fresh attempt if it fails before the file payload. Partial-body failures
stop the operation, preserving the existing staging/error behavior. Metadata
requests and updater downloads outside this scope retain their close behavior.

The ext2 writer supplies complete, zero-padded data blocks and initializes
pointer blocks separately. Adjacent file-data blocks are batched into up to
32 KiB per raw RPC, without a preliminary zero write. Pending data must be
written successfully before publishing the completed inode or marking the
filesystem clean. Raw I/O errors propagate through the installation failure path.

An ownership marker protects cleanup. Successful installation removes the
temporary files; a failed download or install leaves the folder for inspection.
Because formatting now happens first, download/verification failure leaves a
formatted HDD with an incomplete software installation. The UI reports this
explicitly. Network setup and CA readability are checked before the erase prompts.

The installer activates the downloaded MBR only after files/configuration
succeed, after flushing the payload and verifying its readback. APA-Jail
recovery metadata is refreshed after creating the software's partitions.
After that commit succeeds, MBR/HOSDMenu installs also enable the console's
persistent HDD boot setting through the MECHACON configuration service, using
the same set-0 boot flags as FreeMcBoot. All unrelated configuration bits are
preserved and the entire 15-byte block is read back for verification. An already
enabled console needs no write. Format-only and apps-only installs leave the
console setting alone. A configuration read/write/verification failure is
reported explicitly and retains the staged files and diagnostic log; the
installed software and MBR remain on disk.
Installation keeps the ATA filesystem mounted so archives can be read from
the same drive. The private raw service validates the on-disk APA-Jail boundary
and refuses writes into exFAT. Installation transfers use the existing HDD
driver's devctl semaphore; reads/copies/raw writes run sequentially on the EE
worker. The destructive formatter still detaches ATA before formatting. The
HDD and ATA driver sources/ABIs are unchanged. Storage is reset/reloaded after
raw writes, including errors. A failed software install reports the incomplete
installation and retains the download folder; it does not silently reformat or
report success. Cancellation or preparation failure before formatting leaves
the HDD untouched.

### Installer verification

`tests/test_hdd_installer.py` checks bounded metadata/archive parsing, layout
settings, Unix metadata, language overlays, allocation cleanup, music/swap
filesystems, and injected errors. `e2fsck`, `debugfs` and `fsck.fat` validate the
output independently. `tests/test_hdd_installer_apply.py` exercises the production
app/HOSD copy path against a host storage facade, including visibility flags
and PSBBN browser resources. `tests/test_hdd_installer_partitions.py` runs all
default and optional Linux partition requests against the actual HDD driver's
size parser, including its required `1G`/`2G` syntax, custom media/home sizes,
extent validation and injected errors. `tests/test_hdd_installer_choices.py`
checks choice defaults/cancellation, allocation and reserve bounds, optional
asset metadata and the Linux boot hotkey.
`tests/test_hdd_installer_launchers.py` runs production package discovery and
downloads against a local HTTPS facade, checking pinned URLs, recursive runtime
trees, quick size/ELF-header checks without full-file reads, short I/O, missing files, duplicate/traversal/symlink
metadata, and network/storage failures. Apply tests cover both defaults, archive
replacement, runtime modules/configuration, both RiptOPL core settings, Ember
ELF/BIOS installation and launcher resources. Legacy OPL/NHDDL packages
and installation journals remain covered.
The stage test checks internal folder creation,
CA preservation and ownership-checked cleanup. `tests/test_hdd_installer_finish.py` verifies software
and flush/readback checks precede MBR activation, with failure cleanup.
`tests/test_hdd_installer_boot.py` checks console configuration preservation,
already-enabled behavior, bounded service failures and readback verification,
and exercises the installation job's ordering and component/failure guards.
The format UI test also exercises format-before-download and failed-install
cache retention. Raw-session tests verify the ATA source remains available,
HDD/PFS serialization and exFAT write bounds; transport tests verify status
callbacks and cleanup. `tests/test_https_io_timeout.py` exercises the no-progress
socket retry deadline. Host tests never open a physical disk. PS2 hardware boot
and network/storage validation are still required.

`tests/test_https_download_alignment.py` reproduces the fileXio prefix split,
FatFs partial-sector handling and ATA DMA address rounding. It checks raw and
chunked bodies, arbitrary fragment lengths/source alignments, buffer tails,
short writes and write failures against the production download writer.


### Temporary verbose PSBBN diagnostics

APA-Jail PSBBN installs show a scrolling installation log throughout
preparation, formatting, downloading, checks and installation. It includes
elapsed time, time since the last activity, progress counts, the last raw-disk
command (including its LBA, sector count and result), and a timestamped log.
An outstanding raw command shows how long it has been waiting.
Up/Down scroll by line, Left/Right by a visible page, and Square returns
to the latest messages. The shared scrollbar tracks the visible position within
the retained log history, including during installation. A review screen stays
open at completion or failure.

Two progress bars stay visible from preparation through completion. The upper
bar is a monotonic, weighted estimate across preparation, formatting, downloading,
checks, installation and final boot/storage setup. Download progress adds bytes
across all selected files; archive extraction adds compressed bytes across
the selected system, language and optional Linux archives. Starting a new file
does not reset overall progress. Only a successful final result reaches 100%;
failures retain the last overall value, and IOP resets preserve it in EE memory.

The lower bar tracks the current file or operation independently. Extracted
files show their names and uncompressed write progress. Operations whose size
is unknown show an animated segment rather than a misleading percentage.

The log records the Launchstation build, disk layout and LBAs, Git revision,
downloaded files, partition creation, filesystem setup, archive completion,
MBR activation, recovery and errors. Byte counters and transient DNS/TLS/header
status update the live display without adding history entries or disk checkpoints.
Repeated status counters and sampled archive-entry records are omitted.
It never records certificate contents, credentials,
request headers or response bodies.

After the temporary folder exists, checkpoints append diagnostics to
`hdd0:__common:pfs:/tmp/INSTALLER.LOG` for APA Jail. Successful installs remove downloaded
payloads but retain this log and its ownership marker. Failed installs retain
the entire temporary folder. If the drive cannot write the log, the GUI reports
the write error and keeps the latest 256 display lines in RAM. Before a log
file can be created, diagnostics are available in the GUI only.

File SHA-1 comparisons and their full-file read passes are omitted. The HTTPS
downloader also skips SHA-256 when no digest is requested, as in this installer;
callers requesting a digest, including the app updater, still receive one.
TLS validation, transfer/file-size bounds, archive CRC/format checks and
MBR/NVRAM readback checks remain in place.

`tests/test_hdd_installer_log.py` checks the bounded history, timestamps,
progress/idle snapshots, raw command snapshots, file checkpoints, short writes
and error handling. `tests/test_hdd_installer_log_view.py` checks log navigation
and that the diagnostic layout stays within its panel across display heights.
`tests/test_hdd_installer_progress.py` checks cumulative archive progress with
and without Linux, individual file-write progress, and I/O errors. Log/view tests
check both bars, large byte counters, phase transitions, file resets and the
success-only completion rule.

### Planned reboot before local installation

After successful downloads/cache checks, the worker saves its checkpoint/log,
unmounts `__common` staging and flushes the HDD. Before queueing the local
PSBBN installation job, the UI performs one normal IOP reboot and reloads the
core/controller, HDD/PFS/ATA and raw-install services. It does not reload the
download network stack; optional UDP debug networking is suppressed during
this reset too. Both fresh and resumed installs use this path when filesystem
population is still pending. Already populated or committed checkpoints skip
the planned reboot. Preparation failures leave cached downloads intact and
stop before the installation worker runs. This is a diagnostic mitigation,
not evidence that IOP memory pressure causes the observed extraction failures.

The archive reader recognizes `__linux.*` and PFS destinations from each tar
entry. It logs and saves destination transitions, including revisits later in
the same archive. These messages do not trigger additional resets. Extraction
still uses one gzip pass; switching destinations is not proof that a partition
is complete. Resetting inside that pass would require flushing ext2 metadata
without marking filesystems clean, closing/remounting PFS and archive handles,
and restarting the raw-write session while retaining the EE gzip state.

`tests/test_hdd_installer_retry.py` covers preparation ordering/failures,
completed-stage skips, durable download handoff and storage-only recovery.
`tests/test_hdd_installer_streaming.py` covers destination changes and revisits.

### Recovery from ATA timeouts

During installer download and software installation jobs, ATA timeout `-502`
stops further IOP calls, including disk-log writes, unmounts and flushes. An
installer RPC or server binding that does not complete within 60 seconds also
requests recovery. The UI performs an emergency IOP reset without first calling
unresponsive storage, audio or controller servers. Outstanding RPC buffers stay
alive until the reset is acknowledged; only after the worker unwinds are the EE
clients recreated and controller/storage drivers reloaded. Download retries
also restore networking; local installation retries leave it unloaded. This
does not depend on the controller responding. The DS34 polling thread is also
stopped before its clients and buffers are reused.

There are at most two automatic retries across the installation. Completed,
closed downloads are retained after checking their sizes; a partial download is
truncated and downloaded again. The pinned manifest and staging ownership marker
remain in use. The drive is never formatted again by recovery. A partially
completed partition/app setup reuses only the expected installer-owned partition
names with matching types, sizes and APA bounds. Its new PFS volumes are
reinitialized before copying their files again, including when their first PFS
format was interrupted. The staging volume is preserved.

An interrupted PSBBN filesystem population rebuilds its ext2 filesystems from
the cached archives and reapplies PFS overlays and generated settings. It does
not resume an arbitrary tar entry or a buffered filesystem write. Completed
population is retained if the later MBR/boot stage needs retrying, and completed
boot setup is not repeated for a cleanup retry. RAM diagnostics survive resets
and disk logging resumes once storage is available again.

If timeouts persist, a final reset restores the controller and reports the
incomplete installation, preserving cached downloads. If the IOP cannot
queue the reset request within 15 seconds, acknowledge its boot within a further
15 seconds, or complete core/controller initialization, the GUI displays a
restart-console message naming the failed stage. RAM diagnostics include SIF
status flags and the command-buffer address before reset, after queuing, and
on boot acknowledgment or timeout. The fault path stops EE RPC reception before
queuing reset, matching the SDK's full reboot preparation, while retaining old
client/DMA storage until boot is acknowledged. It does not release buffers
that the old IOP might still reference or enter an unlimited reset loop.
IOP retries keep their checkpoints in EE memory. Starting with this version,
durable checkpoints also permit resuming after restarting Launchstation or the
console, as described below.

`tests/test_hdd_installer_recovery.py` exercises returned faults, stalled calls
and bindings, the UI/reset handshake, client reconstruction order and failed
reset handling. `tests/test_hdd_installer_retry.py` checks the retry limit and
download/app/population/boot checkpoints. The staging, launcher, app and
partition tests also cover partial-file replacement, completed-download reuse,
ownership mismatches and invalid partition geometry. Real timeout recovery and
controller reconnection still require PS2 hardware testing.

### Resuming after restarting the console

HDD Manager's Options menu shows **Resume installation...** only when the
installation log exists and the newest valid checkpoint is unfinished and
belongs to the staging owner. A completed log (including older successful
session markers), a committed checkpoint, or missing/invalid checkpoints hides
the action. Successful logs end with `Installation finished successfully.`;
failed and cancelled sessions have explicit final status lines too. It reads
the cache before showing a confirmation table with the saved layout, language,
launcher and space choices. This action cannot format the drive. Cancellation
and failed validation preserve the cache.

Two alternating `RESUME0.BIN` / `RESUME1.BIN` files live in the owned
staging folder in `__common`: `tmp` for APA Jail, or `PSBBN_DP_TEMP` for
pure APA. Resume detection, saved certificates and timeout retries all use
these same PFS paths. Older ATA staging folders are not migrated or resumed
by this test build; their contents are left alone.
They contain a versioned little-endian record of the layout, owner, pinned
repository revision, selected software, metadata and completed operations.
Records are bounded to 64 KiB and checked with CRC32. If a checkpoint write is
interrupted, the previous valid record remains available. Completed payloads
are flushed before publishing their checkpoint, and the checkpoint itself is
closed and flushed before advancing its sequence number. PFS metadata is
synced before the HDD cache flush; log appends also sync PFS before reporting
that diagnostics have been saved. Journals are removed
after successful cleanup. The CRC checks the checkpoint, not downloaded files;
payload content hashing remains disabled.

Resume verifies the staging owner, actual drive capacity and APA boundary.
APA Jail also verifies the exFAT offset, size and volume serial. If software
setup completed, PSBBN partition types, extents and sizes must still match.
Paths in saved launcher metadata must remain inside the permitted repository
trees. Valid closed downloads are retained; interrupted files are downloaded
again. Interrupted filesystem population is rebuilt from cached archives,
while completed population and boot stages can be skipped. Normal HTTPS trust,
archive CRC/bounds and final MBR/NVRAM checks remain enabled.

The saved certificate is read before changing network stacks. Fresh installer
preparation also starts the ELF's source device before looking for its CA,
then tries the settings device as a fallback. This lets UDPFS-launched installs
read their certificate after an IOP reset, snapshot it in EE memory, and switch
to Internet networking without needing UDPFS to remain loaded.

Older installations without journal files cannot be resumed by this action.
The cache alone does not reliably describe their original choices and layout.
`tests/test_hdd_installer_resume.py` covers journal serialization, interrupted
writes, corrupted/truncated records, ownership/capacity/serial mismatches and
the actual UI's read-before-confirmation and no-format behavior. The language
and boot-path tests exercise device startup and CA snapshot ordering.


## Partition rename and HOSDMenu visibility

HDD Manager renames use the complete 32-byte APA identifier, padding shorter
names before driver lookup. A successful rename preserves the partition's
location, size, subpartitions and contents. The target's PFS mount is released;
other retained mounts stay open. A VMC pin or another active handle blocks the
rename, and the error is reported. System partitions with the `__` prefix are
protected. Existing destination names are refused rather than numbered or
truncated automatically.

When `hdd0:__system:pfs:/osdmenu/hosdmenu.elf` exists, a non-system PFS
partition's Options menu offers **Hide in HOSDMenu HDD Browser**
or **Show in HOSDMenu HDD Browser**. These append or remove the exact uppercase
`.HIDDEN` suffix documented by [HOSDMenu](https://github.com/pcm720/OSDMenu/blob/main/patcher/README.md).
Appending it requires an existing name of at most 25 characters; a longer name
must be shortened explicitly first. Hidden partitions remain visible and
manageable in Launchstation. Managed app updates recognize their hidden
launcher partition and preserve its visibility and ownership markers.

Visibility here controls HOSDMenu's HDD Browser. PSBBN DP uses separate app and
shortcut entries: its [Game Installer](https://github.com/CosmicScale/PSBBN-Definitive-Project/blob/main/scripts/Game-Installer.sh)
even creates a shortcut referring to `PP.HOSDMENU.HIDDEN`. This toggle does not
rewrite PSBBN entries or other saved paths referring to the old partition ID.


### PSBBN DP selections

The PSBBN DP installer is labeled **Experimental** in its software choice,
review and installer-log popups. Format/install choice lists use
only the cursor to indicate focus; initial defaults do not receive check marks.
The APA Jail software menu offers **No software, format only** and
**PSBBN DP, HOSDMenu**, with **EXPERIMENTAL** in the second row's detail column.
Selecting PSBBN immediately shows the Sony Network Adapter / GameStar warning,
then asks for the default PS2 game core: **Neutrino (RiptOPL)**, listed before
**OPL (RiptOPL)**.
After the unnumbered compatibility notice, its six numbered dialogs cover
the PS2 game core, Music size, Contents size, standalone PS2 Linux, future APA
reserve and language. The format review and final erase confirmation are
unnumbered. The Linux dialog
lists **Do not install PS2 Linux**, then **1 GiB**, **2 GiB**, **4 GiB** and
**8 GiB** home sizes, subject to the driver's extent limit. These share one
dialog, so the total stays accurate with either choice.
The allocation-information popup is omitted; the final table starts with
Format, Drive Capacity and APA total space. HDD Manager maintains audio in its
own navigation loop, and language preparation queues audio recovery after an
IOP/network reset so cancelling the installer does not require leaving the
manager to restore navigation sounds.

Upstream DP's [Game Selector](https://github.com/CosmicScale/PSBBN-Definitive-Project/blob/main/scripts/helper/game-selector.py)
writes `selected.list` and remembers deselected titles in the exFAT root's
`exclude.list`. Its Game Installer removes the old `PP.*` launcher partitions,
then creates 8 MiB launcher partitions only for selected titles. The original
game/application payloads on exFAT remain available in the other launchers.
This collection-selection mechanism is different from HOSDMenu's `.HIDDEN`
suffix and is not implemented by Launchstation's Hide/Show partition action.

The File Browser header displays HDD partition paths in launcher syntax, for
example `hdd0:__common:pfs:/APPS/` or `hdd1:+APPS:pfs:/`. Device roots remain
`hdd0:/` and `hdd1:/` until a partition is entered. This is display formatting;
browsing and filesystem operations keep using their original paths.
