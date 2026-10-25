"""Patch the emu8051 core: clear the interrupt in-service latch on RET too.

This firmware sometimes leaves an ISR through a bank trampoline
(push DPH/DPL, then RET). The stock core clears the latch only on RETI.
Without this change, all interrupts stop after the first one.
"""
import pathlib
import sys

NEEDLE = "static uint8_t ret(struct em8051 *aCPU)\n{\n"
MARK = "in-service latch"
INSERT = (
    "    /* This firmware can leave an ISR through a bank trampoline "
    "(push DPH/DPL, RET).\n"
    "       Clear the in-service latch on RET as well as on RETI. */\n"
    "    aCPU->mInterruptActive = 0;\n"
)


def main(path: str) -> int:
    p = pathlib.Path(path) / "opcodes.c"
    s = p.read_text()
    if MARK in s:
        print("emu8051: already patched")
        return 0
    if NEEDLE not in s:
        print("emu8051: ret() not found - the core changed", file=sys.stderr)
        return 1
    p.write_text(s.replace(NEEDLE, NEEDLE + INSERT))
    print("emu8051: patch applied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "emu/emu8051"))
