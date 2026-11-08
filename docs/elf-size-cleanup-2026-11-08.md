# Packed ELF cleanup — November 8, 2026

The standard packed ELF shrank by **175,584 bytes (11.63%)**; DS34 shrank by
**176,064 bytes (11.58%)**. The final before/after comparison uses fresh builds
with the same SDK and installed-build identity. Existing binaries in the checkout were
preserved separately and were not used as the comparison baseline.

| Variant | Baseline packed | Final packed | Saved |
| --- | ---: | ---: | ---: |
| Standard | 1,509,808 | 1,334,224 | 175,584 |
| DS34 | 1,520,304 | 1,344,240 | 176,064 |

| Variant | Baseline stripped | Final stripped | Saved |
| --- | ---: | ---: | ---: |
| Standard | 3,986,496 | 3,588,416 | 398,080 |
| DS34 | 4,013,888 | 3,615,424 | 398,464 |

## Changes and evidence

- Removed PS2NETFS from the PS2BUILD and historical Makefile/embed graphs,
  together with its unused import and residency flag. There was no loader
  function or service caller. Linker garbage collection already discarded it,
  so this cleanup alone does not account for a packed-size saving. FTP, Host,
  UDPFS and Internet clients retain their existing module-loading paths.
- Added an explicit `opt: -Os` to the main EE target. The freshly installed SDK
  defaults to `-O2`; the loader already specified `-Os`. Application sources,
  controller variants, assets and hardware features stay in the build.
- Added a pinned Mbed TLS client profile in
  `include/https_mbedtls_config.h`. It removes server/DTLS support, session
  caching/tickets, PSK/static RSA/static ECDH/finite-field DH exchanges,
  unused algorithms and curves, key/certificate writing, encrypted key-file
  formats, filesystem helpers, persistent PSA storage and library self-tests.
- Retained TLS 1.2 and 1.3, ECDHE-RSA/ECDHE-ECDSA, AES-CBC/GCM,
  ChaCha20-Poly1305, SHA-2, RSA PKCS#1/PSS verification, P-256/P-384/P-521,
  X25519, PEM trust anchors, SNI, certificate dates, hostname verification,
  entropy collection and actionable verification diagnostics.
- The dependency builder appends the profile to the upstream configuration
  before compilation and installation. Application headers and archives
  therefore share the feature-dependent TLS context layouts. CI checks the
  effective preprocessor configuration and compiled archive symbols with
  `scripts/check_https_tls.py`.
- The main link now explicitly writes `wLaunchELF.map` in each output
  directory, so future size analysis has a freshly generated map.

An intermediate build with the reduced TLS profile and `-O2` measured
1,425,840 bytes packed for standard and 1,435,664 for DS34. The subsequent
`-Os` change saved another 91,616 / 91,424 packed bytes. Archive size is not
packed contribution: the three TLS archives together went from 1,525,606 to
825,394 bytes, while the TLS-only packed saving was 83,968 / 84,640 bytes.
The intermediate measurements preceded the final installed-build identity
refresh; the baseline and final tables were remeasured with matching identity.

## Reproduction and provenance

Measured with PS2BUILD v2026.11.07, toolchain/tools v2026.11.04 and
sdk-core/sdk-world v2026.11.05. Both comparisons embed checkout identity
`4bb954f31c36c77071edf2e774b0b8e1f7e93804` plus these uncommitted changes.
The baseline reused the original installed `.https-deps` headers/archives;
the reduced dependency was rebuilt from the script's SHA-256-verified
Mbed TLS 3.6.7 source archive. The original installed configuration header's
SHA-256 was `2d8192b10ceae946342d6635bab4d35a3e915eb8a90b523900fa065a0bc8c4fd`.

```sh
bash scripts/build_https_tls.sh
python3 scripts/gen_githash.py --require-git
ps2build build
python3 scripts/configure_ds34.py
ps2build build -c .ps2-ds34.yaml -o build-ds34
toolbin="${PS2BUILD_ROOT:-$HOME/.local/share/ps2build}/toolchain/ee/bin"
python3 scripts/check_https_tls.py \
  "$toolbin/mips64r5900el-ps2-elf-gcc" "$toolbin/mips64r5900el-ps2-elf-nm"
wc -c build/bin/wLaunchELF*.elf build-ds34/bin/wLaunchELF*.elf
```

## Validation and limits

Both EE/IOP builds, installed-build identity checks, DS34 linkage checks,
source-built UDPFS/peer ABI checks, loader memory-layout validation and both
installable app packages passed. The existing HTTPS framing/TLS failure,
updater, ancestry, transaction, DEV9 transition, real loopback FTP, app package
and release-workflow tests passed.

A host build of the same reduced Mbed TLS profile completed real, verified
TLS 1.2 and TLS 1.3 connections to `api.github.com`, `github.com`,
`release-assets.githubusercontent.com` and `objects.githubusercontent.com`.
The API/website negotiated ECDSA and download hosts negotiated RSA with TLS
1.2. An intentionally wrong hostname failed certificate verification with
the CN-mismatch flag. This host probe used POSIX sockets and host entropy;
the production PS2 transport/entropy implementation is covered by the existing
harnesses, not by that live network probe.

Physical-console boot, updater/download, frame-time, transfer and launch
acceptance remain to be run. In particular, `-Os` changes generated code;
host tests and successful links do not establish PS2 performance.

## Remaining candidates

- Font input sections total about 607 KB before ELF packing. Any representation
  experiment needs a packed comparison and visual checks while preserving
  ASCII/Latin-1 coverage, sizes, alignment and texture behavior.
- `embed_blobs.S` retains about 344 KB in a shared input section. Separating
  payload sections would improve individual accounting and allow independent
  garbage collection; all currently referenced payloads must remain present.
- The classic main-loop fallback still has compiled callers. `DashRun()` has
  a re-entry return, so removing that fallback needs an explicit entry/return
  contract and launch/settings checks before claiming it is unreachable.
- Large file-browser/HDD BSS buffers are RAM candidates. Shrinking zero-filled
  BSS does not directly remove their capacity from the packed ELF.

These are follow-up investigations, not additional savings claimed here.
