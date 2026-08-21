"""
Servicio de Reproducción de Alarma Sonora y Bip Auditivo (SoundService).
Sintetiza y reproduce bips de alerta sin congelar el hilo de la interfaz.
"""
import logging
import threading

logger = logging.getLogger("BabyDetector.Sound")

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

class SoundService:
    """
    Controla la inicialización de audio y la reproducción no bloqueante de alertas sonoras.
    """
    def __init__(self):
        self.initialized = False
        self._sound_cache = None
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
                self.initialized = True
            except Exception as e:
                logger.warning(f"No se pudo inicializar pygame mixer: {e}")

    def play_beep(self):
        """Reproduce un bip de alerta suave en un hilo independiente para evitar lag."""
        threading.Thread(target=self._play_beep_sync, daemon=True).start()

    def _play_beep_sync(self):
        if not self.initialized:
            try:
                import winsound
                winsound.Beep(880, 180)
            except Exception:
                pass
            return

        try:
            if self._sound_cache is None:
                import numpy as np
                duration = 0.18 # segundos
                sample_rate = 44100
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                # Tono senoidal suave a 880Hz (La5) con decaimiento exponencial
                tone = np.sin(2 * np.pi * 880 * t) * np.exp(-t * 6.0)
                audio_data = (tone * 32767 * 0.5).astype(np.int16)
                self._sound_cache = pygame.sndarray.make_sound(audio_data)

            if self._sound_cache is not None:
                self._sound_cache.play()
        except Exception as e:
            try:
                import winsound
                winsound.Beep(880, 180)
            except Exception:
                pass
