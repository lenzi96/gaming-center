"""Interactive download and installation dialog for fan patches, mods, and fixes."""

import os
import subprocess
from typing import Optional
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QComboBox, QFrame, QMessageBox
)

from ..backend.game_scanner import GameInfo
from ..backend.pcgw_client import PCGWDownload
from ..backend.downloader import DownloadWorker, GitHubReleaseResolver, ArchiveExtractor
from ..style.theme import ThemeColors


class GitHubResolveThread(QThread):
    resolved = pyqtSignal(object)  # dict or None

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        res = GitHubReleaseResolver.resolve_latest_asset(self.url)
        self.resolved.emit(res)


class DownloadDialog(QDialog):
    """Modern modal dialog for downloading and extracting fan patches and fixes."""

    def __init__(self, download: PCGWDownload, game: Optional[GameInfo] = None, parent=None):
        super().__init__(parent)
        self.download = download
        self.game = game
        self.download_worker: Optional[DownloadWorker] = None
        self.downloaded_file: Optional[str] = None
        self.resolved_asset: Optional[dict] = None

        self.setWindowTitle("Patch & Fix Downloader")
        self.setMinimumWidth(560)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {ThemeColors.BG_ROOT};
                color: {ThemeColors.TEXT_PRIMARY};
                font-family: "Segoe UI", "Cantarell", sans-serif;
            }}
        """)

        self._setup_ui()
        self._check_and_resolve_source()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Card
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 8px;
                padding: 14px;
            }}
        """)
        hv = QVBoxLayout(header_card)
        hv.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel(self.download.title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        title_lbl.setWordWrap(True)
        title_row.addWidget(title_lbl, stretch=1)

        source_pill = QLabel(self.download.source.upper())
        if self.download.source == "GitHub":
            source_pill.setStyleSheet("background-color: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 3px 8px;")
        elif self.download.source in ("NexusMods", "ModDB"):
            source_pill.setStyleSheet("background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 3px 8px;")
        elif self.download.source == "PCGamingWiki":
            source_pill.setStyleSheet("background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 3px 8px;")
        else:
            source_pill.setStyleSheet("background-color: rgba(0, 212, 148, 0.2); color: #00d494; font-size: 11px; font-weight: bold; border-radius: 4px; padding: 3px 8px;")
        title_row.addWidget(source_pill)
        hv.addLayout(title_row)

        url_lbl = QLabel(self.download.url)
        url_lbl.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_MUTED};")
        url_lbl.setWordWrap(True)
        hv.addWidget(url_lbl)

        layout.addWidget(header_card)

        # Body Container
        self.body_container = QVBoxLayout()
        layout.addLayout(self.body_container)

        # Destination Selection
        dest_label = QLabel("Speicherort für Download:")
        dest_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #ffffff;")
        self.body_container.addWidget(dest_label)

        self.dest_combo = QComboBox()
        self.dest_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {ThemeColors.BG_INPUT};
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 10px;
                color: {ThemeColors.TEXT_PRIMARY};
                font-size: 12px;
            }}
        """)

        # Add destinations
        user_downloads = os.path.expanduser("~/Downloads")
        self.dest_combo.addItem(f"📥 Downloads-Ordner ({user_downloads})", user_downloads)

        if self.game and self.game.install_dir and os.path.isdir(self.game.install_dir):
            self.dest_combo.addItem(f"📁 Spiel-Installationsordner ({self.game.install_dir})", self.game.install_dir)

        if self.game and self.game.has_prefix and os.path.isdir(self.game.prefix_dir):
            prefix_c = os.path.join(self.game.prefix_dir, "drive_c")
            if os.path.isdir(prefix_c):
                self.dest_combo.addItem(f"⚙️ Proton drive_c ({prefix_c})", prefix_c)

        self.body_container.addWidget(self.dest_combo)

        # Status & Progress Box
        self.status_box = QFrame()
        self.status_box.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.BG_INPUT};
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 6px;
                padding: 12px;
            }}
        """)
        sv = QVBoxLayout(self.status_box)
        sv.setSpacing(8)

        self.status_lbl = QLabel("Bereit zum Herunterladen.")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
        sv.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {ThemeColors.BG_ROOT};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00d494, stop:1 #00d2ff);
                border-radius: 4px;
            }}
        """)
        self.progress_bar.setVisible(False)
        sv.addWidget(self.progress_bar)

        self.metrics_lbl = QLabel("")
        self.metrics_lbl.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_MUTED};")
        self.metrics_lbl.setVisible(False)
        sv.addWidget(self.metrics_lbl)

        self.body_container.addWidget(self.status_box)

        # Action Buttons Row
        self.btn_row = QHBoxLayout()
        self.btn_row.setSpacing(8)

        self.btn_action = QPushButton("⬇️ Download starten")
        self.btn_action.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.ACCENT_GREEN};
                color: #0d131c;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: #00ffb0;
            }}
        """)
        self.btn_action.clicked.connect(self._on_action_clicked)
        self.btn_row.addWidget(self.btn_action)

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                color: {ThemeColors.TEXT_PRIMARY};
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.08);
            }}
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_row.addWidget(self.btn_cancel)

        self.body_container.addLayout(self.btn_row)

        # Post-download options container (hidden initially)
        self.post_download_frame = QFrame()
        self.post_download_frame.setVisible(False)
        pv = QHBoxLayout(self.post_download_frame)
        pv.setContentsMargins(0, 4, 0, 0)
        pv.setSpacing(8)

        self.btn_open_folder = QPushButton("📂 Ordner öffnen")
        self.btn_open_folder.setStyleSheet("padding: 7px 12px; font-size: 11px;")
        self.btn_open_folder.clicked.connect(self._open_dest_folder)
        pv.addWidget(self.btn_open_folder)

        self.btn_extract = QPushButton("📦 In Spielordner entpacken")
        self.btn_extract.setStyleSheet("padding: 7px 12px; font-size: 11px;")
        self.btn_extract.clicked.connect(self._extract_to_game)
        pv.addWidget(self.btn_extract)

        self.btn_run_wine = QPushButton("▶️ Setup ausführen (Wine)")
        self.btn_run_wine.setStyleSheet("padding: 7px 12px; font-size: 11px;")
        self.btn_run_wine.clicked.connect(self._run_setup_exe)
        self.btn_run_wine.setVisible(False)
        pv.addWidget(self.btn_run_wine)

        self.body_container.addWidget(self.post_download_frame)

    def _check_and_resolve_source(self):
        """Checks if URL is a GitHub repo and resolves latest release asset."""
        if self.download.source == "GitHub" or GitHubReleaseResolver.is_github_repo_or_release(self.download.url):
            self.status_lbl.setText("🔄 Frage GitHub API nach dem neuesten Release-Asset ab...")
            self.btn_action.setEnabled(False)
            self.resolve_thread = GitHubResolveThread(self.download.url)
            self.resolve_thread.resolved.connect(self._on_github_resolved)
            self.resolve_thread.start()
        elif self.download.source in ("NexusMods", "ModDB"):
            self.status_lbl.setText("ℹ️ Dieser Mod wird auf NexusMods / ModDB gehostet (erfordert Browser-Login zum Download).")
            self.btn_action.setText("🌐 Mod-Seite im Browser öffnen")
            self.btn_action.setStyleSheet(f"""
                QPushButton {{
                    background-color: {ThemeColors.ACCENT_CYAN};
                    color: #0d131c;
                    font-weight: bold;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-size: 12px;
                }}
            """)
        else:
            self.status_lbl.setText("Direkter Download verfügbar.")

    def _on_github_resolved(self, asset: Optional[dict]):
        self.btn_action.setEnabled(True)
        if asset and asset.get("download_url"):
            self.resolved_asset = asset
            size_mb = f"{asset.get('size', 0) / (1024 * 1024):.1f} MB" if asset.get('size') else ""
            tag = asset.get('tag_name', '')
            self.status_lbl.setText(f"✓ Neuestes Release gefunden: {asset.get('filename')} ({tag} {size_mb})")
            self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.ACCENT_GREEN};")
            self.btn_action.setText(f"⬇️ {asset.get('filename')} herunterladen")
        else:
            self.status_lbl.setText("Kein direktes Binär-Release auf GitHub gefunden. Du kannst die Release-Seite im Browser öffnen.")
            self.btn_action.setText("🌐 GitHub-Releases im Browser öffnen")

    def _on_action_clicked(self):
        if "im Browser öffnen" in self.btn_action.text():
            url = self.download.url
            if self.download.source == "GitHub" and not url.endswith("/releases"):
                url = url.rstrip("/") + "/releases"
            QDesktopServices.openUrl(QUrl(url))
            self.accept()
            return

        # Start direct file download
        target_url = self.download.url
        custom_name = None
        if self.resolved_asset:
            target_url = self.resolved_asset.get("download_url")
            custom_name = self.resolved_asset.get("filename")

        dest_dir = self.dest_combo.currentData()

        self.btn_action.setEnabled(False)
        self.btn_cancel.setText("Download abbrechen")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.metrics_lbl.setVisible(True)
        self.status_lbl.setText("⏳ Verbindung wird hergestellt...")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.ACCENT_AMBER};")

        self.download_worker = DownloadWorker(target_url, dest_dir, custom_name)
        self.download_worker.started.connect(self._on_download_started)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.finished.connect(self._on_download_finished)
        self.download_worker.error.connect(self._on_download_error)
        self.download_worker.cancelled.connect(self._on_download_cancelled)
        self.download_worker.start()

    def _on_download_started(self, filename: str, total_bytes: int):
        size_str = f" ({total_bytes / (1024*1024):.1f} MB)" if total_bytes > 0 else ""
        self.status_lbl.setText(f"Lade {filename}{size_str} herunter...")

    def _on_download_progress(self, dl_bytes: int, total_bytes: int, percent: int, speed_str: str, eta_str: str):
        self.progress_bar.setValue(percent)
        dl_mb = dl_bytes / (1024 * 1024)
        total_mb = total_bytes / (1024 * 1024)
        eta_part = f" • Noch {eta_str}" if eta_str else ""
        self.metrics_lbl.setText(f"{dl_mb:.1f} MB / {total_mb:.1f} MB ({percent}%) • {speed_str}{eta_part}")

    def _on_download_finished(self, file_path: str):
        self.downloaded_file = file_path
        self.progress_bar.setValue(100)
        self.status_lbl.setText(f"✓ Erfolgreich heruntergeladen:\n{file_path}")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.ACCENT_GREEN};")
        self.metrics_lbl.setText("Download abgeschlossen.")
        self.btn_action.setVisible(False)
        self.btn_cancel.setText("Schließen")

        # Show post-download actions
        self.post_download_frame.setVisible(True)

        # Check if archive
        is_archive = ArchiveExtractor.is_supported_archive(file_path)
        self.btn_extract.setVisible(is_archive and bool(self.game and self.game.install_dir))

        # Check if exe
        is_exe = file_path.lower().endswith(".exe")
        self.btn_run_wine.setVisible(is_exe)

    def _on_download_error(self, err: str):
        self.status_lbl.setText(f"❌ Download-Fehler: {err}")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.ACCENT_RED};")
        self.btn_action.setEnabled(True)
        self.btn_cancel.setText("Schließen")

    def _on_download_cancelled(self):
        self.status_lbl.setText("Download abgebrochen.")
        self.status_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_MUTED};")
        self.btn_action.setEnabled(True)
        self.btn_cancel.setText("Schließen")

    def _on_cancel_clicked(self):
        if self.download_worker and self.download_worker.isRunning():
            self.download_worker.cancel()
            self.download_worker.wait()
        self.reject()

    def _open_dest_folder(self):
        if self.downloaded_file and os.path.exists(self.downloaded_file):
            folder = os.path.dirname(self.downloaded_file)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _extract_to_game(self):
        if not self.downloaded_file or not self.game or not self.game.install_dir:
            return

        dest = self.game.install_dir
        reply = QMessageBox.question(
            self,
            "Archiv entpacken",
            f"Möchtest du das Archiv wirklich direkt in das Spielverzeichnis entpacken?\n\n{dest}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            success, msg, files = ArchiveExtractor.extract(self.downloaded_file, dest)
            if success:
                QMessageBox.information(
                    self,
                    "Erfolg",
                    f"✓ Patch erfolgreich entpackt!\n\n{msg}\nZiel: {dest}"
                )
            else:
                QMessageBox.critical(self, "Fehler", f"Entpacken fehlgeschlagen: {msg}")

    def _run_setup_exe(self):
        if not self.downloaded_file:
            return

        # Run with Wine or Proton prefix if available
        cmd = ["wine", self.downloaded_file]
        env = os.environ.copy()
        if self.game and self.game.has_prefix:
            env["WINEPREFIX"] = self.game.prefix_dir

        try:
            subprocess.Popen(cmd, env=env)
            QMessageBox.information(
                self,
                "Setup gestartet",
                f"Das Setup wurde im Hintergrund gestartet:\n{self.downloaded_file}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Konnte Wine nicht starten: {e}")
