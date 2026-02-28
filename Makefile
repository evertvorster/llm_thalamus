# Makefile for llm_thalamus (system install)
#
# Installs the repo's Python sources under:
#   /usr/lib/llm_thalamus/src/...
# and provides a canonical launcher:
#   /usr/bin/llm-thalamus
#
# Installs runtime resources (config template, prompts, graphics) under:
#   /usr/share/llm-thalamus/...
#
# Notes:
# - Honors DESTDIR and PREFIX.
# - Does NOT install anything into /etc (per current config policy).
# - Canonical entry point is `llm_thalamus` (module: src.llm_thalamus).

PREFIX      ?= /usr
BINDIR      ?= $(PREFIX)/bin
LIBDIR      ?= $(PREFIX)/lib/llm_thalamus
SHAREDIR    ?= $(PREFIX)/share/llm-thalamus
DESKTOPDIR  ?= $(PREFIX)/share/applications
ICONDIR     ?= $(PREFIX)/share/icons/hicolor/scalable/apps

PYTHON      ?= python3

APPNAME     := llm-thalamus
WRAPPER     := $(BINDIR)/$(APPNAME)

# Source roots (repo-relative)
SRC_DIR         := src
RESOURCES_DIR   := resources
PROMPTS_DIR     := $(RESOURCES_DIR)/prompts
GRAPHICS_DIR    := $(RESOURCES_DIR)/graphics
CONFIG_TEMPLATE := $(RESOURCES_DIR)/config/config.json
DESKTOP_FILE    := llm_thalamus.desktop
ICON_FILE       := $(GRAPHICS_DIR)/llm_thalamus.svg

all:
	@echo "Nothing to build (pure Python). Use 'make install'."

install:
	@set -eu; \
	echo "==> Installing Python sources to $(DESTDIR)$(LIBDIR)/src"; \
	mkdir -p "$(DESTDIR)$(LIBDIR)"; \
	cp -a "$(SRC_DIR)" "$(DESTDIR)$(LIBDIR)/"; \
	find "$(DESTDIR)$(LIBDIR)/src" -type d -name "__pycache__" -prune -exec rm -rf {} +; \
	find "$(DESTDIR)$(LIBDIR)/src" -type f -name "*.py[co]" -delete; \
	\
	echo "==> Installing resources to $(DESTDIR)$(SHAREDIR)"; \
	install -Dm0644 "$(CONFIG_TEMPLATE)" "$(DESTDIR)$(SHAREDIR)/config/config.json"; \
	if [ -d "$(PROMPTS_DIR)" ]; then \
		mkdir -p "$(DESTDIR)$(SHAREDIR)/prompts"; \
		install -m0644 "$(PROMPTS_DIR)"/*.txt "$(DESTDIR)$(SHAREDIR)/prompts/" 2>/dev/null || true; \
	fi; \
	if [ -d "$(GRAPHICS_DIR)" ]; then \
		mkdir -p "$(DESTDIR)$(SHAREDIR)/graphics"; \
		cp -a "$(GRAPHICS_DIR)/." "$(DESTDIR)$(SHAREDIR)/graphics/"; \
	fi; \
	\
	echo "==> Installing desktop file"; \
	install -Dm0644 "$(DESKTOP_FILE)" "$(DESTDIR)$(DESKTOPDIR)/llm_thalamus.desktop"; \
	\
	echo "==> Installing icon"; \
	if [ -f "$(ICON_FILE)" ]; then \
		install -Dm0644 "$(ICON_FILE)" "$(DESTDIR)$(ICONDIR)/llm_thalamus.svg"; \
	fi; \
	\
	echo "==> Installing launcher $(DESTDIR)$(WRAPPER)"; \
	mkdir -p "$(DESTDIR)$(BINDIR)"; \
	install -Dm0755 /dev/null "$(DESTDIR)$(WRAPPER)"; \
	printf '%s\n' \
'#!/bin/sh' \
'set -eu' \
'' \
'# Installed code lives under /usr/lib/llm_thalamus/src' \
'# Ensure Python can import the in-tree "src" package.' \
'export PYTHONPATH="$(LIBDIR):$${PYTHONPATH:-}"' \
'' \
'# Run the canonical module entry point' \
'exec "$(PYTHON)" -m src.llm_thalamus "$$@"' \
	> "$(DESTDIR)$(WRAPPER)"; \
	chmod 0755 "$(DESTDIR)$(WRAPPER)"; \
	\
	echo "==> Done."

uninstall:
	@set -eu; \
	echo "==> Removing launcher"; \
	rm -f "$(DESTDIR)$(WRAPPER)"; \
	\
	echo "==> Removing desktop file"; \
	rm -f "$(DESTDIR)$(DESKTOPDIR)/llm_thalamus.desktop"; \
	\
	echo "==> Removing icon"; \
	rm -f "$(DESTDIR)$(ICONDIR)/llm_thalamus.svg"; \
	\
	echo "==> Removing installed library dir"; \
	rm -rf "$(DESTDIR)$(LIBDIR)"; \
	\
	echo "==> Removing installed share dir"; \
	rm -rf "$(DESTDIR)$(SHAREDIR)"; \
	\
	echo "==> Done."

.PHONY: all install uninstall