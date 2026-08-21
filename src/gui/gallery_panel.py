"""
Panel de Galerías Visuales (Álbum de Fotos, Negativos Vetados y Sugerencias de IA).
Maneja la presentación gráfica, cards, scrolls horizontales y acciones directas.
"""
import os
import cv2
import numpy as np
from typing import Callable, Optional, List

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QFrame
)

class GalleryPanel(QObject):
    """
    Controlador de las tres galerías interactivas:
    1. Álbum de fotos del bebé
    2. Negativos / Falsos positivos vetados
    3. Sugerencias detectadas por la IA
    """
    album_updated = Signal()
    negatives_updated = Signal()
    start_crop_requested = Signal()

    def __init__(self, detector, parent_widget: QWidget, on_status_msg: Optional[Callable[[str, str], None]] = None):
        super().__init__(parent_widget)
        self.detector = detector
        self.parent = parent_widget
        self.on_status_msg = on_status_msg

        # Contenedores principales
        self.album_widget = QWidget(parent_widget)
        self.album_layout = QHBoxLayout(self.album_widget)
        self.album_layout.setContentsMargins(0, 0, 0, 0)

        self.negatives_widget = QWidget(parent_widget)
        self.negatives_layout = QHBoxLayout(self.negatives_widget)
        self.negatives_layout.setContentsMargins(0, 0, 0, 0)

        self.candidate_widget = QWidget(parent_widget)
        self.candidate_layout = QHBoxLayout(self.candidate_widget)
        self.candidate_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_album_title = QLabel("📸 Álbum de Fotos Guardadas (0)", parent_widget)
        self.lbl_album_title.setStyleSheet("font-weight: bold; color: #38BDF8;")

        self.lbl_negatives_title = QLabel("🚫 Falsos Positivos Vetados (0)", parent_widget)
        self.lbl_negatives_title.setStyleSheet("font-weight: bold; color: #FCA5A5; font-size: 11px; margin-top: 4px;")

    def update_album_ui(self):
        """Actualiza la galería visual de fotos del bebé en orden FIFO (más nueva a la izquierda)."""
        while self.album_layout.count():
            child = self.album_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        templates = getattr(self.detector, "target_templates", [])
        self.lbl_album_title.setText(f"📸 Álbum de Fotos Guardadas ({len(templates)})")

        if not templates:
            onboarding_box = QFrame(self.album_widget)
            onboarding_box.setStyleSheet("""
                QFrame {
                    background-color: #1E293B;
                    border: 1px dashed #38BDF8;
                    border-radius: 6px;
                    padding: 8px;
                }
            """)
            ob_layout = QVBoxLayout(onboarding_box)
            ob_layout.setContentsMargins(6, 6, 6, 6)
            ob_layout.setSpacing(4)

            lbl_ob_title = QLabel("💡 ¡Registra a tu Bebé!", onboarding_box)
            lbl_ob_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #38BDF8; border: none;")
            
            lbl_ob_desc = QLabel("Aún no tienes fotos registradas en el álbum. Recorta su carita o cuerpo con el ratón para que la IA aprenda su silueta única.", onboarding_box)
            lbl_ob_desc.setWordWrap(True)
            lbl_ob_desc.setStyleSheet("font-size: 10px; color: #CBD5E1; border: none; line-height: 1.2;")

            btn_start_crop = QPushButton("✂️ Recortar Primera Foto Ahora", onboarding_box)
            btn_start_crop.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; font-size: 10px; border-radius: 4px; padding: 5px;")
            btn_start_crop.clicked.connect(lambda: self.start_crop_requested.emit())

            ob_layout.addWidget(lbl_ob_title)
            ob_layout.addWidget(lbl_ob_desc)
            ob_layout.addWidget(btn_start_crop)
            self.album_layout.addWidget(onboarding_box)
        else:
            scroll = QScrollArea(self.album_widget)
            scroll.setFixedHeight(85)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

            cont = QWidget()
            cont_layout = QHBoxLayout(cont)
            cont_layout.setContentsMargins(0, 0, 0, 0)
            cont_layout.setSpacing(6)

            for item in templates:
                fname, img = item[0], item[1]
                card = QFrame(cont)
                card.setFixedSize(65, 75)
                card.setStyleSheet("background-color: #1E293B; border-radius: 4px; border: 1px solid #334155;")
                c_layout = QVBoxLayout(card)
                c_layout.setContentsMargins(2, 2, 2, 2)
                c_layout.setSpacing(2)

                lbl_pic = QLabel(card)
                lbl_pic.setAlignment(Qt.AlignCenter)
                lbl_pic.setFixedHeight(50)
                try:
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    ch, cw, _ = rgb.shape
                    qimg = QImage(rgb.data, cw, ch, 3 * cw, QImage.Format_RGB888)
                    lbl_pic.setPixmap(QPixmap.fromImage(qimg).scaled(58, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    pass

                btn_del = QPushButton("❌", card)
                btn_del.setFixedSize(16, 16)
                btn_del.setStyleSheet("background: #EF4444; color: white; border-radius: 8px; font-size: 8px; font-weight: bold; padding: 0;")
                btn_del.setToolTip(f"Eliminar foto {fname}")
                btn_del.clicked.connect(lambda _, fn=fname: self._on_delete_template(fn))

                c_layout.addWidget(lbl_pic)
                c_layout.addWidget(btn_del, alignment=Qt.AlignRight)
                cont_layout.addWidget(card)

            cont_layout.addStretch()
            scroll.setWidget(cont)
            self.album_layout.addWidget(scroll)

    def _on_delete_template(self, filename: str):
        if self.detector.delete_template(filename):
            self.update_album_ui()
            self.album_updated.emit()

    def update_negatives_ui(self):
        """Actualiza la galería visual de falsos positivos vetados en orden FIFO."""
        while self.negatives_layout.count():
            child = self.negatives_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        negatives = getattr(self.detector, "negative_templates", [])
        self.lbl_negatives_title.setText(f"🚫 Falsos Positivos Vetados ({len(negatives)})")

        if not negatives:
            hint_box = QFrame(self.negatives_widget)
            hint_box.setStyleSheet("""
                QFrame {
                    background-color: #1E293B;
                    border: 1px dashed #7F1D1D;
                    border-radius: 6px;
                    padding: 6px;
                }
            """)
            h_layout = QVBoxLayout(hint_box)
            h_layout.setContentsMargins(6, 4, 6, 4)
            h_layout.setSpacing(2)

            lbl_h_title = QLabel("🚫 Lista Negra de Falsos Positivos (0)", hint_box)
            lbl_h_title.setStyleSheet("font-size: 10px; font-weight: bold; color: #FCA5A5; border: none;")
            
            lbl_h_desc = QLabel("¿Una almohada o madera activa falsas alertas? Recórtala con el ratón y toca 'Vetar Falso Positivo' para ignorarla.", hint_box)
            lbl_h_desc.setWordWrap(True)
            lbl_h_desc.setStyleSheet("font-size: 9px; color: #94A3B8; border: none; line-height: 1.2;")

            h_layout.addWidget(lbl_h_title)
            h_layout.addWidget(lbl_h_desc)
            self.negatives_layout.addWidget(hint_box)
        else:
            scroll = QScrollArea(self.negatives_widget)
            scroll.setFixedHeight(75)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

            cont = QWidget()
            cont_layout = QHBoxLayout(cont)
            cont_layout.setContentsMargins(0, 0, 0, 0)
            cont_layout.setSpacing(6)

            for item in negatives:
                fname, img = item[0], item[1]
                card = QFrame(cont)
                card.setFixedSize(60, 68)
                card.setStyleSheet("background-color: #2D151B; border-radius: 4px; border: 1px solid #7F1D1D;")
                c_layout = QVBoxLayout(card)
                c_layout.setContentsMargins(2, 2, 2, 2)
                c_layout.setSpacing(2)

                lbl_pic = QLabel(card)
                lbl_pic.setAlignment(Qt.AlignCenter)
                lbl_pic.setFixedHeight(42)
                try:
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    ch, cw, _ = rgb.shape
                    qimg = QImage(rgb.data, cw, ch, 3 * cw, QImage.Format_RGB888)
                    lbl_pic.setPixmap(QPixmap.fromImage(qimg).scaled(52, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    pass

                btn_del = QPushButton("❌", card)
                btn_del.setFixedSize(16, 16)
                btn_del.setStyleSheet("background: #64748B; color: white; border-radius: 8px; font-size: 8px; font-weight: bold; padding: 0;")
                btn_del.setToolTip(f"Desvetar y permitir {fname}")
                btn_del.clicked.connect(lambda _, fn=fname: self._on_delete_negative(fn))

                c_layout.addWidget(lbl_pic)
                c_layout.addWidget(btn_del, alignment=Qt.AlignRight)
                cont_layout.addWidget(card)

            cont_layout.addStretch()
            scroll.setWidget(cont)
            self.negatives_layout.addWidget(scroll)

    def _on_delete_negative(self, filename: str):
        if self.detector.delete_negative_template(filename):
            self.update_negatives_ui()
            self.negatives_updated.emit()

    def update_candidates_ui(self):
        """Actualiza la galería visual de sugerencias detectadas automáticamente por la IA."""
        if not getattr(self.detector, "suggestions_enabled", False) or not self.candidate_widget.isVisible():
            return

        candidates = self.detector.get_recent_candidates()
        while self.candidate_layout.count():
            child = self.candidate_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not candidates:
            lbl_empty = QLabel("⏳ Esperando que la IA detecte al bebé en la cuna...", self.candidate_widget)
            lbl_empty.setStyleSheet("font-size: 10px; color: #94A3B8; font-style: italic; padding: 4px;")
            self.candidate_layout.addWidget(lbl_empty)
            return

        scroll = QScrollArea(self.candidate_widget)
        scroll.setFixedHeight(98)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        cont = QWidget()
        cont_layout = QHBoxLayout(cont)
        cont_layout.setContentsMargins(0, 0, 0, 0)
        cont_layout.setSpacing(6)

        for idx, (crop_img, score_lbl) in enumerate(candidates):
            card = QFrame(cont)
            card.setFixedSize(85, 92)
            card.setStyleSheet("background-color: #1E293B; border-radius: 4px; border: 1px solid #0EA5E9;")
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(2, 2, 2, 2)
            c_layout.setSpacing(2)

            lbl_pic = QLabel(card)
            lbl_pic.setAlignment(Qt.AlignCenter)
            lbl_pic.setFixedHeight(44)
            try:
                rgb = cv2.cvtColor(crop_img, cv2.COLOR_BGR2RGB)
                ch, cw, _ = rgb.shape
                qimg = QImage(rgb.data, cw, ch, 3 * cw, QImage.Format_RGB888)
                lbl_pic.setPixmap(QPixmap.fromImage(qimg).scaled(78, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception:
                pass

            btn_box = QHBoxLayout()
            btn_box.setContentsMargins(0, 0, 0, 0)
            btn_box.setSpacing(2)

            btn_add = QPushButton("➕ Bebé", card)
            btn_add.setStyleSheet("background: #0284C7; color: white; border-radius: 3px; font-size: 8px; font-weight: bold; padding: 2px 3px;")
            btn_add.setToolTip("Guardar foto en el álbum del bebé")
            btn_add.clicked.connect(lambda _, c=crop_img: self._on_add_candidate(c))

            btn_veto = QPushButton("🚫 Vetar", card)
            btn_veto.setStyleSheet("background: #DC2626; color: white; border-radius: 3px; font-size: 8px; font-weight: bold; padding: 2px 3px;")
            btn_veto.setToolTip("Vetar como falso positivo (almohada/fondo)")
            btn_veto.clicked.connect(lambda _, c=crop_img: self._on_veto_candidate(c))

            btn_box.addWidget(btn_add)
            btn_box.addWidget(btn_veto)

            c_layout.addWidget(lbl_pic)
            c_layout.addLayout(btn_box)
            cont_layout.addWidget(card)

        cont_layout.addStretch()
        scroll.setWidget(cont)
        self.candidate_layout.addWidget(scroll)

    def _on_add_candidate(self, crop: np.ndarray):
        if self.detector.save_target_template_from_crop(crop):
            self.update_album_ui()
            if hasattr(self.detector, "recent_candidates"):
                self.detector.recent_candidates = [cand for cand in self.detector.recent_candidates if not np.array_equal(cand[0], crop)]
            self.update_candidates_ui()
            if self.on_status_msg:
                self.on_status_msg("✨ ¡Foto sugerida agregada con éxito al álbum del bebé!", "#38BDF8")
            self.album_updated.emit()

    def _on_veto_candidate(self, crop: np.ndarray):
        if self.detector.save_negative_template_from_crop(crop):
            self.update_negatives_ui()
            if hasattr(self.detector, "recent_candidates"):
                self.detector.recent_candidates = [cand for cand in self.detector.recent_candidates if not np.array_equal(cand[0], crop)]
            self.update_candidates_ui()
            if self.on_status_msg:
                self.on_status_msg("🚫 ¡Sugerencia añadida a la lista de falsos positivos vetados!", "#F87171")
            self.negatives_updated.emit()
