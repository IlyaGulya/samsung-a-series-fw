#!/bin/sh
# Fetch a pinned emu8051 core, apply the interrupt patch, build bankemu.
set -eu

SHA=5dc681275151c4a5d7b85ec9ff4ceb1b25abd5a8
REPO=https://github.com/jarikomppa/emu8051.git
DIR=emu/emu8051

if [ ! -f "$DIR/opcodes.c" ]; then
    git init -q "$DIR"
    git -C "$DIR" remote add origin "$REPO" 2>/dev/null || true
    git -C "$DIR" fetch -q --depth 1 origin "$SHA"
    git -C "$DIR" checkout -q FETCH_HEAD
    git -C "$DIR" log -1 --format='core: %h %ad' --date=short >&2
fi

python3 emu/apply_patch.py "$DIR"
cc -O2 -o emu/bankemu emu/bankemu.c \
    "$DIR/core.c" "$DIR/opcodes.c" "$DIR/disasm.c" -I"$DIR"
echo "built emu/bankemu"
