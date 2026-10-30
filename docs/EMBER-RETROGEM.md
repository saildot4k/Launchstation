# Ember RetroGEM identity

Backported from [NathanNeurotic/Launchstation at c184101e38d58dde5c41a43b95e0c8b07af5e10e](https://github.com/NathanNeurotic/Launchstation/tree/c184101e38d58dde5c41a43b95e0c8b07af5e10e).
The imported components are `src/ember_gameid.c`, the shared PS1 reader and
serial parser changes in `src/popstarter_vcd.c` and `src/popstarter_gameid.c`,
and the two Ember identity/handoff regression tests. Local integration retains
this fork's ELF-preparation interface, launch paths, and USB remount checks.

`src/ember.c` owns launch orchestration. The existing **Settings > Launching >
Game ID output > Game ID launch signal for discs** preference gates optional
identity lookup. Lookup completes before cleanup frees configuration or changes
mount numbers. The saved ID is sent through `displayRetroGemGameID(id, 2)`
after successful cleanup and any USB remount, immediately before keep-IOP
execution. Cancellation or a failed remount sends no signal. An unavailable ID
omits the signal and lets the normal launch proceed.

`src/ember_gameid.c` resolves a CUE's first supported data track using its relative
`FILE` and file-sector `INDEX 01`. Neither `PREGAP` nor `INDEX 00` is added to the
offset. It supports MODE1/MODE2 tracks with 2048-, 2336-, or 2352-byte sectors,
quoted filenames, audio tracks, BOM, and CRLF. CUE text is limited to 64 KiB.
Absolute/cross-device FILE paths are refused. The reader is bounded and read-only.

A BIN first uses its same-stem `.cue` or `.CUE` when present; otherwise it probes
the supported layouts at offset zero. An EXE may use a same-stem CUE; a standalone
PS-X executable has no disc filesystem to identify.

`src/popstarter_vcd.c` contains the shared ISO9660 sector/SYSTEM.CNF reader. Its
existing VCD entry points retain the one-MiB container offset. `src/popstarter_gameid.c`
shares the PS1 identity rules: SYSTEM.CNF BOOT serial, then the existing PVD timestamp
database, then filename fallback after confirming an ISO filesystem. Serials are
normalized consistently for CUE/BIN and VCD, including lowercase/separators, SLUSP,
and LSP spellings. Generic ELF and Neutrino PS2 identity rules are unchanged.

`src/main_gameid.c` remains the visual-signal implementation. This integration
adds no MMCE card-selection command, image rewriting, metadata file, or save change.

Validation: `tests/test_ember_gameid.py` runs the production readers and timestamp
database against equivalent generated CUE/BIN/VCD images, including malformed
inputs and fragmented/failed reads. `tests/test_ember_retrogem_handoff.py` runs the
production launch function with simulated cleanup/remount to verify preference,
ordering, failures, and launch arguments. Both standard and DS34 target sources
are compiled separately. RetroGEM decoding and actual Ember execution still need
physical-console verification.
