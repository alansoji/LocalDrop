# =============================================================================
#  LocalDrop  —  Makefile
# =============================================================================

APP        := localdrop
VERSION    := 1.0.0
PYTHON     := python3
PIP        := pip3

IS_EXT := $(shell $(PYTHON) -c "import os; print(os.path.exists('/usr/lib/python3.12/EXTERNALLY-MANAGED') or os.path.exists('/usr/lib/python3/EXTERNALLY-MANAGED'))" 2>/dev/null)

ifeq ($(IS_EXT),True)
    PIP_FLAGS += --break-system-packages
endif

PIP_FLAGS += --ignore-installed
# Install paths (Linux)
PREFIX       ?= /usr/local
BINDIR       := $(PREFIX)/bin
SHAREDIR     := $(PREFIX)/share/$(APP)
ICONDIR_256  := $(PREFIX)/share/icons/hicolor/256x256/apps
ICONDIR_SVG  := $(PREFIX)/share/icons/hicolor/scalable/apps
DESKTOPDIR   := $(PREFIX)/share/applications

# Launcher script (written to BINDIR)
LAUNCHER     := $(BINDIR)/$(APP)

# ─────────────────────────────────────────────
#  Default target
# ─────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  LocalDrop $(VERSION) — build & install targets"
	@echo ""
	@echo "  LINUX"
	@echo "  ─────"
	@echo "  make deps        Install Python dependencies (pip)"
	@echo "  make install     Install app + .desktop launcher (needs sudo)"
	@echo "  make uninstall   Remove installed files (needs sudo)"
	@echo "  make appdir      Populate AppDir for AppImage build"
	@echo "  make appimage    Build portable AppImage (needs appimage-builder)"
	@echo "  make run         Run directly from source (no install)"
	@echo ""
	@echo "  WINDOWS  (run these in PowerShell from repo root)"
	@echo "  ────────"
	@echo "  See windows/BUILD_WINDOWS.md for step-by-step instructions"
	@echo ""

# ─────────────────────────────────────────────
#  Dependencies
# ─────────────────────────────────────────────
.PHONY: deps
deps:
	@echo "→ Checking/Installing Python dependencies…"
	@# Try PyQt6 first, fallback to PyQt5 if needed
	$(PIP) install $(PIP_FLAGS) --upgrade pyqt6 "qrcode[pil]" Pillow || \
	$(PIP) install $(PIP_FLAGS) --upgrade pyqt5 "qrcode[pil]" Pillow
	@echo "✓ Dependencies satisfied"
# ─────────────────────────────────────────────
#  Run from source (no install)
# ─────────────────────────────────────────────
.PHONY: run
run: deps
	$(PYTHON) localdrop.py

# ─────────────────────────────────────────────
#  Install  (Linux — requires sudo)
# ─────────────────────────────────────────────
.PHONY: install
install: deps
	@echo "→ Installing LocalDrop to $(PREFIX)…"

	# App script
	install -Dm755 localdrop.py $(SHAREDIR)/localdrop.py

	# Launcher wrapper (so `localdrop` works from terminal / app menu)
	@echo "#!/usr/bin/env bash" > /tmp/localdrop-launcher
	@echo "exec $(PYTHON) $(SHAREDIR)/localdrop.py \"\$$@\"" >> /tmp/localdrop-launcher
	install -Dm755 /tmp/localdrop-launcher $(LAUNCHER)
	@rm /tmp/localdrop-launcher

	# Icons
	@if [ -f assets/icon.png ]; then \
		install -Dm644 assets/icon.png $(ICONDIR_256)/$(APP).png; \
		echo "  ✓ PNG icon installed"; \
	fi
	@if [ -f assets/icon.svg ]; then \
		install -Dm644 assets/icon.svg $(ICONDIR_SVG)/$(APP).svg; \
		echo "  ✓ SVG icon installed"; \
	fi

	# .desktop file
	install -Dm644 linux/localdrop.desktop $(DESKTOPDIR)/$(APP).desktop

	# Refresh icon cache + app menu
	@command -v update-desktop-database >/dev/null 2>&1 && \
		update-desktop-database $(DESKTOPDIR) || true
	@command -v gtk-update-icon-cache >/dev/null 2>&1 && \
		gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor || true
	@command -v xdg-icon-resource >/dev/null 2>&1 && \
		xdg-icon-resource forceupdate || true

	@echo ""
	@echo "✓ LocalDrop installed! Launch from your app menu or run: localdrop"

# ─────────────────────────────────────────────
#  Uninstall  (Linux — requires sudo)
# ─────────────────────────────────────────────
.PHONY: uninstall
uninstall:
	@echo "→ Removing LocalDrop…"
	rm -f  $(LAUNCHER)
	rm -rf $(SHAREDIR)
	rm -f  $(ICONDIR_256)/$(APP).png
	rm -f  $(ICONDIR_SVG)/$(APP).svg
	rm -f  $(DESKTOPDIR)/$(APP).desktop
	@command -v update-desktop-database >/dev/null 2>&1 && \
		update-desktop-database $(DESKTOPDIR) || true
	@echo "✓ LocalDrop uninstalled."

# ─────────────────────────────────────────────
#  AppImage — step 1: populate AppDir
# ─────────────────────────────────────────────
.PHONY: appdir
appdir:
	@echo "→ Building AppDir structure…"
	mkdir -p AppDir/usr/bin
	mkdir -p AppDir/usr/share/$(APP)
	mkdir -p AppDir/usr/share/applications
	mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps

	cp localdrop.py AppDir/usr/share/$(APP)/localdrop.py
	cp linux/localdrop.desktop AppDir/usr/share/applications/localdrop.desktop
	@if [ -f assets/icon.png ]; then \
		cp assets/icon.png AppDir/usr/share/icons/hicolor/256x256/apps/localdrop.png; \
		cp assets/icon.png AppDir/localdrop.png; \
	fi
	cp linux/localdrop.desktop AppDir/localdrop.desktop

	# AppImage entrypoint script
	@echo '#!/usr/bin/env bash' > AppDir/usr/bin/localdrop
	@echo 'exec python3 "$$APPDIR/usr/share/localdrop/localdrop.py" "$$@"' >> AppDir/usr/bin/localdrop
	chmod +x AppDir/usr/bin/localdrop

	@echo "✓ AppDir ready at ./AppDir"

# ─────────────────────────────────────────────
#  AppImage — step 2: build (needs appimage-builder)
# ─────────────────────────────────────────────
.PHONY: appimage
appimage: appdir
	@command -v appimage-builder >/dev/null 2>&1 || { \
		echo ""; \
		echo "  appimage-builder not found. Install it first:"; \
		echo "  pip install appimage-builder"; \
		echo ""; \
		exit 1; \
	}
	@echo "→ Building AppImage…"
	cd linux && appimage-builder --recipe AppImageBuilder.yml --skip-test
	@echo ""
	@echo "✓ AppImage built: linux/LocalDrop-$(VERSION)-x86_64.AppImage"

# ─────────────────────────────────────────────
#  Clean build artefacts
# ─────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf AppDir appimage-builder-cache dist build __pycache__ *.spec.bak
	find . -name "*.pyc" -delete
	@echo "✓ Clean"
