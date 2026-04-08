#!/usr/bin/env python3
"""
generate_icon.py  —  Creates placeholder icons for LocalDrop
Run this once if you don't have a custom icon yet.
Produces: assets/icon.png, assets/icon.ico, assets/icon.svg

Requirements: pip install Pillow
"""

import os
import math
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
ASSETS.mkdir(exist_ok=True)

def make_png():
    """256x256 PNG — purple rounded square with an up/down arrow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        size = 256
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # Rounded background
        r = 52
        bg = (124, 109, 250, 255)
        d.rounded_rectangle([0, 0, size-1, size-1], radius=r, fill=bg)

        # Simple arrow glyphs (↑↓) via text — fallback to shapes if no font
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 130)
            d.text((size//2, size//2), "⬆↓", font=font, fill="white", anchor="mm")
        except Exception:
            # Draw two triangles as arrows
            mid = size // 2
            # Up arrow
            d.polygon([(mid, 50), (mid-45, 120), (mid+45, 120)], fill="white")
            d.rectangle([mid-20, 120, mid+20, 160], fill="white")
            # Down arrow
            d.polygon([(mid, 206), (mid-45, 136), (mid+45, 136)], fill="white")
            d.rectangle([mid-20, 96, mid+20, 136], fill="white")

        out = ASSETS / "icon.png"
        img.save(out)
        print(f"✓ {out}")
        return img
    except ImportError:
        print("⚠  Pillow not found — skipping PNG/ICO generation")
        print("   Install: pip install Pillow")
        return None

def make_ico(png_img):
    """Multi-size .ico from the PNG."""
    if png_img is None:
        return
    out = ASSETS / "icon.ico"
    png_img.save(
        out,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    )
    print(f"✓ {out}")

def make_svg():
    """Simple SVG version — vector, scales to any size."""
    svg = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" width="256" height="256">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%"   stop-color="#7c6dfa"/>
      <stop offset="100%" stop-color="#9b6dfa"/>
    </linearGradient>
  </defs>
  <!-- Background -->
  <rect width="256" height="256" rx="52" ry="52" fill="url(#bg)"/>
  <!-- Up arrow -->
  <polygon points="128,40 80,110 108,110 108,148 148,148 148,110 176,110"
           fill="white" opacity="0.95"/>
  <!-- Down arrow -->
  <polygon points="128,216 80,146 108,146 108,108 148,108 148,146 176,146"
           fill="white" opacity="0.95"/>
</svg>
"""
    out = ASSETS / "icon.svg"
    out.write_text(svg)
    print(f"✓ {out}")

if __name__ == "__main__":
    print("Generating LocalDrop icons…")
    img = make_png()
    make_ico(img)
    make_svg()
    print("\nDone! Icons saved to assets/")
    print("Replace them with your own artwork any time.")
