"""
Módulo de registro centralizado y depuración para Tapo C225.
Permite guardar logs de depuración detallados en logs/app_debug.log y configurar niveles por consola.
"""

import os
import logging
from logging.handlers import RotatingFileHandler

LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "app_debug.log")

def setup_logger(name: str = "TapoApp", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) # Capturar todo a nivel debug

    if not logger.handlers:
        # Handler para consola
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
        console_handler.setFormatter(console_fmt)
        logger.addHandler(console_handler)

        # Handler para archivo rotativo debug (máximo 5MB por archivo, reteniendo 3 archivos)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s")
        file_handler.setFormatter(file_fmt)
        logger.addHandler(file_handler)

    return logger

# Instancia global preconfigurada para uso directo
debug_logger = setup_logger("TapoDebug", level=logging.INFO)
