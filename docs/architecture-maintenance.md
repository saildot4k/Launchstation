# Launchstation Maintainer Notes

This project is now organized around two maintenance goals:

1. Keep runtime behavior stable on real PS2 hardware.
2. Make feature combinations predictable in CI and local builds.

## Build Profiles

High-level build profile resolution lives in:

- `scripts/ci/resolve_make_args.sh`

It maps profile selectors:

- `psx_profile`: `no-psx` or `psx`
- `pad_profile`: `no-ds34` or `ds34`
- `storage_profile`: `usb`, `mmce`, `mx4sio`, `all`, `minimal`

into concrete make flags (e.g. `EXFAT`, `MMCE`, `MX4SIO`, `DVRP`, `XFROM`, `DS34`).

This keeps CI and local profile builds aligned.

Local `make` defaults to the CI-style UDPFS stack (`ETH=0 UDPFS=1`). Developers can
opt into the legacy host/FTP stack with `ETH=1 UDPFS=0`, or compile both stacks
with `ETH=1 UDPFS=1`. Combined builds must switch between `host:` and `udpfs:`
by rebooting the IOP before loading the other network stack.

## CI Matrix

Workflow: `.github/workflows/compile.yml`

- Release variants use the `all` storage profile and build PSX variants for DS34 on/off.

## Stale Code Audit

Script: `scripts/stale_code_audit.sh`

Current checks:

- stale markers (`TODO`/`FIXME`/`HACK`, legacy aliases)
- disabled `#if 0` blocks
- duplicate config-probe hotspots
- largest source files (refactor candidates)

Use:

- `make stale-audit`

CI does not upload this report; it is a local/manual maintenance aid only.

## Recommended Future Splits

Startup orchestration in `src/main.c` is compact. The larger remaining owners include `src/filer.c`, `src/dash_browser.c` and `src/dash_settings.c`.

Completed so far:

1. `src/main_fileops.c` now owns file/path support helpers (`wleExists`, `uLE_related`, file-type checks).
2. `src/main_startup.c` now owns startup/system parsing helpers (`getIpConfig`, `readSystemCnf`).
3. Legacy SMB and the old classic JPG-viewer subsystem were removed from the runtime/build paths. Image viewing has since returned as a native dashboard viewer: PNG uses `src/dash_png.c`, while JPG/JPEG uses the bounded `src/dash_jpeg.c` libjpeg path.
4. `src/filer.c` helper splits now include:
   - `src/gui_sort.c` (`cmpFile`, `sort`)
   - `src/gui_texteditor.c` (`canOpenInTextEditor`)
   - `src/gui_hdd0_format.c` (`getHddParty`, `getHddDVRPParty`)
   - `src/psu_functions.c` (`clear_psu_header`, `pad_psu_header`)
   - `src/gui.c` (`ynDialog`, `nonDialog`, `keyboard`)
   - `src/gui_colors.c` (`scanSkinCNF`, `storeSkinCNF`)
5. PSU data layout structs are centralized in `include/psu_types.h` to avoid duplicated type blocks in `filer.c`.
6. `src/main.c` helper splits now include:
   - `src/main_info_screens.c` (`Show_About_uLE`, `Show_build_info`, `ShowDebugInfo`, `ShowFont`)
   - `src/main_gameid.c` (RetroGem/game-ID helpers)
   - `src/main_actions.c` (`Execute` action dispatch + launch cleanup)
7. Startup flow now consists of:
   - `src/main_boot.c` (early boot sequence + argument capture)
   - `src/main_modules.c` (runtime module/font/pad startup + CNF path validation)
   - `src/dash_main.c` owns the active shell, launch keys and boot countdowns. The old main-menu loop and separate Devices list/grid views have been removed.

Recommended extraction order (lowest risk first):

1. `filer_menu.c` (R1 menu enable/dispatch logic)
2. `filer_paths.c` (device/path mapping helpers)
3. `dash_browser.c` (separate browser interaction, row rendering and timestamp editor owners)

Keep each split behavior-neutral and verify on both PCSX2 and real hardware after each pass.

## ELF size maintenance

Both build paths enable function/data section garbage collection. Each plain
embedded payload in `src/embed_blobs.S` keeps its data and size symbol in one
independent read-only section: referencing either retains the pair; unused
payload sections can be discarded. Remove retired payloads from both
`src/embed_blobs.S` and `embed.make`/`Makefile`.

`tests/test_cleanup_build.py` executes the production startup entry against
host adapters and assembles/links the real blob macros to verify section
retention. Existing saved section IDs remain stable; Devices routes to Files,
and the obsolete `Dash_FilesMode` key is ignored and omitted on save.

Measure packed and unpacked ELFs from the same toolchain and profile before
claiming binary savings. Source deletion and RAM savings are separate: the
linker may already discard unreferenced functions, and BSS does not occupy
payload bytes in the ELF.
