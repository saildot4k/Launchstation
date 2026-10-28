# Muted music and missing interface sounds

The reported case is a physical PS2 using analog red/white audio cables.
Interface sounds become unreliable with Background music Off or Music volume
at 0%, and recover immediately when music is audible again.

## Confirmed software defects corrected

- `dashSoundPlay()` discarded cursor requests less than 45 ms apart. Controller
  scrolling in `pad.c` accelerates to a 40 ms delay (41 ms in the existing
  millisecond polling regression). This rejected roughly every other fast
  navigation click. Input already controls repeat; the audio layer now uses its
  six rotating cursor voices without another time gate.
- A reused voice was started before its interface volume was restored. The
  volume RPC now completes before playback, preserving the attack of a short
  effect on a voice that was previously muted. Playback succeeds only when the
  returned channel equals the requested SFX channel.

The cursor gate is independent of the music setting. Its removal fixes a
reproducible source of missed feedback; it does not, by itself, establish why
the console report specifically changes with the music setting.

## Driver checks

The successful release at `228448878eed8646503dd842d8306e5efcdb544e`
contains the earlier SFX-only fallback change. Its CI uses SDK world
`v2026.10.13.1`, which has `audio` and `audsrv-compat` but no `audsrv` package;
the workflow installs this repository's original audsrv package as its fallback.

The bundled audsrv IRX disassembly matches the
[upstream ADPCM driver](https://github.com/ps2dev/ps2sdk/blob/master/iop/sound/audsrv/src/adpcm.c)
for playback and volume: playback checks ENDX and keys on the requested voice,
and volume writes that voice's left/right parameters. It provides no per-voice
stop API. Music Off retains a muted looping voice 23. No driver replacement or
inaudible-music workaround is included in this correction.

## Evidence and remaining validation

`tests/test_sound_channels.py` reproduces the dropped cursor events before the
change. It now checks one playback per request at intervals from 17 to 83 ms
with music On, Off and at 0%, volume-before-play ordering, voice contention,
music-channel isolation and error handling. These are host tests, not an SPU2
or analog-output simulation.

Tools > Audio diagnostics provides cached playback counts and the last failure
reason/result without contacting the IOP. It preserves a failure across later
successful effects so opening the page does not erase the relevant evidence.

Both changed EE translation units (`dash_sound.c` and `dash_tools.c`) compile
with toolchain `v2026.09.27`, SDK core/world `v2026.10.13.1`, the project's
standard feature defines and the bundled audsrv header. Sound-channel, recovery,
sidecar, input-repeat, Tools and navigation host regressions pass. A complete
GitHub Actions rebuild has not been run for this correction.

On-console retesting must cover slow individual cursor/confirm/cancel presses,
accelerated scrolling and section switches in all three music states. If
isolated presses still disappear at Off/0%, the music-dependent hardware
symptom remains unresolved and requires playback/result diagnostics on that
console; passing the host cadence test is not proof that symptom is fixed.
