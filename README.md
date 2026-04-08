# LocalDrop

A lightweight desktop app that lets you wirelessly transfer files and send notes between your laptop and any device on the same Wi-Fi — no cables, no cloud, no internet required.

## Features

- 📁 **Send files** from phone → laptop (drag & drop or tap to pick)
- 📥 **Receive files** — browse and download files from your laptop
- ✉️ **Notes** — send quick text, URLs or messages to your laptop instantly
- 📱 **QR code** — scan once and you're connected, no typing URLs
- 🔌 **No internet** — everything stays on your local network
- 🖥️ **Cross-platform** — runs on Windows and Linux

## Usage

1. Launch LocalDrop on your laptop
2. Scan the QR code with your phone
3. Start sending files or notes from the browser UI

## Build

**Linux:**
```bash
make install
```

**Windows:**
```powershell
pyinstaller windows/localdrop.spec
cd windows && makensis installer.nsi
```

## Requirements

```bash
pip3 install pyqt6 "qrcode[pil]" Pillow
```

## License

MIT
