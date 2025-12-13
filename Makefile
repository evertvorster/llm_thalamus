# Simple Makefile for llm-thalamus
# Installs Python sources into /usr/lib/llm_thalamus and
# creates symlinks in /usr/bin for the main entry points.

PREFIX     ?= /usr
BINDIR     ?= $(PREFIX)/bin
LIBDIR     ?= $(PREFIX)/lib/llm_thalamus
SHAREDIR   ?= $(PREFIX)/share/llm-thalamus
CONFDIR    ?= /etc/llm-thalamus
DESKTOPDIR ?= $(PREFIX)/share/applications

PYTHON     ?= python

# All Python modules we ship (excluding tests and experimental stuff)
PY_FILES = \
	llm_thalamus.py \
	llm_thalamus_ui.py \
	ui_chat_renderer.py \
	ui_config_dialog.py \
	memory_retrieval.py \
	memory_ingest.py \
	memory_retrieve_documents.py \
	memory_storage.py \
	retrieve_ingested_file.py \
	thalamus_worker.py \
	tool_registry.py \
	spaces_manager.py \
	paths.py \
	$(wildcard llm_thalamus_internal/*.py) \
	$(wildcard ui/*.py)

GRAPHICS_FILES = \
	graphics/llm_thalamus.svg \
	graphics/llm.jpg \
	graphics/thalamus.jpg \
	graphics/inactive.jpg

all:
	@echo "Nothing to build (pure Python). Use 'make install'."

install:
	# Code
	mkdir -p "$(DESTDIR)$(LIBDIR)"
	for f in $(PY_FILES); do \
		install -m 0644 "$$f" "$(DESTDIR)$(LIBDIR)/"; \
	done

	# Make the main modules executable (shebang already present)
	chmod 0755 "$(DESTDIR)$(LIBDIR)/llm_thalamus.py"
	chmod 0755 "$(DESTDIR)$(LIBDIR)/llm_thalamus_ui.py"

	# Entry point symlinks
	mkdir -p "$(DESTDIR)$(BINDIR)"
	ln -sf "$(LIBDIR)/llm_thalamus.py"    "$(DESTDIR)$(BINDIR)/llm-thalamus"
	ln -sf "$(LIBDIR)/llm_thalamus_ui.py" "$(DESTDIR)$(BINDIR)/llm-thalamus-ui"

	# Config template (system-wide)
	mkdir -p "$(DESTDIR)$(CONFDIR)"
	install -m 0644 "config/config.json" \
		"$(DESTDIR)$(CONFDIR)/config.json"

	# Install all call/prompt template files (every .txt in config/)
	mkdir -p "$(DESTDIR)$(LIBDIR)/config"
	for f in config/*.txt; do \
		install -m 0644 "$$f" "$(DESTDIR)$(LIBDIR)/config/"; \
	done

	# Graphics (for icons / glowing brain)
	mkdir -p "$(DESTDIR)$(SHAREDIR)/graphics"
	for f in $(GRAPHICS_FILES); do \
		install -m 0644 "$$f" "$(DESTDIR)$(SHAREDIR)/graphics/"; \
	done

	# Desktop launcher
	install -Dm0644 llm_thalamus.desktop \
		"$(DESTDIR)$(DESKTOPDIR)/llm_thalamus.desktop"

uninstall:
	# Remove symlinks
	rm -f "$(DESTDIR)$(BINDIR)/llm-thalamus"
	rm -f "$(DESTDIR)$(BINDIR)/llm-thalamus-ui"

	# Remove library dir
	rm -rf "$(DESTDIR)$(LIBDIR)"

	# Remove shared data
	rm -rf "$(DESTDIR)$(SHAREDIR)"

	# Remove desktop file
	rm -f "$(DESTDIR)$(DESKTOPDIR)/llm_thalamus.desktop"

	# Do NOT remove user configs automatically,
	# but remove system template:
	rm -f "$(DESTDIR)$(CONFDIR)/config.json"
	# (Optionally remove empty dir)
	-rmdir "$(DESTDIR)$(CONFDIR)" 2>/dev/null || true

.PHONY: all install uninstall
