# Launchstation source map

Current ownership map, updated October 31, 2026. This describes the existing tree; proposed extractions are in the [refactoring and ELF-size plan](plans/2026-10-25-refactor-and-elf-size.md). All 104 top-level `src/*.c` files are listed once. The DS34 variant substitutes `pad_ds34.c` for the standard target's `pad.c`.

## Where to start

| Change | Start here |
| --- | --- |
| Startup or boot path | `main.c`, `main_startup.c`, `main_boot.c` |
| Device/IOP reset or driver ordering | `init.c`, then `filer_device.c`; read the worker rules before changing it |
| Filesystem name/path behavior | `filer.c`, `filer_fileops.c`, `filer_mount.c` |
| Copy, paste, PSU or replacement integrity | `filer_browser.c` entry points, `filer_device.c` preflight, `filer_copy.c`, `psu_functions.c` |
| Native file browser | `dash_browser.c`; `dash_files.c` connects it to the Files tab |
| Frame presentation or texture corruption | `draw_gs.c`, `dash_gfx.c`, texture owner in `dash_font.c`/`dash_art.c` |
| Theme schema or saving | `dash_themes.c`; classic-screen adapter is `dash_theme.c` |
| Settings Save/Discard | `dash_settings.c`, `dash_store.c`, `config.c` |
| Game launch | `main_actions.c`, selected core adapter, `elf.c`, then `loader/loader.c` |
| Update download/install | `https_client.c`, `self_update.c`, `update_psu.c`, `scripts/build_https_tls.sh` |
| Internet socket receive integrity | `ee_libs/tcpips/ps2ipc.c` (EE client), `iop/ps2ips_rpc/ps2ips.c` (IOP server); shared wire ABI in `iop/ps2ips_rpc/ps2ip_rpc.h` |

## Boundaries to preserve

- Use [saildot4k/wLaunchELF_R3Z 4.80](https://github.com/saildot4k/wLaunchELF_R3Z/tree/4.80) as the compatibility baseline for copying, moving, pasting, PSU creation/restoration and VMC browsing/transfers. Exact reuse of its working code is authorized where appropriate. Preserve native device contracts and the UDPFS final-byte fix; compare changes with that baseline before adding filesystem assumptions. See the [device-transfer audit](plans/2026-10-26-device-transfer-audit.md) for Launchstation-specific integration fixes and test limits.
- UI thread owns drawing, input and application state. IO jobs execute serially; completion callbacks apply results on the UI thread. Read `dash_worker.c` before adding background work.
- IO worker and UI must respect libmc/fileXio/PAD barriers. A path resolver can load a driver and reboot the IOP; it is not necessarily a pure string helper.
- IOP reset generation invalidates mounts, clipboard assumptions, device caches and audio state. Worker shutdown/parking and launch handoff order are observable behavior.
- Neutrino keeps its mounted backing stack. Ember USB rebuilds its storage IOP and rematches game identity before a keep-IOP launch. Preserve these separate protocols.
- GS framebuffers and texture VRAM mappings are invalidated by video-mode/screen-generation changes. CPU pixel ownership and VRAM residency are different lifetimes.
- Configuration keys, enum values, filesystem metadata, RPC layouts, loader addresses and release package names are compatibility contracts.

## Application startup and console information

| Existing file | Responsibility |
| --- | --- |
| [main.c](../src/main.c) | Process entry, boot context and top-level startup orchestration; `main`, `wleBootElfPath`. |
| [main_boot.c](../src/main_boot.c) | Capture boot arguments and perform earliest initialization. |
| [main_startup.c](../src/main_startup.c) | Boot paths, ROM/region detection, SYSTEM.CNF/IPCONFIG parsing and boot device/display setup. |
| [main_modules.c](../src/main_modules.c) | Configured CNF path validation and runtime input/display startup. |
| [main_menu.c](../src/main_menu.c) | Classic launch-key menu state, drawing, input and automatic launch timers. |
| [main_console_info.c](../src/main_console_info.c) | Console model, boot ROM and DVD version identification/formatting. |
| [main_title.c](../src/main_title.c) | Clock, date and temperature cache, conversion and title formatting. |
| [main_info_screens.c](../src/main_info_screens.c) | Classic About, build, diagnostics and font screens. |
| [main_history.c](../src/main_history.c) | Console OSD launch history persistence. |
| [main_fileops.c](../src/main_fileops.c) | Related-file lookup, existence checks and supported/editor file classification. |
| [timer.c](../src/timer.c) | Millisecond timer wrapper used across the application. |

## Launch dispatch, game identity and embedded loader

| Existing file | Responsibility |
| --- | --- |
| [main_actions.c](../src/main_actions.c) | Dispatch built-in commands and executable paths; coordinate launch cleanup and browser entry. |
| [elf.c](../src/elf.c) | Launch argument parsing/storage, ELF checks, loader payload preparation and reset/keep-IOP handoff entry points. |
| [main_gameid.c](../src/main_gameid.c) | Disc/application game-ID derivation and RetroGem notification. |
| [main_gameid_table.c](../src/main_gameid_table.c) | Read-only PS1 generic game-ID lookup table; data rather than control flow. |
| [neutrino_gameid.c](../src/neutrino_gameid.c) | Neutrino game-ID preparation and MMCE game-ID bus interaction. |
| [neutrino_iso.c](../src/neutrino_iso.c) | Neutrino ISO discovery, launch configuration and keep-IOP launch coordination. |
| [gui_neutrino.c](../src/gui_neutrino.c) | Per-game Neutrino options, profile handling and argument construction. |
| [ember.c](../src/ember.c) | Ember image/core discovery, path resolution, launch arguments and USB handoff coordination. |
| [ember_gameid.c](../src/ember_gameid.c) | Bounded CUE/BIN image reading and PS1 game-ID extraction for Ember RetroGem handoff. |
| [popstarter.c](../src/popstarter.c) | Public POPStarter VCD recognition and launch orchestration. |
| [popstarter_path.c](../src/popstarter_path.c) | POPStarter candidate selection, HDD/PFS path handling and launch preparation. |
| [popstarter_vcd.c](../src/popstarter_vcd.c) | VCD validation, ISO primary volume descriptor and SYSTEM.CNF reads. |
| [popstarter_gameid.c](../src/popstarter_gameid.c) | PS1 VCD game-ID derivation. |
| [popstarter_elf.c](../src/popstarter_elf.c) | POPStarter ELF candidate validation and launch preparation. |
| [chkesr.c](../src/chkesr.c) | ESR disc detection. |

## Storage, browser operations and save archives

The [device transfer audit](plans/2026-10-26-device-transfer-audit.md) records
R3Z parity, device-specific replacement contracts, HDD-OSD/card attributes,
regression coverage and console acceptance checks.
The [rename audit](plans/2026-10-26-device-rename-audit.md) covers files/folders,
card RPC completion, device limits, conflict checks, driver-specific case-only renames
and the HOST ioctl.

| Existing file | Responsibility |
| --- | --- |
| [init.c](../src/init.c) | IOP reset generation, module loading, device stack transitions, network/input bring-up, power-off and Ember USB rebuild. Highest-risk lifecycle owner. |
| [filer.c](../src/filer.c) | Filesystem path translation, directory readers, partitions, USB/root device enumeration and shared browser/clipboard/transfer state. |
| [filer_device.c](../src/filer_device.c) | Ensure source/destination device stacks and reject incompatible transfer combinations. |
| [filer_mount.c](../src/filer_mount.c) | HDD/DVR partition mounts, VMC relationships and clipboard-aware unmounting. |
| [filer_fileops.c](../src/filer_fileops.c) | Device-aware `gen*` open/read/write/seek/stat/directory/delete wrappers, BDM FatFs stat-result normalization, shared sibling rename implementation and filename limits. |
| [filer_browser.c](../src/filer_browser.c) | Classic browser loop/menu plus clipboard/paste entry points, VMC actions, free-space queries and launch-folder helper. |
| [filer_actions.c](../src/filer_actions.c) | Delete/rename/mkdir, native case-only rename validation/dispatch, exploit-folder protection, title.cfg creation and timestamp editing/organization. |
| [filer_copy.c](../src/filer_copy.c) | Recursive transfer engine, batch file counting (including PSU payloads), replacement staging/verification, metadata restoration, diagnostics and save-title reads. |
| [gui_sort.c](../src/gui_sort.c) | FILEINFO comparison and browser sort ordering. |
| [gui_hdd0_format.c](../src/gui_hdd0_format.c) | HDD/DVR partition path and selection formatting helpers; not disk formatting implementation. |
| [gui_texteditor.c](../src/gui_texteditor.c) | Determine whether a selected file can enter the text editor. |
| [psu_functions.c](../src/psu_functions.c) | PSU archive header, padding, backup and restore primitives. |
| [hdd.c](../src/hdd.c) | HDD information, partition operations, format/header workflows and classic manager menus. |
| [hdd_header_injector.c](../src/hdd_header_injector.c) | HDD partition header asset lookup, SYSTEM.CNF editing and header injection. |
| [hdl_rpc.c](../src/hdl_rpc.c) | EE RPC client for HDL game information and rename operations. |

## Classic configuration, dialogs and editor

| Existing file | Responsibility |
| --- | --- |
| [config.c](../src/config.c) | LAUNCHELF.CNF defaults/parser/serializer, save destinations and classic configuration entry menu. |
| [config_screen.c](../src/config_screen.c) | Classic screen/display configuration UI. |
| [config_startup.c](../src/config_startup.c) | Classic startup configuration UI. |
| [config_network.c](../src/config_network.c) | Classic network UI and IPCONFIG snapshot/write behavior. |
| [config_advanced.c](../src/config_advanced.c) | Classic advanced configuration UI. |
| [gui.c](../src/gui.c) | Classic yes/no, message and keyboard dialogs, including replacement UI hooks. |
| [gui_colors.c](../src/gui_colors.c) | Legacy GUI color configuration parsing and serialization. |
| [lang.c](../src/lang.c) | Built-in/external language selection, key parsing and localized command names. |
| [editor.c](../src/editor.c) | Classic text editor process, shared editor state and main edit/render loop. |
| [editor_file.c](../src/editor_file.c) | Editor document lifecycle and file open/save operations. |
| [editor_input.c](../src/editor_input.c) | Editor physical/virtual keyboard input and text editing commands. |
| [editor_menu.c](../src/editor_menu.c) | Editor menu and window selection. |
| [editor_rules.c](../src/editor_rules.c) | Editor cursor, row and selection normalization. |

## Dashboard shell, models and screens

| Existing file | Responsibility |
| --- | --- |
| [dash_main.c](../src/dash_main.c) | Dashboard frame/section lifecycle, scene overrides, boot launch keys, menu and launch/tool dispatch. |
| [dash_worker.c](../src/dash_worker.c) | Single serialized IO worker, admission/queue/completions, progress and IOP-reset parking. |
| [dash_lib.c](../src/dash_lib.c) | Application discovery, metadata, launch sidecars and application library cache. |
| [dash_store.c](../src/dash_store.c) | DASHBOARD/DASHAPPS persistence, save jobs, settings/lists and shared text/key-value helpers. |
| [dash_devices.c](../src/dash_devices.c) | Cached device view model, presence/readiness, device rows and explicit startup requests. |
| [dash_home.c](../src/dash_home.c) | Home view, application groups and application/shortcut focus. |
| [dash_apps.c](../src/dash_apps.c) | Application list/grid views, filtering/focus and app actions. |
| [dash_files.c](../src/dash_files.c) | Files section integration and pending device navigation; native browser implementation is in dash_browser.c. |
| [dash_browser.c](../src/dash_browser.c) | Native file listing jobs, browser state, selection/actions and modal/Files-tab integration. |
| [dash_settings.c](../src/dash_settings.c) | Settings pages/bindings, preview, Save/Discard sessions and classic/network configuration save jobs. |
| [dash_tools.c](../src/dash_tools.c) | Tools menu, worker-owned update checks, package timestamps and tool actions. |
| [dash_info.c](../src/dash_info.c) | Dashboard text, About/build/system information and font viewer screens. |
| [dash_hdd.c](../src/dash_hdd.c) | Native HDD manager UI and operation presentation. |
| [dash_editor.c](../src/dash_editor.c) | Native text editor UI, document interaction and save flow. |
| [dash_exploit.c](../src/dash_exploit.c) | Bridge between dashboard presentation and the exploit installer. |

## Graphics, images, typography and theme rendering

| Existing file | Responsibility |
| --- | --- |
| [draw_gs.c](../src/draw_gs.c) | Shared GS initialization, video modes, display offsets and screen generation. |
| [draw.c](../src/draw.c) | Classic screen primitives, messages/frame redraw and GS globals; contains old icon uploader. |
| [draw_text.c](../src/draw_text.c) | Classic bitmap/SJIS text drawing, external font loading and text conversion. |
| [font_uLE.c](../src/font_uLE.c) | Built-in bitmap glyph data and mutable FontBuffer; no rendering functions. |
| [icon.c](../src/icon.c) | Two 1,024-byte legacy icon arrays; 2,055 lines represent only 2,048 payload bytes. |
| [makeicon.c](../src/makeicon.c) | Generate memory-card folder icons/icon.sys, text rasterization and RLE encoding. |
| [dash_gfx.c](../src/dash_gfx.c) | Dashboard frame presentation, GS/texture state, clipping/offset/alpha stacks, primitives and sprite batches. |
| [dash_font.c](../src/dash_font.c) | Dashboard font texture lifecycle, bitmap fallback, proportional face selection, text measurement/layout/drawing. |
| [dash_font_data.c](../src/dash_font_data.c) | Generated Roboto pixel atlases and glyph metrics at three sizes; edit scripts/gen_dash_font.py and regenerate. |
| [dash_font_emotion_engine.c](../src/dash_font_emotion_engine.c) | Generated Emotion Engine Regular atlases/metrics; source version, license and regeneration commands in docs/font-generation.md. |
| [dash_font_emotion_engine_bold.c](../src/dash_font_emotion_engine_bold.c) | Generated Emotion Engine Bold atlases/metrics at the same three sizes. |
| [dash_icons.c](../src/dash_icons.c) | Procedural dashboard icon distance fields, atlas generation and icon rendering. |
| [dash_png.c](../src/dash_png.c) | Bounded PNG decode/downsample and gen* file loading; returns CPU pixel buffers. |
| [dash_jpeg.c](../src/dash_jpeg.c) | Bounded JPEG decode/downsample and gen* file loading; returns CPU pixel buffers. |
| [dash_image.c](../src/dash_image.c) | Native image viewer, navigation/slideshow state and presentation. |
| [dash_art.c](../src/dash_art.c) | Artwork probing/async cache, theme texture cache and application tile drawing. |
| [dash_bg.c](../src/dash_bg.c) | Background composition, Crystal scene state, wallpaper crossfade, scanlines and launch flash. |
| [dash_bg_ps2.c](../src/dash_bg_ps2.c) | Procedural PS2-style tunnel/mist/towers/disc/orbit/clock/streak/cloud scenes. |
| [dash_bg_geo.c](../src/dash_bg_geo.c) | Procedural geometric gradient/grid/lines/cubes/stream/tiles/brushed/wave scenes. |
| [dash_themes.c](../src/dash_themes.c) | Theme presets, validation/application, key/value schema, serialization and theme-folder IO. |
| [dash_theme.c](../src/dash_theme.c) | Adapter that renders classic screens using dashboard colors/fonts; distinct from theme storage/presets. |

## Input, widgets, sound and service features

| Existing file | Responsibility |
| --- | --- |
| [pad.c](../src/pad.c) | Standard controller backend plus repeat, keyboard emulation and pad state policy. |
| [pad_ds34.c](../src/pad_ds34.c) | Optional DS3/DS4 backend and polling thread, with duplicated common input policy. |
| [virtual_keyboard.c](../src/virtual_keyboard.c) | Shared keyboard layouts, character eligibility and navigation for classic/dashboard editors. |
| [dash_ui.c](../src/dash_ui.c) | Input polling, chrome/hints/clock, selection primitives, modals, toasts and loading/progress overlays. |
| [dash_widgets.c](../src/dash_widgets.c) | Keyboard model/presentation, IP editor, path picker and classic-dialog adapter. |
| [dash_sound.c](../src/dash_sound.c) | audsrv/IOP sound lifecycle, embedded ADP effects and optional BGM.ADP streaming. |
| [dash_clock_sync.c](../src/dash_clock_sync.c) | Internet/manual clock changes and time service integration. |
| [remote_control.c](../src/remote_control.c) | Remote command polling and action dispatch integration. |
| [pc_game_receiver.c](../src/pc_game_receiver.c) | Network game transfer receiver polling and receive workflow. |
| [https_client.c](../src/https_client.c) | PS2 socket/entropy/time adapter, TLS verification/session, HTTP parsing/redirects, streaming download and optional request-thread status reports. |
| [self_update.c](../src/self_update.c) | Verified staged update, package selection, ancestry/digest checks, install transaction and rollback paths. |
| [update_psu.c](../src/update_psu.c) | Extract ELF and optional sidecars from updater PSU packages. |
| [main_exploit_installer.c](../src/main_exploit_installer.c) | Exploit target selection, install plan/space estimation, MagicGate signing, asset writes and installer UI. |
| [kelf_signer.c](../src/kelf_signer.c) | Key parsing/validation and ELF-to-KELF construction; conditional host test/utility entry point. |

## Public and private headers

`launchelf.h` and `dash_internal.h` are current umbrella headers, not the desired boundary for new features. Prefer the narrowest existing owner header. These groups cover all 42 top-level `include/*.h` files.

| Header(s) | Current contract |
| --- | --- |
| `launchelf.h` | Legacy SDK imports, constants/types, application globals and broad subsystem declarations. |
| `init.h`, `pccf_control.h`, `cdvd_macro.h` | Runtime device lifecycle; PC CARD control ABI; CD/DVD helpers. `init.h` currently relies on caller-provided SDK types. |
| `main_actions.h`, `main_boot.h`, `main_startup.h`, `main_modules.h`, `main_menu.h` | Launch context/dispatch, startup stages and classic main menu. |
| `main_console_info.h`, `main_title.h`, `main_info_screens.h`, `main_gameid.h`, `main_history.h` | Console identity, clock/title, information screens, game IDs and OSD history. |
| `main_exploit_installer.h`, `kelf_signer.h` | Installer entry point and KELF signing API. |
| `config_private.h` | Shared classic settings UI, save destinations, serialization and network snapshot helpers. |
| `filer_shared.h`, `filer_internal.h` | Browser/transfer enums and shared mutable globals; private mount/network declarations. |
| `filer_actions.h`, `filer_copy.h` | File mutations, timestamp UI adapter and transfer diagnostics/title helpers. |
| `psu_types.h`, `psu_functions.h` | On-disk save/archive layouts and archive operations. |
| `gui_sort.h`, `gui_hdd0_format.h`, `gui_texteditor.h`, `gui_colors.h`, `gui_neutrino.h` | Sorting, partition path formatting, editor eligibility, color schema and Neutrino options. |
| `draw_private.h`, `editor_private.h` | Shared rendering generation and legacy editor state/functions. |
| `dash.h` | Dashboard integration facade used by classic application code. |
| `dash_internal.h` | Dashboard types/settings/models, renderer, worker, screens, widgets and legacy accessors in one header. |
| [list_scroll.h](../include/list_scroll.h) | Shared centered viewport calculation for dashboard lists, path pickers and menu popups; clamps at the first/last page. |
| `dash_font_data.h`, `dash_sound.h`, `dash_autotest.h` | Generated font layout, audio API and conditional dashboard automation. |
| `hdd_header_injector.h`, `hdl_rpc.h`, `neutrino_gameid.h` | HDD headers, HDL EE/IOP RPC and Neutrino/MMCE game-ID interface. |
| `lang.h`, `https_client.h`, `self_update.h` | Language keys, HTTPS API and updater/package contract. |

`src/popstarter_internal.h` is private to the POPStarter implementation. `include/snippets/readCD.h` is a retained snippet, outside the top-level header inventory.

## Other source trees and build inputs

| Path | Responsibility |
| --- | --- |
| [ps2.yaml](../ps2.yaml) | Supported standard EE/IOP target graph, libraries, features and embedding. |
| [scripts/configure_ds34.py](../scripts/configure_ds34.py) | Generate the DS34 target graph from exact anchors in ps2.yaml; update anchors when source paths change. |
| [src/embed_blobs.S](../src/embed_blobs.S) | Plain payload slices, UDPFS peers and sound embedding; most target/SDK IRXs are separately embedded by ps2.yaml. |
| [loader/loader.c](../loader/loader.c), [loader/linkfile](../loader/linkfile) | Embedded executable loader and fixed low-memory link layout; separate EE build. |
| `ee_libs/iopreboot/`, `ee_libs/hdd/` | Local EE libraries for IOP reboot and HDD RPC. |
| `iop/ata_bd/`, `iop/pccf/`, `iop/ps2hdd_osd/` | ATA block driver, PC CARD CompactFlash and HDD/APA driver. |
| `iop/mmceman/`, `iop/vmcman/`, `iop/usbd-ra/` | Memory-card emulator, virtual memory-card and pinned USB host implementations. |
| `iop/udpfs_smap/`, `iop/ps2ips_rpc/`, `iop/ps2host/`, `iop/oldlibs/ps2ftpd/` | Network transport/interface, socket RPC server, host filesystem and FTP service. |
| `iop/ds34usb/`, `iop/ds34bt/` | Optional controller EE clients and IOP backends. |
| `iop/AllowDVDV/`, `iop/dev9_poweroff/`, `iop/hdl_info/`, `iop/xparam/` | DVD access, DEV9 shutdown, HDL service and Deckard game parameters. |
| `iop/__precompiled/`, `packages/` | Embedded prebuilt dependencies and local package fallbacks. Preserve provenance/ABI notices. |
| `iop/oldlibs/libcdvd/` | Historical Makefile LEGACY CD/DVD support; not the default PS2BUILD path. |
| `res/`, `exploits/`, `__Headers/`, `Lang/` | Sound/CA assets, installer payloads, HDD header templates and translations. |
| `igr/`, `research/`, `windows/` | Auxiliary inputs/research/platform material; not top-level EE sources in ps2.yaml. Inspect their own references before cleanup. |
| [scripts/gen_dash_font.py](../scripts/gen_dash_font.py) | Generate proportional font atlases/metrics, validate ASCII/Latin-1 coverage, and name each family's export and license notice. |
| [scripts/build_https_tls.sh](../scripts/build_https_tls.sh) | Pinned Mbed TLS source/checksum and EE dependency configuration. |
| `scripts/gen_githash.py`, `scripts/check_build_identity.py` | Installed commit metadata generation and compiled release identity checks. |
| `Makefile`, `embed.make`, `scripts/ci/resolve_make_args.sh` | Retained historical/profile build workflow; not release CI source of truth. |
| `tests/`, `scripts/check_*.py`, `scripts/check_loader_layout.sh` | Host behavior contracts, linked-artifact checks and loader bounds. |
| `scripts/package_apps.py`, `scripts/release_notes.py`, `.github/workflows/compile.yml` | ZIP/PSU packages, release metadata and build/publication gates. |
| `docs-site/content/`, `docs-site/manifest.json`, `docs-site/build.py`, `docs/wiki/` | Authored documentation, generated site and wiki publishing inputs. |

## Keeping this map useful

Update the relevant row when an implementation changes ownership. Add new source files under the subsystem that owns their state and effects. Each non-generated source should name its responsibility, exported API header, state owner, thread/IO restrictions and cleanup/reset contract in a short leading comment. Preserve original attribution.

Before deleting a candidate, check both controller graphs, Makefile-only profiles, assembly/linker references, tests, generated assets and auxiliary consumers. A repository text search establishes a candidate, not proof of linker reachability.
