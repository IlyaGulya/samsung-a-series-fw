EMU_REPO := https://github.com/jarikomppa/emu8051.git
EMU_DIR  := emu/emu8051
# pinned commit: upstream is dormant, but master is not a guarantee
EMU_SHA  := 5dc681275151c4a5d7b85ec9ff4ceb1b25abd5a8
CORE     := $(EMU_DIR)/core.c $(EMU_DIR)/opcodes.c $(EMU_DIR)/disasm.c

.PHONY: all emu fetch fw test clean

all: emu

$(EMU_DIR):
	git init -q $(EMU_DIR)
	git -C $(EMU_DIR) remote add origin $(EMU_REPO)
	git -C $(EMU_DIR) fetch -q --depth 1 origin $(EMU_SHA)
	git -C $(EMU_DIR) checkout -q FETCH_HEAD
	@git -C $(EMU_DIR) log -1 --format="emu8051 @ %h %ad" --date=short

# Use your own model page here.
MODEL_PAGE ?= https://www.samsung.com/hk_en/support/model/LS32A700NWCXXK/

fw:
	python3 tools/fetch_fw.py --page "$(MODEL_PAGE)" -o fw

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
