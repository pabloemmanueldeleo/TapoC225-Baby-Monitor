"""
👶 Tapo C225 AI Baby Monitor — Punto de Entrada Principal (Entrypoint)
"""
import sys
import os
import ctypes
import traceback
from datetime import datetime

# Asegurar que el directorio de trabajo actual sea siempre la carpeta de la aplicación
if getattr(sys, "frozen", False):
    app_dir = os.path.dirname(sys.executable)
    try:
        os.chdir(app_dir)
    except Exception:
        pass

# Optimización de concurrencia de CPU para inferencia neuronal y render fluido (evita contienda de hilos)
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["NUMEXPR_NUM_THREADS"] = "2"

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

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QLockFile, QDir, QTimer
from PySide6.QtGui import QIcon

# 🛡️ Manejador Global de Excepciones para registrar fallos en modo ventana (sin consola)
def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        with open("crash_log.txt", "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR INESPERADO:\n{error_msg}\n")
    except Exception:
        pass
    try:
        app_inst = QApplication.instance()
        if app_inst is not None:
            QMessageBox.critical(
                None,
                "Error Inesperado — Tapo C225",
                f"Se produjo un error al iniciar o ejecutar la aplicación:\n\n{exc_value}\n\nDetalles guardados en crash_log.txt"
            )
    except Exception:
        pass

sys.excepthook = handle_uncaught_exception

from src.gui.pyside_app import PySideTapoApp

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(True)

    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "assets", "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 🔒 Candado de Instancia Única (Single Instance Lock)
    is_smoke_test = "--smoke-test" in sys.argv or "--test-launch" in sys.argv
    lock_file = None

    if not is_smoke_test:
        lock_path = os.path.join(QDir.tempPath(), "tapo_c225_single_instance.lock")
        lock_file = QLockFile(lock_path)
        lock_file.setStaleLockTime(5000)

        if not lock_file.tryLock(100):
            # Intentar traer la ventana existente al primer plano
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, "Tapo C225 - Monitor de Bebé (PySide6 C++ Engine)")
                if hwnd:
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

            QMessageBox.information(
                None,
                "Tapo C225 — Ya en Ejecución",
                "Ya hay una instancia de Tapo C225 abierta en segundo plano o en la bandeja del sistema (junto al reloj de Windows).\n\nPuedes restaurarla haciendo doble clic en el icono de la bandeja."
            )
            sys.exit(0)

    window = PySideTapoApp()
    window.showNormal()
    window.show()
    window.raise_()
    window.activateWindow()

    # En modo smoke-test, cerramos limpiamente tras unos segundos para certificar el arranque
    if is_smoke_test:
        def _smoke_shutdown():
            try:
                window.close()
            except Exception:
                pass
            try:
                app.quit()
            except Exception:
                pass

        QTimer.singleShot(2500, _smoke_shutdown)

    # Mantener el lock_file en memoria mientras la app esté abierta
    ret = app.exec()
    if lock_file is not None:
        lock_file.unlock()
    sys.exit(ret)

if __name__ == "__main__":
    main()
