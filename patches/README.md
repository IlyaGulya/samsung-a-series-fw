# Example patches

This directory describes changes only: offset and bytes.
No firmware images are published.

After any edit, rebuild the file name and the checksum:

```bash
python3 tools/fwtool.py retag original.Bin patched.Bin M-A8000SGZA-1015.0
```

The updater, based on strings in the image, compares the version and the sum.
The tag must match the contents. The version must be equal or higher than the
current one.

---

## 0001: skip the page 27 check

This is the only known check that fails in the emulator, because shared memory
is missing. On real hardware the check passes. So this patch is useful for
emulation only.

```
offset : 27 * 0x10000 + 0x1B3F = 0x1B1B3F
before : 60 03        JZ  +3
after  : 80 03        SJMP +3      (the check always passes)
effect : tag 288E -> 28AE
```

Context:

```
0x1B39  SWAP A
0x1B3A  RRC  A
0x1B3B  ANL  A,#7
0x1B3D  XRL  A,#5        ; expects 5
0x1B3F  JZ   +3          ; patched
0x1B41  LJMP 0x1E73      ; otherwise: reboot
```

The byte under test must have bits 7..5 equal to `101`, that is, a value in
`0xA0..0xBF`.

One-line patch:

```bash
python3 - <<'PY'
import pathlib
d = bytearray(pathlib.Path("original.Bin").read_bytes())
assert d[0x1B1B3F:0x1B1B41] == bytes.fromhex("6003")
d[0x1B1B3F:0x1B1B41] = bytes.fromhex("8003")
pathlib.Path("patched.Bin").write_bytes(d)
print("tag %04X" % (sum(d) & 0xFFFF))
PY
```
