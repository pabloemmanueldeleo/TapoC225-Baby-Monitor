"""
Prueba Automatizada End-to-End del Binario Ejecutable Nativo (.exe) para Windows.
Verifica que el ejecutable empaquetado por PyInstaller inicialice correctamente,
cargue todos los módulos C++/Qt/ONNX/Torchvision y cierre limpiamente sin crasheos silenciosos.
"""
import os
import sys
import time
import subprocess
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE_PATH = os.path.join(PROJECT_ROOT, "dist", "TapoC225_BabyMonitor", "TapoC225_BabyMonitor.exe")

class TestExecutableBinary(unittest.TestCase):
    def test_exe_smoke_launch(self):
        if not os.path.exists(EXE_PATH):
            self.skipTest(f"El ejecutable compilado no existe en '{EXE_PATH}'. Ejecute primero 'scripts/build_exe.py'.")

        print(f"\n[TEST EXE] Verificando ejecutable: {EXE_PATH}")
        
        # Eliminar crash_log previo si existía
        exe_dir = os.path.dirname(EXE_PATH)
        crash_log = os.path.join(exe_dir, "crash_log.txt")
        if os.path.exists(crash_log):
            try:
                os.remove(crash_log)
            except Exception:
                pass

        # Ejecutar en modo smoke-test (cierre automático tras 3 segundos de renderizado)
        cmd = [EXE_PATH, "--smoke-test"]
        start_time = time.time()
        
        # Para ejecutables GUI (console=False en Windows), evitamos colgar en pipes de stdout y monitoreamos el proceso directamente
        proc = subprocess.Popen(
            cmd,
            cwd=exe_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            returncode = proc.wait(timeout=45)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.fail("El ejecutable se colgó y no respondió en 45 segundos.")

        duration = time.time() - start_time
        print(f"[TEST EXE] Duración de ejecución de prueba: {duration:.2f}s | Código de salida: {returncode}")

        # Verificar que no haya crash_log
        if os.path.exists(crash_log):
            with open(crash_log, "r", encoding="utf-8", errors="replace") as f:
                log_content = f.read()
            self.fail(f"Se detectó un crasheo no controlado en el ejecutable:\n{log_content}")

        self.assertEqual(returncode, 0, f"El ejecutable falló con código de salida {returncode}.")
        print("[TEST EXE] [OK] El ejecutable (.exe) arranco, inicializo la GUI y cerro con exito absoluto (Codigo 0).")

if __name__ == "__main__":
    unittest.main()
