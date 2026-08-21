"""
Gestor de Configuración y Preferencias del Usuario (config.json).
Maneja los valores por defecto, la persistencia en disco y la verificación de horarios silenciosos.
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger("BabyDetector.Config")

DEFAULT_CONFIG: Dict[str, Any] = {
    "camera_url": "0",
    "baby_name": "Bebé",
    "sensitivity": 0.03,
    "sound_threshold": 0.35,
    "sound_enabled": True,
    "alert_motion": True,
    "alert_sound": True,
    "alert_popup": True,
    "popup_duration_sec": 30,
    "motion_min_duration_sec": 5.0,
    "mute_alarm_sound": False,
    "live_audio": False,
    "use_roi": True,
    "roi": [0.15, 0.15, 0.85, 0.85],
    "template_enabled": True,
    "template_threshold": 0.60,
    "suggestions_enabled": False,
    "only_baby_motion": False,
    "show_persons": False,
    "silent_sched_enabled": False,
    "silent_sched_start": "09:00",
    "silent_sched_end": "18:00",
    "pause_duration_str": "10 Minutos"
}

class ConfigManager:
    """
    Carga y guarda la configuración del usuario en JSON y evalúa reglas de negocio (ej. horarios).
    """
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Carga la configuración desde el archivo JSON fusionándola con valores por defecto."""
        cfg = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        # Manejo transparente de aliases para compatibilidad hacia atrás
                        if "roi_enabled" in loaded and "use_roi" not in loaded:
                            loaded["use_roi"] = loaded["roi_enabled"]
                        if "roi_coords" in loaded and "roi" not in loaded and loaded["roi_coords"] is not None:
                            loaded["roi"] = loaded["roi_coords"]
                        if "silent_schedule_enabled" in loaded and "silent_sched_enabled" not in loaded:
                            loaded["silent_sched_enabled"] = loaded["silent_schedule_enabled"]
                        if "silent_start_hour" in loaded and "silent_sched_start" not in loaded:
                            loaded["silent_sched_start"] = loaded["silent_start_hour"]
                        if "silent_end_hour" in loaded and "silent_sched_end" not in loaded:
                            loaded["silent_sched_end"] = loaded["silent_end_hour"]
                        
                        cfg.update(loaded)
            except Exception as e:
                logger.error(f"Error al leer configuración {self.config_path}: {e}")
        return cfg

    def save_config(self, new_cfg: Dict[str, Any] = None) -> bool:
        """Guarda la configuración actual en el archivo JSON."""
        if new_cfg is not None:
            self.config.update(new_cfg)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error al guardar configuración en {self.config_path}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value

    def is_in_silent_schedule(self) -> bool:
        """Determina si la hora local actual cae dentro del horario de trabajo silencioso configurado."""
        is_silent = self.config.get("silent_sched_enabled", self.config.get("silent_schedule_enabled", False))
        if not is_silent:
            return False
        try:
            now_t = datetime.now().time()
            start_str = self.config.get("silent_sched_start", self.config.get("silent_start_hour", "09:00"))
            end_str = self.config.get("silent_sched_end", self.config.get("silent_end_hour", "18:00"))
            
            s_h, s_m = map(int, start_str.split(":"))
            e_h, e_m = map(int, end_str.split(":"))
            
            start_t = datetime.now().replace(hour=s_h, minute=s_m, second=0, microsecond=0).time()
            end_t = datetime.now().replace(hour=e_h, minute=e_m, second=0, microsecond=0).time()

            if start_t <= end_t:
                return start_t <= now_t <= end_t
            else:
                # Horario que cruza la medianoche (ej. 22:00 a 06:00)
                return now_t >= start_t or now_t <= end_t
        except Exception:
            return False

