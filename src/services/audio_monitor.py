import logging
import threading
import time
import numpy as np
from typing import Optional

try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

logger = logging.getLogger("AudioMonitor")

class RTSPAudioMonitor:
    """
    Decodifica el flujo de audio RTSP de la cámara Tapo C225 en tiempo real para calcular
    el nivel de volumen ambiental RMS y transmitir el audio a los altavoces de Windows.
    """
    def __init__(self, rtsp_url: str):
        self.rtsp_url = rtsp_url
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.current_volume: float = 0.0 # 0.0 a 1.0
        self.threshold: float = 0.40 # Umbral por defecto (40%)
        self.passthrough_enabled = False # Escuchar audio en altavoces de Windows
        self.audio_out_stream = None
        self.lock = threading.Lock()
        self.warmup_count = 30 # Descartar primeros 30 paquetes de audio de inicio para estabilizar RMS

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.thread.start()

    def _delayed_start(self, delay: float):
        """Arrancar con retraso para no competir con el video stream por el slot RTSP."""
        import time
        time.sleep(delay)
        if self.running:
            self._audio_loop()

    def set_passthrough(self, enabled: bool):
        with self.lock:
            self.passthrough_enabled = enabled
        logger.info(f"Reproducción de audio en altavoces de Windows: {enabled}")

    def set_threshold(self, value: float):
        with self.lock:
            self.threshold = max(0.05, min(1.0, value))


    def get_volume(self) -> float:
        with self.lock:
            return self.current_volume

    def is_sound_alert(self) -> bool:
        with self.lock:
            return self.current_volume > self.threshold

    def _audio_loop(self):
        if not AV_AVAILABLE:
            logger.warning("Librería 'av' (PyAV) no disponible. Nivel de volumen en modo estimación.")
            self._fallback_loop()
            return

        try:
            av.logging.set_level(av.logging.ERROR)
        except Exception:
            pass

        retry_delay = 5.0
        while self.running:
            try:
                # Opciones de transporte TCP con timeout optimizado para la Tapo C225
                options = {
                    "rtsp_transport": "tcp",
                    "max_delay": "500000",
                    "flags": "low_delay"
                }
                container = av.open(self.rtsp_url, options=options)
                audio_streams = [s for s in container.streams if s.type == 'audio']
                
                if not audio_streams:
                    logger.warning("No se encontró stream de audio en la cámara Tapo C225 (verifique permisos de micrófono en App Tapo).")
                    container.close()
                    time.sleep(retry_delay)
                    continue

                audio_stream = audio_streams[0]
                rate = audio_stream.rate or 16000
                channels = audio_stream.channels or 1

                # Dispositivo de altavoces de Windows
                audio_out = None
                if SOUNDDEVICE_AVAILABLE:
                    try:
                        audio_out = sd.OutputStream(samplerate=rate, channels=channels, dtype='int16')
                        audio_out.start()
                    except Exception as sd_err:
                        logger.warning(f"No se pudo abrir dispositivo de audio de Windows: {sd_err}")

                for frame in container.decode(audio_stream):
                    if not self.running:
                        break
                    
                    arr = frame.to_ndarray()
                    if arr.size > 0:
                        # 1. Reproducir por altavoces si está activo
                        if self.passthrough_enabled and audio_out and SOUNDDEVICE_AVAILABLE:
                            try:
                                # Transponer si los canales están en forma (canales, muestras)
                                pcm_data = arr.T if (arr.ndim > 1 and arr.shape[0] == channels) else arr
                                audio_out.write(pcm_data.astype(np.int16))
                            except Exception:
                                pass

                        # 2. Calcular valor RMS (Root Mean Square) para el medidor
                        if self.warmup_count > 0:
                            self.warmup_count -= 1
                            rms_vol = 0.0
                        else:
                            float_arr = arr.astype(np.float32)
                            rms = np.sqrt(np.mean(float_arr**2))
                            # Escala mejorada de sensibilidad para ruidos de habitación (escala 6000)
                            rms_vol = float(np.clip(rms / 6000.0, 0.0, 1.0))

                        with self.lock:
                            self.current_volume = self.current_volume * 0.5 + rms_vol * 0.5

                if audio_out:
                    try:
                        audio_out.stop()
                        audio_out.close()
                    except Exception:
                        pass
                container.close()

            except Exception as e:
                logger.debug(f"Reintentando conexión de audio RTSP: {e}")
                time.sleep(4)

    def _fallback_loop(self):
        """Simulación suave si av no está activo"""
        while self.running:
            # Pequeño ruido de fondo simulado
            sim_vol = 0.05 + 0.03 * np.random.rand()
            with self.lock:
                self.current_volume = sim_vol
            time.sleep(0.1)

    def stop(self):
        self.running = False
        self.passthrough_enabled = False
        if hasattr(self, "audio_out_stream") and self.audio_out_stream:
            try:
                self.audio_out_stream.stop()
                self.audio_out_stream.close()
            except Exception:
                pass

