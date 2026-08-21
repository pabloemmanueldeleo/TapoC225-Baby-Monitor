"""
Componentes y widgets visuales reutilizables para la interfaz PySide6.
"""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QWidget

class AudioThresholdProgressBar(QWidget):
    """
    Componente visual que muestra el medidor de decibeles ambiental (0-100%)
    con una línea divisoria vertical que indica la tolerancia/umbral de disparo configurado.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.value = 0.0      # Nivel actual 0.0 - 1.0
        self.threshold = 0.40  # Tolerancia 0.0 - 1.0

    def set_value_and_threshold(self, val: float, thresh: float):
        self.value = max(0.0, min(1.0, val))
        self.threshold = max(0.0, min(1.0, thresh))
        self.update()

    def set_value(self, val: float):
        self.value = max(0.0, min(1.0, val))
        self.update()

    def set_threshold(self, thresh: float):
        self.threshold = max(0.0, min(1.0, thresh))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()

        # Fondo oscuro de la barra
        painter.fillRect(rect, QColor("#1E293B"))

        # Color dinámico de la barra según si supera o se acerca a la tolerancia
        if self.value >= self.threshold:
            bar_color = QColor("#EF4444") # Rojo Alerta
        elif self.value >= self.threshold * 0.7:
            bar_color = QColor("#F59E0B") # Amarillo Advertencia
        else:
            bar_color = QColor("#10B981") # Verde Normal

        # Dibujar relleno del nivel actual de audio
        fill_w = int(w * self.value)
        if fill_w > 0:
            painter.fillRect(QRect(0, 0, fill_w, h), bar_color)

        # Dibujar Línea Indicadora de Tolerancia / Umbral Vertical
        thresh_x = int(w * self.threshold)
        line_color = QColor("#FFFFFF") if self.value < self.threshold else QColor("#EF4444")
        painter.setPen(QPen(line_color, 2, Qt.SolidLine))
        painter.drawLine(thresh_x, 0, thresh_x, h)

        # Pequeño marcador indicador flotante sobre la línea
        painter.setPen(QPen(QColor("#38BDF8"), 1))
        painter.setBrush(QBrush(QColor("#0284C7")))
        painter.drawRect(max(0, thresh_x - 3), 0, 6, 4)

        # Borde exterior estético
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
