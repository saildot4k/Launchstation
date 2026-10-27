# Launchstation refactoring and ELF-size plan

Reviewed October 25, 2026 against checkout `b84cac6a51be23d0435ff086587d6af97f6d8c77` and the current working files.

## Recommendation

Refactor around ownership and runtime effects, then reorganize directories. Keep ELF-size experiments separately measurable. The most valuable work is reducing shared state and clarifying storage, graphics, settings and launch boundaries; moving functions into additional files alone will not achieve that.

Start with reproducible build/size evidence, documentation corrections, narrow headers and a small group of pure helpers. Follow with settings and graphics boundaries. Migrate device reset, copy and launch protocols in smaller, separately validated changes. Keep all current release features in the default builds.

This deliverable is analysis and an implementation plan. No production C, headers, build configuration or runtime behavior was changed. The [source map](../source-map.md) identifies every top-level C source and its current role. The [evidence snapshot](2026-10-25-refactor-evidence.json) records inventory, source fingerprints, asset measurements and validation outcomes.

## Evidence and limits

| Observation | Measured result | Meaning |
| --- | ---: | --- |
| Top-level `src/*.c` files | 101 | Standard PS2BUILD lists 100 C files plus `embed_blobs.S`; DS34 substitutes the controller backend. |
| Physical C source lines | 75,516 | Includes comments, whitespace, conditional code and embedded data. Not executable size. |
| Top-level `include/*.h` files | 41 / 2,952 lines | Excludes `include/snippets/readCD.h` and `src/popstarter_internal.h`. |
| C sources exposed to `launchelf.h` | 89 of 101 | 42 include it directly; the rest acquire it through other top-level owner headers. Lexical include traversal, without preprocessing. |
| Direct users of `dash_internal.h` | 34 C files | One 1,095-line header exposes nearly all dashboard subsystems. |
| `filer_shared.h` / `editor_private.h` | 31 / 36 `extern` declaration lines | Declaration-line counts, not independent variable counts; indicate split implementations still sharing broad mutable state. |
| Main target `embed_irx` entries | 43 | Includes the embedded loader and SDK/local modules; separate from plain payloads in assembly. |
| Existing release ELF / cross-compiler | Neither available here | No compiled-byte savings, effective compiler flags or library contribution percentages can be established yet. |

The working tree was already marked modified across many files. `git diff --ignore-space-at-eol --stat` produced no changes during review; this suggests the existing diff is whitespace/line-ending related. Do not normalize these files as part of the architectural changes. The new documents are separate from that existing diff.

Counts are a source snapshot. Function spans below include whitespace/comments and, where present, both conditional branches. They are navigation aids rather than complexity scores. The lexical scan cannot balance every preprocessor alternative; the large `copy()` span was checked directly.

### Largest useful maintenance targets

| File | Lines | Actual issue to address |
| --- | ---: | --- |
| `src/dash_settings.c` | 2,882 | Page/schema definitions, editors, preview, transaction state and asynchronous persistence are combined. |
| `src/init.c` | 2,748 | Device/module state, resets, bus ownership, network, input, shutdown and special handoffs are intertwined. |
| `src/main_exploit_installer.c` | 2,519 | Console/target policy, payload selection, plan building, space estimation, signing, writing and UI share one implementation. |
| `src/filer_browser.c` | 2,461 | Classic browser UI also owns operation entry points and clipboard/device policy. |
| `src/filer.c` | 2,144 | Path translation, enumeration, discovery, partition caches and unrelated mutable state. |
| `src/filer_actions.c` | 2,039 | Timestamp domain logic/presentation, exploit protection and filesystem mutations. |
| `src/hdd.c` | 1,975 | Classic manager UI, partition operations and header workflows. |
| `src/dash_browser.c` | 1,858 | Native browser state, IO jobs, navigation, action dispatch and rendering. |
| `src/config.c` | 1,683 | Configuration format, locations, lifecycle and classic menu. |
| `src/filer_copy.c` | 1,423 | Recursive transfer, publication, metadata, archive paths and progress. |

`src/main.c` is already only 236 lines. The existing recommendation in `docs/architecture-maintenance.md` to treat it as a large monolith is stale. `src/dash_font_data.c` is 9,657 lines of generated data, while `src/icon.c` is 2,055 lines representing two 1,024-byte arrays. Neither belongs at the top of a function-refactoring backlog solely because of line count.

### Concrete duplicate-helper candidates

These function bodies matched after removing whitespace/comments, while retaining identifiers. They still require a contract review before consolidation.

| Copies | Function/body | Maintenance implication |
| --- | --- | --- |
| `config_advanced.c`, `config_startup.c` | `normalizeHideHddMode`, 8 lines | Put normalization with configuration policy. |
| `ember.c`, `neutrino_iso.c` | `readableElf` / `neutrinoElfReadable`, 13 lines | Share executable readability validation without merging the two launch protocols. |
| `filer.c`, `filer_actions.c`, `filer_copy.c` | `getXfromRelativePath`, 11 lines | One pure storage-path helper. |
| `filer_browser.c`, `hdd.c` | `getCenteredListTop`, 23 lines | One list-navigation/layout helper if its bounds contract remains identical. |
| `main_console_info.c`, `main_exploit_installer.c` | `copy_printable_prefix`, 21 lines | Console identity/text formatting owner. |
| `main_gameid.c`, `popstarter_gameid.c` | `isLikelyTitleID`, 7 lines | Shared title-ID syntax validation, preserving disc/VCD extraction differences. |
| `pad.c`, `pad_ds34.c` | `simPadKB`, 126 lines; repeat/readiness helpers | Common input policy, with separate transport backends. Only one backend is compiled per variant. |

The list is intentionally specific. Similar-looking device/launch/cleanup sequences with different ordering are not interchangeable helpers.

## Twelve review passes

Each pass below names the evidence, proposed boundary and validation required. These are completed analysis passes; the proposed implementation remains future work.

### 1. Build graph and source-of-truth pass

**Findings.** `ps2.yaml` and `.github/workflows/compile.yml` are the supported release path, as documented in `docs/wiki/Building-and-Validation.md`. `Makefile`, `embed.make`, `scripts/ci/resolve_make_args.sh` and the old maintainer notes describe a different profile system. The Makefile's main object list lacks the current HTTPS/updater implementation. The YAML main target has ETH/UDPFS/native HTTPS enabled; the Makefile defaults have ETH disabled. Treating them as equivalent produces misleading build and size comparisons.

The YAML loader explicitly uses `-Os`, function/data sections and linker garbage collection. The main EE target does not explicitly request those settings. PS2BUILD may supply defaults: inspect actual compile/link commands before claiming optimization is absent. TLS already builds with `-Os -ffunction-sections -fdata-sections`.

**Plan.** Document PS2BUILD as authoritative; classify the Makefile as historical/profile support until its maintenance policy is settled. Record effective sources, defines, SDK/compiler/packer/dependency versions and flags for both release variants. Generate size reports from those exact artifacts. Make variant changes through `scripts/configure_ds34.py`, whose exact text anchors currently resolve successfully. Pin or record resolved SDK/package revisions because CI currently installs/updates the SDK during a run.

**Exit.** A new developer can reproduce both standard and DS34 artifacts from documented commands. A size comparison identifies the same feature set, toolchain and dependency provenance. Updating a source path changes both variant graphs intentionally.

### 2. Types and header-boundary pass

**Findings.** `launchelf.h` imports SDK, GS, pad, storage and libc interfaces, defines settings/file types and declares application globals/functions. `dash_internal.h` combines color/theme/rendering, input, widgets, worker, library, persistence, screens and legacy accessors. It repeats filer and title declarations instead of including their owner interfaces. `init.h` exposes `u32` and `size_t` without importing their definitions, relying on include order.

`FILEINFO` lives in `launchelf.h`; PSU wire types are already centralized in `psu_types.h`. Timestamp representations include `PS2TIME`, `ps2time` and SDK types: similarity does not justify changing layout or casting between them.

**Plan.** Extract small domain headers for file information/limits, configuration types, launch contracts and render types. Split dashboard interfaces by consumer: rendering/textures, font, theme, input, worker, store/library and screen integration. Keep state-specific private declarations with their implementation family. Temporarily retain umbrella includes as compatibility facades while migrating callers one subsystem at a time.

Move declarations to exactly one owner header, make headers self-contained, and use forward declarations where the definition is unnecessary. Preserve enum values and on-disk/RPC/DMA layouts. Verify `sizeof`, alignment and selected offsets for wire types on the target compiler. Do not put every shared type in a new universal `types.h`.

**Exit.** A rendering helper can be included without importing the storage/browser API. Storage/format code can compile against a narrow host harness. New feature files do not need either umbrella header merely to obtain unrelated declarations.

### 3. State, ownership and lifetime pass

**Findings.** Previous splits moved functions but left clipboard, recursive transfer, mount and browser globals in `filer.c`. The classic editor similarly shares many independent globals through `editor_private.h`. Hook pointers include dialog overrides, timestamp UI, reset notifications, draw messages, launch callbacks and HDD text editing. Their installation and restoration are lifecycle-sensitive.

The native browser already has a private `fb` state object. Its USB job counter intentionally outlives individual browser sessions; moving that counter into a per-tab object would reintroduce a documented stale-completion/PAD race.

**Plan.** Give each domain one explicit state owner: clipboard, transfer session, mount registry, device runtime, browser session, editor document/session and settings session. Initially preserve singleton lifetimes and expose targeted operations/accessors. Pass a context only where it represents a real independently owned operation; avoid one giant application context threaded through every call.

Document each returned pointer/buffer as borrowed, transferred or caller-owned; state whether calls can block, draw, load modules or reset the IOP. Consolidate hook installation/restoration behind scoped enter/leave functions that restore previous hooks across nested dialogs and error/cancel paths. Keep durable job counters/reset generations outside disposable views.

**Exit.** Every shared mutable datum has one named owner and reset policy. A function's header documents material effects. No large state object is copied onto the EE stack simply to eliminate globals.

### 4. Device initialization and reset pass

**Findings.** `init.c` has an established reset generation, worker notification/blocking hooks and nuanced shutdown/order barriers. USB host recovery, MMCE/MX4SIO slot use, PC CARD versus DEV9 ownership, network stack switching and Ember handoff are different protocols. They cannot safely be flattened into a generic list of module names.

**Proposed extractions, initially retaining existing public entry points:**

| Implementation group | Functions/state to move together |
| --- | --- |
| Runtime/reset coordinator | `Reset`, `resetRuntimeDeviceState`, `clearIopModuleState`, reset generation, transition notifications and core reboot sequence. |
| Storage loading | BDM/USB, ATA/HDD/DVR, MMCE/MX4SIO, VMC and PC CARD load/readiness state; retain one bus-ownership coordinator. |
| Network loading | `load_ps2ip`, host/FTP/netfs/UDPFS loading, DNS setup and IP-network readiness. |
| Input loading | PAD/DS34/keyboard module startup and keyboard readiness. |
| Power-off | DEV9/USB idle/stop, handler registration and `closeAllAndPoweroff`. |
| Ember USB handoff | `EmberUsbIdentity`, probing/remount identity checks and `prepareEmberUsbHandoffIop`. |

Keep coordinator-owned state private, with a small private implementation interface where necessary. Extract one group per change. Preserve current delays, module order, reset notifications, generation updates and refusal to perform implicit resets on the worker.

**Exit.** Existing device-transition/USB/CF/MMCE/worker/power-off contracts pass. PCSX2 and relevant hardware confirm cold/warm boot, reconnect, stack switching, bus ownership and handoffs. Do not remove delays just because they appear redundant in a host test.

### 5. Path handling and directory-model pass

**Findings.** `filer.c` owns `genFixPath`, device-specific directory readers, root discovery, partition lists and USB mapping. Similar path-prefix logic exists in filer actions/copy, launch adapters and the updater. Some functions called path helpers trigger module loads or IOP resets. Numbered `massN:` slots are a shared BDM namespace; they must not all be rewritten as USB units. Display paths and launch/open paths also serve different purposes.

**Plan.** Separate pure path classification/formatting from effectful resolution, device preparation and directory reading. Extract a path module, a directory service, root-device discovery and partition-cache ownership. Retain `filer_fileops.c` as the device-aware IO boundary and `filer_mount.c` as the mount owner. Reuse existing names until each interface is stable; avoid another overlapping `filer_device` abstraction.

Introduce a parsed device/path view only where multiple consumers require identical semantics. Test bare and numbered aliases, HDD/PFS nesting, roots, trailing slashes, case rules, destination limits and failed preparation. Centralize the three identical `getXfromRelativePath` implementations after checking every caller's contract.

**Exit.** Rendering/display helpers cannot accidentally initialize storage. Directory listing does not own unrelated clipboard state. Namespace tests continue to distinguish USB identity from BDM mount order.

### 6. Transfer engine, file actions and archive pass

**Findings.** `copy()` occupies lines 568–1420 of `filer_copy.c`, approximately 853 physical lines. It combines recursive traversal, device preparation, ordinary/PSU copy paths, staging/backup publication, metadata and progress. It allocates `FILEINFO files[MAX_ENTRY]` on the stack, with `MAX_ENTRY=2048`, on recursive calls. Measure target stack usage before changing its context or concurrency model.

`filer_actions.c` mixes exploit-folder protection, filesystem mutation, timestamp arithmetic/model, timestamp UI and title.cfg output. Existing `FilerTimestampUi` already provides a useful presentation seam. `psu_functions.c`/`psu_types.h` are useful existing archive boundaries.

**Plan.** First extract save-title reads and pure timestamp/protection classification from mutation/presentation. Then separate transfer traversal, chunk IO, metadata application and publication/rollback behind a private transfer session. Preserve one cleanup owner for each open descriptor, buffer, backup/staging path and mount. Keep cancellation/progress behind a small adapter; callbacks do not gain permission to reset devices mid-transfer.

Keep preflight before opening descriptors. Preserve short-read/write loops, checksum/length verification, replacement rollback, actual child error propagation, PSU padding/metadata and clipboard reset-generation checks. Change recursion or allocate reusable directory buffers only in a distinct memory-focused change after measuring peak usage. One shared listing buffer cannot survive nested recursion without an explicit traversal strategy.

**Exit.** Existing short-IO, replacement, pipeline, preflight, transfer-progress and PSU/update-sidecar tests pass. Add behavior cases only for newly exposed failure boundaries. Real-device copy fixtures verify cross-device transfers, cancellation, full media, metadata and restore.

### 7. Browsers, shell and input pass

**Findings.** `getFilePath()` spans roughly 907 lines. The native browser has a separate model/worker lifecycle, but still calls operational entry points hosted in `filer_browser.c`. Both presentations share capabilities through `filerMenuEnables`; this is a good starting point for an operation service.

`main.c` enters `DashRun` unconditionally with a valid context and then retains the classic launch-key loop. A successful `DashRun` enters an infinite loop. Its public header still describes returning to a classic launch-key menu. `DashRun` also has legitimate early guard returns, so globally marking its current API `noreturn` would be incorrect. `DashIsEnabled()` has no source call sites outside its definition/declaration in the reviewed tree.

`pad.c` and `pad_ds34.c` contain an identical 126-line `simPadKB` and smaller repeat/readiness helpers. These backends are mutually exclusive in release builds: sharing that code improves maintenance but does not remove two compiled copies from one ELF.

**Plan.** Extract browser capabilities/commands and clipboard/paste/VMC/free-space entry points from the classic view. Give classic and native browsers separate view state over shared services; do not force them into a single frame loop. Split native list jobs, action handling and view rendering only after its state boundaries are clear.

Audit the classic main-loop tail as a deletion candidate under the dashboard-only shell contract. Preserve boot launch-key timing, re-entry guards and shared classic tools. Resolve stale API comments and compatibility settings before removing related code. A narrow non-returning internal runner or explicit result contract is preferable to an incorrect attribute on `DashRun`.

Extract common input policy/keyboard emulation from the two pad backends, leaving transport polling and DS34 threading backend-specific. Preserve repeat behavior, confirm/cancel mapping, USB barriers and input rearming.

**Exit.** Navigation, modal/tab lifecycle, editor Save/Discard, launch-key, controller-variant and input contracts pass. Removing the old main menu does not remove classic configuration/editor/HDD/browser tools still reachable through adapters.

### 8. Graphics, typography, image and asset pass

**Findings.** The code already distinguishes classic `draw_*` from dashboard rendering, but `dash_gfx.c` combines frame/GS state, textures, geometry, batching, interpolation and color math. `dash_ui.c` combines input with chrome, modals and progress. `dash_widgets.c` combines keyboard behavior/drawing with path/IP editors and classic adapters. `dash_art.c` combines asset discovery/cache with application-tile presentation. `dash_theme.c` is a classic-screen adapter; `dash_themes.c` owns the theme system. Their names hide this distinction.

PNG and JPEG decoders are already bounded, row-oriented implementations. Preserve that design and the codec-specific `setjmp`/cleanup rules. They should return CPU image data without acquiring GS ownership. `dash_gfx.c` currently pumps worker completions between frames; any extraction must preserve that scheduling contract.

**Plan.** Establish clear graphics layers:

| Layer | Responsibility |
| --- | --- |
| Display/GS backend | `draw_gs.c` plus dashboard frame/flip/texture state; screen generation, vsync and worker yield/park points. |
| Render primitives | Clip/alpha/offset stacks, geometry, gradients and sprite batches. |
| Font/text | Typeface assets/lifecycle, measurement/layout and text drawing; retain bitmap/SJIS fallback. |
| Image decoding/loading | Bounded PNG/JPEG decode, with shared file-loading policy only where behavior is identical. |
| Asset cache | Artwork/theme texture requests, job ownership, cache invalidation and CPU/VRAM lifetime. |
| Presentation | App tiles, chrome, backgrounds, modals and widgets. |
| Theme | Data/schema/presets/persistence, with a separately named classic rendering adapter. |

Move small pure color/animation helpers together if they have independent consumers; do not create one file per primitive. Keep scene families in their existing sensible groups. Keep rendering on the UI thread and IO/decode on the serialized worker. Preserve double buffering, cache flush/alignment, texture invalidation, alpha conventions and scissor nesting.

Audit `loadIcon()` separately: it assigns static icon-array addresses to texture memory and then frees those pointers. No caller was found in current C sources, making it a deletion candidate rather than evidence of an observed runtime crash. Confirm both build graphs/link reachability and remaining `TexIcon` consumers before deleting the uploader/assets or changing ownership.

**Exit.** Presentation/buffer, nested scissor, scene override, font, motion, tile, border and PNG tests pass. Capture representative PAL/NTSC/progressive screens, both fonts, accented/SJIS save titles, nested dialogs, wallpaper, image viewing and video-mode rollback. Check frames during worker IO, not only idle screenshots.

### 9. Settings, theme schema and persistence pass

**Findings.** `dash_settings.c` has separate switches for describing, reading and mutating options alongside editing and Save/Discard state. It already snapshots serialized text and queues immutable configuration text for writes. That is important behavior, not duplication to remove blindly. `dash_store.c` mixes persistence with generic string/KV/file helpers. `dash_themes.c` mixes presets, validation, schema, application and folder IO.

**Plan.** Extract a settings session owning baseline/snapshot, dirty/pending/failed state, commit and revert; a binding/schema layer for ordinary fields; focused choice/color/path/IP/launch-key editors; and screen navigation/drawing. Reuse declarative descriptors for regular bounded values only. Video preview/rollback, launch keys, device changes, IO and user prompts keep explicit handlers.

Separate configuration format/defaults, save-location policy and classic UI. Split theme preset data, parse/serialize/validate, runtime application and folder IO. Move generic KV/string utilities out of dashboard persistence only when multiple real domains share their precise behavior. Keep legacy/new config keys and numeric values, unknown-key tolerance, save precedence and failed-save retry semantics stable.

**Exit.** Changing a value and changing it back is clean. Save/Discard restores preview/runtime state correctly. A queued save writes its captured content/path rather than later UI edits. Older save failures remain visible without falsely dirtying a new session. Existing settings/persistence/theme/network tests pass.

### 10. Launch, HDD and exploit-feature pass

**Findings.** `ExecuteMainAction()` spans approximately 512 lines and dispatches pseudo-commands, core-specific launches and ordinary executables. `elf.c` combines arguments and loader transport. Neutrino and Ember require different IOP behavior despite both ultimately using a keep-IOP loader. `main_exploit_installer.c` exposes one public entry point but contains many unrelated responsibilities. `hdd.c` likewise combines operations and classic UI, while `dash_hdd.c` supplies a second presentation.

**Plan.** Extract pure launch argument parsing/storage, command dispatch and executable preparation from loader transport. Introduce an explicit launch request only for shared data, with a named handoff policy and validated argv/path ownership. Keep Neutrino, Ember, POPStarter, ordinary reset launch, KELF and MBR specifics in their own handlers. Preserve cleanup/fade/worker/audio/IOP ordering and cancellation.

Extract HDD service operations from classic/dash presentation without altering their safety prompts or header transaction behavior. Divide installer target/payload catalog, pure install-plan/space calculation, signing adapter, writer and UI. Keep KELF format/crypto/key validation inside the existing signer module; do not combine that with unrelated HTTPS crypto to save code.

**Exit.** Existing core launch/argument/game-ID/ancestry/loader checks pass. Compare representative generated argv and installer plan/written-file sets. Validate relevant keep-IOP/reset, multi-USB, HDD and MMCE handoffs on physical hardware. Preserve loader `0x84000..0xa0000` bounds and startup/linker contracts.

### 11. Network, dependencies and size pass

**Findings.** `https_client.c` combines PS2 sockets/time/entropy, TLS setup/verification, HTTP parsing/redirect policy and streaming download. Its `httpsDownloadFd()` is approximately 299 lines. `scripts/build_https_tls.sh` pins Mbed TLS 3.6.7 and changes a few defaults, leaving a broader configuration than a narrowly scoped HTTPS client may need. Linked contribution is not yet measured. Archive size is not the amount retained in the ELF.

**Plan.** Separate PS2 transport/time/entropy from HTTP parsing/session/download logic at natural test seams. Preserve hostname, certificate-chain/date verification, redirects, response limits, streaming digest and error cleanup. Keep verified staged installation in `self_update.c` and PSU extraction in `update_psu.c`; do not merge download and filesystem publication.

Capture a full-size baseline, then test section GC and optimization settings, dependency configuration and asset representation independently as described below. Adopt a versioned TLS configuration shared by both the application headers and the built archives. Use the pinned release's configuration/dependency checks. Keep the algorithms/certificate/curve support required by GitHub API, release redirects and actual download hosts, with failed-verification tests and real network checks. Endpoint observations alone do not establish a durable compatibility guarantee.

Clock sync, remote control, FTP/host/UDPFS and game receiver should consume network readiness through the device/network owner rather than adding new init dependencies to UI code. Keep IOP ABI/provenance and pinned USB behavior intact.

**Exit.** Both release variants retain update/network features and verification. Size wins are attributable to linked sections and packed artifacts. Handshake/download latency and memory remain acceptable. Do not reduce TLS buffers or verification merely to obtain a smaller file.

### 12. Regression coverage, documentation and hygiene pass

**Findings.** The compile workflow references 105 distinct Python test scripts. There are 106 in `tests/`; `test_zack_launch_sizing.py` is the extra script. Many tests extract production functions using source strings/markers into host harnesses, so moving a function breaks their location assumptions even when behavior is unchanged. These harnesses still provide useful behavior coverage.

Baseline here: 25 of the 105 CI-referenced scripts completed successfully; 79 stopped because no host C compiler is installed, and one (`test_release_notes.py`) stopped because this Python 3.10 lacks `hashlib.file_digest`. The extra launch-sizing script passed. No compiler-dependent behavior suite, target build, emulator run or console acceptance was completed. Treat this as an environment-limited baseline, not 80 established product regressions.

The documentation generator successfully built 31 pages and 230 search entries into a temporary output directory. Separate document checks verified that the source map covers all 101 C files and 41 headers, all relative Markdown links resolve, the evidence source fingerprints match, and measured payload/font totals are consistent. The new Markdown documents are repository references; they are not automatically added to the website's authored page manifest.

**Plan.** State host prerequisites explicitly: a C compiler and Python 3.11+ for the current release scripts, plus the PS2BUILD/HTTPS dependencies for target builds. Centralize the existing test command inventory while retaining explicit hardware/artifact gates. When a module becomes independently compilable, have its harness compile the real production unit with narrow platform stubs; gradually reduce substring extraction. Update tests alongside each move, preserving assertions and failure cases. Avoid a bulk rewrite of the suite.

Update maintainer notes/build instructions and this source map as ownership changes. Preserve licenses and vendored origin documents. Mark generated sources with their generator/input/version; document the font asset dependency and rendering parameters for repeatable regeneration. Run formatting only on touched handwritten code in separate mechanical changes when necessary. Review dead code against both variants, assembly, linker roots, historical profiles and recovery/tool paths.

**Exit.** Developers can identify the owning file, run relevant tests, reproduce the build and distinguish host checks from real-console acceptance. No unresolved size/performance/hardware claim is presented as verified.

## ELF size: measured source data

These bytes are payload contents, excluding symbols, metadata, alignment, code and dependencies. They are not a compiled ELF breakdown.

| Input | Raw embedded content bytes | Observation |
| --- | ---: | --- |
| Small font pixels | 34,816 | `face0_px`, 256×136 PSMT8. |
| Medium font pixels | 57,344 | `face1_px`, 256×224 PSMT8. |
| Large font pixels | 122,880 | `face2_px`, 256×480 PSMT8. |
| All three font pixel atlases | 215,040 | Excludes glyph tables and face descriptors. |
| Eight embedded ADP sound effects | 238,656 | Boot sound alone is 143,984 bytes; ADPCM is already an encoded audio format. |
| Embedded exploit slices/assets | 88,590 | Includes a shared XLF body; do not count the three full source XLFs again. |
| Two plain embedded UDPFS peers | 16,658 | SMAP is separately source-built/embedded. |
| All contents named by `embed_blobs.S` | 343,904 | Excludes 43 `embed_irx` entries, which include local/SDK drivers and the loader. |
| Legacy icon arrays | 2,048 | A visually large C file is a small binary contributor. |

Background music is already an optional external `BGM.ADP`; `res/music.sad` is not included by the current embedding file. The updater CA is supplied through packaging/sidecar behavior. Do not count every file in `res/`, `exploits/` or `iop/__precompiled/` as embedded without following the actual graph.

A host zlib level-9 experiment on the three exact font pixel arrays produced 8,666 / 13,629 / 24,851 bytes, totaling **47,146 bytes** versus 215,040 raw. Each stream was round-trip checked. This shows source-data compressibility, not a 167,894-byte release-ELF saving: PS2PACK already compresses the whole ELF. Embedded font compression would add decode code and require aligned writable output, lifetime management and extra RAM compared with direct DMA from read-only ELF data. Compare packed bytes and peak live memory before considering it worthwhile.

### Measurement contract

For both standard and DS34 builds record:

| Metric | Purpose |
| --- | --- |
| SHA/revision, normalized source/config fingerprint, feature defines | Establish what was built. |
| PS2BUILD/compiler/binutils/packer versions and resolved SDK packages | Avoid attributing dependency/toolchain changes to refactoring. |
| Actual compile and link commands; TLS config hash | Confirm effective optimization and ABI assumptions. |
| Unstripped ELF, stripped ELF and packed ELF byte sizes | Separate analysis/debug overhead from delivered file size. |
| Sections: text, read-only data, initialized data, BSS | Distinguish code/assets from zero-initialized runtime memory. |
| PT_LOAD file/memory sizes and address range | See loaded footprint; avoid summing overlapping symbol aliases. |
| Link map: archive members and retained/discarded sections | Attribute application, SDK libraries, TLS, codecs and payloads. |
| Individual embedded payload lengths | Handle `.incbin` labels that lack ELF symbol-size metadata. |
| Peak heap/stack/VRAM and frame/IO timing on target | Detect costs hidden by a smaller file. |

The workflow already reports stripped/packed sizes, section totals and 40 large symbols. Extend that reporting and preserve comparison artifacts. Do not start by replacing it with an unrelated tool. Main-target map output must use the actual link working directory; validate that any added flag generated the expected file.

`nm` alone is insufficient for assembly blobs: the current embedding macros export start/size labels but do not add `.size` metadata for the payload labels. Measure their explicit size values or boundaries. Static library archive totals also overstate linked contribution.

### Repeatable baseline commands

Run in an environment with the documented toolchain/dependencies. These commands were not runnable in this review environment:

```sh
bash scripts/build_https_tls.sh
ps2build build
python3 scripts/configure_ds34.py
ps2build build -c .ps2-ds34.yaml -o build-ds34

task_toolbin="${PS2BUILD_ROOT:-$HOME/.local/share/ps2build}/toolchain/ee/bin"
"$task_toolbin/mips64r5900el-ps2-elf-size" -A build/obj/wLaunchELF/wLaunchELF.unstripped.elf
"$task_toolbin/mips64r5900el-ps2-elf-readelf" -lW build/obj/wLaunchELF/wLaunchELF.unstripped.elf
"$task_toolbin/mips64r5900el-ps2-elf-nm" -S --size-sort build/obj/wLaunchELF/wLaunchELF.unstripped.elf
stat -c '%n %s' build/bin/wLaunchELF.elf build/bin/wLaunchELF-packed.elf
stat -c '%n %s' build-ds34/bin/wLaunchELF.elf build-ds34/bin/wLaunchELF-packed.elf
python3 scripts/check_ds34_build.py "$task_toolbin/mips64r5900el-ps2-elf-nm" build/obj/wLaunchELF/wLaunchELF.unstripped.elf build-ds34/obj/wLaunchELF/wLaunchELF.unstripped.elf
python3 scripts/check_udpfs_smap.py build build-ds34
sh scripts/check_loader_layout.sh build/obj/loader/loader.unstripped.elf "$task_toolbin/mips64r5900el-ps2-elf-nm" 0x84000 auto auto 0xa0000
```

Save the baseline before changing flags. Use fresh, isolated output/dependency directories for comparisons; do not overwrite a known-good result. Retain SDK build output to identify defaults rather than assuming the YAML expresses every flag. Re-run package validation against the selected packed builds.

### Ranked experiments

Ranks are the recommended investigation order, not measured benefit claims. Test each independently against baseline, then combine only the winners and remeasure. A zero-byte result is a valid result.

| Rank | Experiment | Expected mechanism | Risk and acceptance |
| --- | --- | --- | --- |
| 1 | Verify/apply function/data sections plus `--gc-sections` to the main target | Remove unreachable input sections, including unused functions in otherwise retained objects. | Check SDK defaults first. Preserve startup/linker roots, callback tables, assembly references and loader ABI. Compare maps and boot both variants. |
| 2 | Explicit main-target `opt: -Os` comparison | Trade some speed-oriented transforms for code size using an option already used by the loader. | May already be the default. Compare packed size and busy-frame/transfer/launch timing. Try `-Oz` only if the actual compiler supports it. |
| 3 | Prove/remove obsolete main-loop and old icon-upload paths | Eliminate retained unreachable application code/data and stale contracts. | Trace entry/guard cases and all consumers first. Preserve shared classic tools and boot behavior. GC may already remove some candidates. |
| 4 | Narrow pinned Mbed TLS configuration | Avoid generating/retaining client-unneeded server, protocol, algorithm and support paths. | Linked map must justify work. Preserve required X.509/date/hostname checks, host/redirect compatibility and entropy behavior. Keep headers/archive config identical. |
| 5 | Put each plain embedded blob in its own named section and add useful size metadata | Allow independent GC and accurate reporting instead of retaining the single shared `.rodata` input section. | All required payloads may be live, giving no saving. Preserve alignment, names and `size_*` semantics. Confirm the effective linker script accepts `.rodata.*`. |
| 6 | Consolidate genuinely identical linked helpers and regular settings/theme schema | Reduce repeated implementations and maintenance drift. | Compiler may already fold/inline them; tables can increase data or retain handlers. Compare every result. Mutually exclusive pad duplicates are a maintenance win only. |
| 7 | Examine retained codec/formatting/math routines | Avoid accidental dependency pull-in; consider precomputed 256-entry font alpha ramps if they remove a uniquely retained math path. | `powf`/printf may be required elsewhere; removing one call need not remove a library routine. Keep image formats, localization and numeric correctness. |
| 8 | LTO trial on compatible EE application objects/libraries | Cross-unit dead-code elimination and optimization. | Requires matching GCC/plugin/archive tooling; preserve assembly-visible symbols and ABI. Trial after ordinary GC, with separate output and full checks. Do not apply globally to IOP/loader dependencies at once. |
| 9 | Font representation/atlas packing or lossless compression prototype | Reduce raw font bytes while preserving three sizes and glyph coverage. | Whole-ELF compression may erase the gain; decoding adds RAM/code/startup cost. Preserve 128-byte alignment, texture dimensions, accents and visual quality. |
| 10 | Audio asset tuning | If packed contribution remains large, shorten/re-encode effects after a listening comparison. | This changes perceptible behavior; keep separate from behavior-neutral refactoring. Externalizing sounds/modules changes recovery/install assumptions and is not the default proposal. |

The section/GC/optimization/LTO mechanisms are documented by [GCC optimization options](https://gcc.gnu.org/onlinedocs/gcc/Optimize-Options.html). Linker roots that must survive GC can be retained with the linker script's [KEEP mechanism](https://sourceware.org/binutils/docs/ld/Input-Section-Keep.html). Applicability and defaults must be checked against the installed PS2 compiler/linker. The loader already has explicit startup retention rules.

Mbed TLS recommends removing unneeded configured features to reduce binary footprint, while distinguishing that from runtime-memory tradeoffs. Use the [official footprint guide](https://mbed-tls.readthedocs.io/en/latest/kb/how-to/reduce-polarssl-memory-and-storage-footprint/) as background and the pinned version's actual configuration definitions for implementation.

Avoid claiming size wins from whitespace/comments, directory moves, shorter variable names, splitting generated data text, converting all functions to inline, or reducing the worker's BSS stack. Moving immutable data to `const` clarifies ownership/placement but does not by itself remove its bytes. Newlib-nano, aggressive ABI changes, unsafe packing/alignment, blanket fast-math and removal of current default features are outside the first optimization series.

## Proposed eventual directory layout

Keep files in place during early boundary work. Move complete, stable module families in a final mechanical series, updating YAML, DS34 generation, retained Makefile sources and test paths together. Preserve recognizable filenames unless a name actively misleads (`dash_theme.c` versus `dash_themes.c`, for example).

```text
src/
  app/                entry, boot orchestration, action routing
  platform/ps2/       IOP runtime, reset, input backends, display, shutdown
  storage/            paths, directory service, mounts, IO, transfer, PSU
  launch/             arguments, ELF transport, Neutrino, Ember, POPStarter
  config/             classic format/defaults, destinations, network config
  dashboard/          shell, screens, browser/editor/settings view state
  render/             GS backend, primitives, text, image decode, caches
  ui/                 input policy, layouts, modals, widgets, classic adapters
  features/           HDD service, exploit planner/writer, console/history
  net/                PS2 HTTPS transport, HTTP, clock/remote/receiver services
  update/             verified update transaction and PSU extraction
  generated/          font pixels and generated lookup/asset data
include/               small public/domain headers; private headers near owners
loader/                separate fixed-address EE executable
ee_libs/               local EE SDK adaptations
iop/                   separate IOP modules with their provenance
```

Allowed dependency direction: screens/controllers call domain services and rendering; domain services call storage/platform adapters; pure models/parsers do not call UI or initialize devices. The application composition layer installs UI adapters. Platform transition status reaches presentation through an explicit observer rather than a new dashboard import in every device module. Backend frame scheduling keeps an explicit worker pump/park integration hook.

Keep wire-format declarations and platform-neutral models small and separate from GS/SDK-heavy interfaces. Do not introduce a plugin framework, generalized service locator, second build system or C++ rewrite to accomplish these boundaries.

## Implementation sequence and review units

The twelve passes are review lenses, not twelve mandatory giant PRs. A practical sequence is:

| Change set | Scope | Depends on | Required evidence |
| --- | --- | --- | --- |
| A | Correct maintainer/build contracts; source map; reproducible size baseline and artifact retention. | Environment prerequisites. | Both builds, package/loader checks, measured sizes and effective flags. |
| B | Move types/declarations to narrow headers; self-contained includes; no state or behavior changes. | A. | Host suite and standard/DS34 build; compare exported contracts and wire layout. |
| C | Share pure path/console/layout/input-policy helpers; resolve current API/comment drift; prove dead candidates. | B. | Behavior harnesses and linked reachability/size comparison. |
| D | Run independent GC and `-Os` experiments; retain justified winners. | A, B as needed. | Before/after map, both packed sizes and timing/boot checks. |
| E | Settings session/schema/persistence and theme boundary extraction. | B, C. | Save/Discard/preview/failure tests, config round trips and target UI checks. |
| F | Render/asset/cache/UI separation; clarify pixel/VRAM ownership. | B. | Existing graphics tests, screenshots/video-mode/worker-IO acceptance. |
| G | Storage paths/listing/clipboard/action service; browser views consume it. | B, C. | Namespace, browse/tab/cancel/clipboard tests and device smoke tests. |
| H | IOP lifecycle extraction, one device family per review. | B, G; existing transition contracts. | Reset/order/generation traces and relevant console/device matrix. |
| I | Transfer/timestamp/PSU internal boundaries, then separately address measured stack costs. | G, H. | Failure injection, archive/metadata integrity, copy fixtures and peak usage. |
| J | Launch arguments/handlers, HDD service and installer plan/writer extractions, as separate PRs. | B, G, H. | Loader, core-specific handoffs, install-plan/file-set comparisons. |
| K | Measured TLS/asset/library/LTO experiments, each independent. | A, D; lifecycle boundaries as needed. | Packed/unpacked/RAM deltas, network compatibility, full relevant acceptance. |
| L | Mechanical directory moves, final source-map/API review and removal of temporary umbrella compatibility. | Stable preceding interfaces. | Both source graphs, unchanged contracts, complete suite and packages. |

Separate an extraction, a behavioral fix, an asset-quality change and a compiler-setting change into distinct review units. A refactor may legitimately have a small compiler-generated size difference; explain it with the map rather than assuming byte-identical ELF output. Keep a known-good packed build for every hardware tranche.

### Focused validation matrix

| Boundary changed | Existing checks to prioritize | Target acceptance |
| --- | --- | --- |
| Device/worker/reset | `test_worker_queue`, `test_dev9_transition`, `test_usb_storage_lifecycle`, `test_usb_iop_pad_handoff`, `test_mc_poll_usb_barrier`, `test_pccf_owner`, `test_mmce_bus_restore`, power-off tests. | Fat/slim; relevant PC CARD/PSX; USB, MMCE, MX4SIO, HDD and network transitions. |
| Copy/archive/path | `test_copy_pipeline`, `test_copy_short_io`, `test_paste_replace`, `test_transfer_stack_preflight`, `test_transfer_progress`, `test_usb_shared_namespace`, `test_update_sidecar_transaction`. | Cross-device copy/PSU restore, short/full-media/cancel/reconnect behavior and metadata. |
| Graphics/UI | `test_dashboard_present_buffers`, `test_nested_scissor`, `test_scene_override_nesting`, `test_font_weight`, `test_rounded_borders`, `test_png_viewer`, browser/navigation tests. | PAL/NTSC/progressive, fonts/localization, nested modals, video preview and busy IO. |
| Settings | `test_settings_persistence`, `test_settings_save_prompt`, `test_settings_navigation`, `test_display_feedback`, `test_theme_motion`, `test_bgm_sidecar`. | Change/revert, failed save/retry, reload, theme preview and runtime restoration. |
| Launch | Ember/Neutrino/POPStarter-relevant launch/game-ID contracts, `test_dashboard_start`, `test_loader_linkfile`, `test_zack_launch_sizing`; linked loader bounds. | Ordinary ELF/KELF/reset; keep-IOP cores; multiple USB units; HDD/MMCE game identity. |
| HTTPS/update/packages | `test_https_client`, `test_self_update`, `test_update_ancestry`, `test_update_sidecar_transaction`, `test_app_packages`, `test_release_notes`, release-workflow contracts. | Verified HTTPS redirects/download, bad certificate/hostname/date rejection, interrupted install and rollback. |

Names in this table omit `.py` for readability. Use the workflow's full suite as the release gate; focused checks are for individual iterations. Host tests cannot establish EE scheduler timing, DMA/VRAM correctness or physical storage bridge behavior.

## Definition of done

1. A developer can find the owner of a feature/type/state from the source map and a narrow header without tracing umbrella imports.
2. Storage/reset/launch ordering and UI/worker restrictions are explicit and preserved; ownership and cleanup have one home.
3. Current config keys, file formats, release variants/features, package names and hardware protocols remain compatible.
4. Existing host contracts, both EE/IOP builds, linked variant/loader checks and release packaging pass in a complete environment, with recorded emulator/hardware acceptance for touched boundaries.
5. The selected release build has a recorded packed-size comparison against the same-feature/toolchain baseline. Unpacked sections, RAM and performance tradeoffs are reported. If experiments yield no defensible size win, report that instead of removing features or claiming source cleanup reduced bytes.
6. Maintainer/build documentation, generated-data instructions and the source map describe the final tree; temporary compatibility facades and stale API comments are removed deliberately.

The immediate next implementation step is change set A: obtain the supported build environment and record the two-variant baseline. Header/pure-helper planning is complete enough to begin afterward; high-risk lifecycle work should remain gated on reproducible builds and console validation.
