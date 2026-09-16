"""Main application window for Gaming Center."""

import sys
import time
from typing import List, Optional
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QStackedWidget,
    QScrollArea,
    QFrame,
    QStatusBar,
)
from .backend.game_scanner import GameScanner, GameInfo
from .backend.pcgw_client import PCGWClient
from .backend.savegame_manager import SavegameManager
from .backend.updater import UpdateCheckerWorker, UpdateInfo
from .widgets.game_card import GameCard
from .widgets.game_detail_view import GameDetailView
from .widgets.flow_layout import FlowLayout
from .widgets.update_dialog import UpdateDialog
from .style.theme import ThemeColors, APP_STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gaming Center - Linux Spiele Service Center")
        self.resize(1280, 820)
        self.setMinimumSize(1000, 680)

        # Backend services
        self.scanner = GameScanner()
        self.pcgw_client = PCGWClient()
        self.save_manager = SavegameManager()

        self.all_games: List[GameInfo] = []
        self.filtered_games: List[GameInfo] = []
        self.card_widgets: List[GameCard] = []
        self._bg_updater: Optional[UpdateCheckerWorker] = None

        self._setup_ui()
        self._apply_styles()

        # Initial scan and silent background update check
        QTimer.singleShot(100, self.refresh_library)
        QTimer.singleShot(1500, self.start_background_update_check)

    def _apply_styles(self):
        self.setStyleSheet(APP_STYLESHEET)

    def _setup_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Top Navigation Bar
        self.top_bar = QFrame()
        self.top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(18, 10, 18, 10)
        top_layout.setSpacing(16)

        # App Brand
        brand_box = QVBoxLayout()
        brand_box.setSpacing(1)
        title_lbl = QLabel("Gaming Center")
        title_lbl.setObjectName("AppTitle")
        title_lbl.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ThemeColors.ACCENT_GREEN};")
        sub_lbl = QLabel("Service Hub mit PCGamingWiki Anbindung")
        sub_lbl.setObjectName("AppSubtitle")
        brand_box.addWidget(title_lbl)
        brand_box.addWidget(sub_lbl)
        top_layout.addLayout(brand_box)

        top_layout.addSpacing(20)

        # Search Bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Spiel suchen...")
        self.search_edit.setFixedWidth(260)
        self.search_edit.textChanged.connect(self._apply_filters)
        top_layout.addWidget(self.search_edit)

        # Platform Filter
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["Alle Plattformen", "Steam", "Heroic", "Lutris", "Benutzerdefiniert"])
        self.platform_combo.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.platform_combo)

        # Prefix Filter
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItems(["Alle Spiele", "Nur mit Prefix"])
        self.prefix_combo.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.prefix_combo)

        # Sort Filter
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Kürzlich gespielt", "Name (A-Z)", "Größe (Absteigend)"])
        self.sort_combo.currentIndexChanged.connect(self._apply_filters)
        top_layout.addWidget(self.sort_combo)

        top_layout.addStretch()

        # Refresh button
        self.refresh_btn = QPushButton("🔄 Neu laden")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_library)
        top_layout.addWidget(self.refresh_btn)

        # Updates button
        self.btn_updater = QPushButton("🚀 Updates")
        self.btn_updater.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_updater.setToolTip("Update-Center & GitHub-Releases öffnen")
        self._reset_updater_btn_style()
        self.btn_updater.clicked.connect(self.show_update_dialog)
        top_layout.addWidget(self.btn_updater)

        root_layout.addWidget(self.top_bar)

        # 2. Central Stacked Widget (Library Grid vs Detail View)
        self.stack = QStackedWidget()

        # Page 0: Library Grid
        self.grid_page = QWidget()
        grid_page_layout = QVBoxLayout(self.grid_page)
        grid_page_layout.setContentsMargins(18, 14, 18, 14)
        grid_page_layout.setSpacing(10)

        # Meta summary line
        self.summary_lbl = QLabel("Bibliothek wird geladen...")
        self.summary_lbl.setStyleSheet(f"font-size: 12px; color: {ThemeColors.TEXT_SECONDARY}; font-weight: 500;")
        grid_page_layout.addWidget(self.summary_lbl)

        # Scroll Area for Cards
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.cards_container = QWidget()
        self.cards_layout = FlowLayout(self.cards_container, margin=4, h_spacing=14, v_spacing=16)

        self.scroll_area.setWidget(self.cards_container)
        grid_page_layout.addWidget(self.scroll_area)

        self.stack.addWidget(self.grid_page)

        # Page 1: Detail View
        self.detail_view = GameDetailView(self.pcgw_client, self.save_manager)
        self.detail_view.back_clicked.connect(self._show_library)
        self.stack.addWidget(self.detail_view)

        root_layout.addWidget(self.stack, stretch=1)

        # 3. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Bereit")
        self.status_bar.addWidget(self.status_label)

    def refresh_library(self):
        """Scans installed games and rebuilds grid."""
        self.status_label.setText("Scanne Spiele-Bibliotheken...")
        self.refresh_btn.setEnabled(False)

        games = self.scanner.scan_all()
        self.all_games = games
        self.refresh_btn.setEnabled(True)

        libs_count = len(self.scanner.get_steam_libraries())
        self.status_label.setText(f"{len(games)} Spiele erkannt across {libs_count} Bibliotheken • PCGamingWiki bereit")

        self._apply_filters()

    def _apply_filters(self):
        """Filters and sorts games, then displays cards."""
        query = self.search_edit.text().strip().lower()
        platform_sel = self.platform_combo.currentText().lower()
        prefix_sel = self.prefix_combo.currentText()
        sort_sel = self.sort_combo.currentText()

        filtered = []
        for g in self.all_games:
            # Query match
            if query and query not in g.name.lower():
                continue
            # Platform match
            if platform_sel == "steam" and g.platform != "steam":
                continue
            elif platform_sel == "heroic" and g.platform != "heroic":
                continue
            elif platform_sel == "lutris" and g.platform != "lutris":
                continue
            elif platform_sel == "benutzerdefiniert" and g.platform != "custom":
                continue

            # Prefix filter
            if prefix_sel == "Nur mit Prefix" and not g.has_prefix:
                continue

            filtered.append(g)

        # Sorting
        if sort_sel == "Name (A-Z)":
            filtered.sort(key=lambda g: g.name.lower())
        elif sort_sel == "Größe (Absteigend)":
            filtered.sort(key=lambda g: g.size_mb, reverse=True)
        else: # Kürzlich gespielt
            filtered.sort(key=lambda g: (-g.last_played, g.name.lower()))

        self.filtered_games = filtered
        self._rebuild_grid()

    def _rebuild_grid(self):
        """Clears existing cards and mounts filtered game cards."""
        # Clear layout
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.card_widgets.clear()

        # Update summary label
        self.summary_lbl.setText(f"{len(self.filtered_games)} von {len(self.all_games)} Spielen angezeigt")

        for g in self.filtered_games:
            card = GameCard(g)
            card.clicked.connect(self._open_game_details)
            self.cards_layout.addWidget(card)
            self.card_widgets.append(card)

    def _open_game_details(self, game: GameInfo):
        """Switches to detail page and loads game data."""
        self.detail_view.load_game(game)
        self.stack.setCurrentIndex(1)
        self.top_bar.setVisible(False)

    def _show_library(self):
        """Returns to grid library view."""
        self.stack.setCurrentIndex(0)
        self.top_bar.setVisible(True)

    def _reset_updater_btn_style(self):
        self.btn_updater.setText("🚀 Updates")
        self.btn_updater.setStyleSheet(f"""
            QPushButton {{
                background-color: {ThemeColors.BG_CARD};
                color: {ThemeColors.TEXT_PRIMARY};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {ThemeColors.BG_CARD_HOVER};
                border-color: {ThemeColors.ACCENT_CYAN};
            }}
        """)
        self.btn_updater.setToolTip("Update-Center & GitHub-Releases öffnen")

    def show_update_dialog(self):
        dlg = UpdateDialog(self)
        dlg.exec()
        self._reset_updater_btn_style()

    def start_background_update_check(self, force: bool = False):
        """Silently checks for updates in the background without modal dialogs."""
        settings = QSettings("GamingCenter", "GamingCenter")
        last_check = settings.value("updater/last_background_check", 0, type=int)
        now = int(time.time())
        # Check at most once every 24 hours in background, unless forced
        if not force and (now - last_check < 86400):
            return

        self._bg_updater = UpdateCheckerWorker()
        self._bg_updater.finished.connect(self._on_bg_update_finished)
        self._bg_updater.start()

    def _on_bg_update_finished(self, info: UpdateInfo):
        settings = QSettings("GamingCenter", "GamingCenter")
        settings.setValue("updater/last_background_check", int(time.time()))

        if info.app_has_update:
            self.btn_updater.setText(f"● Update verfügbar (v{info.app_remote})")
            self.btn_updater.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #d97706, stop:1 #b45309);
                    color: #ffffff;
                    border: 1px solid {ThemeColors.ACCENT_AMBER};
                    border-radius: 6px;
                    padding: 7px 14px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                QPushButton:hover {{
                    background: #d97706;
                    border-color: #fde047;
                }}
            """)
            self.btn_updater.setToolTip(
                f"Neue Version v{info.app_remote} verfügbar!\nKlicken, um das Update-Center zu öffnen."
            )

