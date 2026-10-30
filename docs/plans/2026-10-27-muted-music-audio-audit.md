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
stop API. At this stage Music Off retained a muted looping voice 23. No driver
replacement or music-gain workaround was included in that correction.

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

## October 28 user-requested workaround

The physical-console symptom persisted. At the user's request, runtime music
now stays at 5% whenever the requested music switch is Off or its volume is
zero. This also starts the sidecar from an Off/zero saved configuration.
The UI presents Off/0%; stored user values remain separate from the effective
playback gain. Increasing Music volume re-enables normal playback, and the
Background music On action leaves zero volume at the smallest UI step (10%).
Music gain is set before the first key-on to avoid a startup burst.
Suspend and shutdown continue to mute/stop audio for application handoff.
The workaround requires a readable BGM.ADP on an already active boot stack;
missing/invalid music keeps the previous silent fallback and once-per-session
read policy. Existing voice reservations and SFX volumes are unchanged.
This implements the requested workaround; console testing is still needed
to establish whether it prevents the reported dropout/cutoff symptom.

## October 29 console feedback and Neutrino options

The user reports that the 5% workaround still produces missing or truncated
interface sounds, while manually enabling music at 10% works. The runtime
fallback in `src/dash_sound.c` now uses 10%, matching that reported working
setting through the same sidecar, voice 23 and gain-before-key-on path. Off
and zero volume still display Off/0% and retain their saved values. This is
an adjustment to the workaround, not an established diagnosis of the SPU2 or
analog-output symptom. It still requires a readable optional `BGM.ADP`.

The Neutrino options popup had a separate confirmed lifecycle defect:
`dashLaunchApp()` muted all audio before `ExecuteMainAction()` opened the
interactive options. It now leaves audio active for ISO launches until
Neutrino reaches `CleanUpForKeepIopExec()` after Run game and loader
preparation. Ordinary ELF launches retain their existing mute and recovery.
The Neutrino popup also calls the guarded `dashSoundMaintain()` on entry,
because ISO/profile preparation can have replaced the IOP while the main
dashboard loop is paused. This recovers a stale service without restarting
a healthy music voice. Cancellation leaves the dashboard audio available.

The host regressions execute the production frontend, handoff gate, popup,
sidecar and gain functions. They check cancellation, nested options, committed
handoff, a cancelled background-work wait, IOP recovery and the equivalence
of Off/0% to On/10% without saving the effective gain. They do not simulate
physical SPU2 output; the revised workaround still needs console retesting.
