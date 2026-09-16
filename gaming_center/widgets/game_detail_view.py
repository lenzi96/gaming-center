"""Comprehensive game detail view with PCGamingWiki tabs, paths, fixes, and backups."""

import os
import subprocess
from typing import List, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QPixmap, QDesktopServices, QClipboard
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QScrollArea,
    QFrame,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QApplication,
)
from ..backend.game_scanner import GameInfo
from ..backend.pcgw_client import PCGWClient, PCGWData, PCGWDownload
from ..backend.path_resolver import PathResolver, ResolvedPath
from ..backend.savegame_manager import SavegameManager, BackupInfo
from ..backend.launch_builder import LaunchOptionBuilder, LaunchConfig
from ..backend.translator import Translator
from .download_dialog import DownloadDialog
from ..style.theme import ThemeColors


class PCGWFetchThread(QThread):
    finished_data = pyqtSignal(object, object, list, list, list) # game, pcgw_data, saves, configs, fast_fixes
    single_fix_translated = pyqtSignal(object, int, object)      # game, index, translated_fix
    translation_ready = pyqtSignal(object, list)                 # game, translated_fixes

    def __init__(self, game: GameInfo, client: PCGWClient, translator: Translator):
        super().__init__()
        self.game = game
        self.client = client
        self.translator = translator

    def run(self):
        pcgw_data = None
        # 1. Try search by title
        results = self.client.search_game(self.game.name)
        if results:
            best_title, _ = results[0]
            pcgw_data = self.client.fetch_game_data(best_title)

        # 2. If not found or empty, try exact name
        if not pcgw_data:
            pcgw_data = self.client.fetch_game_data(self.game.name)

        # 3. Resolve paths
        saves = []
        configs = []
        if pcgw_data:
            saves = PathResolver.resolve_paths(self.game, pcgw_data.save_paths_windows, "save")
            configs = PathResolver.resolve_paths(self.game, pcgw_data.config_paths_windows, "config")

        # 4. Instant Fast-Translation pass (Dictionary + Disk Cache, 0 ms)
        fast_fixes = []
        pending_indices = []
        if pcgw_data and pcgw_data.fixes:
            for idx, f in enumerate(pcgw_data.fixes):
                tf, fully_done = self.translator.translate_fix_fast(f)
                fast_fixes.append(tf)
                if not fully_done:
                    pending_indices.append(idx)

        # Emit main data with instant German translations so user never sees English when DE is selected
        self.finished_data.emit(self.game, pcgw_data, saves, configs, fast_fixes)

        # 5. Full text translation in background for pending fixes
        if pcgw_data and pcgw_data.fixes:
            if not pending_indices:
                self.translation_ready.emit(self.game, fast_fixes)
                return

            current_fixes = list(fast_fixes)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            try:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_idx = {
                        executor.submit(self.translator.translate_fix, pcgw_data.fixes[i]): i
                        for i in pending_indices
                    }
                    for future in as_completed(future_to_idx):
                        idx = future_to_idx[future]
                        tf = future.result()
                        current_fixes[idx] = tf
                        self.single_fix_translated.emit(self.game, idx, tf)

                self.translation_ready.emit(self.game, current_fixes)
            except Exception:
                self.translation_ready.emit(self.game, current_fixes)


class GameDetailView(QWidget):
    back_clicked = pyqtSignal()

    def __init__(self, pcgw_client: PCGWClient, save_manager: SavegameManager, parent: QWidget = None):
        super().__init__(parent)
        self.pcgw_client = pcgw_client
        self.save_manager = save_manager
        self.translator = Translator()
        self.game: Optional[GameInfo] = None
        self.pcgw_data: Optional[PCGWData] = None
        self.resolved_saves: List[ResolvedPath] = []
        self.resolved_configs: List[ResolvedPath] = []
        self.translated_fixes: List[PCGWFix] = []
        self.launch_config = LaunchConfig()
        self.fetch_thread: Optional[PCGWFetchThread] = None

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(16)

        # 1. Back button & Top row
        top_row = QHBoxLayout()
        self.back_btn = QPushButton("← Zurück zur Bibliothek")
        self.back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.BG_PANEL};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 13px;
                color: {ThemeColors.TEXT_ACCENT};
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.BG_CARD_HOVER};
                border-color: {ThemeColors.ACCENT_GREEN};
                color: #ffffff;
            }}
        """)
        self.back_btn.clicked.connect(self.back_clicked.emit)
        top_row.addWidget(self.back_btn)
        top_row.addStretch()

        self.launch_btn = QPushButton("▶️  Spiel starten")
        self.launch_btn.setProperty("class", "primary-btn")
        self.launch_btn.clicked.connect(self._launch_game)
        top_row.addWidget(self.launch_btn)

        main_layout.addLayout(top_row)

        # 2. Header Hero Card
        self.hero_card = QFrame()
        self.hero_card.setObjectName("GameCard")
        hero_layout = QHBoxLayout(self.hero_card)
        hero_layout.setContentsMargins(16, 16, 16, 16)
        hero_layout.setSpacing(20)

        # Thumbnail
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(110, 150)
        self.thumb_label.setStyleSheet("background-color: #0d131b; border-radius: 6px;")
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.thumb_label)

        # Info Box
        info_box = QVBoxLayout()
        info_box.setSpacing(6)

        self.title_label = QLabel("Spielname")
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #ffffff;")
        info_box.addWidget(self.title_label)

        self.meta_label = QLabel("Plattform • AppID • Installation")
        self.meta_label.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY};")
        info_box.addWidget(self.meta_label)

        self.prefix_label = QLabel("Prefix: Nicht gefunden")
        self.prefix_label.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_MUTED};")
        info_box.addWidget(self.prefix_label)

        # Web links
        links_row = QHBoxLayout()
        links_row.setSpacing(10)

        self.pcgw_link_btn = QPushButton("🌐 PCGamingWiki")
        self.pcgw_link_btn.clicked.connect(self._open_pcgw_url)
        links_row.addWidget(self.pcgw_link_btn)

        self.protondb_btn = QPushButton("🌐 ProtonDB")
        self.protondb_btn.clicked.connect(self._open_protondb)
        links_row.addWidget(self.protondb_btn)

        self.steamdb_btn = QPushButton("🌐 SteamDB")
        self.steamdb_btn.clicked.connect(self._open_steamdb)
        links_row.addWidget(self.steamdb_btn)

        links_row.addStretch()
        info_box.addLayout(links_row)

        hero_layout.addLayout(info_box, stretch=1)
        main_layout.addWidget(self.hero_card)

        # 3. Tabs
        self.tabs = QTabWidget()
        self.tab_paths = QWidget()
        self.tab_fixes = QWidget()
        self.tab_features = QWidget()
        self.tab_tuning = QWidget()
        self.tab_backups = QWidget()

        self._setup_tab_paths()
        self._setup_tab_fixes()
        self._setup_tab_features()
        self._setup_tab_tuning()
        self._setup_tab_backups()

        self.tabs.addTab(self.tab_paths, "📁 Pfade & Ordner")
        self.tabs.addTab(self.tab_fixes, "⚡ PCGW Fixes & Optimierungen")
        self.tabs.addTab(self.tab_features, "✨ Feature-Matrix")
        self.tabs.addTab(self.tab_tuning, "🚀 Startoptionen & Tuning")
        self.tabs.addTab(self.tab_backups, "💾 Spielstand-Backups")

        main_layout.addWidget(self.tabs, stretch=1)

    def load_game(self, game: GameInfo):
        """Loads and displays game details."""
        self.game = game
        self.title_label.setText(game.name)

        # Meta string
        meta_parts = [game.platform.upper()]
        if game.app_id:
            meta_parts.append(f"AppID: {game.app_id}")
        if game.size_mb > 0:
            meta_parts.append(game.formatted_size)
        self.meta_label.setText(" • ".join(meta_parts))

        # Prefix string
        if game.has_prefix:
            self.prefix_label.setText(f"📁 Proton Prefix: {game.prefix_dir}")
            self.prefix_label.setStyleSheet(f"font-size: 11px; color: {ThemeColors.ACCENT_GREEN};")
        else:
            self.prefix_label.setText("📁 Proton Prefix: Kein aktiver Präfix gefunden")
            self.prefix_label.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_MUTED};")

        # Thumbnail
        img_path = game.poster_image or game.banner_image
        if img_path and os.path.isfile(img_path):
            pix = QPixmap(img_path)
            if not pix.isNull():
                self.thumb_label.setPixmap(pix.scaled(
                    110, 150, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
                ))
        else:
            self.thumb_label.clear()

        # Update external links visibility
        is_steam = game.platform == "steam" and game.app_id.isdigit()
        self.protondb_btn.setVisible(is_steam)
        self.steamdb_btn.setVisible(is_steam)

        # Clear tabs content while loading
        self._clear_dynamic_views()

        # Start asynchronous PCGW data fetch
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.terminate()
            self.fetch_thread.wait()

        self.translated_fixes = []
        self.fetch_thread = PCGWFetchThread(game, self.pcgw_client, self.translator)
        self.fetch_thread.finished_data.connect(self._on_pcgw_data_loaded)
        self.fetch_thread.single_fix_translated.connect(self._on_single_fix_translated)
        self.fetch_thread.translation_ready.connect(self._on_translation_ready)
        self.fetch_thread.start()

        # Refresh backups list
        self._refresh_backups_table()

    def _clear_dynamic_views(self):
        # Clear paths tab
        while self.paths_container_layout.count():
            item = self.paths_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear fixes tab
        while self.fixes_container_layout.count():
            item = self.fixes_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Clear features
        while self.features_grid.count():
            item = self.features_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        loading_lbl = QLabel("⏳ Lade Daten von PCGamingWiki...")
        loading_lbl.setStyleSheet(f"font-size: 13px; color: {ThemeColors.TEXT_SECONDARY}; padding: 20px;")
        self.paths_container_layout.addWidget(loading_lbl)

        fixes_loading_lbl = QLabel("⏳ Lade Fixes & Anleitungen von PCGamingWiki...")
        fixes_loading_lbl.setStyleSheet(f"font-size: 13px; color: {ThemeColors.TEXT_SECONDARY}; padding: 20px;")
        self.fixes_container_layout.addWidget(fixes_loading_lbl)

    def _on_pcgw_data_loaded(
        self,
        game: GameInfo,
        pcgw_data: Optional[PCGWData],
        saves: List[ResolvedPath],
        configs: List[ResolvedPath],
        fast_fixes: List[PCGWFix]
    ):
        if self.game != game:
            return

        self.pcgw_data = pcgw_data
        self.resolved_saves = saves
        self.resolved_configs = configs
        self.translated_fixes = fast_fixes
        self.is_translating = True if (pcgw_data and pcgw_data.fixes) else False

        # Populate Tab 1: Paths
        self._populate_paths_tab()

        # Populate Tab 2: Fixes (immediately in German via instant dictionary & cache!)
        self._populate_fixes_tab()

        # Populate Tab 3: Features
        self._populate_features_tab()

        # Pre-fill custom arguments if any from PCGW
        if pcgw_data and pcgw_data.command_line_arguments:
            self.custom_args_edit.setText(" ".join(pcgw_data.command_line_arguments))
            self._update_launch_preview()

    def _on_single_fix_translated(self, game: GameInfo, idx: int, translated_fix: PCGWFix):
        if self.game != game:
            return
        if idx < len(self.translated_fixes):
            self.translated_fixes[idx] = translated_fix

        # If user is currently viewing German mode, update card in real time
        if self.btn_translate_toggle.isChecked() and hasattr(self, "fix_card_widgets") and idx < len(self.fix_card_widgets):
            card_info = self.fix_card_widgets[idx]
            if card_info.get("title_lbl"):
                card_info["title_lbl"].setText(translated_fix.title)
            if card_info.get("desc_lbl") and translated_fix.description:
                card_info["desc_lbl"].setText(translated_fix.description)
                card_info["desc_lbl"].setVisible(True)

            text_to_show = translated_fix.instructions or translated_fix.description
            inst_box = card_info.get("inst_box")
            if inst_box and text_to_show:
                inst_box.setText(text_to_show)
                inst_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                inst_box.setStyleSheet(f"""
                    background-color: {ThemeColors.BG_INPUT};
                    border: 1px solid {ThemeColors.BORDER_SUBTLE};
                    border-radius: 6px;
                    padding: 10px 12px;
                    color: {ThemeColors.TEXT_PRIMARY};
                    font-size: 12px;
                    font-family: "DejaVu Sans Mono", "Cantarell", monospace;
                """)

            # If copy button didn't exist (because instruction was loading), create it
            act_layout = card_info.get("act_layout")
            if act_layout and text_to_show and not card_info.get("copy_btn"):
                copy_btn = QPushButton("📋 Anleitung kopieren")
                copy_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                copy_btn.clicked.connect(
                    lambda _, text=text_to_show, btn=copy_btn: self._copy_text_with_feedback(text, btn)
                )
                act_layout.addWidget(copy_btn)
                card_info["copy_btn"] = copy_btn
            elif card_info.get("copy_btn") and text_to_show:
                try:
                    card_info["copy_btn"].clicked.disconnect()
                except Exception:
                    pass
                card_info["copy_btn"].clicked.connect(
                    lambda _, text=text_to_show, btn=card_info["copy_btn"]: self._copy_text_with_feedback(text, btn)
                )

    def _on_translation_ready(self, game: GameInfo, translated_fixes: List[PCGWFix]):
        if self.game != game:
            return
        self.translated_fixes = translated_fixes
        self.is_translating = False
        if hasattr(self, "progress_banner") and self.progress_banner:
            self.progress_banner.hide()
        if self.btn_translate_toggle.isChecked():
            # Refresh to ensure complete consistency
            self._populate_fixes_tab()

    # -------------------------------------------------------------
    # TAB 1: PATHS & FOLDERS
    # -------------------------------------------------------------
    def _setup_tab_paths(self):
        layout = QVBoxLayout(self.tab_paths)
        layout.setContentsMargins(12, 12, 12, 12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self.paths_container_layout = QVBoxLayout(container)
        self.paths_container_layout.setContentsMargins(4, 4, 4, 4)
        self.paths_container_layout.setSpacing(12)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _populate_paths_tab(self):
        while self.paths_container_layout.count():
            item = self.paths_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 1. System Directories
        sys_frame = self._create_path_card(
            title="System: Installations- & Prefix-Ordner",
            original="Systemverzeichnisse",
            resolved=self.game.install_dir or "Nicht angegeben",
            folder=self.game.install_dir,
            exists=os.path.isdir(self.game.install_dir) if self.game.install_dir else False,
            extra_btn_text="Prefix öffnen",
            extra_btn_action=lambda: self._open_folder(self.game.prefix_dir) if self.game.has_prefix else None
        )
        self.paths_container_layout.addWidget(sys_frame)

        # 2. Savegame Locations
        saves_header = QLabel("💾 Spielstand-Verzeichnisse (Savegames)")
        saves_header.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {ThemeColors.ACCENT_GREEN}; margin-top: 10px;")
        self.paths_container_layout.addWidget(saves_header)

        if not self.resolved_saves:
            no_saves = QLabel("Keine spezifischen Speicherpfade in PCGamingWiki hinterlegt.")
            no_saves.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED};")
            self.paths_container_layout.addWidget(no_saves)
        else:
            for r in self.resolved_saves:
                card = self._create_path_card(
                    title=f"{r.label}",
                    original=f"PCGW: {r.original}",
                    resolved=r.resolved_path,
                    folder=r.folder_path,
                    exists=r.exists,
                    is_save=True
                )
                self.paths_container_layout.addWidget(card)

        # 3. Config Locations
        configs_header = QLabel("⚙️ Konfigurations-Dateien & Ordner")
        configs_header.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {ThemeColors.ACCENT_CYAN}; margin-top: 10px;")
        self.paths_container_layout.addWidget(configs_header)

        if not self.resolved_configs:
            no_cfg = QLabel("Keine spezifischen Konfigurationspfade in PCGamingWiki hinterlegt.")
            no_cfg.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED};")
            self.paths_container_layout.addWidget(no_cfg)
        else:
            for r in self.resolved_configs:
                card = self._create_path_card(
                    title=f"{r.label}",
                    original=f"PCGW: {r.original}",
                    resolved=r.resolved_path,
                    folder=r.folder_path,
                    exists=r.exists,
                    is_save=False
                )
                self.paths_container_layout.addWidget(card)

        self.paths_container_layout.addStretch()

    def _create_path_card(
        self,
        title: str,
        original: str,
        resolved: str,
        folder: str,
        exists: bool,
        is_save: bool = False,
        extra_btn_text: str = "",
        extra_btn_action = None
    ) -> QFrame:
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        v_layout = QVBoxLayout(card)
        v_layout.setSpacing(6)

        # Top row: Title + Status Pill
        row1 = QHBoxLayout()
        t_label = QLabel(title)
        t_label.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {ThemeColors.TEXT_PRIMARY};")
        row1.addWidget(t_label)

        status_pill = QLabel("Gefunden" if exists else "Prefix-Vorlage")
        if exists:
            status_pill.setStyleSheet("background-color: rgba(0, 212, 148, 0.2); color: #00d494; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
        else:
            status_pill.setStyleSheet("background-color: rgba(148, 163, 184, 0.15); color: #94a3b8; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
        row1.addWidget(status_pill)
        row1.addStretch()
        v_layout.addLayout(row1)

        # Original PCGW path
        orig_lbl = QLabel(original)
        orig_lbl.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_MUTED};")
        v_layout.addWidget(orig_lbl)

        # Resolved Linux path
        path_box = QLineEdit(resolved)
        path_box.setReadOnly(True)
        path_box.setStyleSheet(f"font-family: monospace; font-size: 11px; background-color: {ThemeColors.BG_INPUT}; padding: 6px 8px;")
        v_layout.addWidget(path_box)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        open_btn = QPushButton("📂 Ordner öffnen")
        open_btn.setEnabled(bool(folder and os.path.exists(folder)))
        open_btn.clicked.connect(lambda: self._open_folder(folder))
        btn_row.addWidget(open_btn)

        copy_btn = QPushButton("📋 Pfad kopieren")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(resolved))
        btn_row.addWidget(copy_btn)

        if is_save and exists:
            backup_btn = QPushButton("💾 1-Klick Backup")
            backup_btn.setProperty("class", "primary-btn")
            backup_btn.clicked.connect(lambda: self._create_instant_backup(folder))
            btn_row.addWidget(backup_btn)

        if extra_btn_text and extra_btn_action:
            ext_btn = QPushButton(extra_btn_text)
            ext_btn.clicked.connect(extra_btn_action)
            btn_row.addWidget(ext_btn)

        btn_row.addStretch()
        v_layout.addLayout(btn_row)

        return card

    # -------------------------------------------------------------
    # TAB 2: PCGW FIXES & IMPROVEMENTS
    # -------------------------------------------------------------
    def _setup_tab_fixes(self):
        layout = QVBoxLayout(self.tab_fixes)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header bar with Language Toggle
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 0, 4, 8)
        head_title = QLabel("⚡ Problembehebungen & Optimierungen")
        head_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {ThemeColors.ACCENT_GREEN};")
        top_bar.addWidget(head_title)
        top_bar.addStretch()

        self.btn_filter_downloads = QPushButton("📥 Nur Fixes mit Patches/Downloads")
        self.btn_filter_downloads.setCheckable(True)
        self.btn_filter_downloads.setChecked(False)
        self.btn_filter_downloads.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 11px;
                color: {ThemeColors.TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                border-color: {ThemeColors.ACCENT_CYAN};
                color: #ffffff;
            }}
            QPushButton:checked {{
                background-color: rgba(0, 210, 255, 0.15);
                border-color: {ThemeColors.ACCENT_CYAN};
                color: #00d2ff;
            }}
        """)
        self.btn_filter_downloads.toggled.connect(lambda _: self._populate_fixes_tab())
        top_bar.addWidget(self.btn_filter_downloads)

        self.btn_translate_toggle = QPushButton("🇩🇪 Deutsch (Automatisch)")
        self.btn_translate_toggle.setCheckable(True)
        self.btn_translate_toggle.setChecked(True)
        self.btn_translate_toggle.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 12px;
                color: {ThemeColors.ACCENT_GREEN};
            }}
            QPushButton:hover {{
                border-color: {ThemeColors.ACCENT_CYAN};
            }}
            QPushButton:checked {{
                background-color: rgba(0, 212, 148, 0.15);
                border-color: {ThemeColors.ACCENT_GREEN};
                color: #00ffb0;
            }}
        """)
        self.btn_translate_toggle.toggled.connect(self._on_translate_toggle)
        top_bar.addWidget(self.btn_translate_toggle)
        layout.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self.fixes_container_layout = QVBoxLayout(container)
        self.fixes_container_layout.setContentsMargins(4, 4, 4, 4)
        self.fixes_container_layout.setSpacing(12)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _on_translate_toggle(self, checked: bool):
        if checked:
            self.btn_translate_toggle.setText("🇩🇪 Deutsch (Automatisch)")
        else:
            self.btn_translate_toggle.setText("🇬🇧 Original (Englisch)")
        self._populate_fixes_tab()

    def _populate_fixes_tab(self):
        while self.fixes_container_layout.count():
            item = self.fixes_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.fix_card_widgets = []

        use_de = self.btn_translate_toggle.isChecked()
        fixes_to_display = self.translated_fixes if use_de else (self.pcgw_data.fixes if self.pcgw_data else [])

        if hasattr(self, "btn_filter_downloads") and self.btn_filter_downloads.isChecked():
            fixes_to_display = [fx for fx in fixes_to_display if fx.downloads]

        if not fixes_to_display:
            if hasattr(self, "btn_filter_downloads") and self.btn_filter_downloads.isChecked():
                lbl = QLabel("ℹ️ Keine spezifischen Fixes mit Download-Links für dieses Spiel gefunden.")
            elif use_de and self.pcgw_data and self.pcgw_data.fixes and getattr(self, "is_translating", False):
                lbl = QLabel("⏳ Übersetze Anleitungen automatisch auf Deutsch...")
            else:
                lbl = QLabel("Keine spezifischen Fixes für dieses Spiel gefunden oder Wiki-Seite nicht erreichbar.")
            lbl.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED}; padding: 16px;")
            self.fixes_container_layout.addWidget(lbl)
            self.fixes_container_layout.addStretch()
            return

        # Progress banner if German is active and background translation is still running
        if use_de and getattr(self, "is_translating", False):
            self.progress_banner = QLabel("🔄 Titel geladen • Detaillierte deutsche Schritt-für-Schritt-Anleitungen werden abgerufen...")
            self.progress_banner.setStyleSheet(f"font-size: 11px; color: {ThemeColors.ACCENT_AMBER}; background-color: rgba(245, 158, 11, 0.1); border-radius: 4px; padding: 6px 10px;")
            self.fixes_container_layout.addWidget(self.progress_banner)
        else:
            self.progress_banner = None

        for idx, fix in enumerate(fixes_to_display):
            fix_card = QFrame()
            fix_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.BG_CARD};
                    border: 1px solid {ThemeColors.BORDER_CARD};
                    border-radius: 8px;
                    padding: 12px;
                }}
            """)
            fv = QVBoxLayout(fix_card)
            fv.setSpacing(6)

            # Header
            head_row = QHBoxLayout()
            title_lbl = QLabel(fix.title)
            title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
            title_lbl.setWordWrap(True)
            head_row.addWidget(title_lbl, stretch=1)

            if use_de:
                lang_pill = QLabel("DE")
                lang_pill.setStyleSheet("background-color: rgba(0, 212, 148, 0.15); color: #00d494; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 5px;")
                head_row.addWidget(lang_pill)

            type_pill = QLabel(fix.fix_type.upper())
            if fix.fix_type == "intro":
                type_pill.setStyleSheet("background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
            elif fix.fix_type == "crash":
                type_pill.setStyleSheet("background-color: rgba(239, 68, 68, 0.2); color: #f87171; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
            elif fix.fix_type == "performance":
                type_pill.setStyleSheet("background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
            elif fix.fix_type == "video":
                type_pill.setStyleSheet("background-color: rgba(0, 212, 148, 0.2); color: #00d494; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
            else:
                type_pill.setStyleSheet("background-color: rgba(168, 85, 247, 0.2); color: #c084fc; font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
            head_row.addWidget(type_pill)
            fv.addLayout(head_row)

            # Description (if different from title and instructions)
            desc_lbl = None
            if fix.description and fix.description != fix.title and fix.description != fix.instructions:
                desc_lbl = QLabel(fix.description)
                desc_lbl.setWordWrap(True)
                desc_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_MUTED}; margin-bottom: 2px;")
                fv.addWidget(desc_lbl)

            card_info = {
                "title_lbl": title_lbl,
                "desc_lbl": desc_lbl,
                "inst_box": None,
                "act_layout": None,
                "copy_btn": None
            }

            # Instructions
            orig_inst = self.pcgw_data.fixes[idx].instructions if (self.pcgw_data and idx < len(self.pcgw_data.fixes)) else ""
            if use_de and getattr(self, "is_translating", False) and not fix.instructions and orig_inst:
                inst_box = QLabel("⏳ Deutsche Schritt-für-Schritt-Anleitung wird geladen...")
                inst_box.setWordWrap(True)
                inst_box.setStyleSheet(f"""
                    background-color: rgba(245, 158, 11, 0.06);
                    border: 1px dashed rgba(245, 158, 11, 0.3);
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: {ThemeColors.ACCENT_AMBER};
                    font-size: 12px;
                    font-style: italic;
                """)
                fv.addWidget(inst_box)
                card_info["inst_box"] = inst_box

                act_row = QHBoxLayout()
                act_row.addStretch()
                fv.addLayout(act_row)
                card_info["act_layout"] = act_row
            else:
                text_to_show = fix.instructions or fix.description
                if text_to_show:
                    inst_box = QLabel(text_to_show)
                    inst_box.setWordWrap(True)
                    inst_box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                    inst_box.setStyleSheet(f"""
                        background-color: {ThemeColors.BG_INPUT};
                        border: 1px solid {ThemeColors.BORDER_SUBTLE};
                        border-radius: 6px;
                        padding: 10px 12px;
                        color: {ThemeColors.TEXT_PRIMARY};
                        font-size: 12px;
                        font-family: "DejaVu Sans Mono", "Cantarell", monospace;
                    """)
                    fv.addWidget(inst_box)
                    card_info["inst_box"] = inst_box

                    # Action row with copy button
                    act_row = QHBoxLayout()
                    act_row.addStretch()

                    copy_fix_btn = QPushButton("📋 Anleitung kopieren")
                    copy_fix_btn.setStyleSheet("padding: 3px 8px; font-size: 11px;")
                    copy_fix_btn.clicked.connect(
                        lambda _, text=text_to_show, btn=copy_fix_btn: self._copy_text_with_feedback(text, btn)
                    )
                    act_row.addWidget(copy_fix_btn)
                    card_info["act_layout"] = act_row
                    card_info["copy_btn"] = copy_fix_btn
                    fv.addLayout(act_row)

            # Downloads / Fan Patches Section
            if fix.downloads:
                dl_box = QFrame()
                dl_box.setStyleSheet(f"""
                    QFrame {{
                        background-color: rgba(0, 212, 148, 0.04);
                        border: 1px solid rgba(0, 212, 148, 0.25);
                        border-radius: 6px;
                        padding: 8px 10px;
                        margin-top: 4px;
                    }}
                """)
                dl_v = QVBoxLayout(dl_box)
                dl_v.setContentsMargins(0, 0, 0, 0)
                dl_v.setSpacing(6)

                dl_hdr = QLabel("📥 Hinterlegte Fan-Patches & Fixes:")
                dl_hdr.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {ThemeColors.ACCENT_GREEN};")
                dl_v.addWidget(dl_hdr)

                btn_flow = QHBoxLayout()
                btn_flow.setSpacing(8)

                for dl in fix.downloads:
                    if dl.is_direct or dl.source == "GitHub":
                        dl_btn = QPushButton(f"⬇️ {dl.title} ({dl.source})")
                        dl_btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: {ThemeColors.ACCENT_GREEN};
                                color: #0d131c;
                                font-weight: bold;
                                padding: 5px 12px;
                                border-radius: 5px;
                                font-size: 11px;
                            }}
                            QPushButton:hover {{
                                background-color: #00ffb0;
                            }}
                        """)
                    else:
                        dl_btn = QPushButton(f"🌐 {dl.title} ({dl.source})")
                        dl_btn.setStyleSheet(f"""
                            QPushButton {{
                                background-color: rgba(0, 210, 255, 0.15);
                                border: 1px solid {ThemeColors.ACCENT_CYAN};
                                color: #00d2ff;
                                font-weight: bold;
                                padding: 5px 12px;
                                border-radius: 5px;
                                font-size: 11px;
                            }}
                            QPushButton:hover {{
                                background-color: rgba(0, 210, 255, 0.25);
                            }}
                        """)

                    dl_btn.clicked.connect(lambda _, item=dl: self._open_download_dialog(item))
                    btn_flow.addWidget(dl_btn)

                btn_flow.addStretch()
                dl_v.addLayout(btn_flow)
                fv.addWidget(dl_box)

            self.fix_card_widgets.append(card_info)
            self.fixes_container_layout.addWidget(fix_card)

        self.fixes_container_layout.addStretch()

    def _open_download_dialog(self, download: PCGWDownload):
        dialog = DownloadDialog(download, self.game, self)
        dialog.exec()

    # -------------------------------------------------------------
    # TAB 3: FEATURE MATRIX
    # -------------------------------------------------------------
    def _setup_tab_features(self):
        layout = QVBoxLayout(self.tab_features)
        layout.setContentsMargins(16, 16, 16, 16)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        self.features_grid = QHBoxLayout(container)
        self.features_grid.setSpacing(16)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _populate_features_tab(self):
        while self.features_grid.count():
            item = self.features_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.pcgw_data or not self.pcgw_data.features:
            lbl = QLabel("Keine Feature-Matrix verfügbar.")
            lbl.setStyleSheet(f"color: {ThemeColors.TEXT_MUTED};")
            self.features_grid.addWidget(lbl)
            return

        col1 = QVBoxLayout()
        col2 = QVBoxLayout()
        col1.setSpacing(12)
        col2.setSpacing(12)

        items = list(self.pcgw_data.features.items())
        for i, (feat_name, feat_val) in enumerate(items):
            box = QFrame()
            box.setStyleSheet(f"""
                QFrame {{
                    background-color: {ThemeColors.BG_CARD};
                    border: 1px solid {ThemeColors.BORDER_CARD};
                    border-radius: 8px;
                    padding: 12px;
                }}
            """)
            bv = QVBoxLayout(box)
            bv.setSpacing(4)

            name_lbl = QLabel(feat_name)
            name_lbl.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {ThemeColors.TEXT_SECONDARY};")
            bv.addWidget(name_lbl)

            val_lbl = QLabel(feat_val)
            val_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
            bv.addWidget(val_lbl)

            if i % 2 == 0:
                col1.addWidget(box)
            else:
                col2.addWidget(box)

        col1.addStretch()
        col2.addStretch()

        self.features_grid.addLayout(col1, stretch=1)
        self.features_grid.addLayout(col2, stretch=1)

    # -------------------------------------------------------------
    # TAB 4: TUNING & LAUNCH OPTIONS
    # -------------------------------------------------------------
    def _setup_tab_tuning(self):
        layout = QVBoxLayout(self.tab_tuning)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Performance Wrappers
        wrappers_box = QFrame()
        wrappers_box.setStyleSheet(f"background-color: {ThemeColors.BG_CARD}; border-radius: 8px; padding: 10px;")
        wb_layout = QVBoxLayout(wrappers_box)

        self.cb_gamemode = QCheckBox("GameMode aktivieren (gamemoderun %command%)")
        self.cb_gamemode.setChecked(True)
        self.cb_gamemode.stateChanged.connect(self._update_launch_preview)
        wb_layout.addWidget(self.cb_gamemode)

        self.cb_mangohud = QCheckBox("MangoHud Overlay aktivieren (mangohud %command%)")
        self.cb_mangohud.stateChanged.connect(self._update_launch_preview)
        wb_layout.addWidget(self.cb_mangohud)

        layout.addWidget(wrappers_box)

        # Proton & Vulkan Tweaks
        proton_box = QFrame()
        proton_box.setStyleSheet(f"background-color: {ThemeColors.BG_CARD}; border-radius: 8px; padding: 10px;")
        pb_layout = QVBoxLayout(proton_box)

        self.cb_nvapi = QCheckBox("NVIDIA DLSS / Raytracing Support (PROTON_ENABLE_NVAPI=1)")
        self.cb_nvapi.stateChanged.connect(self._update_launch_preview)
        pb_layout.addWidget(self.cb_nvapi)

        self.cb_dxvk_async = QCheckBox("DXVK Shader Pre-Caching / Async (DXVK_ASYNC=1)")
        self.cb_dxvk_async.stateChanged.connect(self._update_launch_preview)
        pb_layout.addWidget(self.cb_dxvk_async)

        self.cb_no_esync = QCheckBox("ESync deaktivieren bei Audio-/Stutter-Problemen (PROTON_NO_ESYNC=1)")
        self.cb_no_esync.stateChanged.connect(self._update_launch_preview)
        pb_layout.addWidget(self.cb_no_esync)

        layout.addWidget(proton_box)

        # Custom arguments
        args_row = QHBoxLayout()
        args_lbl = QLabel("Benutzerdefinierte Argumente:")
        args_lbl.setStyleSheet("font-weight: bold;")
        args_row.addWidget(args_lbl)

        self.custom_args_edit = QLineEdit()
        self.custom_args_edit.setPlaceholderText("-skipintro -novid --launcher-skip")
        self.custom_args_edit.textChanged.connect(self._update_launch_preview)
        args_row.addWidget(self.custom_args_edit)
        layout.addLayout(args_row)

        # Generated Output box
        layout.addWidget(QLabel("Generierte Startoptionen (für Steam / Heroic):"))
        self.preview_box = QLineEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setStyleSheet(f"font-family: monospace; font-size: 12px; background-color: {ThemeColors.BG_INPUT}; padding: 10px;")
        layout.addWidget(self.preview_box)

        # Copy button
        copy_row = QHBoxLayout()
        self.copy_cmd_btn = QPushButton("📋 In Zwischenablage kopieren")
        self.copy_cmd_btn.setProperty("class", "primary-btn")
        self.copy_cmd_btn.clicked.connect(self._copy_launch_command)
        copy_row.addWidget(self.copy_cmd_btn)
        copy_row.addStretch()
        layout.addLayout(copy_row)

        layout.addStretch()
        self._update_launch_preview()

    def _update_launch_preview(self):
        self.launch_config.use_gamemode = self.cb_gamemode.isChecked()
        self.launch_config.use_mangohud = self.cb_mangohud.isChecked()
        self.launch_config.env_vars["PROTON_ENABLE_NVAPI"] = "1" if self.cb_nvapi.isChecked() else "0"
        self.launch_config.env_vars["DXVK_ASYNC"] = "1" if self.cb_dxvk_async.isChecked() else "0"
        self.launch_config.env_vars["PROTON_NO_ESYNC"] = "1" if self.cb_no_esync.isChecked() else "0"

        args_str = self.custom_args_edit.text().strip()
        self.launch_config.custom_args = [args_str] if args_str else []

        cmd = LaunchOptionBuilder.build_command_line(self.launch_config)
        self.preview_box.setText(cmd)

    def _copy_launch_command(self):
        cmd = self.preview_box.text()
        self._copy_to_clipboard(cmd)
        self.copy_cmd_btn.setText("✅ Kopiert!")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self.copy_cmd_btn.setText("📋 In Zwischenablage kopieren"))

    # -------------------------------------------------------------
    # TAB 5: SAVEGAME BACKUPS
    # -------------------------------------------------------------
    def _setup_tab_backups(self):
        layout = QVBoxLayout(self.tab_backups)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Create Backup Controls
        ctrl_card = QFrame()
        ctrl_card.setStyleSheet(f"background-color: {ThemeColors.BG_CARD}; border-radius: 8px; padding: 12px;")
        ctrl_layout = QHBoxLayout(ctrl_card)

        self.backup_note_edit = QLineEdit()
        self.backup_note_edit.setPlaceholderText("Optionale Notiz (z. B. 'Vor Bosskampf' oder 'Vor Patch 2.0')")
        ctrl_layout.addWidget(self.backup_note_edit, stretch=1)

        self.make_backup_btn = QPushButton("💾 Backup jetzt erstellen")
        self.make_backup_btn.setProperty("class", "primary-btn")
        self.make_backup_btn.clicked.connect(self._create_manual_backup)
        ctrl_layout.addWidget(self.make_backup_btn)

        layout.addWidget(ctrl_card)

        # Backups Table
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(4)
        self.backup_table.setHorizontalHeaderLabels(["Datum & Zeit", "Dateiname", "Größe", "Aktionen"])
        self.backup_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.backup_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.backup_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {ThemeColors.BG_PANEL};
                border: 1px solid {ThemeColors.BORDER_SUBTLE};
                border-radius: 6px;
            }}
            QHeaderView::section {{
                background-color: {ThemeColors.BG_CARD};
                color: {ThemeColors.TEXT_SECONDARY};
                font-weight: bold;
                border: none;
                padding: 6px;
            }}
        """)
        layout.addWidget(self.backup_table)

    def _refresh_backups_table(self):
        if not self.game:
            return

        backups = self.save_manager.list_backups(self.game.app_id)
        self.backup_table.setRowCount(len(backups))

        for row, b in enumerate(backups):
            # Date
            item_date = QTableWidgetItem(b.formatted_date)
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.backup_table.setItem(row, 0, item_date)

            # File name & note
            label = b.file_name
            if b.note:
                label += f" ({b.note})"
            item_name = QTableWidgetItem(label)
            self.backup_table.setItem(row, 1, item_name)

            # Size
            item_size = QTableWidgetItem(b.formatted_size)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.backup_table.setItem(row, 2, item_size)

            # Action Buttons
            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 2, 4, 2)
            act_layout.setSpacing(6)

            restore_btn = QPushButton("Wiederherstellen")
            restore_btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
            restore_btn.clicked.connect(lambda _, path=b.file_path: self._restore_backup_prompt(path))
            act_layout.addWidget(restore_btn)

            del_btn = QPushButton("Löschen")
            del_btn.setProperty("class", "danger-btn")
            del_btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
            del_btn.clicked.connect(lambda _, path=b.file_path: self._delete_backup_prompt(path))
            act_layout.addWidget(del_btn)

            self.backup_table.setCellWidget(row, 3, act_widget)

    def _create_manual_backup(self):
        if not self.game:
            return

        # Find best save folder
        target_folder = None
        for r in self.resolved_saves:
            if r.exists and os.path.isdir(r.folder_path):
                target_folder = r.folder_path
                break

        if not target_folder:
            QMessageBox.warning(self, "Backup fehlgeschlagen", "Es wurde kein existierender Spielstand-Ordner gefunden.")
            return

        note = self.backup_note_edit.text().strip()
        info = self.save_manager.create_backup(self.game.app_id, target_folder, note=note)
        if info:
            self.backup_note_edit.clear()
            self._refresh_backups_table()
            QMessageBox.information(self, "Backup erfolgreich", f"Backup erstellt: {info.file_name} ({info.formatted_size})")
        else:
            QMessageBox.warning(self, "Fehler", "Backup konnte nicht erstellt werden.")

    def _create_instant_backup(self, folder: str):
        if not self.game or not folder:
            return
        info = self.save_manager.create_backup(self.game.app_id, folder, note="Schnellsicherung")
        if info:
            self._refresh_backups_table()
            QMessageBox.information(self, "Backup erstellt", f"Spielstand gesichert:\n{info.file_name}")

    def _restore_backup_prompt(self, backup_file: str):
        target_folder = None
        for r in self.resolved_saves:
            if os.path.isdir(r.folder_path):
                target_folder = r.folder_path
                break

        if not target_folder:
            QMessageBox.warning(self, "Fehler", "Ziel-Speicherordner konnte nicht ermittelt werden.")
            return

        reply = QMessageBox.question(
            self,
            "Backup wiederherstellen?",
            f"Möchten Sie diesen Spielstand wirklich in:\n{target_folder}\n\nwiederherstellen? Bestehende Dateien werden überschrieben.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Extract parent of folder
            parent_dir = os.path.dirname(target_folder)
            success = self.save_manager.restore_backup(backup_file, parent_dir)
            if success:
                QMessageBox.information(self, "Wiederhergestellt", "Spielstand erfolgreich wiederhergestellt!")
            else:
                QMessageBox.critical(self, "Fehler", "Fehler bei der Wiederherstellung des Archivs.")

    def _delete_backup_prompt(self, backup_file: str):
        reply = QMessageBox.question(
            self, "Backup löschen?", "Soll dieses Backup unwiderruflich gelöscht werden?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.save_manager.delete_backup(backup_file)
            self._refresh_backups_table()

    # -------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------
    def _open_folder(self, folder_path: str):
        if folder_path and os.path.exists(folder_path):
            subprocess.Popen(["xdg-open", folder_path])

    def _copy_to_clipboard(self, text: str):
        cb = QApplication.clipboard()
        cb.setText(text)

    def _copy_text_with_feedback(self, text: str, btn: QPushButton):
        self._copy_to_clipboard(text)
        old_text = btn.text()
        btn.setText("✅ Kopiert!")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: btn.setText(old_text))

    def _open_pcgw_url(self):
        if self.pcgw_data and self.pcgw_data.pcgw_url:
            QDesktopServices.openUrl(QUrl(self.pcgw_data.pcgw_url))
        elif self.game:
            url = f"https://www.pcgamingwiki.com/wiki/{QUrl.toPercentEncoding(self.game.name)}"
            QDesktopServices.openUrl(QUrl(url))

    def _open_protondb(self):
        if self.game and self.game.app_id:
            url = f"https://www.protondb.com/app/{self.game.app_id}"
            QDesktopServices.openUrl(QUrl(url))

    def _open_steamdb(self):
        if self.game and self.game.app_id:
            url = f"https://steamdb.info/app/{self.game.app_id}/"
            QDesktopServices.openUrl(QUrl(url))

    def _launch_game(self):
        if not self.game:
            return
        if self.game.platform == "steam" and self.game.app_id.isdigit():
            subprocess.Popen(["xdg-open", f"steam://run/{self.game.app_id}"])
        elif self.game.executable and os.path.isfile(self.game.executable):
            subprocess.Popen([self.game.executable])
        else:
            QMessageBox.information(self, "Starten", f"Starte {self.game.name}...")
