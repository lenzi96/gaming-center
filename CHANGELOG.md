# Gaming Center - Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [v1.1.0] - 2026-09-16

### Hinzugefügt
- **GitHub Updater & Release-Manager**:
  - Integration des Release-Updaters aus der Cachy Security Suite.
  - Automatischer Versionsabgleich mit GitHub Releases via API.
  - Unterstützung für Token-Authentifizierung (PAT) für private Repositories.
  - Update-Center-Dialog mit Versionsstatus, Changelog-Viewer und Live-Installationslog.
  - 1-Klick-Selbstaktualisierung im laufenden Betrieb mit automatischem Neustart.
  - Diskrete Hintergrundprüfung auf neue Versionen beim Start mit Badge in der Menüleiste.
- **Grafischer Setup-Assistent (`installer_gui.py` & `install-gui.sh`)**:
  - Moderner CachyOS/Arch Setup-Wizard im Emerald/Cyan Dark Theme.
  - Automatisches System-Auditing (Python, PyQt6, Steam, Heroic, Lutris, GameMode, MangoHud, Gamescope).
  - Flexible Komponenten- und Pfadauswahl mit Größenberechnung.
  - Asynchrone Installation & Deinstallation mit Live-Fortschritt und Log-Konsole.
  - 1-Klick-Direktstart nach erfolgreicher Einrichtung.
- **PCGamingWiki Community Patches & Fixes Downloader**:
  - Automatisches Scannen und Extrahieren von Fixes, Patches und Mod-Links aus PCGamingWiki Artikeln.
  - GitHub Release Resolver: Direkte Erkennung und Auflösung der neuesten Binärdateien aus GitHub-Releases (z. B. Cyber Engine Tweaks, DSfix, SilentPatch).
  - Integrierter Download-Manager mit Fortschrittsbalken, MB/s-Rate und ETA.
  - Zielortauswahl: Download wahlweise nach `~/Downloads`, direkt ins Spielverzeichnis oder ins Proton-Prefix.
  - 1-Klick-Sicherheitsentpacken direkt in das Spielverzeichnis (Zip-Slip geschützt).
  - Wine-Installer Ausführung im Prefix für `.exe`-Patcher.
  - Schnellfilter `Nur Fixes mit Patches/Downloads` im Fixes-Reiter.

---

## [v1.0.0] - 2026-09-15

### Initiales Release
- Erstveröffentlichung des **Gaming Centers** für Linux (CachyOS / Arch).
- Automatische Erkennung von Spielen aus **Steam**, **Heroic Games Launcher** und **Lutris**.
- Vollständige Anbindung an die **PCGamingWiki API** mit lokaler Zwischenspeicherung.
- Automatische Übersetzung englischer Wiki-Texte ins Deutsche (Offline-Wörterbuch mit Satzbau-Transformation & Online-Fallback).
- Spielstart-Konfigurator mit Proton-Prefix-Erkennung, Wine-Optionen, Gamemode, Gamescope und Mangohud.
- Savegame-Manager mit Erkennung von Linux- und Windows/Proton-Speicherständen.
- Modernes Dark-Theme im CachyOS/Arch-Design.
