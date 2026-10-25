# Thin shim. Tasks live in mise.toml; this file only forwards to mise,
# for muscle memory and CI that expect make. mise must be installed.

MISE  ?= mise
TASKS := fw list emu test clean

.PHONY: all $(TASKS)

all: emu

$(TASKS):
	@command -v $(MISE) >/dev/null 2>&1 || { \
		echo "mise not found. Install it: brew install mise  (https://mise.jdx.dev)"; \
		exit 1; }
	@$(MISE) run $@
