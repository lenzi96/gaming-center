# Gaming Center - Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [v1.1.5] - 2026-09-17

### Hinzugefügt
- **Hardware- & Spiele-Auto-Optimierung (1-Klick)**:
  - Intelligente Hardware-Erkennung (`GameOptimizer`): Ermittelt automatisch GPU (AMD Radeon, NVIDIA GeForce, Intel Arc), CPU-Kerne, Handheld-Modus (Steam Deck) sowie Gaming-Tools (`gamemoderun`, `mangohud`, `gamescope`, `prime-run`).
  - GPU-spezifische Profile:
    - **AMD Radeon**: Automatische Aktivierung von RADV GPL Shader Pipeline (`RADV_PERFTEST=gpl`), DXVK Async (`DXVK_ASYNC=1`) und FSR Upscaling (`WINE_FULLSCREEN_FSR=1`).
    - **NVIDIA GeForce**: Freischaltung von NVIDIA NVAPI für DLSS/Reflex (`PROTON_ENABLE_NVAPI=1`), DirectX 12 Raytracing (`VKD3D_CONFIG=dxr11,dxr`) und DXVK Async.
    - **Intel / Standard**: DXVK Async und ausgewogene Performance-Profile.
  - Retro- & 32-Bit Heuristiken: Schutz vor Speicherabstürzen durch automatische Aktivierung von Large Address Aware (`PROTON_FORCE_LARGE_ADDRESS_AWARE=1`) für ältere Klassiker.
  - PCGamingWiki Parameter-Extraktion: Übernahme empfohlener Startflags (z. B. `-novid`, `-skipintro`).
  - **Spiele-Detailansicht**:
    - Prominenter **„⚡ Auto-Optimierung“** Button direkt in der oberen Aktionsleiste neben „▶️ Spiel starten“.
    - Interaktive **Auto-Optimierungs-Aktionskarte** mit System-Info im Reiter „🚀 Startoptionen & Tuning“.
  - **Bibliotheks-Übersicht**:
    - Neuer Button **„⚡ Auto-Optimierung“** in der Haupt-Navigationsleiste.
    - Neuer Batch-Optimierungs-Dialog (`AutoOptimizeDialog`) zur gleichzeitigen Optimierung der gesamten Spiele-Bibliothek mit Profilauswahl (Performance, Ausgewogen, Handheld) und Fortschrittsanzeige.

---

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
