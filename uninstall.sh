#!/bin/bash
set -e

BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
SHARE_DIR="$HOME/.local/share/gaming-center"
HICOLOR_DIR="$HOME/.local/share/icons/hicolor"
PIXMAPS_DIR="$HOME/.local/share/pixmaps"

DESKTOP_DIR="$HOME/Desktop"
if [ -d "$HOME/Schreibtisch" ]; then
    DESKTOP_DIR="$HOME/Schreibtisch"
fi

echo "======================================================="
echo "   Deinstallation: Gaming Center                       "
echo "======================================================="

rm -f "$BIN_DIR/gaming-center"
rm -rf "$SHARE_DIR/gaming_center" "$SHARE_DIR/main.py" "$SHARE_DIR/README.md"
rm -f "$APP_DIR/gaming-center.desktop"
[ -d "$DESKTOP_DIR" ] && rm -f "$DESKTOP_DIR/gaming-center.desktop"

rm -f "$HICOLOR_DIR/scalable/apps/gaming-center.svg"
rm -f "$PIXMAPS_DIR/gaming-center.svg"
rm -f "$PIXMAPS_DIR/gaming-center.png"
for sz in 16 24 32 48 64 128 256 512; do
    rm -f "$HICOLOR_DIR/${sz}x${sz}/apps/gaming-center.png"
done

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$HICOLOR_DIR" 2>/dev/null || true
fi

echo "[✓] Gaming Center erfolgreich deinstalliert."
