# Launchstation dashboard

The dashboard is the only shell of this build; the classic launch-key
menu and the classic screens are gone. Underneath it still uses the proven
underlying wLaunchELF code: every launch goes through `ExecuteMainAction()`, and file
operations, the HDD tools and the exploit installer run the same logic as
before. Settings, the File Browser, the Text Editor, the HDD Manager (PSX
included), the memory card exploit installer, the information screens and
the file/folder picker are all dashboard screens, and the questions those
tools ask (yes/no, names, progress) are dashboard dialogs. Commands with no
screen of their own (start disc, OSDSYS, PS2 browser, network, power off,
reboot IOP) run behind the loading overlay.

File Browser: Confirm opens a folder, previews PNG/JPG/JPEG images, starts an ELF/KELF/VCD/ISO or opens a
text file in the Text Editor. The image viewer supports sibling-image browsing,
90-degree rotation, 1x-4x zoom, left-stick panning, fullscreen mode and a
configurable 1-60 second slideshow; Square selects; Triangle has copy, cut,
paste (also with new names), PSU create/extract, delete, rename, new
folder, folder icon (icon.sys), size, start with arguments, title.cfg,
mount as vmc0:/vmc1: (for .bin/.vmc/.mc2/.ps2 images; mounted images
appear in the device list), the memory card *Tuna date and *Folder
dates* (memory card roots and `hdd0:/__common`: edit dates by hand or
order the saves A-Z, Z-A or the SAS way). The offered operations follow
the classic rules (nothing that writes on a disc or read-only host, no
file operations in the partition list).

Also in the File Browser menu, as in the classic browser:

* *Show*: file names, names and details (size and date), or game titles
  and details (the title of each save or PSU file).
* *Sort by*: name, game title, date, or as stored. Folders come first,
  then ELF files.
* *Bookmarks...*: the PathPad. Jump to a bookmarked folder, bookmark the
  current one or remove one (saved in LAUNCHELF.CNF; *Lock shortcuts & bookmarks*
  under Settings > Launching locks them).
* *Go to Launchstation's folder*, *Invert selection*.
* *Use as launch arguments* on a text file: its lines become the
  arguments of the application you start next from the browser.
* The header shows the free space of memory cards and HDD partitions.

In file pickers (Settings, launch keys) R3 chooses the highlighted file as
a `uLE:/` path, relative to Launchstation's own folder, like the classic R3;
elsewhere R3 opens that folder.

The cursor never waits for the memory card or a slow device: file reads
and writes (artwork, saves, library scans, folder listings) run on a
background thread, and a small indicator above the button hints shows
what is being worked on. Starting a device's drivers happens in the
foreground behind a short loading overlay.

## Sections

The four top-level tabs are **HOME, FILES, TOOLS, SETTINGS**. Unlike the
earlier modal browser shortcut, **FILES is now a full dashboard section**.
Its file list is drawn inside the ordinary dashboard frame with the section
selector, L1/R1 shoulder navigation, animated background and status bar still
visible. Entering Files does not start a second independent input/draw loop.
L1/R1 moves between adjacent tabs even when browsing a folder. On returning
to Files, the browser restores the previous folder and highlighted entry.

HOME includes both Continue and the entire application library. Use the
**Applications** shortcut in Home's **Browse & shortcuts** row to enter
the full library (Grid, List, Carousel, filters, favorites/pins and refresh).
Back returns to Home. The Home **Last folder** chip refreshes when Home
becomes active, without device-readiness probes during Files I/O.

Within Files, **Back** moves to the parent folder. Back from the device
root returns to Home, but Files remains available as a regular tab. The file
operations, browse/view/sort modes, copy/paste, VMC backup operations and
PathPad features remain in the same browser. The directory reader keeps its
USB/PAD serialization across all tabs (including reads started before a tab switch) and invalidates in-flight results when switching tabs.

**Tools > Storage > MISC commands** opens a popup menu of built-in commands.
**Configure** switches to the Settings tab, and **File Browser** switches to
the Files tab. The popup closes before the selected command runs.

| Tab | Contents |
| --- | --- |
| HOME | Continue carousel, full Applications library shortcut, Last folder, optional launch-key shortcuts. |
| FILES | Native File Browser as an actual tab, with shared header and L1/R1 navigation. |
| TOOLS | MISC commands, storage/device utilities, application and disc launch helpers, information and power commands. |
| SETTINGS | Appearance, Home & applications, Sound, Input, Launching, Storage & devices, Network and System; unchanged save/discard behavior. |

Start screen offers Home, Applications, Files, Tools and Settings.
Applications opens the full library under Home with All selected. The old
Devices startup value still opens Files.

On HOME and the DEVICES grid, a small console label uses the ROM region already
read at boot. It does not probe hardware while drawing. The DEVICES grid's
**Triangle → Options → Console information** action opens the System information sheet;
that explicit action may query CDVD for the exact console model. Once read,
the model is cached for the small HOME/DEVICES labels. Until then they show
PS2 or PSX and the available ROM region rather than guessing a model.

## Dashboard top-edge flicker / tearing

The classic wLE GS renderer uses a single framebuffer. This is suitable for
mostly static screens but causes horizontal tear bands when the animated
dashboard draws into the same image being scanned by the TV. The earlier
header-selector smoothing removed a high-frequency highlight animation but
did not fix that scanout race.

Launchstation now enables **gsKit double buffering when the dashboard starts**,
without altering the classic GS initialization routine. It renders the next
complete frame into the hidden buffer and flips buffers at VBLANK. It retains
GS screen offsets and refreshes the texture manager after the framebuffer
layout changes, including when changing the video mode. When file I/O is
running in the background, the renderer continues yielding during VBLANK but
uses exactly the same display/active-buffer progression as gsKit's standard
double-buffer flip. Standard and DS34 builds use the same path.

Trade-off: the second frame consumes approximately 1.1 MiB (NTSC/480p)
or 1.25 MiB (PAL) of the PS2's 4 MiB GS VRAM, leaving less room for
cached artwork. The existing small (128px) art thumbnails and texture-manager
eviction are retained. This is a code-level anti-tearing correction; actual
console output still needs verification across video modes before concluding
that every source of interlaced display shimmer has been eliminated.

## Intermittent USB stalls (standard build)

Launchstation limits USB-startup media discovery to four spaced scans, accepting
late first and second drives without probing an absent port twenty times.
The checks use synchronous IOP filesystem RPC: a single stalled request
cannot be interrupted by the retry timer, so this is containment, **not a
proven fix for every USB hang**. A pending async memory-card poll is drained
before any deliberate IOP reset closes/reopens PADMAN, to avoid an outstanding
SIO2 request crossing a reset. This applies to the standard and DS34 build;
the user-reported failure was on the standard build, not yet on DS34.

When a controller's analog LED goes dark as the USB screen stalls, suspect
an IOP/PADMAN/SIO2 session disruption or a console USB power issue; the LED
alone does not identify which. If the issue persists, checking the same drive
on one port, the second port, and through a **powered USB hub** can help
isolate electrical loading. With two devices, compare drive combinations.
Do not unplug drives during active writes. No automatic IOP reset is attempted
as a recovery from a blocked USB filesystem RPC.

**Explicit two-drive diagnosis:** Open **Tools > Storage > USB unit
diagnostics**. **Show cached units** reads only the previous detection result
without performing USB I/O. Select **Probe logical unit 0 once** or
**Probe logical unit 1 once** to issue exactly one filesystem root-stat RPC
(after the worker and outstanding memory-card status request have finished).
A confirmation warns that the console can lock up within this synchronous
request; no timeout or automatic IOP reset can recover a wedged RPC. The
diagnostic shows which request begins before it enters the RPC and displays
its return code if it completes. It does **not** rescan both units, change
device visibility settings, reset the IOP, write to USB, or alter the cached device
list. A successful root stat alone is not a completed file-read test.

For two attached drives, first capture the cache, then probe logical unit 0
and 1 separately. Repeat with only the FAT32 drive, only the exFAT drive, both
connected but swapped between physical ports, and (when available) through a
powered USB hub. Record the last on-screen probe path, whether the clock
freezes, whether the controller's analog light stays on, and which drive
was plugged into which *physical* port. **usb0/usb1 are logical enumeration
units, not guaranteed physical port numbers.** On a frozen screen, power-cycle
safely rather than unplugging a drive during an active transfer.

## Settings navigation

Settings opens at the overview. Confirm or Right opens a group; Back returns
to the previous page with its selection and scroll position intact. Back at
the overview returns Home through the normal save decision. Left also goes
back on rows that do not use Left/Right to change a value. L2/R2 jump to the
first/last row. The breadcrumb shows where the page lives.

Screen calibration previews video modes for 10 seconds so the display has
time to resync. Choose Keep to browse the full interface in that mode;
cancel or let the countdown expire to restore the previous mode and offsets.
Save Settings separately to retain an accepted mode after restarting.
NTSC, VGA and 480p render at 640×448; PAL and 576p render at 640×512.
The dashboard scales its shared 640×448 canvas to the framebuffer, preserving
relative panel, text, clipping and row spacing. Check Home, Files, Tools,
Settings and the Text Editor after each switch. The graphics transfer and
rendering finish before a live GS reset, and the texture pool is recreated
for the new framebuffer layout.

| Group | Contents |
|-------|----------|
| Appearance | Theme preset, customization groups, screen calibration, motion, animation, theme files and resets. Panel opacity belongs to Interface colours > Panels. |
| Home & applications | Start screen, view, artwork, recent count/history and Application library (folders and refresh). |
| Sound | Interface effects, music and their separate volumes. |
| Input | Confirm button, on-screen keyboard and USB keyboard (driver and map). |
| Launching | Automatic start & boot, Launch keys, shortcut/bookmark lock, disc/PS1 loaders, IOP reset and game IDs. |
| Storage & devices | Browser device visibility and storage preferences. |
| Network | IP address, netmask, gateway and network write access. |
| System | Language, memory card backup-file rules, configuration folder, alternate launch/tool settings save location and welcome message. |

Unavailable dependent options remain visible with help explaining what to
enable first. Path rows open a Choose/Clear dialog. Launch-key rows open
Choose target/Edit title/Clear target; Square edits a title directly.
Square resets individual appearance options to their preset defaults.

Previewed changes share the existing Save/Discard session, including themes
and network addresses. Unchanged sessions and changes returned to their
original values do not prompt. Triangle's Changes menu is global to Settings;
it is not buried in a configuration group. LAUNCHELF.CNF and IPCONFIG.DAT keep
their existing save targets; System's alternate save action writes only
LAUNCHELF.CNF. Theme export writes a separate theme folder immediately.

An earlier failed automatic/bookmark save is reported separately as *save
failed*, with an explicit *Retry failed saves* action. It does not turn an
untouched visit into changes or force a leave prompt. Failed saves requested
during the current visit still keep that visit unsaved until retried or
discarded; Discard does not claim the failed write succeeded.

Clearing history and refreshing the library are immediate maintenance actions;
Discard does not undo them or unload drivers started by an operation.

## Controls

Animated backgrounds continue behind menus, theme previews, dialogs and
native full-screen tools. These frames share the dashboard's measured visual
clock; motion and menu easing do not assume 60 frames per second. Opening a
menu does not run dashboard input, device polling or library scans behind it.
Background motion at 0% still intentionally freezes the scene. Long blocking
operations retain the existing 100 ms visual-step limit rather than jumping
the animation forward on return.

OSD orb/clock-background phase is RTC-anchored but continues on the shared
visual clock if RTC fields stop changing or become invalid. That keeps
these effects moving with a dead/stalled console clock; it does not invent
an accurate date/time or replace the footer clock. A valid RTC tick
re-anchors the effect. Motion at 0% still holds the scene.

Confirm/cancel follow the existing `GUI_Swap_Keys` setting (Settings >
Input > Confirm button), as the classic browser did.

| Button | Action |
|--------|--------|
| D-pad / left stick | Navigate |
| Confirm (Circle or Cross) | Start / open / select |
| Cancel | Back / close |
| Triangle | Options for the focused item |
| Square | Add to / remove from Favorites |
| L1 / R1 | Previous / next section |
| L2 / R2 | Page jump |
| START | Open / close the Dashboard menu (home, refresh library, File Browser, settings, reboot IOP, power off) |
| SELECT | Tap: switch application view (APPS). Hold: your launch keys appear; press a button to start its application |

`Init_Delay` is honoured, and a launch key held when the delay ends
starts its application. Automatic start requires both a configured
`LK_auto` path and a positive timeout. Any button cancels the countdown.
A timeout of 0s disables automatic start while keeping the target saved,
so the selected Start screen stays open. Held-button launch keys still work
at 0s. Set the timeout under Settings > Launching > Automatic start & boot,
then save Settings.

## Themes

Settings > Appearance chooses among 19 built-in themes (OSD Classic, PS2
Towers, Disc Error Red, System Clock and more) and opens the theme editor,
where the background, every colour, selection style, corners, font, text
size, icons, clock and app-artwork wallpaper can be changed with the
controller. Themes can be saved to and loaded from
`THEMES/<name>/theme.cfg` folders. See **[themes.md](themes.md)**.

## Application discovery

Only the configured folders are scanned (Settings > Home & applications >
Application library > Application folders). The defaults are `mc:/APPS/`,
`mc:/BOOT/`, `mass:/APPS/`, and `mass:/BOOT/`; Launchstation does not
silently scan every folder on every device. Each configured folder is searched
one sub-folder deep (`APPS/<folder>/*.ELF`). The settings screen shows the
active list and lets the user add or remove exact scan roots.

* At startup only memory cards and devices whose driver is already running
  are refreshed (Settings > Home & applications > Application library >
  Refresh at startup). Nothing else is
  initialised for the dashboard.
* *Refresh library* (APPS > Triangle, START menu or Settings) scans every
  folder, starting the drivers it needs first; the search itself runs in
  the background while you keep using the dashboard.
* Results are cached in `DASHLIB.CNF` and shown instantly next boot.
  Apps that disappeared (device removed) stay usable as shortcuts and fail
  with a friendly message instead of a crash.

## Metadata (optional)

Plain `key = value` text; every key is optional; `#` starts a comment.

* `<dir>/<ELFNAME>.cfg` (e.g. `OPNPS2LD.cfg` next to `OPNPS2LD.ELF`)
* `<dir>/title.cfg` in OPL application format (`title=`, `boot=`); applied
  only when `boot=` matches the ELF

```
title = Open PS2 Loader
description = Game loader for USB, HDD, SMB and MX4SIO.
author = ifcaro & contributors
version = 1.2.0
category = Loader
cover = cover.png          # relative to the ELF folder, or a full path
arg = -some-option         # one argument per line, repeatable
pinned = 1                 # show on HOME
```

Arguments: a classic `<ELFNAME>.arg` sidecar always wins; metadata `arg`
lines are used only when no `.arg` exists. *Start with arguments...* uses
the Text Editor's "Launch with args" flow. *Edit metadata* in Home or
Applications options opens the app folder's `title.cfg` in the Text Editor.
If it is missing, the action offers to create it with the current title and
`boot = <ELF filename>`, even when an ELF-specific sidecar already exists.

## Artwork (optional)

First match wins; nothing is required.

1. `cover =` from the metadata
2. `<dir>/<ELFNAME>.ELF_COV.png` (OPL naming, e.g. `OPNPS2LD.ELF_COV.png`)
3. `<dir>/<ELFNAME>_COV.png`, `<dir>/<ELFNAME>.png`
4. `<dir>/cover.png`, `<dir>/icon.png` (only for per-app folders)
5. `<dir>/<ELFNAME>_ICO.png`
6. `<device>/ART/<ELFNAME>.ELF_COV.png`, `<device>/ART/<ELFNAME>_COV.png`
   (OPL ART folder; `hdd0:/+OPL/ART/` on the internal HDD)
7. `<dashboard folder>/ART/` with the same names
8. the theme's default application icon (a PS2-style program tile with a
   device badge; a theme may use its own PNG, or the device icon or the
   old initials tile instead, see [themes.md](themes.md#icons))

Any PNG size up to 2048x2048 / 1.5 MB is accepted and box-filtered down to
at most 128x128 while decoding. Artwork on a device whose driver is not
running is looked up later, when that device is opened.

## Files written by the dashboard

Next to LAUNCHELF.CNF when it was loaded from a writable device, otherwise
in `mc0:/SYS-CONF/`: `DASHBOARD.CNF` (settings, scan folders),
`DASHAPPS.CNF` (favorites, pins, recents), `DASHLIB.CNF` (library cache).
The active theme is part of DASHBOARD.CNF (`Theme_*` keys); saved themes
go to `THEMES/<name>/theme.cfg`, only when you choose
*Export theme to folder* — in the ELF's own folder when writable, else the
dashboard folder (see [themes.md](themes.md#theme-folders-user-created-themes)).
LAUNCHELF.CNF itself is never modified behind your
back.

## Interface sounds

The dashboard plays short sound effects through the ps2sdk `audsrv`
audio server: cursor moves, confirm/cancel in dialogs, section switches,
toasts, the startup boot sound, and device connect/disconnect. They are
Sony ADP samples embedded in the ELF (no files needed at runtime).

Settings > Sound has *Interface sounds* (the UI effects) and
*Background music* (the music track), each with its own volume
(`Dash_Sound` / `Dash_SoundVolume` / `Dash_BGM` / `Dash_BGMVolume` in
DASHBOARD.CNF, all on at 80% by default). The two switches are independent;
turning off interface effects keeps enabled music playing. When the audio driver cannot
start, everything stays silent — the dashboard works normally without
sound (a toast says why).

## Optional background music

Music is no longer embedded in the ELF. Installable ZIP/PSU packages now
include `BGM.ADP` beside the ELF automatically. For an ELF-only installation,
you can add the optional `BGM.ADP` beside the ELF, for example:

```text
usb0:/BOOT/BOOT.ELF
usb0:/BOOT/BGM.ADP
```

Local builders can copy `res/music.sad` unchanged as `BGM.ADP`. It is a
mono PS-ADPCM file with the `APCM` header produced by ps2sdk's `adpenc`,
not an Ogg/WAV/MP3 file renamed to `.ADP`. Custom tracks must be at most
1 MiB, have a 16-byte header and complete 16-byte ADPCM blocks, and use
mono format/version 1 with a valid SPU2 pitch. Use loop-enabled encoding
for continuous music.

The file is read from the actual boot folder, not the folder of an imported
LAUNCHELF.CNF. If no boot folder is known, the existing Launchstation folder
is the fallback. Disc boots preserve the disc folder for sidecar reads
while keeping the writable memory-card configuration fallback.

Missing, malformed or unreadable music leaves the dashboard and embedded
interface effects usable. A missing/invalid sidecar is tried only once per
audio session; turn Background music off and on to retry after adding it.
The loader waits until worker IO is idle and the boot device's drivers are
already active. It never starts a storage stack just to look for music.
IOP resets discard the uploaded track; it reloads when audio and the boot
storage stack become available again. The original track is 284,656 bytes;
omitting it saves that much storage in addition to the smaller packed ELF.

## Devices and the applications filter

Driver residency alone does not mean that storage is attached. Optional
HDD/ATA, MMCE (each slot separately), MX4SIO and UDPFS cards are dimmed and
marked *Not checked yet* until a root check succeeds. Failed explicit
checks remain dimmed and hide that storage's cached applications. Checks
run when a browser or operation needs the device; there are no blocking root probes during
drawing. Results expire on IOP reset, but are not continuous hotplug
monitoring for these optional families: select *Check again* after changing
the attached device/server. USB and memory cards retain their existing
live discovery. Storage free-space labels use MB/GB; file sizes still use
B/KB where appropriate.

Storage drivers load on demand when opening a device, launching an application,
or using a tool that needs it. Startup scans only devices whose drivers are
already running. There are no per-device driver auto-start switches; old
`Dash_DevAuto` and `Dash_ShowUnavailableDevices` entries are ignored and omitted
when saving `DASHBOARD.CNF`. Eligible device families remain listed; opening
an unprobed device starts the existing lazy driver stack.

Neutrino launches initialize MMCE before preparing the loader, then request
the ISO's game-ID VMC on responding MMCE adapters just before handoff. This
follows R3Z 4.80 without requiring a storage preference. MMCE initialization
and card switching are skipped when the ISO or loader uses MX4SIO. Slots
holding the ISO or Neutrino executable are left unchanged; absent hardware
or a rejected switch does not prevent launching the game.

On APPS, the *Show* choice (Triangle menu) filters the list — All,
**Favorites**, Memory Cards, USB, HDD, Other devices — and the choice is
remembered across restarts (`Dash_AppFilter`).

## Optional PSBBN layers (Crystal background)

With the *Crystal* background, `<dashboard folder>/THEME/background.png`,
`stars1.png`, `stars2.png` are used when present (backdrop plus two
additive star layers). Build them from a PSBBN texture pack you own with:

```
python scripts/prepare_psbbn_theme.py PSBBN-Texture-PNGs.zip
```

No third-party artwork is embedded in the ELF.

## Typography

Dashboard text uses Roboto Regular (Copyright 2015 Google Inc., Apache
License 2.0, see `docs/licenses/Roboto-COPYRIGHT.txt`). It is rendered on the
host by `scripts/gen_dash_font.py` (4x supersampled) into three PSMT8 alpha
atlases (14, 20 and 32 px em; 35 + 57 + 123 KB) committed as
`src/dash_font_data.c`; the PS2 needs no font engine. Sizes run from 12 px
captions to 28 px titles. Themes can switch the dashboard to that bitmap font as well
(*System* font, see [themes.md](themes.md#fonts)), scale text from 90 to
115 % and draw it bold. Regenerate the Roboto atlases with another TTF/OTF:

```
python scripts/gen_dash_font.py path/to/Font.ttf
```

## Memory and VRAM budget

* Framebuffer: unchanged (single buffered, CT32, as the classic UI).
* Dashboard font atlases ~215 KB, bitmap-font atlas 512x340 PSMT8 (~170 KB,
  only with the *System* font), icon atlas 512x408 PSMT8 (~204 KB),
  five tiny CT32 helper textures. All textures are owned by gsKit's texture
  manager (inline uploads, LRU eviction) above the framebuffer.
* Artwork: at most 40 thumbnails (<= 64 KB each) in EE RAM; one probe or
  one decode per frame, only after the pad has been idle ~110 ms (focused
  item) or ~260 ms (neighbours). Slots drawn in the current or previous
  frame are never evicted.
* Library: 512 entries x ~850 bytes. Scans temporarily allocate one
  FileBrowser listing buffer (~800 KB) and free it afterwards.
* Themes: the theme itself is ~700 bytes. Theme images (wallpaper <= 320 KB,
  default app icon <= 64 KB, PSBBN layers) share 8 slots and are loaded
  once on first use. The Brushed background builds one 32 KB texture on
  first use; every other background is pure geometry. Listing theme
  folders temporarily allocates one FileBrowser listing buffer.

## Developer aid

Defining `DASH_AUTOTEST` (add it to the `wLaunchELF` target's `defines` in
ps2.yaml) replays the timed button script in `include/dash_autotest.h` and
seeds a sample library, so every screen can be exercised in an emulator.
`DASH_THEME_TOUR` shows every theme preset for five seconds. Never ship
such builds.


## File Browser metadata and sorting

Detailed rows keep full date/time precision, including seconds. Size and
date-time are laid out as independent columns so the timestamp does not have
to be shortened to fit. The dashboard browser can sort by name, game title,
size, date-time, or kind, in ascending or descending order; folders remain
grouped first for predictable navigation.

Demand-loaded storage such as the internal APA HDD is
selectable while its state is `Not checked`. Opening it runs the existing
lazy loader/probe. Only a device that was explicitly checked and found absent
is skipped by navigation.

### Device names and ELF handoffs

USB devices in the browser are named **USB Storage** and display `usb:/`, `usb0:/`,
`usb1:/` and so on. Current-folder paths use numbered `usbN:/` labels;
legacy `mass:/` and `massN:/` aliases are formatted only for display.
Ordinary ELF launches follow the fixed
[wLaunchELF R3Z 4.80 policy](https://github.com/saildot4k/wLaunchELF_R3Z/blob/4.80/src/elf.c):
`usb:` and `mass:` paths become `mass0:/...`, and numbered `usbN:` / `massN:`
paths become `massN:/...`. ATA (`ata0:/`, `ata1:/`) and MX4SIO (`mx4sio:/`)
keep their selected device paths. There is no configurable handoff namespace.

The old `Modern_Device_Handoff` key is ignored when loading an existing
`LAUNCHELF.CNF` and is omitted on save. Ember, POPStarter and Neutrino retain
their loader-specific arguments. The IOP reset option remains independent.

### Video mode preview and browser navigation

Video mode changes require confirmation within **5 seconds**. Keep retains the mode in the current settings session; Cancel or timeout restores the previous mode and screen offsets. Settings are written only through the existing Save action. Physical-console timing and display compatibility still require testing.

The native File Browser provides eleven rows and the path picker ten, with centered scrolling and endpoint-first Left/Right paging. A page that overshoots lands at the first/last item; the next press at that endpoint wraps. USB entries appear immediately after Memory Card Slot 2. Device rows use two left-aligned columns: the browse path on the left and the device description on the right. Examples include `mc0:/` / Memory Card Slot 1, `mmce0:/` / SD2PSX SD Card Slot 1, and `usbN:/` / USB Storage. Both APA and exFAT HDD units are listed when enabled; mounted VMCs appear once each. PSX Internal Flash uses the driver’s `xfrom0:/` path. Diagnostic status remains in device tools and opening a device reports initialization/errors. MISC/Configure opens dashboard Settings while the dashboard owns the screen; its classic configuration behavior remains available outside the dashboard.
