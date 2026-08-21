"""
Lienzo gráfico de alta definición (Video Canvas) con soporte de aceleración gráfica,
Zoom vectorial interactivo por ratón, arrastre panorámico (Pan),
y renderizado de metadatos desacoplado (Vector Overlay) con QPainter.
"""
import cv2
import numpy as np
from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPoint, QRect, QRectF, QPointF
from PySide6.QtGui import (
    QImage, QPixmap, QFont, QColor, QPainter, QPen, QBrush,
    QPolygonF
)
from PySide6.QtWidgets import QLabel

class VideoCanvas(QLabel):
    """
    Visor de video en PySide6 con soporte de Zoom interactivo por ratón (Rueda),
    arrastre panorámico (Pan) y dibujo de rectángulo ROI exacto.
    """
    roi_changed = Signal(tuple)
    crop_selected = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #020617; border-radius: 8px;")
        
        self.current_qimage: Optional[QImage] = None
        self.render_rect = QRect()
        self.is_drawing = False
        self.drag_start = QPoint()
        self.drag_current = QPoint()
        self.mouse_mode = "NONE"
        # Zoom y Panorámica (Pan)
        self.zoom_factor = 1.0
        self.pan_offset = QPoint(0, 0)
        self.is_panning = False
        self.pan_start = QPoint()
        self.vector_overlay = {}
        self.selected_crop_norm: Optional[Tuple[float, float, float, float]] = None
        self.clean_osd_enabled: bool = True

    def set_clean_osd(self, enabled: bool):
        self.clean_osd_enabled = bool(enabled)
        self.update()

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.pan_offset = QPoint(0, 0)
        self.update()

    def clear_selected_crop(self):
        self.selected_crop_norm = None
        self.update()

    def set_mouse_mode(self, mode: str):
        self.mouse_mode = mode
        if mode == "NONE":
            self.is_drawing = False
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    def wheelEvent(self, event):
        """ Zoom con la rueda del ratón (Wheel) """
        angle_delta = event.angleDelta().y()
        if angle_delta > 0:
            new_zoom = min(self.zoom_factor * 1.15, 5.0)
        else:
            new_zoom = max(self.zoom_factor / 1.15, 1.0)

        if new_zoom == 1.0:
            self.pan_offset = QPoint(0, 0)
        elif new_zoom != self.zoom_factor:
            mouse_pos = event.position().toPoint()
            factor_change = new_zoom / self.zoom_factor
            self.pan_offset = (self.pan_offset - mouse_pos) * factor_change + mouse_pos

        self.zoom_factor = new_zoom
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton or event.button() == Qt.MiddleButton:
            if self.zoom_factor > 1.0:
                self.is_panning = True
                self.pan_start = event.position().toPoint() - self.pan_offset
        elif event.button() == Qt.LeftButton:
            if self.mouse_mode != "NONE":
                self.is_drawing = True
                self.drag_start = event.position().toPoint()
                self.drag_current = self.drag_start

    def mouseMoveEvent(self, event):
        if self.is_panning:
            self.pan_offset = event.position().toPoint() - self.pan_start
            self.update()
        elif self.is_drawing:
            self.drag_current = event.position().toPoint()
            self.update()

    def _screen_to_norm_coords(self, pt: QPoint) -> Tuple[float, float]:
        """Convierte exactamente un punto de pantalla al espacio normalizado [0.0 - 1.0] del video, respetando Zoom y Pan."""
        if self.render_rect.isEmpty() or self.render_rect.width() <= 0 or self.render_rect.height() <= 0:
            return 0.0, 0.0
        
        center = QPointF(self.render_rect.center())
        x_img = (float(pt.x()) - float(self.pan_offset.x()) - center.x()) / float(self.zoom_factor) + center.x()
        y_img = (float(pt.y()) - float(self.pan_offset.y()) - center.y()) / float(self.zoom_factor) + center.y()
        
        rx = float(self.render_rect.x())
        ry = float(self.render_rect.y())
        rw = float(self.render_rect.width())
        rh = float(self.render_rect.height())
        
        norm_x = max(0.0, min(1.0, (x_img - rx) / rw))
        norm_y = max(0.0, min(1.0, (y_img - ry) / rh))
        return norm_x, norm_y

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.RightButton or event.button() == Qt.MiddleButton) and self.is_panning:
            self.is_panning = False
        elif event.button() == Qt.LeftButton and self.is_drawing:
            self.is_drawing = False
            self.drag_current = event.position().toPoint()
            
            nx1, ny1 = self._screen_to_norm_coords(self.drag_start)
            nx2, ny2 = self._screen_to_norm_coords(self.drag_current)
            
            x1, x2 = min(nx1, nx2), max(nx1, nx2)
            y1, y2 = min(ny1, ny2), max(ny1, ny2)
            if (x2 - x1) > 0.005 and (y2 - y1) > 0.005:
                if self.mouse_mode == "🖐️ Recortar Parte Bebé":
                    self.selected_crop_norm = (x1, y1, x2, y2)
                    self.crop_selected.emit((x1, y1, x2, y2))
                else:
                    self.roi_changed.emit((x1, y1, x2, y2))
            self.update()

    def set_vector_overlay(self, data: dict):
        self.vector_overlay = data if data else {}

    def update_frame(self, cv_frame: np.ndarray, vector_overlay: Optional[dict] = None):
        if vector_overlay is not None:
            self.vector_overlay = vector_overlay
        fh, fw, ch = cv_frame.shape
        bytes_per_line = ch * fw
        rgb = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
        self.raw_image_size = (fw, fh)
        self.current_qimage = QImage(rgb.data, fw, fh, bytes_per_line, QImage.Format_RGB888).copy()
        
        lbl_w, lbl_h = self.width(), self.height()
        if lbl_w <= 0 or lbl_h <= 0 or fw <= 0 or fh <= 0:
            return
        
        scale = min(lbl_w / float(fw), lbl_h / float(fh))
        disp_w, disp_h = int(fw * scale), int(fh * scale)
        offset_x = (lbl_w - disp_w) // 2
        offset_y = (lbl_h - disp_h) // 2

        self.render_rect = QRect(offset_x, offset_y, disp_w, disp_h)
        self.update()

    def _draw_vector_badge(self, painter: QPainter, x: float, y: float, w: float, h: float,
                           label: str, stroke_color: QColor, bg_color: QColor,
                           corner_len: float = 24.0, is_crib: bool = False):
        """Dibuja un recuadro vectorial sutil, translúcido y no invasivo."""
        # 1. Bounding Box con bordes sutiles (sin tapar la imagen de la cámara)
        if is_crib:
            pen = QPen(QColor(stroke_color.red(), stroke_color.green(), stroke_color.blue(), 140), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(x, y, w, h)
            painter.drawRoundedRect(rect, 4, 4)
        else:
            pen = QPen(QColor(stroke_color.red(), stroke_color.green(), stroke_color.blue(), 170), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            rect = QRectF(x, y, w, h)
            painter.drawRoundedRect(rect, 4, 4)

        # 2. Esquinas Acentuadas Tácticas (Corner Brackets)
        cl = min(corner_len, min(w, h) * 0.25)
        if cl > 6:
            pen_corner = QPen(stroke_color, 2.5, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
            painter.setPen(pen_corner)
            painter.drawLine(QPointF(x, y), QPointF(x + cl, y))
            painter.drawLine(QPointF(x, y), QPointF(x, y + cl))
            painter.drawLine(QPointF(x + w, y), QPointF(x + w - cl, y))
            painter.drawLine(QPointF(x + w, y), QPointF(x + w, y + cl))
            painter.drawLine(QPointF(x, y + h), QPointF(x + cl, y + h))
            painter.drawLine(QPointF(x, y + h), QPointF(x, y + h - cl))
            painter.drawLine(QPointF(x + w, y + h), QPointF(x + w - cl, y + h))
            painter.drawLine(QPointF(x + w, y + h), QPointF(x + w, y + h - cl))

        # 3. Badge Translúcido (Opcional si Clean OSD está desactivado)
        if not getattr(self, "clean_osd_enabled", True) and label:
            font = QFont("Segoe UI", 8, QFont.Bold)
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label)
            text_h = fm.height()
            pad_x, pad_y = 6, 2

            badge_w = text_w + pad_x * 2
            badge_h = text_h + pad_y * 2
            badge_x = x
            badge_y = y - badge_h - 2 if y - badge_h - 2 > 5 else y + 2

            badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)
            trans_bg = QColor(bg_color.red(), bg_color.green(), bg_color.blue(), 85)
            trans_stroke = QColor(stroke_color.red(), stroke_color.green(), stroke_color.blue(), 140)
            painter.setPen(QPen(trans_stroke, 1.0))
            painter.setBrush(QBrush(trans_bg))
            painter.drawRoundedRect(badge_rect, 4, 4)

            painter.setPen(QPen(QColor("#F8FAFC")))
            painter.drawText(QRectF(badge_x + pad_x, badge_y + pad_y, text_w + 4, text_h), Qt.AlignVCenter, label)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.fillRect(self.rect(), QColor("#020617"))

        if hasattr(self, "current_qimage") and self.current_qimage and not self.render_rect.isEmpty():
            painter.save()
            if self.zoom_factor != 1.0 or self.pan_offset != QPoint(0, 0):
                painter.translate(self.pan_offset)
                center = self.render_rect.center()
                painter.translate(center)
                painter.scale(self.zoom_factor, self.zoom_factor)
                painter.translate(-center)

            # Capa 0: Video Crudo y Limpio en Alta Resolución
            pixmap = QPixmap.fromImage(self.current_qimage)
            painter.drawPixmap(self.render_rect, pixmap)

            # Capa 1: Overlay Gráfico Vectorial Desacoplado
            rx = float(self.render_rect.x())
            ry = float(self.render_rect.y())
            rw = float(self.render_rect.width())
            rh = float(self.render_rect.height())

            if hasattr(self, "vector_overlay") and self.vector_overlay:
                # 1. Silueta de Segmentación Vectorial (Bebé) - Ultra Translúcida
                for mask_poly in self.vector_overlay.get("baby_masks_norm", []):
                    if len(mask_poly) > 2:
                        qpoly = QPolygonF([QPointF(rx + pt[0] * rw, ry + pt[1] * rh) for pt in mask_poly])
                        poly_pen = QPen(QColor("#EC4899"), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                        painter.setPen(poly_pen)
                        painter.setBrush(QBrush(QColor(236, 72, 153, 24)))
                        painter.drawPolygon(qpoly)

                # 2. Zona Cuna Monitoreada
                roi_norm = self.vector_overlay.get("roi_norm")
                if roi_norm is not None and len(roi_norm) == 4:
                    cx1 = rx + roi_norm[0] * rw
                    cy1 = ry + roi_norm[1] * rh
                    cx2 = rx + roi_norm[2] * rw
                    cy2 = ry + roi_norm[3] * rh
                    self._draw_vector_badge(painter, cx1, cy1, cx2 - cx1, cy2 - cy1,
                                            "🎯 Zona Cuna",
                                            QColor("#0284C7"), QColor(15, 23, 42, 85),
                                            corner_len=24.0, is_crib=True)

                # 3. Recuadro de Bebé Reconocido
                baby_box = self.vector_overlay.get("baby_box_norm")
                if baby_box is not None and len(baby_box) == 4:
                    bx1 = rx + baby_box[0] * rw
                    by1 = ry + baby_box[1] * rh
                    bw_px = baby_box[2] * rw
                    bh_px = baby_box[3] * rh
                    b_name = self.vector_overlay.get("baby_name", "Bebé")
                    b_score = self.vector_overlay.get("baby_score", 0.85)
                    m_ratio = self.vector_overlay.get("motion_ratio", 0.0)
                    m_thresh = self.vector_overlay.get("motion_threshold", 0.03)

                    badge_label = f"👶 {b_name} ({b_score*100:.0f}%)"
                    badge_color = QColor("#EF4444") if m_ratio >= m_thresh else QColor("#F43F5E")
                    self._draw_vector_badge(painter, bx1, by1, bw_px, bh_px,
                                            badge_label,
                                            badge_color, QColor(24, 15, 26, 85),
                                            corner_len=18.0, is_crib=False)

            # 4. Recorte Seleccionado Activo por el Usuario
            if hasattr(self, "selected_crop_norm") and self.selected_crop_norm is not None and len(self.selected_crop_norm) == 4:
                sc_x1 = rx + self.selected_crop_norm[0] * rw
                sc_y1 = ry + self.selected_crop_norm[1] * rh
                sc_w = (self.selected_crop_norm[2] - self.selected_crop_norm[0]) * rw
                sc_h = (self.selected_crop_norm[3] - self.selected_crop_norm[1]) * rh
                self._draw_vector_badge(painter, sc_x1, sc_y1, sc_w, sc_h,
                                        "✂️ Recorte",
                                        QColor("#F97316"), QColor(30, 20, 10, 90),
                                        corner_len=16.0, is_crib=False)

            painter.restore()

        # Capa 2: Herramientas de Dibujo Interactivo del Ratón mientras se arrastra
        if self.is_drawing:
            painter.save()
            color = QColor("#F97316") if self.mouse_mode == "🖐️ Recortar Parte Bebé" else QColor("#38BDF8")
            pen = QPen(color, 2.0, Qt.DashLine)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 45)))
            rect = QRect(self.drag_start, self.drag_current).normalized()
            painter.drawRoundedRect(rect, 4, 4)
            painter.restore()
