# Emulation

## Why not QEMU

QEMU has no 8051/MCS-51 target. It has no CPU model and no machine for it.
The closest existing target is `target/avr`: 137 KB of C plus 29 KB of machine code.
A new target would take 4 to 8 weeks for the core, and as long again for peripherals.
The cost is high. The gain is zero for this task: the value is in the machine model,
not in the CPU core.

## What we use

[jarikomppa/emu8051](https://github.com/jarikomppa/emu8051): MIT, ANSI C,
about 4 thousand lines, full 8051/8052 instruction set, timers, interrupts,
and callbacks for SFR and XDATA.

`bankemu.c` adds what the reference emulator does not have:

- **32 code banks** selected by `P1[4:0]` (the `mCodeMem` pointer moves to the bank);
- **full 256-byte IRAM** (`mUpperData` is required, or the upper 128 bytes alias SFRs);
- **MMIO read-back**: a register read returns the last written value, not a constant;
- **second subsystem model**: mailbox `0xFDF6/0xFDF7` (request `0x41` → answer `0x81`);
- **pty for UART**: the monitor log goes to a terminal;
- **event injection** by opcode number.

## Build and run

```bash
./bin/mise run emu             # fetches the pinned core, applies the patch, builds
PEER=1 STUBS="0xD511=0x17,0xF012=0x01" ./emu/bankemu fw/<image>.Bin 40000000
```

Options:

| Variable | Meaning |
|---|---|
| `STUBS="0xADDR=0xVAL,…"` | forced values for MMIO registers |
| `PEER=1` | enable the second subsystem model (mailbox) |
| `PTY=1` | UART to a pty; the path goes to stderr |
| `EVENTS="5000000:0xD511=0xFF;9000000:reset"` | events by opcode number |
| `WATCH=0xADDR` | trace the first 12 accesses to an address, with PC and bank |
| `XTRACE=1` | map of the `0xA000..0xBFFF` window |
| `SEEDR="0xADDR:0xLEN:0xVAL"` | substitute on read while the cell is zero |
| `HALT_ERASED=1` | stop when PC enters unprogrammed flash |
| `GAP=1` | instruction histogram for a time window |

## What works

- The firmware starts at the reset vector, switches banks, and services the timer.
- It completes `InitCop`, reads its version and panel info from flash, and drives HPD.
- It writes its log to UART.
- It enters the normal sleep state, as on hardware without a signal.

Measured firmware time (1 tick = 1 machine cycle; at 12 MHz, 1 µs):

```
0.0 ms    sr = 0
30.8 ms   InitCop Start
441.1 ms  ShareMemory Size : 0x1800     (clear 64 KiB of XRAM)
442.2 ms  InitCop End
452.7 ms  [S/W Version] M-A8000SGZA-1014.0
490.1 ms  [Panel Info] …
```

Init takes about half a second. Multi-second power-on delays come from hardware:
panel power, HDMI/HDCP handshake. They do not come from this code.

## What is missing

- The contents of shared memory (`ShareMemory Size : 0x1800`), which the second
  subsystem fills.
- The message types of `MailBox_Handler` (page 24).
- The meaning of `0xD511` and `0xD510` for wake-up.
- A model of the video block (OSD, panel timings). Its firmware is not in this image.

As a result, after `[HPD] Set HPD Low` the model runs into unprogrammed flash:
the firmware waits for an answer that the emulator cannot give.

## Emulator patch

`emu/patches/0001-interrupt-latch-on-ret.patch` clears the in-service latch on
`RET`. Without it, interrupts stop after the first one, because this firmware
sometimes leaves an ISR through a bank trampoline instead of `RETI`.
`./bin/mise run emu` applies the patch automatically to the pinned upstream commit.
