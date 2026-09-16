#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "Fehler: python3 wurde nicht gefunden. Bitte installiere Python 3."
    exit 1
fi

# Check for PyQt6
if ! python3 -c "import PyQt6" >/dev/null 2>&1; then
    echo "Fehler: PyQt6 ist nicht installiert."
    echo "Bitte installiere PyQt6 mit deinem Paketmanager (z.B. 'sudo pacman -S python-pyqt6' oder 'pip install PyQt6')."
    exit 1
fi

exec python3 "$DIR/installer_gui.py" "$@"
