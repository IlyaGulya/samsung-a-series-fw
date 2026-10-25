"""Патч ядра emu8051: снимать in-service latch прерывания и по RET.

Прошивка выходит из ISR через банковый трамплин (push DPH/DPL; RET), а оригинал
снимает флаг только по RETI — после первого прерывания все следующие блокируются.
"""
import pathlib
import sys

NEEDLE = "static uint8_t ret(struct em8051 *aCPU)\n{\n"
MARK = "in-service latch"
INSERT = (
    "    /* Эта прошивка выходит из ISR через банковый трамплин (push DPH/DPL; RET),\n"
    "       поэтому снимаем in-service latch и по RET, а не только по RETI. */\n"
    "    aCPU->mInterruptActive = 0;\n"
)


def main(path: str) -> int:
    p = pathlib.Path(path) / "opcodes.c"
    s = p.read_text()
    if MARK in s:
        print("emu8051: уже пропатчен")
        return 0
    if NEEDLE not in s:
        print("emu8051: не найден ret() — версия ядра изменилась", file=sys.stderr)
        return 1
    p.write_text(s.replace(NEEDLE, NEEDLE + INSERT))
    print("emu8051: patch applied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "emu/emu8051"))
