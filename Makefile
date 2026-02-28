# Makefile for llm_thalamus (system install; core package)
#
# Installs Python sources under:
#   /usr/lib/llm_thalamus/src/...
# Provides canonical launcher:
#   /usr/bin/llm-thalamus
#
# Installs runtime resources (config template, prompts) under:
#   /usr/share/llm-thalamus/...
#
# IMPORTANT:
# - No graphics/icons are installed by this package.
#   Those are provided by separate theme packages.
# - Uninstall removes only files owned by this package.

PREFIX      ?= /usr
BINDIR      ?= $(PREFIX)/bin
LIBDIR      ?= $(PREFIX)/lib/llm_thalamus
SHAREDIR    ?= $(PREFIX)/share/llm-thalamus
DESKTOPDIR  ?= $(PREFIX)/share/applications

PYTHON      ?= python3

APPNAME     := llm-thalamus
WRAPPER     := $(BINDIR)/$(APPNAME)

# Source roots (repo-relative)
SRC_DIR         := src
RESOURCES_DIR   := resources
PROMPTS_DIR     := $(RESOURCES_DIR)/prompts
CONFIG_TEMPLATE := $(RESOURCES_DIR)/config/config.json
DESKTOP_FILE    := llm_thalamus.desktop

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
	echo "==> Installing config template to $(DESTDIR)$(SHAREDIR)/config/config.json"; \
	install -Dm0644 "$(CONFIG_TEMPLATE)" "$(DESTDIR)$(SHAREDIR)/config/config.json"; \
	\
	echo "==> Installing prompts to $(DESTDIR)$(SHAREDIR)/prompts"; \
	if [ -d "$(PROMPTS_DIR)" ]; then \
		mkdir -p "$(DESTDIR)$(SHAREDIR)/prompts"; \
		install -m0644 "$(PROMPTS_DIR)"/*.txt "$(DESTDIR)$(SHAREDIR)/prompts/" 2>/dev/null || true; \
	fi; \
	\
	echo "==> Installing desktop file"; \
	install -Dm0644 "$(DESKTOP_FILE)" "$(DESTDIR)$(DESKTOPDIR)/llm_thalamus.desktop"; \
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
	echo "==> Removing installed library dir"; \
	rm -rf "$(DESTDIR)$(LIBDIR)"; \
	\
	echo "==> Removing installed config/prompts (leave theme graphics untouched)"; \
	rm -f "$(DESTDIR)$(SHAREDIR)/config/config.json"; \
	rm -f "$(DESTDIR)$(SHAREDIR)/prompts/"*.txt 2>/dev/null || true; \
	-rmdir "$(DESTDIR)$(SHAREDIR)/prompts" 2>/dev/null || true; \
	-rmdir "$(DESTDIR)$(SHAREDIR)/config" 2>/dev/null || true; \
	-rmdir "$(DESTDIR)$(SHAREDIR)" 2>/dev/null || true; \
	\
	echo "==> Done."

.PHONY: all install uninstall