"""
Servicio Inteligente de Registro, Telemetría y Snapshots de Salud y Descanso del Bebé.
Implementa compresión por eventos (Deadband Filtering) y archivo histórico por Snapshots diarios.
"""

import os
import time
import csv
import json
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from collections import deque
import threading

logger = logging.getLogger("AnalyticsService")

class BabyAnalyticsService:
    def __init__(self, data_dir: str = "data/analytics"):
        self.data_dir = data_dir
        self.snapshots_dir = os.path.join(self.data_dir, "snapshots")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        
        self.csv_path = os.path.join(self.data_dir, "live_telemetry.csv")
        
        self._lock = threading.Lock()
        self._live_samples = deque(maxlen=180) # Buffer rodante en RAM (últimos ~90s a 2Hz)
        self._last_ram_sample_time = 0.0
        self._last_log_time = 0.0
        self._last_state: Optional[str] = None
        self._last_motion: float = -1.0
        self._last_crying: bool = False
        self._current_date_str = datetime.now().strftime("%Y-%m-%d")

        self._init_csv()

    def _init_csv(self):
        """Inicializa el archivo CSV con sus cabeceras si no existe."""
        if not os.path.exists(self.csv_path):
            try:
                with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        "timestamp",
                        "datetime",
                        "baby_present",
                        "motion_ratio",
                        "audio_volume",
                        "sleep_state",
                        "is_crying"
                    ])
            except Exception as e:
                logger.error(f"Error al inicializar CSV de telemetría: {e}")

    def log_sample(self, baby_present: bool, motion_ratio: float, audio_volume: float, is_crying: bool):
        """
        Registro Inteligente:
        - Mantiene buffer continuo en memoria RAM a 2Hz para gráficos en tiempo real fluidos.
        - Persiste en disco de inmediato ante eventos (cambio de estado/llanto/movimiento) o cada 20s.
        """
        now = time.time()
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")

        # Rotación automática de medianoche
        if today_str != self._current_date_str:
            self.create_snapshot(date_label=self._current_date_str)
            self._current_date_str = today_str
            self.clear_live_session()

        # Clasificación clínica de estado de descanso
        if not baby_present:
            sleep_state = "Fuera de Cuna"
        elif motion_ratio < 0.006:
            sleep_state = "Sueño Profundo"
        elif motion_ratio < 0.025:
            sleep_state = "Sueño Ligero"
        else:
            sleep_state = "Despierto"

        # 1. Registro en memoria RAM para actualización de gráficos en vivo a alta frecuencia
        if now - self._last_ram_sample_time >= 0.4:
            self._last_ram_sample_time = now
            with self._lock:
                self._live_samples.append({
                    "timestamp": now,
                    "datetime": now_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "baby_present": bool(baby_present),
                    "motion_ratio": float(motion_ratio),
                    "audio_volume": float(audio_volume),
                    "sleep_state": sleep_state,
                    "is_crying": bool(is_crying)
                })

        # 2. Persistencia en disco (Event-Driven + Deadband)
        time_since_last = now - self._last_log_time
        state_changed = (sleep_state != self._last_state)
        crying_changed = (is_crying != self._last_crying)
        motion_jump = abs(motion_ratio - self._last_motion) > 0.015

        should_log = False
        if time_since_last >= 20.0:
            should_log = True
        elif (state_changed or crying_changed or motion_jump) and time_since_last >= 3.0:
            should_log = True

        if not should_log:
            return

        self._last_log_time = now
        self._last_state = sleep_state
        self._last_motion = motion_ratio
        self._last_crying = is_crying
        dt_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        try:
            with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    round(now, 2),
                    dt_str,
                    1 if baby_present else 0,
                    round(float(motion_ratio), 4),
                    round(float(audio_volume), 4),
                    sleep_state,
                    1 if is_crying else 0
                ])
        except Exception as e:
            logger.error(f"Error al escribir muestra en CSV: {e}")

    def get_live_rolling_samples(self) -> List[Dict]:
        """Obtiene las muestras más recientes en RAM para visualización en tiempo real."""
        with self._lock:
            return list(self._live_samples)

    def load_live_data(self) -> List[Dict]:
        """Carga los registros de la sesión activa actual."""
        if not os.path.exists(self.csv_path):
            return []

        records = []
        try:
            with open(self.csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    records.append({
                        "timestamp": float(row["timestamp"]),
                        "datetime": row["datetime"],
                        "baby_present": bool(int(row["baby_present"])),
                        "motion_ratio": float(row["motion_ratio"]),
                        "audio_volume": float(row["audio_volume"]),
                        "sleep_state": row["sleep_state"],
                        "is_crying": bool(int(row["is_crying"]))
                    })
        except Exception as e:
            logger.error(f"Error al leer datos del CSV: {e}")

        return records

    def compute_summary_statistics(self, view_mode: str = "LIVE") -> Dict:
        """
        Calcula las estadísticas consolidadas.
        view_mode: 'LIVE' (Sesión actual) o 'ALL_HISTORY' (Incluyendo snapshots anteriores).
        """
        records = self.load_live_data()
        ram_samples = self.get_live_rolling_samples()
        
        # Si se solicita historial completo, incorporar snapshots anteriores
        history_snapshots = self.load_all_snapshots() if view_mode == "ALL_HISTORY" else []

        # Si el CSV aún no tiene eventos pero ya hay muestras en RAM:
        effective_records = records if records else ram_samples

        if not effective_records and not history_snapshots:
            return {
                "total_samples": 0,
                "total_hours": 0.0,
                "sleep_distribution": {"Sueño Profundo": 0, "Sueño Ligero": 0, "Despierto": 0, "Fuera de Cuna": 0},
                "deep_sleep_pct": 0.0,
                "light_sleep_pct": 0.0,
                "awake_pct": 0.0,
                "crying_episodes": 0,
                "avg_motion": 0.0,
                "sleep_quality_score": 100,
                "times": [],
                "motions": [],
                "audios": [],
                "live_motions": [],
                "live_audios": [],
                "snapshots_count": len(history_snapshots)
            }

        state_counts = {"Sueño Profundo": 0, "Sueño Ligero": 0, "Despierto": 0, "Fuera de Cuna": 0}
        crying_count = 0
        total_motion = 0.0
        total_seconds = 0.0

        times = []
        motions = []
        audios = []

        # 1. Procesar registros de la sesión viva
        prev_time = None
        for r in effective_records:
            st = r["sleep_state"]
            if st in state_counts:
                state_counts[st] += 1
            if r["is_crying"]:
                crying_count += 1
            total_motion += r["motion_ratio"]

            if prev_time is not None:
                delta = min(30.0, max(0.5, r["timestamp"] - prev_time))
                total_seconds += delta
            else:
                total_seconds += 2.0
            prev_time = r["timestamp"]

            times.append(r["datetime"][11:16]) # HH:MM
            motions.append(r["motion_ratio"] * 100.0)
            audios.append(r["audio_volume"] * 100.0)

        # Si hay muestras de alta resolución en RAM, utilizarlas para la serie temporal en vivo
        if ram_samples:
            live_motions = [s["motion_ratio"] * 100.0 for s in ram_samples]
            live_audios = [s["audio_volume"] * 100.0 for s in ram_samples]
        else:
            live_motions = motions[-60:]
            live_audios = audios[-60:]

        # 2. Agregar métricas acumuladas de snapshots si se visualiza historial
        for snap in history_snapshots:
            for k in state_counts:
                state_counts[k] += snap.get("sleep_distribution", {}).get(k, 0)
            crying_count += snap.get("crying_episodes", 0)
            total_seconds += snap.get("total_hours", 0.0) * 3600.0

        total_samples = sum(state_counts.values()) or 1
        total_hours = total_seconds / 3600.0

        deep_pct = (state_counts["Sueño Profundo"] / float(total_samples)) * 100.0
        light_pct = (state_counts["Sueño Ligero"] / float(total_samples)) * 100.0
        awake_pct = (state_counts["Despierto"] / float(total_samples)) * 100.0

        # Score Pediátrico de Calidad de Sueño (0 - 100)
        score = 100.0
        score -= (awake_pct * 0.4)
        score -= (crying_count * 2.0)
        if deep_pct > 40.0:
            score += 5.0
        score = max(15.0, min(100.0, score))

        return {
            "total_samples": total_samples,
            "total_hours": round(total_hours, 1),
            "sleep_distribution": state_counts,
            "deep_sleep_pct": round(deep_pct, 1),
            "light_sleep_pct": round(light_pct, 1),
            "awake_pct": round(awake_pct, 1),
            "crying_episodes": crying_count,
            "avg_motion": round((total_motion / max(1, len(effective_records))) * 100.0, 2),
            "sleep_quality_score": int(score),
            "times": times,
            "motions": motions,
            "audios": audios,
            "live_motions": live_motions,
            "live_audios": live_audios,
            "snapshots_count": len(history_snapshots)
        }

    def create_snapshot(self, date_label: Optional[str] = None) -> Optional[str]:
        """
        Crea un Snapshot condensado e inteligente de la sesión actual en formato JSON (~1 KB).
        Guarda los KPIs consolidados y permite archivar sin consumir espacio.
        """
        stats = self.compute_summary_statistics(view_mode="LIVE")
        if stats["total_samples"] == 0:
            return None

        date_str = date_label or datetime.now().strftime("%Y-%m-%d_%H%M")
        snapshot_filename = f"snapshot_{date_str}.json"
        snapshot_path = os.path.join(self.snapshots_dir, snapshot_filename)

        snapshot_data = {
            "date": date_str,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_hours": stats["total_hours"],
            "sleep_quality_score": stats["sleep_quality_score"],
            "deep_sleep_pct": stats["deep_sleep_pct"],
            "light_sleep_pct": stats["light_sleep_pct"],
            "awake_pct": stats["awake_pct"],
            "crying_episodes": stats["crying_episodes"],
            "sleep_distribution": stats["sleep_distribution"]
        }

        try:
            with open(snapshot_path, "w", encoding="utf-8") as f:
                json.dump(snapshot_data, f, indent=2)
            logger.info(f"✨ Snapshot inteligente creado con éxito: {snapshot_path}")
            return snapshot_path
        except Exception as e:
            logger.error(f"Error al crear snapshot: {e}")
            return None

    def load_all_snapshots(self) -> List[Dict]:
        """Carga todos los snapshots consolidados almacenados en data/analytics/snapshots/."""
        if not os.path.exists(self.snapshots_dir):
            return []

        snapshots = []
        for fname in sorted(os.listdir(self.snapshots_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(self.snapshots_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        snapshots.append(data)
                except Exception:
                    pass
        return snapshots

    def clear_live_session(self):
        """Limpia el archivo de sesión activa para empezar desde cero conservando snapshots."""
        try:
            if os.path.exists(self.csv_path):
                os.remove(self.csv_path)
            self._init_csv()
            logger.info("Sesión activa reiniciada con éxito (Snapshots históricos conservados).")
        except Exception as e:
            logger.error(f"Error al limpiar sesión activa: {e}")

    def clear_all_history(self):
        """Limpia la sesión activa Y todos los snapshots históricos."""
        self.clear_live_session()
        try:
            if os.path.exists(self.snapshots_dir):
                shutil.rmtree(self.snapshots_dir)
            os.makedirs(self.snapshots_dir, exist_ok=True)
            logger.info("Historial total y snapshots eliminados.")
        except Exception as e:
            logger.error(f"Error al eliminar historial de snapshots: {e}")

    def export_consolidated_report(self, destination_path: str) -> bool:
        """Exporta un reporte completo consolidando la sesión en vivo y todos los snapshots."""
        stats = self.compute_summary_statistics(view_mode="ALL_HISTORY")
        try:
            with open(destination_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["REPORTE DE SALUD Y CALIDAD DE DESCANSO DEL BEBE"])
                writer.writerow(["Fecha de Generación", datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
                writer.writerow(["Índice de Calidad de Sueño (0-100)", stats["sleep_quality_score"]])
                writer.writerow(["Horas Totales Monitoreadas", stats["total_hours"]])
                writer.writerow(["Porcentaje Sueño Profundo", f"{stats['deep_sleep_pct']}%"])
                writer.writerow(["Porcentaje Sueño Ligero", f"{stats['light_sleep_pct']}%"])
                writer.writerow(["Porcentaje Despierto", f"{stats['awake_pct']}%"])
                writer.writerow(["Episodios de Llanto / Alertas", stats["crying_episodes"]])
                writer.writerow([])
                writer.writerow(["DISTRIBUCION DE ESTADOS DE SUEÑO (Muestras)"])
                for k, v in stats["sleep_distribution"].items():
                    writer.writerow([k, v])
            return True
        except Exception as e:
            logger.error(f"Error al exportar reporte consolidado: {e}")
            return False
