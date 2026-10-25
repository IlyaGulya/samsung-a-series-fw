# Debug console and MMIO

The firmware has a full debug console with ANSI colors.
It does **not** use the classic `SBUF` register.
It writes to registers mapped in XDATA.

## Registers

| Address | Direction | Purpose |
|---|---|---|
| `0xF072` | R | status: `bit0` ready from video block, `bit2`/`bit3` TX ready of two channels |
| `0xF073` | W | UART #0 data |
| `0xF036` | R | UART #1 status (`bit2` TX ready) |
| `0xF037` | W | UART #1 data |
| `0xF074` | R | data from video block |
| `0xBB00` | W | mailbox to video block |
| `0xFDF6` / `0xFDF7` | RW | command mailbox: request `0x41`, answer `0x81` |
| `0xF00A` | W | test register (writes `0x55`) |
| `0xD511` / `0xD510` | R | event/state code for the wake routine |
| `0xD5FD` / `0xD5FE` | RW | counters and status read by the timer ISR |

The transmit loop:

```
0x55A9  MOV  DPTR,#0xF072
0x55AC  MOVX A,@DPTR
0x55AD  JNB  ACC.2,0x55A9     ; wait for TX ready
0x55B0  MOV  DPTR,#0xF073
0x55B4  MOVX @DPTR,A
```

Speed: the console strings change `UART3` between `115200` and `9600`.
The working setting is **115200 8N1**, 3.3 V TTL.

## Boot output

```
sr = 0
WSR
InitCop Start
ShareMemory Size : 0x1800
InitCop End
[S/W Version] M-A8000SGZA-1014.0
[Panel Info] I/F : 3, Res : 7, Vendor : 2, PBA : 0, PanelType : 0
[D1][SystemHPDControlOff] [HPD] Set HPD Low(channel:0x2, force:1)
```

Messages start with `[0;33m` and end with `[0;m`. These are ANSI codes.

## Console menus

Strings from the image, in order:

```
[Formal debug Menu]     1..5: OSD/MDHDLR/LINKHDLR/SYNCHDLR state, virtual key
[Custom debug Menu]     1 BFI, 2/3 baudrate, 4..8 DP out mode, 9 check,
                        10 skip checksum flag, 11 verify
[SecLib debug Menu]     Common / EDID / Factory / OSD / Picture / Screen /
                        Sound / Source / T-Con
[SecLib Source debug]   change source, check state, control hotplug,
                        CCG3 (PD) and RTS5411 (USB hub) diagnostics
[Print level]           1..12: output filter (essential, color, osd, modeHandler,
                        inputTiming, appEVT, compatibility, etc, tcon, sensor,
                        source, common)
shell>                  help / reboot / factory / remote / exit
```

Input is locked. The unlock message is `BINGO!!! MAGICKEY!!!! unlock serial input.`
The unlock sequence is not stored as a string. Find it in the code.

## Service menu

Entry on monitors with a jog button:

1. Open the OSD.
2. Set `Brightness = 0` and `Contrast = 0`.
3. Hold the jog button (ENTER or SOURCE) for about 5 seconds.
4. The `SERVICE FUNCTION MENU` appears.

Fields in the menu (from the image strings):

```
Version, Monitor On Time, Panel Ch. No., On Time, Cycle, Type, Scaler-MCU,
Panel Info, Checksum, PixelShift, Country, HotPlug Time, Mute Time, USB PORT,
Signal Noise Lv, Project Name, FlashEraseTimes, Store Mode, ERP, Off Timer Def.
```

Do not change values in this menu if you only want to read the state.
