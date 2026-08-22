"""
Script de Compilación Automatizada a Ejecutable Nativo (.exe) para Windows usando PyInstaller.
"""
import os
import sys
import subprocess

def build_standalone_exe():
    print("=======================================================")
    print(" [*] COMPILANDO TAPO C225 AI BABY MONITOR A EJECUTABLE (.EXE)")
    print("=======================================================")
    
    # Asegurar PyInstaller
    try:
        import PyInstaller
    except ImportError:
        print("[*] Instalando PyInstaller...")
        subprocess.run(["uv", "pip", "install", "pyinstaller"], check=True)
    
    spec_file = "TapoC225_BabyMonitor.spec"
    if os.path.exists(spec_file):
        cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", spec_file]
    else:
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--name=TapoC225_BabyMonitor",
            "--noconsole",
            "--onedir",
            "--clean",
            "--noconfirm",
            "--add-data=.env.example;.",
            "--add-data=assets;assets",
            "--add-data=yolov8n-seg.onnx;.",
            "--add-data=yolov8n-seg.pt;.",
            "--add-data=yolov8n.pt;.",
            "--collect-all=cv2",
            "--collect-all=ultralytics",
            "--collect-all=onnxruntime",
            "--collect-all=onnx",
            "--collect-all=torchvision",
            "--collect-all=pytapo",
            "--collect-all=sounddevice",
            "--collect-all=av",
            "--collect-all=matplotlib",
            "--collect-all=pystray",
            "--collect-all=PIL",
            "--collect-submodules=PySide6.QtWidgets",
            "--collect-submodules=PySide6.QtGui",
            "--collect-submodules=PySide6.QtCore",
            "--exclude-module=PySide6.QtWebEngineCore",
            "--exclude-module=PySide6.QtWebEngineWidgets",
            "--exclude-module=PySide6.QtWebEngineQuick",
            "--exclude-module=PySide6.QtQuick",
            "--exclude-module=PySide6.QtQuick3D",
            "--exclude-module=PySide6.Qt3DCore",
            "--exclude-module=PySide6.Qt3DRender",
            "--exclude-module=PySide6.QtDesigner",
            "--exclude-module=PySide6.QtQml",
            "--exclude-module=PySide6.QtMultimedia",
            "--exclude-module=PySide6.QtMultimediaWidgets",
            "--exclude-module=PySide6.QtSensors",
            "--exclude-module=PySide6.QtPositioning",
            "--exclude-module=PySide6.QtLocation",
            "--exclude-module=PySide6.QtBluetooth",
            "--exclude-module=PySide6.QtNfc",
            "--exclude-module=PySide6.QtTest",
            "--exclude-module=PySide6.QtPdf",
            "--exclude-module=PySide6.QtPdfWidgets",
            "--exclude-module=PySide6.QtSpatialAudio",
            "--exclude-module=polars",
            "--exclude-module=pandas",
            "--exclude-module=scipy",
            "--exclude-module=tkinter",
            "--exclude-module=IPython",
            "--icon=assets/app_icon.ico",
            "main.py"
        ]
    
    print(f"[*] Ejecutando: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print("\n[OK] Compilacion finalizada con exito! Ejecutable listo en 'dist/TapoC225_BabyMonitor/TapoC225_BabyMonitor.exe'")

if __name__ == "__main__":
    build_standalone_exe()
