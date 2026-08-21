"""
👶 Tapo C225 AI Baby Monitor — Punto de Entrada Principal (Entrypoint)
"""
import sys
import os
import ctypes
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLockFile, QDir
from PySide6.QtGui import QIcon

# Silenciar mensajes verbosos de FFmpeg/H264 de OpenCV en la consola de Windows
os.environ["OPENCV_FFMPEG_LOG_LEVEL"] = "quiet"
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
try:
    import cv2
    cv2.setLogLevel(0)
except Exception:
    pass

# Registrar AppUserModelID en Windows para que la barra de tareas muestre el icono personalizado
try:
    myappid = "tapoc225.babymonitor.ai.1.0"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

from src.gui.pyside_app import PySideTapoApp

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(True)

    icon_path = os.path.join(os.path.dirname(__file__), "assets", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 🔒 Candado de Instancia Única (Single Instance Lock)
    lock_path = os.path.join(QDir.tempPath(), "tapo_c225_single_instance.lock")
    lock_file = QLockFile(lock_path)
    lock_file.setStaleLockTime(5000)

    if not lock_file.tryLock(100):
        print("⚠️ Ya hay una instancia de Tapo C225 ejecutándose en segundo plano o barra de tareas.")
        sys.exit(0)

    window = PySideTapoApp()
    window.showNormal()
    window.show()
    window.raise_()
    window.activateWindow()

    # Mantener el lock_file en memoria mientras la app esté abierta
    ret = app.exec()
    lock_file.unlock()
    sys.exit(ret)

if __name__ == "__main__":
    main()
