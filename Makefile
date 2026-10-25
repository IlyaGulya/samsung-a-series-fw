EMU_REPO := https://github.com/jarikomppa/emu8051.git
EMU_DIR  := emu/emu8051
CORE     := $(EMU_DIR)/core.c $(EMU_DIR)/opcodes.c $(EMU_DIR)/disasm.c

.PHONY: all emu fetch test clean

all: emu

$(EMU_DIR):
	git clone --depth 1 $(EMU_REPO) $(EMU_DIR)

fetch: $(EMU_DIR)

$(CORE): | $(EMU_DIR)

$(EMU_DIR)/.patched: $(EMU_DIR) emu/apply_patch.py
	python3 emu/apply_patch.py $(EMU_DIR)
	touch $@

emu: emu/bankemu

emu/bankemu: emu/bankemu.c $(CORE) $(EMU_DIR)/.patched
	cc -O2 -o $@ emu/bankemu.c $(CORE) -I$(EMU_DIR)

test:
	python3 tests/test_fwtool.py

clean:
	rm -f emu/bankemu
	rm -rf $(EMU_DIR)
