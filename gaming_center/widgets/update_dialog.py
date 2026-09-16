"""
Update Dialog for Gaming Center.

Provides GitHub release status, changelog viewer (Markdown), configuration of
repository/token, and live streaming of self-update executions.
"""
import os
import shutil
import subprocess
import sys
from typing import List, Optional

from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtGui import QFont, QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import gaming_center
from ..backend.updater import (
    BatchUpdateWorker,
    UpdateCheckerWorker,
    UpdateInfo,
    UpdateStep,
    get_github_repo,
    get_github_token,
    get_source_root,
    set_github_repo,
    set_github_token,
)
from ..style.theme import ThemeColors


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update-Center - Gaming Center")
        self.resize(780, 580)
        self.setMinimumSize(680, 500)

        self.checker_worker: Optional[UpdateCheckerWorker] = None
        self.batch_worker: Optional[BatchUpdateWorker] = None
        self.latest_info: Optional[UpdateInfo] = None

        self._init_ui()
        self.start_check()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 16)
        root_layout.setSpacing(12)

        # ----------------------------------------------------------------------
        # Top Header
        # ----------------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        lbl_title = QLabel("Gaming Center Update-Center")
        lbl_title.setStyleSheet(f"font-size: 19px; font-weight: 800; color: {ThemeColors.TEXT_PRIMARY};")
        lbl_desc = QLabel("Verwalte Software-Aktualisierungen, Versionshinweise und GitHub-Releases.")
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        lbl_desc.setWordWrap(True)

        header_text.addWidget(lbl_title)
        header_text.addWidget(lbl_desc)
        header_layout.addLayout(header_text)
        header_layout.addStretch()

        self.btn_refresh = QPushButton("🔄  Auf Updates prüfen")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(f"""
            QPushButton {{
                padding: 7px 14px;
                border-radius: 6px;
                border: 1px solid {ThemeColors.BORDER_CARD};
                background: {ThemeColors.BG_CARD};
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ThemeColors.BG_CARD_HOVER};
                border-color: {ThemeColors.ACCENT_CYAN};
            }}
            QPushButton:disabled {{ opacity: 0.5; }}
        """)
        self.btn_refresh.clicked.connect(self.start_check)
        header_layout.addWidget(self.btn_refresh)

        self.btn_update_now = QPushButton("🚀  Jetzt aktualisieren")
        self.btn_update_now.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update_now.setEnabled(False)
        self.btn_update_now.setStyleSheet(f"""
            QPushButton {{
                padding: 7px 16px;
                border-radius: 6px;
                background-color: {ThemeColors.ACCENT_GREEN};
                color: #04100c;
                font-size: 12px;
                font-weight: 800;
                border: none;
            }}
            QPushButton:hover {{ background-color: #00f0a8; }}
            QPushButton:disabled {{ background-color: #1e293b; color: #64748b; }}
        """)
        self.btn_update_now.clicked.connect(self.run_self_update)
        header_layout.addWidget(self.btn_update_now)

        root_layout.addLayout(header_layout)

        # Indeterminate / Status progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background: transparent;
            }}
            QProgressBar::chunk {{
                background-color: {ThemeColors.ACCENT_GREEN};
                border-radius: 2px;
            }}
        """)
        root_layout.addWidget(self.progress_bar)

        # ----------------------------------------------------------------------
        # Tab Widget
        # ----------------------------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 8px;
                background-color: {ThemeColors.BG_MAIN};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {ThemeColors.BG_PANEL};
                color: {ThemeColors.TEXT_SECONDARY};
                padding: 8px 18px;
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
                font-size: 12px;
                font-weight: 600;
            }}
            QTabBar::tab:selected {{
                background-color: {ThemeColors.BG_MAIN};
                color: {ThemeColors.ACCENT_GREEN};
                border-color: {ThemeColors.BORDER_SUBTLE};
            }}
            QTabBar::tab:hover {{
                color: {ThemeColors.TEXT_PRIMARY};
                background-color: {ThemeColors.BG_CARD};
            }}
        """)

        # Tab 1: Status & Overview
        self.tab_status = QWidget()
        self._init_status_tab()
        self.tabs.addTab(self.tab_status, "📊  Status & Übersicht")

        # Tab 2: Changelog
        self.tab_changelog = QWidget()
        self._init_changelog_tab()
        self.tabs.addTab(self.tab_changelog, "📝  Changelog")

        # Tab 3: Terminal Output
        self.tab_log = QWidget()
        self._init_log_tab()
        self.tabs.addTab(self.tab_log, "💻  Installations-Log")

        root_layout.addWidget(self.tabs, stretch=1)

        # Bottom Bar (Cancel button and summary)
        bottom_layout = QHBoxLayout()
        self.lbl_status_summary = QLabel("Bereit")
        self.lbl_status_summary.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        bottom_layout.addWidget(self.lbl_status_summary)
        bottom_layout.addStretch()

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 12px;
                border-radius: 5px;
                border: 1px solid {ThemeColors.ACCENT_RED};
                background: rgba(239, 68, 68, 0.15);
                color: #fca5a5;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {ThemeColors.ACCENT_RED}; color: #ffffff; }}
        """)
        self.btn_cancel.clicked.connect(self.cancel_active_process)
        bottom_layout.addWidget(self.btn_cancel)

        root_layout.addLayout(bottom_layout)

    def _init_status_tab(self):
        scroll = QScrollArea(self.tab_status)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # App Card
        card = QFrame()
        card.setObjectName("cardApp")
        card.setStyleSheet(f"""
            QFrame#cardApp {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 10px;
            }}
            QFrame#cardApp QLabel {{ background: transparent; border: none; }}
        """)
        c_layout = QHBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(14)

        # App icon
        icon_lbl = QLabel()
        source_dir = get_source_root()
        icon_path = os.path.join(source_dir, "gaming_center", "resources", "app_icon_64.png")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(source_dir, "gaming_center", "resources", "gaming-center.svg")

        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QIcon(icon_path).pixmap(48, 48))
        else:
            icon_lbl.setText("🎮")
            icon_lbl.setStyleSheet("font-size: 32px;")
        c_layout.addWidget(icon_lbl)

        # Text info
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        lbl_app_title = QLabel("Gaming Center")
        lbl_app_title.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {ThemeColors.TEXT_PRIMARY};")

        self.lbl_app_version = QLabel(f"Installiert: v{gaming_center.__version__}")
        self.lbl_app_version.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")

        self.lbl_app_github = QLabel("GitHub: Prüfe Releases...")
        self.lbl_app_github.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_MUTED};")

        text_layout.addWidget(lbl_app_title)
        text_layout.addWidget(self.lbl_app_version)
        text_layout.addWidget(self.lbl_app_github)
        c_layout.addLayout(text_layout, stretch=1)

        # Status badge
        self.badge_status = QLabel("Prüfe...")
        self.badge_status.setStyleSheet(f"""
            background-color: rgba(0, 212, 148, 0.12);
            color: {ThemeColors.ACCENT_GREEN};
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 11px;
            border: 1px solid rgba(0, 212, 148, 0.3);
        """)
        c_layout.addWidget(self.badge_status)

        # Actions column
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(6)

        self.btn_card_update = QPushButton("Neu installieren")
        self.btn_card_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_card_update.setStyleSheet(f"""
            QPushButton {{
                padding: 6px 14px;
                border-radius: 6px;
                border: 1px solid {ThemeColors.BORDER_CARD};
                background: {ThemeColors.BG_PANEL};
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {ThemeColors.BG_CARD_HOVER};
                border-color: {ThemeColors.ACCENT_CYAN};
            }}
        """)
        self.btn_card_update.clicked.connect(self.run_self_update)
        actions_layout.addWidget(self.btn_card_update)

        self.btn_link_github = QPushButton("🔗 GitHub-Repo & Token...")
        self.btn_link_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_link_github.setStyleSheet(f"""
            QPushButton {{
                padding: 5px 10px;
                border-radius: 5px;
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                background: rgba(255, 255, 255, 0.04);
                color: {ThemeColors.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.08);
                color: {ThemeColors.TEXT_PRIMARY};
            }}
        """)
        self.btn_link_github.clicked.connect(self.configure_github_repo)
        actions_layout.addWidget(self.btn_link_github)

        c_layout.addLayout(actions_layout)
        layout.addWidget(card)

        # Release Highlights Box
        self.box_highlights = QFrame()
        self.box_highlights.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.BG_PANEL};
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        hl_layout = QVBoxLayout(self.box_highlights)
        hl_layout.setSpacing(6)

        lbl_hl_title = QLabel("Aktuelle Versionshinweise & Highlights:")
        lbl_hl_title.setStyleSheet(f"font-weight: 700; font-size: 12px; color: {ThemeColors.ACCENT_CYAN};")
        hl_layout.addWidget(lbl_hl_title)

        self.lbl_hl_content = QLabel("Lade Informationen...")
        self.lbl_hl_content.setStyleSheet(f"color: {ThemeColors.TEXT_PRIMARY}; font-size: 11px;")
        self.lbl_hl_content.setWordWrap(True)
        hl_layout.addWidget(self.lbl_hl_content)

        layout.addWidget(self.box_highlights)
        layout.addStretch()

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.tab_status)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    def _init_changelog_tab(self):
        layout = QVBoxLayout(self.tab_changelog)
        layout.setContentsMargins(12, 12, 12, 12)

        self.txt_changelog = QTextBrowser()
        self.txt_changelog.setOpenExternalLinks(True)
        self.txt_changelog.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {ThemeColors.BG_PANEL};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 8px;
                padding: 14px;
                font-size: 12px;
                line-height: 1.6;
            }}
        """)
        self.txt_changelog.setMarkdown(self.load_changelog())
        layout.addWidget(self.txt_changelog)

    def _init_log_tab(self):
        layout = QVBoxLayout(self.tab_log)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        log_header = QHBoxLayout()
        lbl_out = QLabel("Live-Befehlsausgabe:")
        lbl_out.setStyleSheet(f"font-weight: 600; font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        log_header.addWidget(lbl_out)
        log_header.addStretch()

        btn_clear = QPushButton("Log leeren")
        btn_clear.setStyleSheet("font-size: 10px; padding: 3px 8px;")
        btn_clear.clicked.connect(lambda: self.txt_log.clear())
        log_header.addWidget(btn_clear)
        layout.addLayout(log_header)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setFont(QFont("JetBrains Mono, monospace", 9))
        self.txt_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: #080c10;
                color: #e2e8f0;
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.txt_log, stretch=1)

    def load_changelog(self) -> str:
        content = ""
        if self.latest_info and self.latest_info.github_release_notes:
            content += (
                f"# Neuestes GitHub-Release (v{self.latest_info.app_remote})\n\n"
                f"{self.latest_info.github_release_notes}\n\n---\n\n"
            )

        source_dir = get_source_root()
        candidates = [
            os.path.join(source_dir, "CHANGELOG.md"),
            os.path.join(source_dir, "gaming_center", "resources", "CHANGELOG.md"),
            "/usr/share/gaming-center/CHANGELOG.md",
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        content += f.read()
                        return content
                except Exception:
                    pass

        if content:
            return content

        return f"# Gaming Center v{gaming_center.__version__}\n\nKein lokales Changelog gefunden."

    def start_check(self):
        self.btn_refresh.setEnabled(False)
        self.btn_update_now.setEnabled(False)
        self.progress_bar.setVisible(True)

        self.badge_status.setText("Prüfe...")
        self.badge_status.setStyleSheet(f"""
            background-color: rgba(56, 189, 248, 0.15);
            color: {ThemeColors.ACCENT_CYAN};
            padding: 5px 12px;
            border-radius: 6px;
            font-weight: 700;
            font-size: 11px;
        """)

        self.lbl_status_summary.setText("Überprüfe neueste Versionen auf GitHub...")

        self.checker_worker = UpdateCheckerWorker()
        self.checker_worker.finished.connect(self.on_check_finished)
        self.checker_worker.start()

    def on_check_finished(self, info: UpdateInfo):
        self.btn_refresh.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.latest_info = info

        # Handle Auth/Error cases
        if info.github_auth_error:
            self.lbl_app_version.setText(f"Installiert: v{info.app_installed}  │  Remote: Nicht abrufbar (404/Privat)")
            self.lbl_app_github.setText(f"GitHub: {info.github_error_message or 'Repository ist privat'}")
            self.lbl_app_github.setStyleSheet(f"color: {ThemeColors.ACCENT_RED}; font-size: 11px;")
            self.badge_status.setText("⚠️ Token erforderlich")
            self.badge_status.setStyleSheet(f"""
                background-color: rgba(245, 158, 11, 0.15);
                color: {ThemeColors.ACCENT_AMBER};
                padding: 5px 12px;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
            """)
            self.lbl_hl_content.setText(
                "Das GitHub-Repository ist privat oder erfordert Authentifizierung. "
                "Klicke auf '🔗 GitHub-Repo & Token...', um dein GitHub Personal Access Token (PAT) einzutragen."
            )
            self.lbl_status_summary.setText("GitHub-Authentifizierung erforderlich.")
            return

        if info.check_error:
            self.lbl_app_github.setText(f"Fehler: {info.check_error}")
            self.lbl_app_github.setStyleSheet(f"color: {ThemeColors.ACCENT_AMBER}; font-size: 11px;")
            self.badge_status.setText("⚠️ Fehler")
            self.lbl_hl_content.setText(f"Fehler beim Abrufen der Release-Daten: {info.check_error}")
            self.lbl_status_summary.setText(info.check_error)
            return

        # Normal response
        self.lbl_app_github.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED}; font-size: 11px;")
        if info.github_repo:
            self.lbl_app_github.setText(f"GitHub: https://github.com/{info.github_repo} (v{info.app_remote})")

        if info.app_has_update:
            self.lbl_app_version.setText(f"Installiert: v{info.app_installed}  │  Verfügbar: v{info.app_remote}")
            self.badge_status.setText(f"🚀 Update auf v{info.app_remote} verfügbar")
            self.badge_status.setStyleSheet(f"""
                background-color: rgba(245, 158, 11, 0.15);
                color: {ThemeColors.ACCENT_AMBER};
                padding: 5px 12px;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid rgba(245, 158, 11, 0.3);
            """)
            self.btn_update_now.setEnabled(True)
            self.btn_update_now.setText(f"🚀  Update auf v{info.app_remote}")
            self.btn_card_update.setText(f"Auf v{info.app_remote} aktualisieren")
            self.btn_card_update.setStyleSheet(f"""
                QPushButton {{
                    padding: 6px 14px;
                    border-radius: 6px;
                    border: 1px solid {ThemeColors.ACCENT_GREEN};
                    background: {ThemeColors.ACCENT_GREEN};
                    color: #04100c;
                    font-size: 11px;
                    font-weight: 800;
                }}
                QPushButton:hover {{ background: #00f0a8; }}
            """)
            self.lbl_status_summary.setText(f"Neue Version v{info.app_remote} verfügbar!")

            if info.github_release_notes:
                preview = info.github_release_notes.strip()
                if len(preview) > 300:
                    preview = preview[:300] + "...\n(Details im Tab 'Changelog')"
                self.lbl_hl_content.setText(preview)
            else:
                self.lbl_hl_content.setText(f"Release v{info.app_remote} steht zum Download bereit.")

        else:
            self.lbl_app_version.setText(f"Installiert: v{info.app_installed}  │  Neueste Version: v{info.app_remote}")
            self.badge_status.setText("✓ Aktuell")
            self.badge_status.setStyleSheet(f"""
                background-color: rgba(0, 212, 148, 0.12);
                color: {ThemeColors.ACCENT_GREEN};
                padding: 5px 12px;
                border-radius: 6px;
                font-weight: 700;
                font-size: 11px;
                border: 1px solid rgba(0, 212, 148, 0.3);
            """)
            self.btn_update_now.setEnabled(False)
            self.btn_card_update.setText("Neu installieren")
            self.lbl_status_summary.setText("Gaming Center ist auf dem neuesten Stand.")
            self.lbl_hl_content.setText("Du verwendest die aktuellste Version von Gaming Center.")

        # Update Changelog Tab
        self.txt_changelog.setMarkdown(self.load_changelog())

    def configure_github_repo(self):
        curr = get_github_repo() or ""
        repo, ok = QInputDialog.getText(
            self,
            "GitHub-Repository verknüpfen",
            "Gib dein GitHub-Repository im Format 'Benutzername/Repository' ein:\n"
            "(z. B. lenzi96/gaming-center oder vollständige HTTPS-URL):",
            text=curr,
        )
        if ok and repo.strip():
            set_github_repo(repo.strip())
            curr_token = get_github_token() or ""
            masked_token = (curr_token[:8] + "..." + curr_token[-4:]) if len(curr_token) > 12 else curr_token
            tok, tok_ok = QInputDialog.getText(
                self,
                "GitHub Access Token (optional)",
                "Gib dein GitHub Personal Access Token (PAT) ein\n"
                "(Erforderlich für private Repositories, optional für öffentliche Repositories):\n"
                f"Aktuell hinterlegt: {masked_token if masked_token else 'Keins'}",
                text=curr_token,
            )
            if tok_ok:
                set_github_token(tok.strip())

            active_repo = get_github_repo()
            QMessageBox.information(
                self,
                "GitHub verknüpft",
                f"Das Update-Center ist jetzt mit folgendem Repository verknüpft:\nhttps://github.com/{active_repo}\n\nUpdates werden künftig direkt von dort bezogen.",
            )
            self.start_check()

    def run_self_update(self):
        source_dir = get_source_root()
        installer = os.path.join(source_dir, "install.sh")

        steps: List[UpdateStep] = []

        if os.path.exists(installer) and os.path.isdir(os.path.join(source_dir, ".git")):
            # Developer git repository: pull and install
            try:
                res = subprocess.run(["git", "-C", source_dir, "remote"], capture_output=True, text=True, check=False)
                if "origin" in res.stdout:
                    steps.append(
                        UpdateStep(
                            "GitHub Quellcode synchronisieren (git pull)",
                            ["git", "-C", source_dir, "pull", "--rebase"],
                            "Aktualisiere lokale Dateien vom GitHub-Repository",
                        )
                    )
            except Exception:
                pass
            steps.append(
                UpdateStep(
                    "Gaming Center Installation",
                    ["bash", installer],
                    "Führe Installationsskript aus",
                )
            )
        else:
            # Standalone package installation: download release tarball & install
            ver = self.latest_info.app_remote if self.latest_info else gaming_center.__version__
            asset_url = self.latest_info.github_asset_api_url if self.latest_info else ""
            tarball_url = self.latest_info.github_tarball_url if self.latest_info else ""
            tok = get_github_token()

            main_script = os.path.join(source_dir, "main.py")
            cmd = [
                sys.executable,
                main_script if os.path.exists(main_script) else "-m",
            ]
            if not os.path.exists(main_script):
                cmd.append("gaming_center.backend.updater")

            cmd.extend([
                "--download-and-install",
                "--version",
                ver,
                "--asset-url",
                asset_url or "",
                "--tarball-url",
                tarball_url or "",
            ])
            if tok:
                cmd.extend(["--token", tok])

            steps.append(
                UpdateStep(
                    f"Gaming Center v{ver} herunterladen & installieren",
                    cmd,
                    "Lädt das offizielle GitHub Release-Archiv herunter und installiert die Version",
                )
            )

        self.execute_batch_steps(steps)

    def execute_batch_steps(self, steps: List[UpdateStep]):
        self.btn_refresh.setEnabled(False)
        self.btn_update_now.setEnabled(False)
        self.btn_card_update.setEnabled(False)
        self.btn_cancel.setVisible(True)
        self.progress_bar.setVisible(True)

        # Switch to Terminal Log tab
        self.tabs.setCurrentIndex(2)

        self.batch_worker = BatchUpdateWorker(steps)
        self.batch_worker.step_started.connect(self.on_step_started)
        self.batch_worker.output_line.connect(self.on_log_line)
        self.batch_worker.all_completed.connect(self.on_batch_completed)
        self.batch_worker.start()

    def cancel_active_process(self):
        if self.batch_worker:
            self.batch_worker.cancel()
            self.btn_cancel.setEnabled(False)

    def on_step_started(self, current: int, total: int, title: str):
        self.lbl_status_summary.setText(f"Führe aus ({current}/{total}): {title}...")

    def on_log_line(self, line: str):
        cursor = self.txt_log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(line + "\n")
        self.txt_log.setTextCursor(cursor)
        self.txt_log.ensureCursorVisible()

    def on_batch_completed(self, success: bool, message: str):
        self.progress_bar.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self.btn_refresh.setEnabled(True)
        self.btn_card_update.setEnabled(True)

        self.lbl_status_summary.setText(message)

        if success:
            self.txt_log.append(f"\n[✓] {message}\n")
            reply = QMessageBox.question(
                self,
                "Update abgeschlossen - Neustart?",
                "Gaming Center wurde erfolgreich aktualisiert!\n\n"
                "Möchten Sie die Anwendung jetzt neu starten, um die Änderungen zu übernehmen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.restart_application()
        else:
            self.txt_log.append(f"\n[✗] {message}\n")
            QMessageBox.warning(
                self,
                "Hinweis",
                f"{message}\n\nDetails finden Sie im Installations-Log-Reiter.",
            )

        self.start_check()

    def restart_application(self):
        """Cleanly restarts Gaming Center."""
        launcher = shutil.which("gaming-center") or sys.executable
        if launcher == sys.executable:
            QProcess.startDetached(sys.executable, sys.argv)
        else:
            QProcess.startDetached(launcher, [])
        QApplication.quit()
