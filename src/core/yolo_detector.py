"""
Motor de Inferencia Neuronal YOLOv8-seg (Ultralytics / ONNX Runtime).
Encapsula la carga del modelo neuronal, inferencia de segmentación y decodificación de polígonos.
"""
import os
import sys
import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Tuple, Optional

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

logger = logging.getLogger("BabyDetector.YOLO")

class YoloDetector:
    """
    Controla el ciclo de vida del modelo YOLOv8-seg y ejecuta la inferencia de personas/bebés y máscaras.
    """
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and YOLO_AVAILABLE
        self.yolo_model = None
        if self.enabled:
            import threading
            threading.Thread(target=self._init_model, daemon=True).start()

    def _init_model(self):
        try:
            base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            pt_seg_path = os.path.join(base_dir, "yolov8n-seg.pt")
            onnx_path = os.path.join(base_dir, "yolov8n-seg.onnx")

            if os.path.exists(pt_seg_path):
                logger.info("Cargando modelo neuronal YOLOv8n-seg (.pt PyTorch)...")
                self.yolo_model = YOLO(pt_seg_path)
                logger.info("Modelo YOLOv8n-seg (.pt) cargado exitosamente.")
            elif os.path.exists(onnx_path):
                try:
                    logger.info("Cargando modelo neuronal YOLOv8n-seg ONNX...")
                    self.yolo_model = YOLO(onnx_path, task="segment")
                    logger.info("Modelo YOLOv8n-seg ONNX cargado exitosamente.")
                except Exception as ex_onnx:
                    logger.warning(f"No se pudo cargar modelo ONNX ({ex_onnx}). Usando yolov8n-seg.pt...")
                    self.yolo_model = YOLO("yolov8n-seg.pt")
            else:
                logger.info("Cargando modelo neuronal YOLOv8n-seg (Ultralytics Segmentación)...")
                self.yolo_model = YOLO("yolov8n-seg.pt")
                logger.info("Modelo YOLOv8n-seg cargado exitosamente.")
        except Exception as e:
            try:
                logger.info(f"Fallback a YOLOv8n (.pt): {e}")
                self.yolo_model = YOLO("yolov8n.pt")
                logger.info("Modelo YOLOv8n cargado exitosamente.")
            except Exception as ex:
                logger.error(f"No se pudo cargar YOLOv8: {ex}. Se utilizará visión por computador básica.")
                self.enabled = False

    def predict(self, roi_crop: np.ndarray, conf_threshold: float = 0.12) -> Tuple[List[Dict[str, Any]], List[Tuple[int, int, int, int, float]]]:
        """
        Ejecuta inferencia de segmentación sobre el recorte de la cuna.
        Retorna:
        - baby_candidates: Lista de dicts con keys {'box': (x1, y1, x2, y2), 'conf': float, 'mask': poly_np}
        - all_person_boxes: Lista de todas las personas detectadas en la escena (bx1, by1, bx2, by2, conf)
        """
        if not self.enabled or self.yolo_model is None or roi_crop is None or roi_crop.size == 0:
            return [], []

        rh, rw = roi_crop.shape[:2]
        if rh < 10 or rw < 10:
            return [], []

        scale_yolo = 640.0 / float(max(rh, rw)) if max(rh, rw) > 640 else 1.0
        yolo_input = cv2.resize(roi_crop, (int(rw * scale_yolo), int(rh * scale_yolo))) if scale_yolo != 1.0 else roi_crop
        eff_scale = scale_yolo if scale_yolo != 1.0 else 1.0

        try:
            results = self.yolo_model.predict(yolo_input, conf=conf_threshold, verbose=False)
        except Exception as e:
            logger.warning(f"Fallo en inferencia YOLO ({e}). Reintentando con modelo .pt de respaldo...")
            try:
                self.yolo_model = YOLO("yolov8n-seg.pt")
                results = self.yolo_model.predict(yolo_input, conf=conf_threshold, verbose=False)
            except Exception as ex:
                try:
                    self.yolo_model = YOLO("yolov8n.pt")
                    results = self.yolo_model.predict(yolo_input, conf=conf_threshold, verbose=False)
                except Exception:
                    logger.error(f"Error definitivo en inferencia YOLO: {ex}")
                    return [], []

        try:
            all_person_boxes = []
            baby_candidates = []

            for r in results:
                boxes = r.boxes
                masks = getattr(r, "masks", None)

                for idx_box, box in enumerate(boxes):
                    cls = int(box.cls[0])
                    if cls == 0: # Clase 0: Person / Baby
                        bx1, by1, bx2, by2 = map(int, box.xyxy[0])
                        bx1, by1 = int(bx1 / eff_scale), int(by1 / eff_scale)
                        bx2, by2 = int(bx2 / eff_scale), int(by2 / eff_scale)
                        bw_box, bh_box = bx2 - bx1, by2 - by1
                        conf = float(box.conf[0])
                        all_person_boxes.append((bx1, by1, bx2, by2, conf))

                        if 35 < bw_box < 420 and 35 < bh_box < 420:
                            baby_poly = None
                            if masks is not None and len(masks.xy) > idx_box:
                                polygon = masks.xy[idx_box]
                                if len(polygon) > 0:
                                    baby_poly = (polygon / eff_scale).astype(np.int32)
                                    if len(baby_poly) > 4:
                                        baby_poly = cv2.approxPolyDP(baby_poly, 1.0, True).reshape(-1, 2)
                                    
                                    p_min_x, p_min_y = int(np.min(baby_poly[:, 0])), int(np.min(baby_poly[:, 1]))
                                    p_max_x, p_max_y = int(np.max(baby_poly[:, 0])), int(np.max(baby_poly[:, 1]))
                                    bx1, by1 = max(0, p_min_x), max(0, p_min_y)
                                    bx2, by2 = min(rw, p_max_x), min(rh, p_max_y)

                            baby_candidates.append({
                                "box": (bx1, by1, bx2, by2),
                                "conf": conf,
                                "mask": baby_poly
                            })

            return baby_candidates, all_person_boxes
        except Exception as e:
            logger.error(f"Error procesando resultados YOLO: {e}")
            return [], []
