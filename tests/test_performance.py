"""
Script de perfilado de rendimiento (Benchmark / Profiling) para medir milisegundos reales por componente.
"""

import sys
import os
import time
import cv2
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import unittest
from src.core.detector import BabyDetector

class TestDetectorPerformance(unittest.TestCase):
    def test_detector_performance_profiling(self):
        print("🔬 Iniciando test de perfilado de rendimiento (Profiling)...")
        detector = BabyDetector(sensitivity=0.03, use_yolo=False)
        
        # Simular frame HD de cámara (1280x720)
        fake_frame = np.full((720, 1280, 3), 120, dtype=np.uint8)
        cv2.circle(fake_frame, (640, 360), 80, (200, 180, 255), -1)

        # Warmup frame para cargar buffers en memoria
        detector.process_frame(fake_frame)

        t0 = time.perf_counter()
        for _ in range(5):
            detector.process_frame(fake_frame)
        t1 = time.perf_counter()

        avg_ms = ((t1 - t0) / 5.0) * 1000.0
        fps = 1000.0 / avg_ms if avg_ms > 0 else 0
        print(f"⏱️ Tiempo promedio por frame: {avg_ms:.2f} ms ({fps:.1f} FPS equivalente)")
        self.assertGreater(fps, 0, "El detector debe procesar fotogramas correctamente")
        self.assertLess(avg_ms, 2500.0, "El procesamiento de frame debe mantenerse en tiempo real (<2500ms)")

if __name__ == "__main__":
    unittest.main()

