# Experimental VU acceleration

The three stages are implemented for review and hardware measurement. Normal
builds keep the existing CPU renderer. Neither prototype is enabled by a saved
setting, and no speedup has yet been measured on a PS2.

## Build and compare

Use the usual installed ps2build SDK from the repository root:

```sh
python3 scripts/configure_vu.py profile
ps2build build -c .ps2-vu-profile.yaml -o build-vu-profile
python3 scripts/configure_vu.py vu0
ps2build build -c .ps2-vu-vu0.yaml -o build-vu-vu0
python3 scripts/configure_vu.py vu1-reference
ps2build build -c .ps2-vu-vu1-reference.yaml -o build-vu-vu1-reference
python3 scripts/configure_vu.py vu1
ps2build build -c .ps2-vu-vu1.yaml -o build-vu-vu1
python3 scripts/configure_vu.py both
ps2build build -c .ps2-vu-both.yaml -o build-vu-both
```

Each generated configuration enables profiling. `vu0` enables tower projection;
`vu1` enables tunnel submission; `both` enables both. `vu1-reference` uses CPU
tunnel geometry with the same submit-before-flip ordering as `vu1`, so comparisons
include the same presentation policy. Generated configurations and output
directories are ignored by Git. For Makefile builds the equivalent variables are
`DASH_PROFILE=1`, `DASH_VU0=1`, `DASH_VU1=1`, and optionally
`DASH_VU1_REFERENCE=1`; clean objects when changing these variables.

## Stage 1: bounded profiling

`dash_profile.c` records EE CP0 Count deltas for frame construction, backgrounds,
tower projection, tunnel construction, presentation, icon initialization, glow
initialization, and VU1 submission/wait. Recording allocates no memory and performs
no I/O. Every 600 eligible foreground frames it prints `[dash-profile]` records
to stdout, outside the measured frame. Reporting defers during foreground I/O
and excludes any nested render work triggered by its own stdout transport.

Each slot stores the most recent 128 samples. `p50` and `p95` describe that
window; `mean`, `max`, and `calls` cover the session. Measurements are elapsed
Count ticks, including interrupts and any preemption, rather than CPU utilization.
`present-wait` includes synchronization and can be dominated by VBLANK. With VU1
enabled, `frame-build` also includes its synchronous background submissions.

Warm the scene and textures first, then compare several reports using the same
scene, theme, effects level, video mode, workload, and stdout transport. Profile
builds use a shared scalar tower batch that computes perspective factors once
per tower. This is the fair scalar comparison for VU0, rather than attributing
that CPU optimization to the vector unit.

## Stage 2: VU0 tower projection

`dash_vu_math.c` keeps scalar and COP2 implementations of the same camera
projection. Four vector lanes process the four tower corners; colors, ordering,
visibility, and GS drawing remain on the EE. Arrays and camera data are aligned
to 16 bytes, with a scalar fallback for unaligned callers.

Each tower's COP2 registers are loaded, used, and stored inside a short interrupt
guard. Interrupt state is restored afterward. No callback, yielding operation,
library math, or DMA occurs while those registers are live. The kernel owns its
COP2 scratch registers and makes no external calls inside that section. Any
future library that retains COP2 state across preemption requires an ownership
review before combining it with this backend. The default renderer remains free
of this ownership requirement.

## Stage 3: VU1 tunnel prototype

`dash_vu1.c` constructs bounded VIF packets and owns the synchronous VIF1 backend;
`dash_vu1_tunnel.vsm` transforms tunnel directions/radii into screen coordinates
and emits RGBAQ/XYZ2 triangle strips through XGKICK. The EE retains ring spacing,
trigonometry, theme colors, fog, and draw order. Successful VU1 frames skip the
duplicate EE screen-coordinate arrays.

| VU1 data-memory qwords | Contents |
| --- | --- |
| 0–6 | Screen transform, quad count, GS offsets, GIF tags, clipping bounds |
| 7–262 | Up to 128 input vertices, two qwords each |
| 512–801 | Up to 32 output strips and final FINISH packet |

The 116-instruction program occupies 928 bytes of instruction memory. VIF UNPACK
splits at 256 qwords. Every strip continues the same GIF packet; only its final
FINISH tag sets EOP. Conservative instruction gaps cover load, arithmetic, store,
and branch dependencies; these are intentionally unscheduled prototype code.

The renderer drains its queued PATH3 clear/state before starting PATH1. Each
batch waits for DMA completion, a VIF MARK after FLUSHA, and GS FINISH before
reusing input/output memory or allowing PATH3 UI rendering. It then completes
the UI in the same backbuffer before flipping. VU calls never return with their
buffers still in flight, so launch cleanup and video changes need no asynchronous
VU shutdown. Normal CPU builds retain their existing presentation sequence.

Only fully opaque tunnel themes at full renderer alpha use the prototype.
Transparent themes and transitions use CPU geometry. Screen scale, GS offsets,
context, clipping, and renderer translation are included. A bounded Count timeout
disables the backend for the session, stops VIF1 DMA, resets VU1/VIF1/GIF, and
recreates GS/texture state for CPU fallback. Healthy frames never reinitialize
the screen. IOP, audio, storage, and launch discovery are unchanged.

Additional EE storage is bounded: approximately 4.3 KiB for profile samples,
10.3 KiB for tower outputs, 8.3 KiB for VU1 packet/vertex queues, and a 4.1 KiB
packet-builder stack frame. There is no per-frame heap allocation. Serializing
batches may cost more than CPU rendering; the prototype makes no performance
claim until full-frame hardware measurements include these costs.

## Validation and hardware acceptance

Host tests exercise the real scalar kernel, packet builder, profiler, renderer
handoff, and presentation functions. Instruction models interpret the actual
VU0 assembly and VU1 source and check projection, colors, boundaries, hazards,
packet termination, and invalid inputs. Models cannot establish real VU numeric
behavior or pipeline correctness.

Build the standalone hardware test with:

```sh
ps2build build -c bench/vu/ps2.yaml -o build-vu-probe
```

Run `build-vu-probe/bin/launchstation-vu-probe.elf` through your usual ELF loader
and capture stdout with ps2link or serial. It compares VU0 against the scalar
reference over 120 camera positions and 165 towers, reports both kernel timings,
then checks actual VU1 output for 1-, 32-, and 65-quad submissions, including
automatic batch flushing. Its final record must read `[vu-probe] PASS failures=0`.
It does not access settings or files. CI cross-builds the integration; the
standalone probe is built manually when needed.

Local validation has cross-compiled the integration with the real EE compiler,
assembled the microprogram, and linked/stripped the standalone probe. No PS2 or
PS2 emulator was available for execution. Before enabling either backend by
default, require the hardware probe to pass, inspect animated towers/tunnel in
NTSC/PAL/progressive modes and transitions, exercise modal screens, storage work,
theme changes and application launches, and establish a repeatable full-frame
benefit over its matching CPU profile without a worse frame-time tail. Leave a
backend opt-in if its benefit is absent or hardware coverage is incomplete.

The implementation follows the [VU instruction manual](https://lukasz.dk/files/vu-instruction-manual.pdf),
the [Sony VU manual mirror](https://docs.alexrp.com/mips/ee_vu.pdf), and
[gsKit's queue and flip implementation](https://github.com/ps2dev/gsKit/blob/master/ee/gs/src/gsCore.c).
