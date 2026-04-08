# Building LocalDrop for Windows

This guide produces **`LocalDrop-Setup.exe`** — a proper Windows installer with:
- Start Menu shortcut
- Desktop shortcut
- Add/Remove Programs entry
- Automatic Windows Firewall rule for port 5005

---

## Prerequisites

Install these once on your Windows machine:

| Tool | Download |
|------|----------|
| Python 3.10+ (64-bit) | https://python.org — ✅ check **"Add to PATH"** |
| PyInstaller | `pip install pyinstaller` |
| NSIS 3.x | https://nsis.sourceforge.io/Download |

Then install app dependencies:
```powershell
pip install pyqt6 "qrcode[pil]" Pillow
```

---

## Step 1 — Add a placeholder icon (or use your own)

If you don't have `assets/icon.ico` yet, generate one from any 256×256 PNG:

```powershell
pip install Pillow
python -c "
from PIL import Image
img = Image.new('RGBA', (256,256), color=(124,109,250,255))
img.save('assets/icon.png')
"
# Then convert PNG -> ICO (use https://convertio.co or any tool)
# Save result as assets/icon.ico
```

> The repo ships a placeholder `assets/icon.png`. Convert it to `.ico` before building.

---

## Step 2 — Build the single-file EXE

Run from the **repo root** in PowerShell:

```powershell
pyinstaller windows/localdrop.spec
```

This produces: `dist/LocalDrop.exe`

**Troubleshooting:**
- If PyQt6 import fails, install PyQt5 instead: `pip install pyqt5`
- If `cgi` module is missing (Python 3.13+), the spec's `hiddenimports` handles it
- `--upx-dir` can shrink the binary further if UPX is on PATH

---

## Step 3 — Build the installer

Open **NSIS** → *Compile NSI scripts* → open `windows/installer.nsi`

Or from command line (if `makensis` is on PATH):

```powershell
cd windows
makensis installer.nsi
```

This produces: `windows/LocalDrop-Setup.exe`

---

## Step 4 — Test the installer

```powershell
.\windows\LocalDrop-Setup.exe
```

It will:
1. Ask for install directory (default: `C:\Program Files\LocalDrop`)
2. Create Start Menu folder + shortcuts
3. Add a Desktop shortcut
4. Register in Add/Remove Programs
5. Add a Windows Firewall inbound rule for TCP port 5005

---

## GitHub Actions (automated builds)

The repo includes `.github/workflows/build-windows.yml` which automatically
builds and attaches the installer to every GitHub Release.

Push a tag to trigger it:
```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Signing (optional but recommended)

To avoid Windows SmartScreen warnings, sign the installer:

```powershell
# With a code-signing certificate (.pfx):
signtool sign /f cert.pfx /p PASSWORD /t http://timestamp.digicert.com LocalDrop-Setup.exe
```

Free option: Get a certificate from [SignPath.io](https://signpath.io) (free for open source).
