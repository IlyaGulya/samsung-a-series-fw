# Image format

Verified on two official releases:

| File | Version | Tag |
|---|---|---|
| `M-A8000SGZA-1013.0[EECE].Bin` | 1013.0 | `EECE` |
| `M-A8000SGZA-1014.0[288E].Bin` | 1014.0 | `288E` |

## Size and layout

```
2 097 152 bytes = 2 MiB = 32 pages of 65 536 bytes
```

Data ends near `0x1FFF89`. The rest is `0xFF`.

Every page starts with a real 8051 vector table:

```
+0x0000  02 01 1F   LJMP 0x011F     ; reset
+0x0003  02 20 00   LJMP 0x2000     ; EXT0
+0x000B  02 30 00   LJMP 0x3000     ; Timer0
+0x0013  02 10 00   LJMP 0x1000     ; EXT1
+0x0023  02 32 00   LJMP 0x3200     ; UART
```

Every page also holds the same runtime library at the same offset.
Example: `+0x5403` contains `Start Program` and `Current Partition(DF)…`.

The pages are code banks, not separate images. See `architecture.md`.
`Partition ONE` and `Partition TWO` in the log are the A/B update pair.

## Version string

ASCII, one occurrence, at offset `0xD5826`:

```
M-A8000SGZA-1014.0
```

## Checksum

**Sum of all 2 097 152 bytes, modulo 0x10000.**
The same value appears as four hex digits in the file name, in square brackets.

Check on both releases:

```
1013.0  sum(bytes) & 0xFFFF = 0xEECE   = [EECE]
1014.0  sum(bytes) & 0xFFFF = 0x288E   = [288E]
```

The image has no signature and no certificate.
`SecLib*` is the updater wrapper. It compares the version and, most likely,
this sum.

Rule: after any edit, raise the version and recompute the tag.
Otherwise the updater rejects the file. `tools/fwtool.py retag` does both.

## Models in one image

One build covers the whole family. A match-id table selects the model:

```
LS27A70  LS27A80  LS32A70  LS32A80
```

## Changes between releases

Diff `1013 → 1014`:

- about 203 bytes in **every** page: page header and version string;
- real code changes in two pages:
  - page 5, `0x058E0C–0x05D248` (17 469 bytes): power, `APPSetPowerOn`,
    auto source, DPMS;
  - page 6, `0x0666B5–0x068B43` (9 359 bytes): backlight, audio mute,
    update validation.

## Page map

From unique strings per page.

| Page | Content |
|---|---|
| 0 | mode handler: timings, `[MODE] #1..#7`, FRC checks |
| 1–2 | OSD DP source, audio, PIP, input selection |
| 3 | sync, DRR, `SyncState` |
| 4 | auto source switch, OSD timeouts |
| 5 | power: `APPSetPowerOn`, DPMS, link to video block |
| 6 | cable detect, USB hub RTS411S, update validation |
| 7 | DPCD, EDID, HPD |
| 11–12, 14, 18, 23, 30 | localized OSD strings |
| 13 | source, refresh rate, H/V position |
| 15 | FRC, HDCP |
| 16, 25 | OSD fonts and graphics |
| 17 | debug console and shell |
| 20 | flash access, USB update |
| 21 | EDID write |
| 24 | `MailBox_Handler` |
| 31 | LED driver |
| 22, 26, 27, 29 | empty slots |
