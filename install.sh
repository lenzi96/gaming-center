#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
echo "   Installation: Gaming Center                         "
echo "======================================================="

mkdir -p "$BIN_DIR" "$APP_DIR" "$SHARE_DIR" "$PIXMAPS_DIR"

# 1. Anwendungsdateien nach ~/.local/share/gaming-center kopieren
echo "→ Kopiere Anwendungsdateien nach $SHARE_DIR..."
rm -rf "$SHARE_DIR/gaming_center"
cp -r "$DIR/gaming_center" "$SHARE_DIR/"
cp "$DIR/main.py" "$SHARE_DIR/"
[ -f "$DIR/README.md" ] && cp "$DIR/README.md" "$SHARE_DIR/"
[ -f "$DIR/CHANGELOG.md" ] && cp "$DIR/CHANGELOG.md" "$SHARE_DIR/"
echo "[✓] Anwendungsdateien installiert"

# 2. Standalone-Launcher nach ~/.local/bin/gaming-center installieren
echo "→ Installiere Launcher nach $BIN_DIR/gaming-center..."
cp "$DIR/gaming-center" "$BIN_DIR/gaming-center"
chmod 755 "$BIN_DIR/gaming-center"
echo "[✓] Standalone-Binary installiert"

# 3. Icons installieren (Multi-Resolution PNGs + SVG)
echo "→ Installiere Icons..."
mkdir -p "$HICOLOR_DIR/scalable/apps"
cp "$DIR/gaming_center/resources/gaming-center.svg" "$HICOLOR_DIR/scalable/apps/gaming-center.svg"
cp "$DIR/gaming_center/resources/gaming-center.svg" "$PIXMAPS_DIR/gaming-center.svg"

for sz in 16 24 32 48 64 128 256 512; do
    if [ -f "$DIR/gaming_center/resources/app_icon_${sz}.png" ]; then
        mkdir -p "$HICOLOR_DIR/${sz}x${sz}/apps"
        cp "$DIR/gaming_center/resources/app_icon_${sz}.png" "$HICOLOR_DIR/${sz}x${sz}/apps/gaming-center.png"
    fi
done
cp "$DIR/gaming_center/resources/app_icon_256.png" "$PIXMAPS_DIR/gaming-center.png"
echo "[✓] Icons erfolgreich installiert"

# 4. Desktop-Eintrag installieren
echo "→ Installiere Menü-Eintrag..."
cp "$DIR/gaming-center.desktop" "$APP_DIR/gaming-center.desktop"
chmod 644 "$APP_DIR/gaming-center.desktop"

# Optional: Verknüpfung auf Desktop/Schreibtisch
if [ -d "$DESKTOP_DIR" ]; then
    cp "$DIR/gaming-center.desktop" "$DESKTOP_DIR/gaming-center.desktop"
    chmod +x "$DESKTOP_DIR/gaming-center.desktop" 2>/dev/null || true
    echo "[✓] Desktop-Verknüpfung erstellt auf $DESKTOP_DIR"
fi

# 5. Icon- & Desktop-Caches aktualisieren
echo "→ Aktualisiere Desktop- & Icon-Datenbanken..."
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f "$HICOLOR_DIR" 2>/dev/null || true
fi

echo "======================================================="
echo "   [✓] Gaming Center erfolgreich installiert!          "
echo "   Startbar über Anwendungsmenü oder: gaming-center    "
echo "======================================================="
