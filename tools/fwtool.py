#!/usr/bin/env python3
"""Samsung A-series monitor firmware (FALCON / M-A8000SGZA) container tool.

Format, verified on releases 1013.0 and 1014.0:

  * 2 MiB, 32 pages of 64 KiB, each page starts with an 8051 vector table;
  * the version string `M-A8000SGZA-XXXX.Y` appears once, at offset 0xD5826;
  * checksum = sum of all bytes modulo 0x10000, also the [XXXX] tag in the name.

Usage:
  fwtool.py info   <bin>                    show size, version, tag, models, pages
  fwtool.py verify <bin>                    compare the name tag with the checksum
  fwtool.py retag  <src> <dst> [version]    write a copy with a new version and tag
"""
import re
import sys
from pathlib import Path

PAGE = 0x10000
SIZE = 32 * PAGE
VER_RE = re.compile(rb"M-A[0-9A-Z]{6,}-\d+\.\d+")
MODEL_RE = re.compile(rb"LS\d\dA\d\d")
TAG_RE = re.compile(r"\[([0-9A-Fa-f]{4})\]")


def tag(data: bytes) -> int:
    return sum(data) & 0xFFFF


def version(data: bytes):
    m = VER_RE.search(data)
    return (m.group().decode(), m.start()) if m else (None, -1)


def cmd_info(path: str) -> int:
    data = Path(path).read_bytes()
    ver, off = version(data)
    models = sorted({m.group().decode() for m in MODEL_RE.finditer(data)})
    markers = [m.start() for m in re.finditer(rb"DUALFW", data)]
    used = len(data.rstrip(b"\xff"))

    print(f"file        : {path}")
    print(f"size        : {len(data)} (0x{len(data):X}), {len(data) // PAGE} pages of 64 KiB")
    print(f"version     : {ver + f'  @ 0x{off:X}' if ver else '<not found>'}")
    print(f"checksum tag: [{tag(data):04X}]")
    print(f"models      : {', '.join(models) if models else '<none>'}")
    print(f"data up to  : 0x{used:X}")
    print(f"'DUALFW' at : {', '.join(hex(m) for m in markers[:4])}"
          f"{' ...' if len(markers) > 4 else ''} ({len(markers)} total)")
    if len(data) != SIZE:
        print(f"warning     : expected {SIZE} bytes", file=sys.stderr)
        return 1
    return 0


def cmd_verify(path: str) -> int:
    p = Path(path)
    data = p.read_bytes()
    computed = tag(data)
    m = TAG_RE.search(p.name)
    if not m:
        print(f"{p.name}: no [TAG] in the file name; computed [{computed:04X}]")
        return 1
    ok = int(m.group(1), 16) == computed
    print(f"{p.name}: tag {m.group(1).upper()} vs computed {computed:04X} -> "
          f"{'OK' if ok else 'MISMATCH'}")
    return 0 if ok else 1


def cmd_retag(src: str, dst: str, new_version: str | None = None) -> int:
    data = bytearray(Path(src).read_bytes())
    if new_version:
        m = VER_RE.search(data)
        if not m:
            print("version string not found", file=sys.stderr)
            return 1
        if len(new_version) != len(m.group()):
            print(f"version must be exactly {len(m.group())} bytes "
                  f"(got {len(new_version)})", file=sys.stderr)
            return 1
        data[m.start():m.end()] = new_version.encode()
    Path(dst).write_bytes(data)
    ver, _ = version(bytes(data))
    print(f"wrote {dst}  version {ver}  tag [{tag(bytes(data)):04X}]")
    return 0


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "info":
        return cmd_info(argv[2])
    if cmd == "verify":
        return cmd_verify(argv[2])
    if cmd == "retag":
        return cmd_retag(*argv[2:5])
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
