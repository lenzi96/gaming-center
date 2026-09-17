"""
Auto-Optimization Dialog for Gaming Center.

Provides hardware-aware 1-click batch optimization for installed games,
configuring presets, DXVK Async, RADV GPL, NVIDIA DLSS / NVAPI, and PCGW fixes.
"""

from typing import List, Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QCheckBox,
    QComboBox,
    QRadioButton,
    QButtonGroup,
    QMessageBox,
)
from ..backend.game_scanner import GameInfo
from ..backend.pcgw_client import PCGWClient
from ..backend.optimizer import GameOptimizer, SystemHardwareInfo, OptimizationResult
from ..style.theme import ThemeColors


class BatchOptimizeWorker(QThread):
    progress = pyqtSignal(int, int, str)               # current, total, game_name
    finished_batch = pyqtSignal(list)                   # List[OptimizationResult]

    def __init__(self, games: List[GameInfo], pcgw_client: PCGWClient, mode: str):
        super().__init__()
        self.games = games
        self.pcgw_client = pcgw_client
        self.mode = mode

    def run(self):
        try:
            results = GameOptimizer.optimize_batch(
                games=self.games,
                pcgw_client=self.pcgw_client,
                mode=self.mode,
                progress_cb=lambda cur, tot, name: self.progress.emit(cur, tot, name),
            )
            self.finished_batch.emit(results)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_batch.emit([])


class AutoOptimizeDialog(QDialog):
    def __init__(self, games: List[GameInfo], pcgw_client: PCGWClient, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Auto-Optimierung - Gaming Center")
        self.resize(840, 600)
        self.setMinimumSize(740, 520)

        self.all_games = games
        self.pcgw_client = pcgw_client
        self.hw: SystemHardwareInfo = GameOptimizer.detect_hardware()
        self.worker: Optional[BatchOptimizeWorker] = None
        self.results: List[OptimizationResult] = []

        self._setup_ui()
        self._populate_games_table()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        # 1. Header
        header = QHBoxLayout()
        h_text = QVBoxLayout()
        h_text.setSpacing(2)

        lbl_title = QLabel("🪄 Spiele Auto-Optimierer")
        lbl_title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {ThemeColors.ACCENT_GREEN};")
        lbl_desc = QLabel("Erkennt deine Hardware & Spiele-Eigenschaften, um mit einem Klick die optimalen Startoptionen zu setzen.")
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        h_text.addWidget(lbl_title)
        h_text.addWidget(lbl_desc)
        header.addLayout(h_text)
        header.addStretch()

        root.addLayout(header)

        # 2. Detected System Hardware Card
        hw_card = QFrame()
        hw_card.setStyleSheet(f"""
            QFrame {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 8px;
                padding: 10px 14px;
            }}
        """)
        hw_layout = QVBoxLayout(hw_card)
        hw_layout.setSpacing(6)

        lbl_hw_title = QLabel("🖥️ Erkanntes System & Umgebung:")
        lbl_hw_title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {ThemeColors.ACCENT_CYAN};")
        hw_layout.addWidget(lbl_hw_title)

        hw_grid = QHBoxLayout()
        hw_grid.setSpacing(16)

        # GPU info
        gpu_col = QVBoxLayout()
        gpu_col.setSpacing(2)
        lbl_g_head = QLabel("Grafikkarte (GPU):")
        lbl_g_head.setStyleSheet(f"font-size: 10px; color: {ThemeColors.TEXT_MUTED}; font-weight: 600;")
        gpu_name_short = self.hw.gpu_name
        if len(gpu_name_short) > 40:
            gpu_name_short = gpu_name_short[:37] + "..."
        lbl_g_val = QLabel(f"🎮 {self.hw.vendor_display}\n({gpu_name_short})")
        lbl_g_val.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ThemeColors.TEXT_PRIMARY};")
        gpu_col.addWidget(lbl_g_head)
        gpu_col.addWidget(lbl_g_val)
        hw_grid.addLayout(gpu_col, stretch=2)

        # CPU info
        cpu_col = QVBoxLayout()
        cpu_col.setSpacing(2)
        lbl_c_head = QLabel("Prozessor (CPU):")
        lbl_c_head.setStyleSheet(f"font-size: 10px; color: {ThemeColors.TEXT_MUTED}; font-weight: 600;")
        cpu_name_short = self.hw.cpu_name
        if len(cpu_name_short) > 35:
            cpu_name_short = cpu_name_short[:32] + "..."
        lbl_c_val = QLabel(f"⚡ {cpu_name_short}\n({self.hw.cpu_threads} Threads)")
        lbl_c_val.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ThemeColors.TEXT_PRIMARY};")
        cpu_col.addWidget(lbl_c_head)
        cpu_col.addWidget(lbl_c_val)
        hw_grid.addLayout(cpu_col, stretch=2)

        # Tools info
        tools_col = QVBoxLayout()
        tools_col.setSpacing(2)
        lbl_t_head = QLabel("Gaming-Tools:")
        lbl_t_head.setStyleSheet(f"font-size: 10px; color: {ThemeColors.TEXT_MUTED}; font-weight: 600;")
        tool_items = []
        if self.hw.has_gamemode:
            tool_items.append("✓ GameMode")
        if self.hw.has_mangohud:
            tool_items.append("✓ MangoHud")
        if self.hw.has_gamescope:
            tool_items.append("✓ Gamescope")
        if self.hw.has_primerun:
            tool_items.append("✓ Prime-Run")
        tools_str = " • ".join(tool_items) if tool_items else "Keine optionalen Tools"
        lbl_t_val = QLabel(f"🛠️ {tools_str}\nBildschirm: {self.hw.screen_res}")
        lbl_t_val.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ThemeColors.ACCENT_GREEN if tool_items else ThemeColors.TEXT_MUTED};")
        tools_col.addWidget(lbl_t_head)
        tools_col.addWidget(lbl_t_val)
        hw_grid.addLayout(tools_col, stretch=2)

        hw_layout.addLayout(hw_grid)
        root.addWidget(hw_card)

        # 3. Optimization Mode Profile Selector
        opt_box = QFrame()
        opt_box.setStyleSheet(f"background-color: {ThemeColors.BG_CARD}; border: 1px solid {ThemeColors.BORDER_CARD}; border-radius: 8px; padding: 8px 12px;")
        opt_l = QHBoxLayout(opt_box)
        opt_l.setSpacing(14)

        lbl_mode = QLabel("Optimierungs-Fokus:")
        lbl_mode.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {ThemeColors.TEXT_PRIMARY};")
        opt_l.addWidget(lbl_mode)

        self.mode_group = QButtonGroup(self)
        self.rb_perf = QRadioButton("🚀 Maximale Performance (Empfohlen)")
        self.rb_perf.setChecked(True)
        self.rb_perf.setToolTip("GameMode + High Priority + GPU Shader GPL / DLSS + DXVK Async")
        self.mode_group.addButton(self.rb_perf)
        opt_l.addWidget(self.rb_perf)

        self.rb_bal = QRadioButton("⚡ Standard (Ausgewogen)")
        self.rb_bal.setToolTip("GameMode + DXVK Async ohne CPU-Priorisierung")
        self.mode_group.addButton(self.rb_bal)
        opt_l.addWidget(self.rb_bal)

        self.rb_handheld = QRadioButton("🔋 Handheld / Akkusparend")
        self.rb_handheld.setToolTip("Gamescope FSR + 60 FPS Cap für mobile Geräte")
        self.mode_group.addButton(self.rb_handheld)
        opt_l.addWidget(self.rb_handheld)

        opt_l.addStretch()
        root.addWidget(opt_box)

        # 4. Games Table
        table_header = QHBoxLayout()
        self.cb_select_all = QCheckBox("Alle Spiele auswählen")
        self.cb_select_all.setChecked(True)
        self.cb_select_all.stateChanged.connect(self._toggle_select_all)
        table_header.addWidget(self.cb_select_all)

        self.lbl_selected_count = QLabel(f"{len(self.all_games)} Spiele ausgewählt")
        self.lbl_selected_count.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        table_header.addStretch()
        table_header.addWidget(self.lbl_selected_count)
        root.addLayout(table_header)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Auswahl", "Spielname", "Plattform", "Geplante Optimierung"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 6px;
                gridline-color: rgba(255, 255, 255, 0.05);
            }}
            QHeaderView::section {{
                background-color: {ThemeColors.BG_PANEL};
                color: {ThemeColors.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
                padding: 6px;
                border: none;
                border-bottom: 1px solid {ThemeColors.BORDER_CARD};
            }}
        """)
        root.addWidget(self.table, stretch=1)

        # 5. Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {ThemeColors.BG_CARD};
                border: 1px solid {ThemeColors.BORDER_CARD};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ThemeColors.ACCENT_GREEN}, stop:1 {ThemeColors.ACCENT_CYAN});
                border-radius: 3px;
            }}
        """)
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet(f"font-size: 11px; color: {ThemeColors.TEXT_SECONDARY};")
        self.status_lbl.setVisible(False)
        root.addWidget(self.status_lbl)

        # 6. Bottom Action Buttons
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.btn_optimize = QPushButton(f"⚡ {len(self.all_games)} Spiele jetzt optimieren")
        self.btn_optimize.setProperty("class", "primary-btn")
        self.btn_optimize.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_optimize.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ThemeColors.ACCENT_GREEN}, stop:1 #00b07c);
                color: #04100c;
                font-size: 13px;
                font-weight: 800;
                padding: 10px 20px;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                background: #00f0a8;
            }}
            QPushButton:disabled {{
                background: #233544;
                color: #5d7589;
            }}
        """)
        self.btn_optimize.clicked.connect(self._start_optimization)
        bottom_row.addWidget(self.btn_optimize)

        bottom_row.addStretch()

        self.btn_close = QPushButton("Schließen")
        self.btn_close.setProperty("class", "ghost-btn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(self.btn_close)

        root.addLayout(bottom_row)

    def _populate_games_table(self):
        self.table.setRowCount(len(self.all_games))
        for row, g in enumerate(self.all_games):
            # 1. Checkbox
            cb_item = QTableWidgetItem()
            cb_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.table.setItem(row, 0, cb_item)

            # 2. Name
            name_item = QTableWidgetItem(g.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            name_item.setForeground(Qt.GlobalColor.white)
            self.table.setItem(row, 1, name_item)

            # 3. Platform
            plat_item = QTableWidgetItem(g.platform.upper())
            plat_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 2, plat_item)

            # 4. Planned preset & detected Graphics API
            api = GameOptimizer.detect_graphics_api(g)
            plan_desc = f"{api.badge_text} • {self.hw.vendor_display}"
            if self.hw.has_gamemode:
                plan_desc += " + GameMode"
            plan_item = QTableWidgetItem(plan_desc)
            plan_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            plan_item.setToolTip(f"Grafik-Schnittstelle: {api.label}\nErkannt über: {api.detection_source}")
            from PyQt6.QtGui import QColor
            plan_item.setForeground(QColor(api.color))
            self.table.setItem(row, 3, plan_item)

        self.table.itemChanged.connect(self._on_table_item_changed)
        self._update_selected_count()

    def _toggle_select_all(self, state):
        self.table.blockSignals(True)
        check = Qt.CheckState.Checked if state == Qt.CheckState.Checked.value or state == 2 else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                item.setCheckState(check)
        self.table.blockSignals(False)
        self._update_selected_count()

    def _on_table_item_changed(self, item):
        if item.column() == 0:
            self._update_selected_count()

    def _update_selected_count(self):
        cnt = sum(1 for row in range(self.table.rowCount()) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self.lbl_selected_count.setText(f"{cnt} von {len(self.all_games)} Spielen ausgewählt")
        self.btn_optimize.setText(f"⚡ {cnt} Spiele jetzt optimieren")
        self.btn_optimize.setEnabled(cnt > 0)

    def _get_selected_games(self) -> List[GameInfo]:
        sel = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked:
                sel.append(self.all_games[row])
        return sel

    def _start_optimization(self):
        games_to_opt = self._get_selected_games()
        if not games_to_opt:
            return

        mode = "performance"
        if self.rb_bal.isChecked():
            mode = "balanced"
        elif self.rb_handheld.isChecked():
            mode = "handheld"

        self.btn_optimize.setEnabled(False)
        self.btn_close.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(games_to_opt))
        self.progress_bar.setValue(0)
        self.status_lbl.setVisible(True)
        self.status_lbl.setText("Starte Auto-Optimierung...")

        self.worker = BatchOptimizeWorker(games_to_opt, self.pcgw_client, mode)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_batch.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, current: int, total: int, game_name: str):
        self.progress_bar.setValue(current)
        self.status_lbl.setText(f"[{current}/{total}] Optimiere {game_name}...")

    def _on_finished(self, results: List[OptimizationResult]):
        self.results = results
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.status_lbl.setText(f"✅ {len(results)} Spiele erfolgreich optimiert und Profile gespeichert!")
        self.btn_optimize.setVisible(False)
        self.btn_close.setEnabled(True)
        self.btn_close.setText("Fertigstellen")

        # Update table status
        for res in results:
            for row in range(self.table.rowCount()):
                name_item = self.table.item(row, 1)
                if name_item and name_item.text() == res.game_name:
                    item = self.table.item(row, 3)
                    if item:
                        item.setText("✅ Optimiert & Gespeichert")
                        item.setForeground(Qt.GlobalColor.green)
                    break

        QMessageBox.information(
            self,
            "Auto-Optimierung abgeschlossen",
            f"🎉 {len(results)} Spiele wurden erfolgreich optimiert!\n\n"
            f"Erkanntes System: {self.hw.vendor_display} • {self.hw.cpu_name}\n"
            f"Profile wurden dauerhaft in ~/.config/gaming-center/profiles/ gespeichert.\n"
            f"Die Spiele können nun direkt mit maximaler Leistung gestartet werden.",
        )
