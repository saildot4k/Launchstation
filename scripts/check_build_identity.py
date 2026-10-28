"""Reject stripped release ELFs that do not embed the tested commit ID.

Check the unpacked executable before packaging; the packed ELF compresses its
strings. This catches missing generation, stale headers and include-path errors.
"""
import argparse
from pathlib import Path
import re
import struct


def verify(elf, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Expected revision must be a full GitHub commit ID")
    data = Path(elf).read_bytes()
    if (len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01" or
            struct.unpack_from("<HH", data, 16) != (2, 8)):
        raise ValueError(f"{elf}: expected an unpacked PS2 executable")
    if revision.encode("ascii") + b"\0" not in data:
        raise ValueError(f"{elf}: missing build identity {revision}; regenerate githash.h and rebuild")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("elf", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        for elf in args.elf:
            verify(elf, args.revision)
            print(f"PASS: {elf} embeds {args.revision}")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Build identity verification failed: {exc}\n")
