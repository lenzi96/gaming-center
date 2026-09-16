#!/usr/bin/env python3
"""
Gaming Center - Graphical Setup and Installation Wizard.

A native Linux PyQt6 installation wizard for Gaming Center, adhering to CachyOS / Arch dark aesthetics.
Provides automatic system audit, customizable install targets, progress reporting, and 1-click launch.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from PyQt6.QtCore import QProcess, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

REPO_DIR = Path(__file__).resolve().parent
if str(REPO_DIR) not in sys.path:
    sys.path.insert(0, str(REPO_DIR))

import gaming_center
from gaming_center.style.theme import ThemeColors

INSTALLER_STYLESHEET = f"""
QWidget {{
    background-color: transparent;
    color: {ThemeColors.TEXT_PRIMARY};
    font-family: "Inter", "Cantarell", "Noto Sans", "Segoe UI", Roboto, sans-serif;
    font-size: 13px;
    outline: none;
}}

QMainWindow {{
    background-color: {ThemeColors.BG_ROOT};
}}

QFrame.wizard-card {{
    background-color: {ThemeColors.BG_CARD};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 10px;
    padding: 16px;
}}

QFrame.wizard-card:hover {{
    border-color: {ThemeColors.BORDER_HOVER};
}}

QPushButton {{
    background-color: {ThemeColors.BG_PANEL};
    color: {ThemeColors.TEXT_PRIMARY};
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
    font-size: 12px;
}}

QPushButton:hover {{
    background-color: {ThemeColors.BG_CARD_HOVER};
    border-color: {ThemeColors.ACCENT_CYAN};
}}

QPushButton.btn-primary {{
    background-color: {ThemeColors.ACCENT_GREEN};
    color: #04100c;
    border: 1px solid {ThemeColors.ACCENT_GREEN};
    font-weight: 800;
}}

QPushButton.btn-primary:hover {{
    background-color: #00f0a8;
    border-color: #00f0a8;
}}

QPushButton.btn-danger {{
    background-color: rgba(239, 68, 68, 0.15);
    color: #fca5a5;
    border: 1px solid rgba(239, 68, 68, 0.4);
}}

QPushButton.btn-danger:hover {{
    background-color: {ThemeColors.ACCENT_RED};
    color: #ffffff;
}}

QProgressBar {{
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    background-color: {ThemeColors.BG_INPUT};
    height: 16px;
    text-align: center;
    font-size: 11px;
    font-weight: bold;
    color: {ThemeColors.TEXT_PRIMARY};
}}

QProgressBar::chunk {{
    background-color: {ThemeColors.ACCENT_GREEN};
    border-radius: 5px;
}}

QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    color: {ThemeColors.TEXT_PRIMARY};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {ThemeColors.BORDER_CARD};
    background-color: {ThemeColors.BG_INPUT};
}}

QCheckBox::indicator:hover {{
    border-color: {ThemeColors.ACCENT_GREEN};
}}

QCheckBox::indicator:checked {{
    background-color: {ThemeColors.ACCENT_GREEN};
    border-color: {ThemeColors.ACCENT_GREEN};
}}

QTextEdit {{
    background-color: #080c10;
    color: #e2e8f0;
    border: 1px solid {ThemeColors.BORDER_CARD};
    border-radius: 6px;
    padding: 8px;
    font-family: 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px;
}}
"""


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        install_bin: bool = True,
        install_desktop: bool = True,
        install_shortcut: bool = True,
        install_icons: bool = True,
        clean_first: bool = True,
    ):
        super().__init__()
        self.install_bin = install_bin
        self.install_desktop = install_desktop
        self.install_shortcut = install_shortcut
        self.install_icons = install_icons
        self.clean_first = clean_first

    def run(self):
        try:
            home = Path.home()
            bin_dir = home / ".local" / "bin"
            app_dir = home / ".local" / "share" / "applications"
            share_dir = home / ".local" / "share" / "gaming-center"
            hicolor_dir = home / ".local" / "share" / "icons" / "hicolor"
            pixmaps_dir = home / ".local" / "share" / "pixmaps"

            # 1. Directories
            self.progress.emit(10, "Erstelle Zielverzeichnisse...")
            self.log_line.emit("[→] Erstelle Verzeichnisstruktur...")
            bin_dir.mkdir(parents=True, exist_ok=True)
            app_dir.mkdir(parents=True, exist_ok=True)
            share_dir.mkdir(parents=True, exist_ok=True)
            pixmaps_dir.mkdir(parents=True, exist_ok=True)
            self.log_line.emit(f"[✓] Verzeichnisse bereit ({share_dir})")

            # 2. Copy Application files
            self.progress.emit(30, "Kopiere Anwendungsdateien...")
            self.log_line.emit(f"[→] Kopiere Gaming Center nach {share_dir}...")
            dest_pkg = share_dir / "gaming_center"
            if self.clean_first and dest_pkg.exists():
                shutil.rmtree(dest_pkg)

            shutil.copytree(REPO_DIR / "gaming_center", dest_pkg, dirs_exist_ok=True)
            shutil.copy(REPO_DIR / "main.py", share_dir / "main.py")
            if (REPO_DIR / "README.md").exists():
                shutil.copy(REPO_DIR / "README.md", share_dir / "README.md")
            if (REPO_DIR / "CHANGELOG.md").exists():
                shutil.copy(REPO_DIR / "CHANGELOG.md", share_dir / "CHANGELOG.md")
            self.log_line.emit("[✓] Anwendungsdateien erfolgreich installiert")

            # 3. Binary Launcher
            if self.install_bin:
                self.progress.emit(50, "Installiere Standalone-Launcher...")
                dest_bin = bin_dir / "gaming-center"
                self.log_line.emit(f"[→] Installiere Launcher nach {dest_bin}...")
                shutil.copy(REPO_DIR / "gaming-center", dest_bin)
                dest_bin.chmod(0o755)
                self.log_line.emit("[✓] Befehlszeilen-Starter 'gaming-center' installiert")

            # 4. Icons
            if self.install_icons:
                self.progress.emit(70, "Installiere Anwendungs-Icons...")
                self.log_line.emit("[→] Installiere Multi-Resolution Icons (16x16 bis 512x512 + SVG)...")
                svg_icon = REPO_DIR / "gaming_center" / "resources" / "gaming-center.svg"
                if svg_icon.exists():
                    svg_dest = hicolor_dir / "scalable" / "apps" / "gaming-center.svg"
                    svg_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(svg_icon, svg_dest)
                    shutil.copy(svg_icon, pixmaps_dir / "gaming-center.svg")

                for sz in (16, 24, 32, 48, 64, 128, 256, 512):
                    png_src = REPO_DIR / "gaming_center" / "resources" / f"app_icon_{sz}.png"
                    if png_src.exists():
                        dest_png_dir = hicolor_dir / f"{sz}x{sz}" / "apps"
                        dest_png_dir.mkdir(parents=True, exist_ok=True)
                        shutil.copy(png_src, dest_png_dir / "gaming-center.png")

                png_256 = REPO_DIR / "gaming_center" / "resources" / "app_icon_256.png"
                if png_256.exists():
                    shutil.copy(png_256, pixmaps_dir / "gaming-center.png")
                self.log_line.emit("[✓] System-Icons erfolgreich registriert")

            # 5. Desktop Menu Entry
            if self.install_desktop:
                self.progress.emit(85, "Registriere Desktop-Menüeintrag...")
                desktop_file = app_dir / "gaming-center.desktop"
                self.log_line.emit(f"[→] Installiere Menüeintrag {desktop_file}...")
                shutil.copy(REPO_DIR / "gaming-center.desktop", desktop_file)
                desktop_file.chmod(0o644)
                self.log_line.emit("[✓] Desktop-Menüeintrag erstellt")

            # 6. Desktop Shortcut
            if self.install_shortcut:
                dt_dir = home / "Desktop"
                if not dt_dir.exists() and (home / "Schreibtisch").exists():
                    dt_dir = home / "Schreibtisch"
                if dt_dir.exists():
                    dt_file = dt_dir / "gaming-center.desktop"
                    self.log_line.emit(f"[→] Erstelle Desktop-Verknüpfung auf {dt_file}...")
                    shutil.copy(REPO_DIR / "gaming-center.desktop", dt_file)
                    try:
                        dt_file.chmod(0o755)
                    except Exception:
                        pass
                    self.log_line.emit("[✓] Schreibtisch-Verknüpfung angelegt")

            # 7. Update System Caches
            self.progress.emit(95, "Aktualisiere Desktop- & Icon-Datenbanken...")
            self.log_line.emit("[→] Aktualisiere System-Caches...")
            if shutil.which("update-desktop-database"):
                subprocess.run(["update-desktop-database", str(app_dir)], check=False)
            if shutil.which("gtk-update-icon-cache"):
                subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", str(hicolor_dir)], check=False)
            self.log_line.emit("[✓] Caches aktualisiert")

            self.progress.emit(100, "Installation erfolgreich abgeschlossen!")
            self.log_line.emit("\n=======================================================")
            self.log_line.emit(f"  Gaming Center v{gaming_center.__version__} ist einsatzbereit!")
            self.log_line.emit("=======================================================")
            self.finished.emit(True, "Installation vollständig!")
        except Exception as e:
            self.log_line.emit(f"\n[✗] FEHLER bei der Installation: {e}")
            self.finished.emit(False, str(e))


class UninstallWorker(QThread):
    progress = pyqtSignal(int, str)
    log_line = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            home = Path.home()
            self.log_line.emit("[→] Starte Deinstallation von Gaming Center...")

            targets = [
                home / ".local" / "share" / "gaming-center",
                home / ".local" / "bin" / "gaming-center",
                home / ".local" / "share" / "applications" / "gaming-center.desktop",
                home / "Desktop" / "gaming-center.desktop",
                home / "Schreibtisch" / "gaming-center.desktop",
                home / ".local" / "share" / "pixmaps" / "gaming-center.svg",
                home / ".local" / "share" / "pixmaps" / "gaming-center.png",
                home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "gaming-center.svg",
            ]

            total = len(targets)
            for i, p in enumerate(targets, 1):
                if p.exists():
                    self.log_line.emit(f"[→] Entferne {p}...")
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                self.progress.emit(int((i / total) * 90), f"Entferne {p.name}...")

            # Remove icons
            hicolor = home / ".local" / "share" / "icons" / "hicolor"
            for sz in (16, 24, 32, 48, 64, 128, 256, 512):
                p = hicolor / f"{sz}x{sz}" / "apps" / "gaming-center.png"
                if p.exists():
                    p.unlink()

            if shutil.which("update-desktop-database"):
                subprocess.run(["update-desktop-database", str(home / ".local" / "share" / "applications")], check=False)
            if shutil.which("gtk-update-icon-cache"):
                subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", str(hicolor)], check=False)

            self.progress.emit(100, "Deinstallation abgeschlossen!")
            self.log_line.emit("[✓] Gaming Center wurde vollständig entfernt.")
            self.finished.emit(True, "Deinstallation abgeschlossen.")
        except Exception as e:
            self.log_line.emit(f"[✗] Fehler bei Deinstallation: {e}")
            self.finished.emit(False, str(e))


class InstallerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gaming Center - Setup-Assistent")
        self.resize(720, 560)
        self.setFixedSize(720, 560)

        self.worker = None
        self._init_ui()
        self.setStyleSheet(INSTALLER_STYLESHEET)

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(14)

        # ----------------------------------------------------------------------
        # Top Header Hero
        # ----------------------------------------------------------------------
        header = QFrame()
        header.setStyleSheet(f"""
            background-color: {ThemeColors.BG_CARD};
            border: 1px solid {ThemeColors.BORDER_CARD};
            border-radius: 10px;
            padding: 12px 16px;
        """)
        hl = QHBoxLayout(header)
        hl.setSpacing(14)

        icon_path = REPO_DIR / "gaming_center" / "resources" / "app_icon_64.png"
        icon_lbl = QLabel()
        if icon_path.exists():
            icon_lbl.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        else:
            icon_lbl.setText("🎮")
            icon_lbl.setStyleSheet("font-size: 32px;")
        hl.addWidget(icon_lbl)

        htext = QVBoxLayout()
        htext.setSpacing(2)
        h_row = QHBoxLayout()
        t_lbl = QLabel("Gaming Center")
        t_lbl.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {ThemeColors.ACCENT_GREEN};")
        h_row.addWidget(t_lbl)

        ver_badge = QLabel(f"v{gaming_center.__version__}")
        ver_badge.setStyleSheet(f"""
            background-color: rgba(56, 189, 248, 0.15);
            color: {ThemeColors.ACCENT_CYAN};
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 10px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: bold;
        """)
        h_row.addWidget(ver_badge)
        h_row.addStretch()
        htext.addLayout(h_row)

        sub_lbl = QLabel("Linux Game Service Center mit PCGamingWiki & Tuning Integration")
        sub_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
        htext.addWidget(sub_lbl)
        hl.addLayout(htext, 1)

        root_layout.addWidget(header)

        # ----------------------------------------------------------------------
        # Stacked Pages
        # ----------------------------------------------------------------------
        self.stack = QStackedWidget()

        # Page 0: Welcome & System Audit
        self.page_welcome = self._create_page_welcome()
        self.stack.addWidget(self.page_welcome)

        # Page 1: Options
        self.page_options = self._create_page_options()
        self.stack.addWidget(self.page_options)

        # Page 2: Progress
        self.page_progress = self._create_page_progress()
        self.stack.addWidget(self.page_progress)

        # Page 3: Complete
        self.page_complete = self._create_page_complete()
        self.stack.addWidget(self.page_complete)

        root_layout.addWidget(self.stack, 1)

        # ----------------------------------------------------------------------
        # Bottom Button Bar
        # ----------------------------------------------------------------------
        self.btn_bar = QHBoxLayout()
        self.btn_bar.setSpacing(10)

        self.btn_uninstall = QPushButton("🗑️ Deinstallieren")
        self.btn_uninstall.setProperty("class", "btn-danger")
        self.btn_uninstall.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_uninstall.clicked.connect(self.start_uninstallation)
        self.btn_bar.addWidget(self.btn_uninstall)

        self.btn_bar.addStretch()

        self.btn_back = QPushButton("← Zurück")
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setEnabled(False)

        self.btn_next = QPushButton("Weiter →")
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next.setProperty("class", "btn-primary")
        self.btn_next.clicked.connect(self.go_next)

        self.btn_bar.addWidget(self.btn_back)
        self.btn_bar.addWidget(self.btn_next)
        root_layout.addLayout(self.btn_bar)

    def _create_page_welcome(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(12)

        # Welcome Card
        card = QFrame()
        card.setProperty("class", "wizard-card")
        cl = QVBoxLayout(card)
        cl.setSpacing(8)

        t = QLabel("Willkommen zur Installation von Gaming Center!")
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {ThemeColors.TEXT_PRIMARY};")
        cl.addWidget(t)

        desc = QLabel(
            "Dieser Assistent richtet Gaming Center vollständig auf deinem System ein.\n"
            "• PCGamingWiki-Liveanbindung mit automatischer deutscher Übersetzung\n"
            "• 1-Klick-Download von Community-Patches, Mods und Fixes (GitHub/Direct)\n"
            "• Erweiterte Startoptionen & Tuning Suite (GameMode, MangoHud, Gamescope FSR)\n"
            "• 1-Klick-Spielstand-Backups (Savegame Manager) für Steam & Proton"
        )
        desc.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; line-height: 1.5;")
        desc.setWordWrap(True)
        cl.addWidget(desc)
        l.addWidget(card)

        # System Audit Card
        audit_card = QFrame()
        audit_card.setProperty("class", "wizard-card")
        al = QVBoxLayout(audit_card)
        al.setSpacing(6)

        al_title = QLabel("🔍 System- und Umgebungserkennung:")
        al_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {ThemeColors.ACCENT_CYAN};")
        al.addWidget(al_title)

        # Perform Quick Checks
        checks: List[Tuple[str, str, bool]] = []

        # Python
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        checks.append(("Python-Laufzeit", f"Python {py_ver}", sys.version_info >= (3, 8)))

        # PyQt6
        checks.append(("PyQt6 Toolkit", "Installiert & Aktiv", True))

        # Steam
        steam_paths = [
            Path.home() / ".local" / "share" / "Steam",
            Path.home() / ".steam" / "steam",
            Path.home() / ".steam" / "root",
        ]
        has_steam = any(p.exists() for p in steam_paths)
        checks.append(("Steam-Bibliothek", "Gefunden" if has_steam else "Nicht gefunden", has_steam))

        # Heroic & Lutris
        has_heroic = (Path.home() / ".config" / "heroic").exists() or shutil.which("heroic") is not None
        checks.append(("Heroic Games Launcher", "Erkannt" if has_heroic else "Nicht installiert", has_heroic))

        # Tools
        has_gamemode = shutil.which("gamemoderun") is not None
        has_mangohud = shutil.which("mangohud") is not None
        has_gamescope = shutil.which("gamescope") is not None
        tools_str = []
        if has_gamemode:
            tools_str.append("gamemoderun")
        if has_mangohud:
            tools_str.append("mangohud")
        if has_gamescope:
            tools_str.append("gamescope")
        checks.append(("Gaming-Tools", ", ".join(tools_str) if tools_str else "Keine optionalen Tools", bool(tools_str)))

        # Render checks
        for name, value, ok in checks:
            row = QHBoxLayout()
            lbl_name = QLabel(f"• {name}:")
            lbl_name.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {ThemeColors.TEXT_PRIMARY};")
            lbl_val = QLabel(value)
            lbl_val.setStyleSheet(
                f"font-size: 12px; color: {ThemeColors.ACCENT_GREEN if ok else ThemeColors.TEXT_MUTED};"
            )
            row.addWidget(lbl_name)
            row.addWidget(lbl_val)
            row.addStretch()
            al.addLayout(row)

        l.addWidget(audit_card)
        l.addStretch()
        return w

    def _create_page_options(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(12)

        card = QFrame()
        card.setProperty("class", "wizard-card")
        cl = QVBoxLayout(card)
        cl.setSpacing(10)

        t = QLabel("Installations-Optionen und Komponenten")
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {ThemeColors.TEXT_PRIMARY};")
        cl.addWidget(t)

        st = QLabel("Wähle aus, welche Verknüpfungen und Starter angelegt werden sollen:")
        st.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px;")
        cl.addWidget(st)

        cl.addSpacing(6)

        self.cb_core = QCheckBox("Kern-Dateien installieren (~/.local/share/gaming-center)")
        self.cb_core.setChecked(True)
        self.cb_core.setEnabled(False)
        cl.addWidget(self.cb_core)

        self.cb_bin = QCheckBox("Befehlszeilen-Starter installieren (~/.local/bin/gaming-center)")
        self.cb_bin.setChecked(True)
        cl.addWidget(self.cb_bin)

        self.cb_desktop = QCheckBox("Desktop-Menüeintrag erstellen (~/.local/share/applications/gaming-center.desktop)")
        self.cb_desktop.setChecked(True)
        cl.addWidget(self.cb_desktop)

        self.cb_shortcut = QCheckBox("Verknüpfung auf dem Schreibtisch / Desktop anlegen")
        self.cb_shortcut.setChecked(True)
        cl.addWidget(self.cb_shortcut)

        self.cb_icons = QCheckBox("System-Icons in allen Auflösungen (16x16 bis 512x512 + SVG) registrieren")
        self.cb_icons.setChecked(True)
        cl.addWidget(self.cb_icons)

        self.cb_clean = QCheckBox("Bestehende Installation vor dem Kopieren bereinigen")
        self.cb_clean.setChecked(True)
        cl.addWidget(self.cb_clean)

        l.addWidget(card)
        l.addStretch()
        return w

    def _create_page_progress(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(12)

        card = QFrame()
        card.setProperty("class", "wizard-card")
        cl = QVBoxLayout(card)
        cl.setSpacing(10)

        t = QLabel("Installation wird ausgeführt...")
        t.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {ThemeColors.TEXT_PRIMARY};")
        cl.addWidget(t)

        self.lbl_status = QLabel("Bereite Einrichtung vor...")
        self.lbl_status.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
        cl.addWidget(self.lbl_status)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        cl.addWidget(self.progress_bar)

        l.addWidget(card)

        # Log Box
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        l.addWidget(self.log_text, 1)

        return w

    def _create_page_complete(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(0, 4, 0, 0)
        l.setSpacing(12)

        card = QFrame()
        card.setProperty("class", "wizard-card")
        cl = QVBoxLayout(card)
        cl.setSpacing(12)

        success_row = QHBoxLayout()
        icon_done = QLabel("✅")
        icon_done.setStyleSheet("font-size: 28px;")
        success_row.addWidget(icon_done)

        t = QLabel("Gaming Center wurde erfolgreich installiert!")
        t.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {ThemeColors.ACCENT_GREEN};")
        success_row.addWidget(t)
        success_row.addStretch()
        cl.addLayout(success_row)

        desc = QLabel(
            "Alle ausgewählten Komponenten wurden ordnungsgemäß eingerichtet.\n"
            "Das Programm kann ab sofort über das Anwendungsmenü oder die Befehlszeile gestartet werden."
        )
        desc.setStyleSheet(f"color: {ThemeColors.TEXT_SECONDARY}; font-size: 12px; line-height: 1.5;")
        cl.addWidget(desc)

        cmd_frame = QFrame()
        cmd_frame.setStyleSheet(f"""
            background-color: {ThemeColors.BG_INPUT};
            border: 1px solid {ThemeColors.BORDER_CARD};
            border-radius: 6px;
            padding: 8px 12px;
        """)
        cfl = QHBoxLayout(cmd_frame)
        cfl.addWidget(QLabel("Terminal-Startbefehl:"))
        cmd_lbl = QLabel("gaming-center")
        cmd_lbl.setStyleSheet(f"font-family: monospace; font-weight: bold; color: {ThemeColors.ACCENT_CYAN};")
        cfl.addWidget(cmd_lbl)
        cfl.addStretch()
        cl.addWidget(cmd_frame)

        cl.addSpacing(6)

        self.cb_launch_now = QCheckBox("Gaming Center jetzt sofort starten")
        self.cb_launch_now.setChecked(True)
        cl.addWidget(self.cb_launch_now)

        l.addWidget(card)
        l.addStretch()
        return w

    def go_next(self):
        idx = self.stack.currentIndex()
        if idx == 0:
            self.stack.setCurrentIndex(1)
            self.btn_back.setEnabled(True)
            self.btn_next.setText("Installieren 🚀")
        elif idx == 1:
            self.stack.setCurrentIndex(2)
            self.btn_back.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.btn_uninstall.setEnabled(False)
            self.start_installation()
        elif idx == 3:
            # Complete -> Launch if requested, then exit
            if self.cb_launch_now.isChecked():
                self.launch_installed_app()
            self.close()

    def go_back(self):
        idx = self.stack.currentIndex()
        if idx == 1:
            self.stack.setCurrentIndex(0)
            self.btn_back.setEnabled(False)
            self.btn_next.setText("Weiter →")

    def start_installation(self):
        self.log_text.clear()
        self.worker = InstallWorker(
            install_bin=self.cb_bin.isChecked(),
            install_desktop=self.cb_desktop.isChecked(),
            install_shortcut=self.cb_shortcut.isChecked(),
            install_icons=self.cb_icons.isChecked(),
            clean_first=self.cb_clean.isChecked(),
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.log_line.connect(self._on_log)
        self.worker.finished.connect(self._on_install_finished)
        self.worker.start()

    def start_uninstallation(self):
        reply = QMessageBox.question(
            self,
            "Deinstallation bestätigen",
            "Möchtest du Gaming Center wirklich von diesem System deinstallieren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.stack.setCurrentIndex(2)
        self.btn_back.setEnabled(False)
        self.btn_next.setEnabled(False)
        self.btn_uninstall.setEnabled(False)

        self.log_text.clear()
        self.worker = UninstallWorker()
        self.worker.progress.connect(self._on_progress)
        self.worker.log_line.connect(self._on_log)
        self.worker.finished.connect(self._on_uninstall_finished)
        self.worker.start()

    def _on_progress(self, val: int, msg: str):
        self.progress_bar.setValue(val)
        self.lbl_status.setText(msg)

    def _on_log(self, text: str):
        self.log_text.append(text)

    def _on_install_finished(self, success: bool, msg: str):
        if success:
            self.stack.setCurrentIndex(3)
            self.btn_back.setVisible(False)
            self.btn_uninstall.setVisible(False)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Fertigstellen")
        else:
            QMessageBox.critical(self, "Installations-Fehler", f"Die Installation schlug fehl:\n{msg}")
            self.btn_back.setEnabled(True)
            self.btn_next.setEnabled(True)
            self.btn_next.setText("Wiederholen")
            self.stack.setCurrentIndex(1)

    def _on_uninstall_finished(self, success: bool, msg: str):
        if success:
            QMessageBox.information(self, "Deinstalliert", "Gaming Center wurde erfolgreich entfernt.")
        else:
            QMessageBox.warning(self, "Hinweis", f"Deinstallation mit Hinweisen abgeschlossen:\n{msg}")
        self.close()

    def launch_installed_app(self):
        launcher = shutil.which("gaming-center") or str(Path.home() / ".local" / "bin" / "gaming-center")
        if os.path.exists(launcher):
            QProcess.startDetached(launcher, [])
        else:
            main_py = Path.home() / ".local" / "share" / "gaming-center" / "main.py"
            if main_py.exists():
                QProcess.startDetached(sys.executable, [str(main_py)])


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("GamingCenterInstaller")
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
