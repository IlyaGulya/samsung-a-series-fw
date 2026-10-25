# Samsung A-series monitor firmware toolkit

Tools and notes for the firmware of Samsung A70/A80 monitors
(`LS27A70*`, `LS27A80*`, `LS32A70*`, `LS32A80*`).
Internal platform name: **FALCON**. Image name: `M-A8000SGZA`.

This repository **contains no firmware files**.
`tools/fetch_fw.py` downloads the image from Samsung's own server; nothing is
redistributed here.

Requirements: [mise](https://mise.jdx.dev), Python 3.10+, a C compiler, git.
All commands run through `mise run <task>`; there is no Makefile.

## What you can do

- Download the official image and check its checksum.
- Read the image layout.
- Repack a modified image with a correct version and checksum.
- Run the image in an 8051 emulator.
- Read the debug console over UART.

## Quick start

```bash
# 1. Get the image. Finds a region page that publishes the catalogue, takes the
#    newest firmware, downloads it from Samsung, and checks the checksum.
mise run fw
#    Another model, and a listing:
MODEL=LS32A700NWCXXK mise run fw
mise run list

#    To list what is available for a model:
python3 tools/fetch_fw.py --page <url> --list

# 2. Check any image you already have
python3 tools/fwtool.py info   "fw/M-A8000SGZA-1014.0[288E].Bin"
python3 tools/fwtool.py verify "fw/M-A8000SGZA-1014.0[288E].Bin"

# 3. Build and run the emulator (fetches the pinned 8051 core)
mise run emu
PEER=1 STUBS="0xD511=0x17,0xF012=0x01" \
    ./emu/bankemu "fw/M-A8000SGZA-1014.0[288E].Bin" 40000000

# 4. Run the tests
mise run test
```

## What the firmware is

It is the system firmware of the **scaler**. The service menu shows
`Scaler-MCU: Novatek`, and the CPU core is an 8051.
The firmware controls power sequencing, HPD, the panel, EDID, keys, the USB hub,
updates, and the link to the video block.

It does **not** draw the picture. Scaling and OSD run in another subsystem.
That firmware is not part of this file.

## Tools and tasks

| Task | Purpose |
|---|---|
| `mise run fw` | download the official image and verify it |
| `mise run list` | list firmware versions for a model |
| `mise run emu` | fetch the pinned 8051 core and build the emulator |
| `mise run test` | run the tool tests |
| `mise run clean` | remove build output, the core clone and images |

| Script | Purpose |
|---|---|
| `tools/fetch_fw.py` | region discovery, download, checksum check |
| `tools/fwtool.py` | inspect, verify, repack (version and checksum) |
| `tools/build_emu.sh` | pinned core checkout, patch, compile |
| `emu/bankemu.c` | run the image in an 8051 emulator |

## Documents

| File | Content |
|---|---|
| [docs/format.md](docs/format.md) | image layout, version string, checksum, A/B partitions |
| [docs/architecture.md](docs/architecture.md) | 8051, code banks, cross-bank calls, sleep loop |
| [docs/debug-console.md](docs/debug-console.md) | UART registers, console menus, service menu |
| [docs/emulation.md](docs/emulation.md) | emulator: what works, what is missing, options |
| [patches/](patches/) | example patch: offset and bytes |

## Status

- Format and checksum are verified on two releases (`1013`, `1014`).
- In the emulator the firmware completes init, reads its version and panel info,
  drives HPD, and enters its normal sleep state.
- The firmware does not reach OSD or input switching. That part needs the second
  subsystem, which is not in the image.

## Safety

Any change to the image puts the monitor at risk. Before you flash:

1. Record the state from the service menu: `Version`, `Checksum`, `Monitor On Time`.
2. Make sure you can recover: A/B partitions, then a second flash over SERVICE.
3. Keep an SPI programmer (CH341A with a SOIC-8 clip) as the last option.

Do not commit or publish the vendor `.Bin` file. It is copyrighted.

## Credits and license

- 8051 CPU core: [jarikomppa/emu8051](https://github.com/jarikomppa/emu8051) (MIT).
  The build fetches a pinned commit and applies one small patch
  (`emu/patches/0001-interrupt-latch-on-ret.patch`).
- Everything else in this repository: MIT, see [LICENSE](LICENSE).
- The notes describe a format for research. Samsung trademarks belong to Samsung.
