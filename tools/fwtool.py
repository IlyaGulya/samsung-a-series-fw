#!/usr/bin/env python3
"""Samsung A-series monitor firmware (FALCON / M-A8000SGZA) container tool.

Format, verified on releases 1013.0 and 1014.0:

  * 2 MiB, 32 pages of 64 KiB, each page starts with an 8051 vector table;
  * the version string `M-A8000SGZA-XXXX.Y` sits at offset 0xD5826;
  * checksum = sum of all bytes modulo 0x10000, also the [XXXX] tag in the name.

Parsing is explicit: fixed offsets, character checks and str.split, no regular
expressions. Each parser returns None when the input does not match.

Usage:
  fwtool.py info   <bin>                  show size, version, tag, models, pages
  fwtool.py verify <bin>                  compare the name tag with the checksum
  fwtool.py retag  <src> <dst> [version]  write a copy with a new version and tag
"""
import sys
from pathlib import Path

PAGE = 0x10000
SIZE = 32 * PAGE
VERSION_OFFSET = 0xD5826
VERSION_SCAN = 32          # maximum printable run to read at a candidate offset
SLOT_MARKER = b"DUALFW"
MODEL_PREFIX = b"LS"
MODEL_LEN = 7
VENDOR_PREFIX = "M-A"


def tag(data: bytes) -> int:
    return sum(data) & 0xFFFF


def is_version(text: str) -> bool:
    """True for M-A8000SGZA-1014.0 style strings."""
    if not text.startswith(VENDOR_PREFIX) or len(text) < 12:
        return False
    head, sep, tail = text.rpartition("-")
    if not sep:
        return False
    if not all(c.isalnum() for c in head[2:]):
        return False
    major, sep, minor = tail.partition(".")
    return bool(sep) and major.isdigit() and minor.isdigit()


def printable_run(data: bytes, start: int) -> str:
    """Decode the run of printable ASCII that starts at start."""
    end = start
    limit = min(start + VERSION_SCAN, len(data))
    while end < limit and 0x20 <= data[end] < 0x7F:
        end += 1
    return data[start:end].decode("ascii")


def read_version(data: bytes):
    """Return (version, offset) or (None, -1).

    Tries the known offset first, then scans for the vendor prefix so that the
    tool still reports something if a future build moves the string.
    """
    text = printable_run(data, VERSION_OFFSET)
    if is_version(text):
        return text, VERSION_OFFSET

    start = 0
    while True:
        start = data.find(b"M-A", start)
        if start < 0:
            return None, -1
        text = printable_run(data, start)
        if is_version(text):
            return text, start
        start += 1


def is_model(text: bytes) -> bool:
    return (len(text) == MODEL_LEN
            and text[:2] == MODEL_PREFIX
            and text[2:4].isdigit()
            and text[4:5] == b"A"
            and text[5:7].isdigit())


def iter_models(data: bytes):
    seen, found, pos = set(), [], 0
    while True:
        pos = data.find(MODEL_PREFIX, pos)
        if pos < 0:
            break
        chunk = data[pos:pos + MODEL_LEN]
        if is_model(chunk):
            text = chunk.decode("ascii")
            if text not in seen:
                seen.add(text)
                found.append(text)
        pos += 1
    return sorted(found)


def find_markers(data: bytes):
    out, pos = [], 0
    while True:
        pos = data.find(SLOT_MARKER, pos)
        if pos < 0:
            return out
        out.append(pos)
        pos += 1


def parse_tag(name: str):
    """Return the integer tag from a [XXXX] part of a file name, or None."""
    start = name.rfind("[")
    if start < 0:
        return None
    end = name.find("]", start + 1)
    if end < 0 or end - start != 5:
        return None
    try:
        return int(name[start + 1:end], 16)
    except ValueError:
        return None


def cmd_info(path: str) -> int:
    data = Path(path).read_bytes()
    version, offset = read_version(data)
    models = iter_models(data)
    markers = find_markers(data)
    used = len(data.rstrip(b"\xff"))

    print(f"file        : {path}")
    print(f"size        : {len(data)} (0x{len(data):X}), {len(data) // PAGE} pages of 64 KiB")
    print(f"version     : {version + f'  @ 0x{offset:X}' if version else '<not found>'}")
    print(f"checksum tag: [{tag(data):04X}]")
    print(f"models      : {', '.join(models) if models else '<none>'}")
    print(f"data up to  : 0x{used:X}")
    print(f"slot marks  : {len(markers)} found at "
          f"{', '.join(hex(m) for m in markers[:4])}{' ...' if len(markers) > 4 else ''}")
    if len(data) != SIZE:
        print(f"warning     : expected {SIZE} bytes", file=sys.stderr)
        return 1
    return 0


def cmd_verify(path: str) -> int:
    p = Path(path)
    data = p.read_bytes()
    computed = tag(data)
    parsed = parse_tag(p.name)
    if parsed is None:
        print(f"{p.name}: no [XXXX] tag in the file name; computed [{computed:04X}]")
        return 1
    print(f"{p.name}: tag {parsed:04X} vs computed {computed:04X} -> "
          f"{'OK' if parsed == computed else 'MISMATCH'}")
    return 0 if parsed == computed else 1


def cmd_retag(src: str, dst: str, new_version: str | None = None) -> int:
    data = bytearray(Path(src).read_bytes())
    if new_version:
        version, offset = read_version(data)
        if not version:
            print("version string not found", file=sys.stderr)
            return 1
        if not is_version(new_version):
            print(f"not a valid version string: {new_version}", file=sys.stderr)
            return 1
        if len(new_version) != len(version):
            print(f"version must be exactly {len(version)} bytes "
                  f"(got {len(new_version)})", file=sys.stderr)
            return 1
        data[offset:offset + len(version)] = new_version.encode("ascii")
    Path(dst).write_bytes(data)
    version, _ = read_version(bytes(data))
    print(f"wrote {dst}  version {version}  tag [{tag(bytes(data)):04X}]")
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
