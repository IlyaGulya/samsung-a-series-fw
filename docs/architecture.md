# Architecture

The CPU is an **8051**. The disassembler confirms it: `MOV DPTR,#imm; MOVX A,@DPTR`
sequences, `LJMP` vectors, `SETB`/`CLR` bit access.

The service menu shows `Scaler-MCU: Novatek`.
So this is the system MCU inside a Novatek scaler (NT68xxx family).

## Code banks: 2 MiB through P1[4:0]

The 8051 code space is 64 KiB. The image is 2 MiB.
The code space is split into 32 banks of 64 KiB.
The bank number is in the low five bits of port P1:

```
bank = P1 & 0x1F
```

At reset the firmware keeps the high bits of P1 and clears the low bits:

```
0x011F  MOV A,P1
0x0121  ANL A,#E0h
0x0123  MOV P1,A
```

## Cross-bank call

A call uses a trampoline. The caller does this:

```
MOV  DPTR,#<target>      ; function address in the target bank
LCALL <trampoline for bank N>
```

The trampoline does this:

```
MOV A,P1                 ; current bank B
ANL A,#1Fh
SWAP A
RR A                     ; A = 8*B
PUSH ACC
MOV A,#2Ch
PUSH ACC                 ; return address = 0x2C{8*B}: restore stub
PUSH DPL
PUSH DPH                 ; target address
LJMP 0x2C00+8*N          ; switch stub for bank N
```

Each stub is 8 bytes at `0x2C00 + 8*N`:

```
ORL P1,#1Fh
ANL P1,#<mask for N>
RET                      ; jumps to target, now in bank N
```

When the function returns, its `RET` goes to the restore stub `0x2C{8*B}`.
That stub sets the original bank and returns to the caller.

All stubs are **byte-identical in every bank**.
Therefore the intermediate P1 values inside `ORL`/`ANL` are harmless.

The top of each bank (`0xFFF8`) holds a table.
The firmware reads it right after a bank switch (`MOV DPTR,#0FFF8h; MOVC A,@A+DPTR`).

## Memory

- IRAM: 256 bytes. Model all of them. The upper 128 bytes are not SFRs.
- XDATA: 64 KiB. `0xA000..0xBFFF` is working RAM. `0xF000..0xFFFF` is registers.

## Sleep loop

The end of boot is a normal power-save loop:

```
CLR IE.7                 ; all interrupts off
MOV DPTR,#0xF0D3
ORL A,#02h
MOVX @DPTR,A             ; request power-save
LCALL <wake routine>     ; reads 0xD511
JC  <wake path>          ; leaves only on carry
SJMP <wait again>
```

The wake routine (`bank 2, 0x9131`) sets bit `03h.5`, decodes `0xD511`,
and **always clears the bit** before `RET`. So `carry` is always 0.
The firmware cannot wake itself. A hardware line from the second subsystem
must wake it.

## Interrupts

Timer 0 runs with `TMOD=0x21`. The ISR is at vector `0x000B`, which jumps to `0x3000`.
The ISR updates time counters and the link.

The ISR ends with `RETI`. However, bank calls go through trampolines,
so some exits use plain `RET`. An emulator must clear the in-service latch on
`RET` too. Otherwise all interrupts stop after the first one.

## Not in this image

The firmware of the other parts: video block and T-Con, PD controller
(Cypress CCG3), USB hub (Realtek RTS5411). The strings and debug menus
mention them. Their code is not here.
