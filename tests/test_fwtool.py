#!/usr/bin/env python3
"""Тесты fwtool на синтетическом образе (никаких файлов Samsung)."""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "fwtool.py"

SIZE = 2 * 1024 * 1024
VER_OFF = 0xD5826
VERSION = b"M-A8000SGZA-1014.0"


def make_image() -> bytes:
    data = bytearray(b"\xff" * SIZE)
    for page in range(32):
        base = page * 0x10000
        data[base:base + 3] = b"\x02\x01\x1f"          # LJMP 0x011F
        data[base + 0x100:base + 0x106] = b"DUALFW"
    data[VER_OFF:VER_OFF + len(VERSION)] = VERSION
    data[0x1000:0x1004] = b"LS32"                       # модель в таблице
    return bytes(data)


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True)


def main() -> int:
    img = make_image()
    expected_tag = sum(img) & 0xFFFF

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        good = tmp / f"M-A8000SGZA-1014.0[{expected_tag:04X}].Bin"
        bad = tmp / "M-A8000SGZA-1014.0[0000].Bin"
        good.write_bytes(img)
        bad.write_bytes(img)

        r = run("info", str(good))
        assert r.returncode == 0, r.stderr
        assert f"[{expected_tag:04X}]" in r.stdout, r.stdout
        assert "M-A8000SGZA-1014.0" in r.stdout
        assert "32 pages" in r.stdout

        r = run("verify", str(good))
        assert r.returncode == 0, r.stdout
        assert "OK" in r.stdout

        r = run("verify", str(bad))
        assert r.returncode == 1, r.stdout
        assert "MISMATCH" in r.stdout

        out = tmp / "patched.bin"
        r = run("retag", str(good), str(out), "M-A8000SGZA-1015.0")
        assert r.returncode == 0, r.stderr
        patched = out.read_bytes()
        assert patched[VER_OFF:VER_OFF + len(VERSION)] == b"M-A8000SGZA-1015.0"
        assert (sum(patched) & 0xFFFF) == expected_tag + 1

        r = run("retag", str(good), str(tmp / "x.bin"), "too-short")
        assert r.returncode == 1, "должен отказать при неверной длине версии"

    print("ok: fwtool info/verify/retag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
