# 🎮 Gaming Center

Ein modernes Linux-Spiele-Service-Center mit **PCGamingWiki**-Live-Anbindung, nativer Erkennung von Steam- (inkl. Multi-Library), Heroic- und Lutris-Installationen, automatischer Übersetzung von Windows-Speicherpfaden in Linux-Proton-Präfixe, 1-Klick-Spielstand-Backups und Startoptionen-Tuning.

---

## 🌟 Highlights & Funktionen

- **🔍 Automatische Spiele-Erkennung**:
  - Scannt alle konfigurierten Steam-Bibliotheken über verschiedene Festplatten/Partitionen (`libraryfolders.vdf`, `appmanifest_*.acf`).
  - Erkennt Spiele aus dem **Heroic Games Launcher** (GOG & Epic Games) sowie **Lutris**.
  - Liest Cover-Artworks lokal aus dem Steam-Appcache oder mit hochauflösendem CDN-Fallback.
- **🌐 PCGamingWiki Live-Integration**:
  - Schnelle OpenSearch- und MediaWiki-API-Abfragen mit lokalem Offline-Cache.
  - Zeigt Fixes für Intro-Skips, Crash-Workarounds und Performance-Tweaks an.
  - Feature-Matrix: Ultrawide (21:9 / 32:9), HDR, Raytracing, Controller-Support, Cloud-Saves und Anti-Cheat-Status.
- **📁 Proton-Präfix Pfad-Übersetzer (Windows ➔ Linux)**:
  - Übersetzt PCGamingWiki-Pfade wie `%USERPROFILE%\Saved Games\...` oder `%LOCALAPPDATA%\...` automatisch in das reale Linux-Verzeichnis:
    `~/.steam/.../steamapps/compatdata/<appid>/pfx/drive_c/users/steamuser/...`
  - Direkte Buttons: **"📂 Ordner öffnen"** (öffnet Dolphin, Nautilus oder Thunar), **"📋 Pfad kopieren"**.
- **💾 Spielstand-Manager (Savegame Backup)**:
  - 1-Klick Backups von Spielständen vor Updates, Patches oder Mod-Experimenten als `.tar.gz`.
  - Backup-Historie mit Zeitstempel, Größe und Notizen.
  - Sichere 1-Klick Wiederherstellung.
- **🚀 Startoptionen & Tuning-Generator**:
  - Toggles für **GameMode** (`gamemoderun`), **MangoHud** (`mangohud`) und **Gamescope**.
  - Flags für **NVIDIA DLSS / Raytracing** (`PROTON_ENABLE_NVAPI=1`), **DXVK Async**, ESync-Workarounds.
  - Übernimmt empfohlene Startparameter aus dem PCGW-Wiki.
  - Generiert den fertigen Startbefehl für Steam auf Knopfdruck.

- **⬇️ Community Patches & Fixes Downloader**:
  - Extrahiert Community-Patches und Mod-Tools direkt aus PCGamingWiki Artikeln (z. B. *Cyber Engine Tweaks*, *DSfix*, *SilentPatch*, *Ultimate-ASI-Loader*).
  - GitHub-Release-Resolver zur direkten Ermittlung der neuesten Binär-Assets (Zip-Archive/Installer).
  - Integrierter Download-Manager mit Fortschrittsbalken, MB/s-Rate und ETA.
  - Zielortauswahl: `~/Downloads`, direktes Spielinstallationsverzeichnis oder Proton-Prefix.
  - Sicheres 1-Klick-Entpacken (Zip-Slip geschützt) und Wine-Setup-Ausführung.
  - Schnellfilter für Fixes mit verfügbaren Patches & Downloads.
- **🔄 Integriertes Update-Center**:
  - Automatischer Versionsabgleich mit GitHub Releases via API.
  - Unterstützung für Token-Authentifizierung (PAT) für private Repositories.
  - 1-Klick-Selbstaktualisierung im laufenden Betrieb mit automatischem Neustart.
  - Diskrete Hintergrundprüfung mit Status-Badge in der Menüleiste.

---

## 🚀 Installation

### Schnellinstallation (Benutzer-Ebene)
```bash
git clone https://github.com/cachyos/gaming-center.git  # oder lokaler Ordner
cd gaming-center
./install.sh
```

### Deinstallation
```bash
./uninstall.sh
```

### Starten
- Über das Anwendungsmenü: **Gaming Center**
- Oder direkt im Terminal: `gaming-center`

---

## 🛠️ Voraussetzungen
- Python 3.8+
- `python-pyqt6` (oder `pip install PyQt6`)
- `xdg-utils` (für Dateimanager- und Browser-Integration)
