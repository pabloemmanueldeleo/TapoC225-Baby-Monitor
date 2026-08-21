"""
Ventana Emergente Always-on-Top (Pop-up flotante de esquina) para alertas de movimiento y audio.
"""
import os
import time
import cv2
import numpy as np
from typing import Optional, Union

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFrame
)

class CornerAlertWindow(QDialog):
    """
    Pop-Up emergente flotante e independiente Always-on-Top.
    Muestra el fotograma recortado del bebé/cuna y se mantiene por encima de todas las ventanas.
    """
    pause_requested = Signal()
    image_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(None) # Parent None para que sea ventana 100% independiente del OS
        self.setWindowTitle("⚠️ ALERTA TAPO C225")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.resize(360, 290)
        self.setStyleSheet("QDialog { background-color: #0F172A; } QLabel { color: #F8FAFC; }")

        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame {
                background-color: #0F172A;
                border: 2px solid #EF4444;
                border-radius: 12px;
            }
        """)
        card_layout = QVBoxLayout(self.card)

        # Encabezado con título
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("⚠️ ¡ALERTA EN CUNA!", self.card)
        self.lbl_title.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 13px; border: none;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        card_layout.addLayout(header_layout)

        # Mensaje de Alerta
        self.lbl_msg = QLabel("Movimiento o llanto detectado", self.card)
        self.lbl_msg.setStyleSheet("color: #F87171; font-size: 11px; font-weight: bold; border: none;")
        card_layout.addWidget(self.lbl_msg)

        # Visor de recorte de Bebé / Cuna (Interactivo para abrir/enfocar el monitor)
        self.lbl_crop = QLabel(self.card)
        self.lbl_crop.setAlignment(Qt.AlignCenter)
        self.lbl_crop.setCursor(Qt.PointingHandCursor)
        self.lbl_crop.setToolTip("🔍 Haz clic para abrir y enfocar el monitor principal")
        self.lbl_crop.setStyleSheet("""
            QLabel {
                background-color: #1E293B;
                border-radius: 8px;
                border: 1px solid #334155;
            }
            QLabel:hover {
                border: 1px solid #38BDF8;
                background-color: #243247;
            }
        """)
        self.lbl_crop.setMinimumHeight(140)
        self.lbl_crop.mousePressEvent = self._on_image_clicked
        card_layout.addWidget(self.lbl_crop)

        # Indicador de ayuda
        self.lbl_hint = QLabel("🔍 Clic en la imagen para abrir la ventana completa", self.card)
        self.lbl_hint.setAlignment(Qt.AlignCenter)
        self.lbl_hint.setCursor(Qt.PointingHandCursor)
        self.lbl_hint.setStyleSheet("color: #94A3B8; font-size: 9px; border: none; margin-top: -2px;")
        self.lbl_hint.mousePressEvent = self._on_image_clicked
        card_layout.addWidget(self.lbl_hint)

        # Botones de Acción (Pausar 1 Minuto & Cerrar)
        btn_layout = QHBoxLayout()
        btn_pause = QPushButton("⏸️ Detener Alarma (1 Min)", self.card)
        btn_pause.setFixedHeight(28)
        btn_pause.setStyleSheet("""
            QPushButton { background-color: #0284C7; color: white; border-radius: 6px; font-weight: bold; font-size: 11px; border: none; padding: 0 8px; }
            QPushButton:hover { background-color: #0369A1; }
        """)
        btn_pause.clicked.connect(self._on_pause_clicked)

        btn_close = QPushButton("✕ Cerrar", self.card)
        btn_close.setFixedSize(70, 28)
        btn_close.setStyleSheet("""
            QPushButton { background-color: #64748B; color: white; border-radius: 6px; font-weight: bold; font-size: 11px; border: none; }
            QPushButton:hover { background-color: #475569; }
        """)
        btn_close.clicked.connect(self._on_close_clicked)

        btn_layout.addWidget(btn_pause)
        btn_layout.addWidget(btn_close)
        card_layout.addLayout(btn_layout)

        main_layout.addWidget(self.card)
        self.suppress_until = 0.0
        self._reposition_to_bottom_right()

    def _on_image_clicked(self, event=None):
        self.suppress_until = time.time() + 10.0
        self.hide()
        self.image_clicked.emit()

    def _on_pause_clicked(self):
        self.pause_requested.emit()
        self.suppress_until = time.time() + 60.0
        self.hide()

    def _on_close_clicked(self):
        self.suppress_until = time.time() + 6.0
        self.hide()

    def closeEvent(self, event):
        self.suppress_until = time.time() + 6.0
        self.hide()
        event.ignore()

    def _reposition_to_bottom_right(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - self.width() - 20
        y = screen.height() - self.height() - 20
        self.move(x, y)

    def trigger_alert(self, title: str, message: str, crop_img: Optional[np.ndarray], alert_level: str = "normal"):
        now = time.time()
        if now < getattr(self, "suppress_until", 0.0):
            return

        is_already_visible = self.isVisible()
        level_changed = (alert_level != getattr(self, "current_alert_level", ""))

        self.current_alert_level = alert_level

        if alert_level == "critical":
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #240A10;
                    border: 3px solid #EF4444;
                    border-radius: 12px;
                }
            """)
            self.lbl_title.setText(f"🚨 {title}")
            self.lbl_title.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 13px; border: none;")
            self.lbl_msg.setText(message)
            self.lbl_msg.setStyleSheet("color: #FCA5A5; font-size: 11px; font-weight: bold; border: none;")
        elif alert_level == "sound":
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #1E170A;
                    border: 2px solid #F59E0B;
                    border-radius: 12px;
                }
            """)
            self.lbl_title.setText(f"👶 {title}")
            self.lbl_title.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 13px; border: none;")
            self.lbl_msg.setText(message)
            self.lbl_msg.setStyleSheet("color: #FDE68A; font-size: 11px; font-weight: bold; border: none;")
        else:
            self.card.setStyleSheet("""
                QFrame {
                    background-color: #0F172A;
                    border: 2px solid #EF4444;
                    border-radius: 12px;
                }
            """)
            self.lbl_title.setText(f"⚠️ {title}")
            self.lbl_title.setStyleSheet("color: #EF4444; font-weight: bold; font-size: 13px; border: none;")
            self.lbl_msg.setText(message)
            self.lbl_msg.setStyleSheet("color: #F87171; font-size: 11px; font-weight: bold; border: none;")

        # Actualizar la captura únicamente cuando se abre la alerta o si cambia el nivel de severidad
        # Esto previene que actúe como un reproductor continuo de video a 30 FPS en el pop-up.
        if not is_already_visible or level_changed:
            self.update_crop(crop_img)

        if not is_already_visible:
            self._reposition_to_bottom_right()
            self.show()
            self.raise_()
            self.activateWindow()

    def reset_manual_close(self):
        self.suppress_until = 0.0

    def update_crop(self, crop_img: Union[np.ndarray, str, None]):
        if isinstance(crop_img, str) and crop_img == "AUDIO_ONLY":
            img = np.zeros((140, 240, 3), dtype=np.uint8)
            img[:] = (30, 27, 15)
            cv2.putText(img, "AUDIO / LLANTO", (40, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)
            cv2.putText(img, "Sin Movimiento Visual", (40, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            cv2.circle(img, (120, 110), 12, (0, 200, 255), -1)
            cv2.putText(img, "(( ! ))", (105, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1)

            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg).scaled(
                self.lbl_crop.width() - 10, self.lbl_crop.height() - 10,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_crop.setPixmap(pixmap)
        elif crop_img is not None and isinstance(crop_img, np.ndarray) and crop_img.size > 0:
            rgb = cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            bytes_per_line = ch * w
            qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg).scaled(
                self.lbl_crop.width() - 10, self.lbl_crop.height() - 10,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_crop.setPixmap(pixmap)
