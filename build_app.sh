#!/bin/bash
# Build Mamp Poo.app for macOS using PyInstaller.
# Run on a Mac — produces dist/Mamp Poo.app

set -e

echo "============================================"
echo " Build Mamp Poo.app (macOS)"
echo "============================================"

# Ensure deps
echo "[1/3] Installing PyInstaller + Pillow + pystray..."
python3 -m pip install --quiet pyinstaller Pillow pystray

# Convert PNG to .icns for the macOS icon (skip if iconutil missing)
echo "[2/3] Converting crab_logo.png → .icns..."
if [ -f crab_logo.png ] && command -v iconutil >/dev/null 2>&1; then
    mkdir -p iconset.iconset
    sips -z 16 16     crab_logo.png --out iconset.iconset/icon_16x16.png >/dev/null
    sips -z 32 32     crab_logo.png --out iconset.iconset/icon_16x16@2x.png >/dev/null
    sips -z 32 32     crab_logo.png --out iconset.iconset/icon_32x32.png >/dev/null
    sips -z 64 64     crab_logo.png --out iconset.iconset/icon_32x32@2x.png >/dev/null
    sips -z 128 128   crab_logo.png --out iconset.iconset/icon_128x128.png >/dev/null
    sips -z 256 256   crab_logo.png --out iconset.iconset/icon_128x128@2x.png >/dev/null
    sips -z 256 256   crab_logo.png --out iconset.iconset/icon_256x256.png >/dev/null
    sips -z 512 512   crab_logo.png --out iconset.iconset/icon_256x256@2x.png >/dev/null
    sips -z 512 512   crab_logo.png --out iconset.iconset/icon_512x512.png >/dev/null
    cp crab_logo.png  iconset.iconset/icon_512x512@2x.png
    iconutil -c icns iconset.iconset -o crab_logo.icns
    rm -rf iconset.iconset
    ICON_ARG="--icon crab_logo.icns"
else
    ICON_ARG=""
fi

# Build .app bundle
echo "[3/3] Building .app (may take 1-2 minutes)..."
pyinstaller \
    --windowed \
    --name "Mamp Poo" \
    $ICON_ARG \
    --add-data "manager:manager" \
    --add-data "ui:ui" \
    --add-data "crab_logo.png:." \
    --hidden-import customtkinter \
    --hidden-import PIL \
    --hidden-import requests \
    --hidden-import pystray \
    --osx-bundle-identifier "com.localdev.mamppoo" \
    main.py

echo
echo "✓ Done!"
echo "  Output: dist/Mamp Poo.app"
echo "  Drag it to /Applications, or just double-click in dist/"
