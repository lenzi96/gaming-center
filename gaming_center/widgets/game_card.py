"""Game card widget for library grid view."""

import os
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QFont, QCursor
from PyQt6.QtWidgets import (
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from ..backend.game_scanner import GameInfo
from ..style.theme import ThemeColors


class GameCard(QFrame):
    clicked = pyqtSignal(object)  # GameInfo

    CARD_WIDTH = 180
    CARD_HEIGHT = 280
    IMAGE_HEIGHT = 220

    def __init__(self, game: GameInfo, parent: QWidget = None):
        super().__init__(parent)
        self.game = game
        self.setObjectName("GameCard")
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 8)
        layout.setSpacing(6)

        # 1. Cover Image Container
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(self.CARD_WIDTH - 12, self.IMAGE_HEIGHT)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setStyleSheet("border-radius: 6px; background-color: #0b1118;")
        self._load_cover()
        layout.addWidget(self.cover_label)

        # 2. Bottom Meta: Platform Badge & Game Title
        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(2, 0, 2, 0)
        meta_layout.setSpacing(2)

        # Title
        self.title_label = QLabel(self.game.name)
        self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {ThemeColors.TEXT_PRIMARY};")
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(self.game.name)
        # Elide text if too long
        metrics = self.title_label.fontMetrics()
        elided = metrics.elidedText(self.game.name, Qt.TextElideMode.ElideRight, self.CARD_WIDTH - 16)
        self.title_label.setText(elided)
        meta_layout.addWidget(self.title_label)

        # Badges row (Platform + Prefix Status)
        badges_row = QHBoxLayout()
        badges_row.setSpacing(4)
        badges_row.setContentsMargins(0, 0, 0, 0)

        # Platform Badge
        plat_label = QLabel(self.game.platform.upper())
        if self.game.platform == "steam":
            plat_label.setStyleSheet(
                "background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; "
                "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        elif self.game.platform == "heroic":
            plat_label.setStyleSheet(
                "background-color: rgba(168, 85, 247, 0.2); color: #c084fc; "
                "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        elif self.game.platform == "lutris":
            plat_label.setStyleSheet(
                "background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; "
                "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        else:
            plat_label.setStyleSheet(
                "background-color: rgba(148, 163, 184, 0.2); color: #94a3b8; "
                "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        badges_row.addWidget(plat_label)

        # Prefix Badge
        if self.game.has_prefix:
            pfx_label = QLabel("PREFIX")
            pfx_label.setStyleSheet(
                "background-color: rgba(0, 212, 148, 0.15); color: #00d494; "
                "font-size: 9px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
            pfx_label.setToolTip("Proton/Wine Prefix vorhanden")
            badges_row.addWidget(pfx_label)

        badges_row.addStretch()

        # Size badge if available
        if self.game.size_mb > 0:
            size_label = QLabel(self.game.formatted_size)
            size_label.setStyleSheet(f"font-size: 10px; color: {ThemeColors.TEXT_MUTED};")
            badges_row.addWidget(size_label)

        meta_layout.addLayout(badges_row)
        layout.addLayout(meta_layout)

    def _apply_cover_image(self, img_path: str) -> bool:
        """Applies local image file to cover label, returns True if successful."""
        target_w = self.CARD_WIDTH - 12
        target_h = self.IMAGE_HEIGHT
        if img_path and os.path.isfile(img_path):
            pixmap = QPixmap(img_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    target_w,
                    target_h,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                # Crop to exact dimensions
                cropped = scaled.copy(
                    (scaled.width() - target_w) // 2,
                    (scaled.height() - target_h) // 2,
                    target_w,
                    target_h,
                )
                # Apply rounded corners
                rounded = self._round_pixmap(cropped, 6)
                self.cover_label.setPixmap(rounded)
                return True
        return False

    def _load_cover(self):
        """Loads and scales cover poster, or triggers background fetch and shows fallback visual."""
        img_path = self.game.poster_image or self.game.banner_image
        target_w = self.CARD_WIDTH - 12
        target_h = self.IMAGE_HEIGHT

        if img_path and self._apply_cover_image(img_path):
            return

        # Fallback cover
        self.cover_label.setPixmap(self._generate_fallback_pixmap(target_w, target_h))

        # Request background fetch if missing or URL
        try:
            from ..backend.cover_manager import CoverManager
            cm = CoverManager.get_instance()
            cm.cover_downloaded.connect(self._on_cover_downloaded)
            cm.fetch_cover_async(self.game)
        except Exception:
            pass

    def _on_cover_downloaded(self, app_id: str, local_path: str):
        if self.game.app_id == app_id and local_path and os.path.isfile(local_path):
            self.game.poster_image = local_path
            self._apply_cover_image(local_path)

    def _round_pixmap(self, src: QPixmap, radius: int) -> QPixmap:
        dest = QPixmap(src.size())
        dest.fill(Qt.GlobalColor.transparent)

        painter = QPainter(dest)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, src.width(), src.height(), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, src)
        painter.end()
        return dest

    def _generate_fallback_pixmap(self, w: int, h: int) -> QPixmap:
        pix = QPixmap(w, h)
        pix.fill(QColor(ThemeColors.BG_CARD))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Gradient background
        from PyQt6.QtGui import QLinearGradient
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor("#16222f"))
        grad.setColorAt(1.0, QColor("#0d151e"))
        painter.fillRect(0, 0, w, h, grad)

        # Game Initial or Abbreviation
        words = self.game.name.split()
        initials = "".join(w[0] for w in words[:3] if w).upper()
        if not initials:
            initials = "G"

        painter.setPen(QColor(ThemeColors.TEXT_MUTED))
        font = QFont("Cantarell", 28, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, w, h - 20, Qt.AlignmentFlag.AlignCenter, initials)

        painter.setPen(QColor(ThemeColors.BORDER_CARD))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 6, 6)
        painter.end()
        return pix

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.game)
        super().mousePressEvent(event)
