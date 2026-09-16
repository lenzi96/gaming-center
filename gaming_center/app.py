"""Application bootstrap and runtime entry point with single-instance IPC."""

import os
import sys
import json
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPolygonF
from PyQt6.QtCore import QPointF
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication
from .main_window import MainWindow

SERVER_NAME = f"gaming_center_ipc_{os.getuid()}"


def create_app_icon() -> QIcon:
    """Generates a modern vector-like gamepad icon."""
    size = 128
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer pill/body of controller
    from PyQt6.QtGui import QLinearGradient, QPen
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#00d494"))
    grad.setColorAt(1.0, QColor("#009668"))

    p.setBrush(grad)
    p.setPen(Qt.PenStyle.NoPen)
    # Controller body rounded rectangle
    p.drawRoundedRect(16, 32, 96, 64, 24, 24)

    # Grips
    p.setBrush(QColor("#007d57"))
    p.drawRoundedRect(22, 60, 24, 38, 12, 12)
    p.drawRoundedRect(82, 60, 24, 38, 12, 12)

    # D-pad (left)
    p.setBrush(QColor("#0d131c"))
    p.drawRect(34, 52, 6, 18)
    p.drawRect(28, 58, 18, 6)

    # Action Buttons (right)
    p.setBrush(QColor("#00d2ff")) # X/A Cyan
    p.drawEllipse(84, 52, 6, 6)
    p.setBrush(QColor("#f59e0b")) # Y/B Amber
    p.drawEllipse(94, 60, 6, 6)
    p.setBrush(QColor("#ef4444")) # Red
    p.drawEllipse(74, 60, 6, 6)
    p.setBrush(QColor("#a855f7")) # Purple
    p.drawEllipse(84, 68, 6, 6)

    # Center LEDs / Logo
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(58, 58, 12, 12)
    p.setBrush(QColor("#0d131c"))
    p.drawEllipse(61, 61, 6, 6)

    p.end()
    return QIcon(pix)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("gaming-center")
    app.setApplicationDisplayName("Gaming Center")
    app.setOrganizationName("GamingCenter")
    app.setDesktopFileName("gaming-center")

    icon = create_app_icon()
    app.setWindowIcon(icon)

    # 1. Single Instance Check via QLocalSocket
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(500):
        # Already running! Bring to front and exit
        args = sys.argv[1:]
        payload = json.dumps({"args": args}).encode("utf-8")
        socket.write(payload)
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)

    # 2. Local IPC Server
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()

    window = MainWindow()
    window.setWindowIcon(icon)

    def on_new_connection():
        client = server.nextPendingConnection()
        if client:
            client.waitForReadyRead(500)
            window.showNormal()
            window.activateWindow()
            window.raise_()
            client.disconnectFromServer()

    server.newConnection.connect(on_new_connection)
    server.listen(SERVER_NAME)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
