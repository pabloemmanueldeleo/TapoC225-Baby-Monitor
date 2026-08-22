"""
Orquestador Principal de Detección de Bebé (BabyDetector).
Coordina el analizador de movimiento (MOG2), el motor neuronal (YOLOv8-seg)
y el gestor de plantillas fotográficas (Template Matching / Veto de Negativos).
"""
import cv2
import numpy as np
import logging
import time
from typing import Tuple, Optional, List, Dict, Any

from src.core.template_manager import TemplateManager
from src.core.motion_analyzer import MotionAnalyzer
from src.core.yolo_detector import YoloDetector

logger = logging.getLogger("BabyDetector")

class BabyDetector:
    """
    Detector de movimiento por Región de Interés (ROI) + Reconocimiento de Bebé con YOLOv8
    + Coincidencia y veto por Plantillas Fotográficas (Multi-escala / Sub-patch containment).
    """
    def __init__(self, sensitivity: float = 0.03, use_yolo: bool = True,
                 templates_dir: str = "templates", negatives_dir: str = "templates_negatives"):
        self.sensitivity = float(sensitivity)
        self.roi: Optional[Tuple[float, float, float, float]] = None # (x1, y1, x2, y2) normalizado 0.0 a 1.0
        self.roi_enabled = True
        self.baby_name = "Bebé"
        self.show_person_boxes = True
        self.template_enabled = True
        self.template_threshold = 0.65
        
        # Sub-módulos especializados
        self.templates = TemplateManager(templates_dir=templates_dir, negatives_dir=negatives_dir)
        self.motion = MotionAnalyzer(sensitivity=self.sensitivity)
        self.yolo = YoloDetector(enabled=use_yolo)

        # Estado y buffers temporales
        self.suggestions_enabled = False
        self.recent_candidates: List[Tuple[np.ndarray, str]] = []
        self._active_baby_mask_poly = None
        self._mask_anchor_box = None
        self._smooth_baby_box = None
        self._last_baby_match_time = 0.0
        self._last_best_score = 0.80
        self._last_candidate_time = 0.0
        self.last_yolo_boxes = []
        self.frame_count = 0

    # --- Propiedades de Compatibilidad Directa con la API previa ---
    @property
    def target_templates(self):
        return self.templates.target_templates

    @target_templates.setter
    def target_templates(self, val):
        self.templates.target_templates = val

    @property
    def negative_templates(self):
        return self.templates.negative_templates

    @negative_templates.setter
    def negative_templates(self, val):
        self.templates.negative_templates = val

    @property
    def last_motion_ratio(self):
        return self.motion.last_motion_ratio

    @last_motion_ratio.setter
    def last_motion_ratio(self, val):
        self.motion.last_motion_ratio = val

    @property
    def last_motion_time(self):
        return self.motion.last_motion_time

    @property
    def bg_subtractor(self):
        return self.motion.bg_subtractor

    @property
    def warmup_frames(self):
        return self.motion.warmup_frames

    @warmup_frames.setter
    def warmup_frames(self, val):
        self.motion.warmup_frames = val

    # --- Métodos de Gestión de Plantillas (Delegación a TemplateManager) ---
    def save_target_template_from_crop(self, crop: np.ndarray, coords: Optional[Tuple[float, float, float, float]] = None) -> bool:
        saved = self.templates.save_target_template(crop)
        if saved:
            self._smooth_baby_box = None
            self._active_baby_mask_poly = None
            self._last_baby_match_time = 0.0
            self.purge_invalid_candidates()
        return saved

    def delete_template(self, filename: str) -> bool:
        deleted = self.templates.delete_target_template(filename)
        if deleted:
            self._smooth_baby_box = None
            self._last_baby_match_time = 0.0
        return deleted

    def save_negative_template_from_crop(self, crop: np.ndarray, roi_coords: Optional[Tuple[float, float, float, float]] = None) -> bool:
        saved = self.templates.save_negative_template(crop, roi_coords)
        if saved:
            # Limpiar inmediatamente tracking activo para forzar re-escaneo limpio
            self._smooth_baby_box = None
            self._active_baby_mask_poly = None
            self._last_baby_match_time = 0.0
            self.purge_invalid_candidates()
        return saved

    def delete_negative_template(self, filename: str) -> bool:
        return self.templates.delete_negative_template(filename)

    def purge_invalid_candidates(self):
        """Elimina de las sugerencias cualquier elemento que coincida con los negativos vetados."""
        if not hasattr(self, "recent_candidates") or not self.recent_candidates:
            return
        cleaned = []
        for cand in self.recent_candidates:
            c_img = cand[0]
            if c_img is not None and c_img.size > 0:
                if not self.templates.is_patch_negative(c_img, None, None, 0.50):
                    cleaned.append(cand)
        self.recent_candidates = cleaned

    def _is_patch_negative(self, patch: np.ndarray, hist: Optional[np.ndarray], norm_box: Optional[Tuple], match_score: float) -> bool:
        return self.templates.is_patch_negative(patch, hist, norm_box, match_score)

    def rebuild_all_caches(self) -> Tuple[int, int, int, int]:
        res = self.templates.rebuild_all_caches()
        self.purge_invalid_candidates()
        self._smooth_baby_box = None
        self._last_baby_match_time = 0.0
        return res

    # --- Configuración de Región de Interés (ROI) ---
    def set_roi_enabled(self, enabled: bool):
        self.roi_enabled = enabled
        self.motion.reset_subtractor()
        logger.info(f"Límite de región ROI activado: {self.roi_enabled}")

    def set_roi(self, x1: float, y1: float, x2: float, y2: float):
        self.roi = (max(0.0, min(x1, 1.0)),
                    max(0.0, min(y1, 1.0)),
                    max(x1, min(x2, 1.0)),
                    max(y1, min(y2, 1.0)))
        self.motion.warmup_frames = 10
        logger.info(f"Región de Interés (ROI cuna) actualizada: {self.roi}")

    def get_recent_candidates(self) -> List[Tuple[np.ndarray, str]]:
        if not getattr(self, "suggestions_enabled", False):
            return []
        self.purge_invalid_candidates()
        return self.recent_candidates[:4]

    # --- Ciclo de Procesamiento de Fotogramas ---
    def process_frame(self, frame: np.ndarray) -> Tuple[bool, bool, np.ndarray, Dict[str, Any]]:
        """
        Procesa el fotograma coordinando MOG2, YOLOv8-seg y Template Matching.
        Retorna: (motion_detected, baby_detected, annotated_frame, info_dict)
        """
        h, w = frame.shape[:2]
        annotated_frame = frame.copy()
        
        motion_detected = False
        baby_detected = False
        now_time = time.time()

        if not self.roi_enabled or self.roi is None:
            rx1, ry1, rx2, ry2 = 0, 0, w, h
        else:
            rx1 = int(self.roi[0] * w)
            ry1 = int(self.roi[1] * h)
            rx2 = int(self.roi[2] * w)
            ry2 = int(self.roi[3] * h)

        rx1, ry1 = max(0, rx1), max(0, ry1)
        rx2, ry2 = min(w, rx2), min(h, ry2)

        if self.roi_enabled:
            cv2.rectangle(annotated_frame, (rx1, ry1), (rx2, ry2), (255, 165, 0), 3)
            cv2.putText(annotated_frame, "ZONA CUNA MONITOREADA", (rx1 + 8, max(ry1 - 12, 25)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 165, 0), 2)
        else:
            cv2.putText(annotated_frame, "ZONA: PANTALLA COMPLETA", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        if rx2 > rx1 and ry2 > ry1:
            roi_crop = frame[ry1:ry2, rx1:rx2]
            
            # 1. Análisis de Movimiento (MOG2)
            self.motion.sensitivity = self.sensitivity
            motion_detected, effective_motion, fg_mask = self.motion.analyze(roi_crop, self._smooth_baby_box)

            if motion_detected:
                cv2.rectangle(annotated_frame, (rx1, ry1), (rx2, ry2), (0, 0, 255), 4)
                cv2.putText(annotated_frame, f"! MOVIMIENTO EN CUNA ! ({effective_motion*100:.1f}%)", 
                            (rx1 + 10, ry1 + 35), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 255), 2)

            self.frame_count += 1
            fresh_candidates: List[Dict[str, Any]] = []

            # 2. Inferencia Neuronal de Segmentación YOLOv8
            top_yolo_conf = 0.0
            should_run_yolo = self.yolo.enabled and (
                motion_detected
                or self._smooth_baby_box is None
                or self.frame_count % 3 == 0
                or self.frame_count <= 3
            )
            if should_run_yolo:
                yolo_cands, all_persons = self.yolo.predict(roi_crop, conf_threshold=0.15)
                self.last_yolo_boxes = all_persons
                
                # Filtrar candidatos contra negativos vetados y validar contra fotos del bebé
                for c in yolo_cands:
                    bx1, by1, bx2, by2 = c["box"]
                    cand_patch = roi_crop[by1:by2, bx1:bx2]
                    cand_norm_box = (
                        (rx1 + bx1) / float(w), (ry1 + by1) / float(h),
                        (rx1 + bx2) / float(w), (ry1 + by2) / float(h)
                    )
                    if cand_patch.shape[0] > 10 and cand_patch.shape[1] > 10:
                        if self.templates.is_patch_negative(cand_patch, None, cand_norm_box, c["conf"]):
                            continue
                    
                    c_conf = float(c["conf"])

                    # Si el reconocimiento por foto/álbum está activo y hay plantillas registradas
                    if self.template_enabled and self.templates.target_templates:
                        best_match_val = 0.0
                        cp_h, cp_w = cand_patch.shape[:2]
                        if cp_h > 12 and cp_w > 12:
                            cp_hsv = cv2.cvtColor(cand_patch, cv2.COLOR_BGR2HSV)
                            cp_hist = cv2.calcHist([cp_hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                            cv2.normalize(cp_hist, cp_hist, 0, 1, cv2.NORM_MINMAX)

                            for _, t_img, t_hist in self.templates.target_templates:
                                try:
                                    h_corr = float(cv2.compareHist(cp_hist, t_hist, cv2.HISTCMP_CORREL)) if t_hist is not None else 0.0
                                    s_timg = cv2.resize(t_img, (min(cp_w, 64), min(cp_h, 64)))
                                    s_cp = cv2.resize(cand_patch, (min(cp_w, 64), min(cp_h, 64)))
                                    res = cv2.matchTemplate(s_cp, s_timg, cv2.TM_CCOEFF_NORMED)
                                    t_score = float(res[0][0]) if not np.isnan(res[0][0]) else 0.0

                                    comb = max(0.0, t_score * 0.65 + max(0.0, h_corr) * 0.35)
                                    best_match_val = max(best_match_val, comb)
                                except Exception:
                                    pass

                        req_thresh = float(self.template_threshold) * 0.75
                        if best_match_val < req_thresh:
                            # No coincide con el álbum del bebé (es un adulto u objeto no bebé)
                            continue

                        final_conf = best_match_val
                    else:
                        final_conf = c_conf

                    top_yolo_conf = max(top_yolo_conf, final_conf)
                    fresh_candidates.append({
                        "box": (bx1, by1, bx2, by2),
                        "conf": final_conf,
                        "mask": c["mask"],
                        "source": "yolo"
                    })

            # 3. Búsqueda por Plantillas Fotográficas (Álbum del Bebé)
            should_run_templates = (
                self.template_enabled
                and bool(self.templates.target_templates)
                and roi_crop.shape[0] > 30
                and roi_crop.shape[1] > 30
                and len(fresh_candidates) == 0  # Si YOLO ya detectó al bebé con éxito, evitamos escaneo exhaustivo innecesario
                and (self._smooth_baby_box is None or motion_detected or self.frame_count % 4 == 0 or self.frame_count <= 3)
            )

            if should_run_templates:
                rh, rw = roi_crop.shape[:2]
                scale_f = 380.0 / float(max(rh, rw)) if max(rh, rw) > 380 else 1.0
                s_rw, s_rh = int(rw * scale_f), int(rh * scale_f)
                scaled_search = cv2.resize(roi_crop, (s_rw, s_rh)) if scale_f != 1.0 else roi_crop

                # Descartar imágenes completamente negras o vacías
                gray_search = cv2.cvtColor(scaled_search, cv2.COLOR_BGR2GRAY)
                if cv2.Laplacian(gray_search, cv2.CV_64F).var() < 1.0:
                    should_run_templates = False

            if should_run_templates:
                eff_threshold = max(0.35, min(0.90, float(self.template_threshold)))
                raw_matches = []

                for item in self.templates.target_templates:
                    fname, t_img = item[0], item[1]
                    hist_tmpl = item[2] if len(item) > 2 else None
                    try:
                        th, tw = t_img.shape[:2]
                        for t_scale in (0.45, 0.65, 0.85, 1.10, 1.40):
                            scaled_tw, scaled_th = int(tw * t_scale), int(th * t_scale)
                            s_tw, s_th = int(scaled_tw * scale_f), int(scaled_th * scale_f)

                            if s_th <= s_rh and s_tw <= s_rw and s_th > 10 and s_tw > 10:
                                s_timg = cv2.resize(t_img, (s_tw, s_th))
                                res = cv2.matchTemplate(scaled_search, s_timg, cv2.TM_CCOEFF_NORMED)
                                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                                score = float(max_val)

                                if score >= eff_threshold:
                                    tx = int(max_loc[0] / scale_f)
                                    ty = int(max_loc[1] / scale_f)
                                    real_tw, real_th = int(s_tw / scale_f), int(s_th / scale_f)

                                    candidate_patch = roi_crop[ty:ty+real_th, tx:tx+real_tw]
                                    if candidate_patch.shape[0] > 10 and candidate_patch.shape[1] > 10:
                                        gray_cand = cv2.cvtColor(candidate_patch, cv2.COLOR_BGR2GRAY)
                                        if cv2.Laplacian(gray_cand, cv2.CV_64F).var() < 2.0:
                                            continue

                                        if hist_tmpl is not None:
                                            cand_hsv = cv2.cvtColor(candidate_patch, cv2.COLOR_BGR2HSV)
                                            cand_hist = cv2.calcHist([cand_hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                                            cv2.normalize(cand_hist, cand_hist, 0, 1, cv2.NORM_MINMAX)
                                            if cv2.compareHist(cand_hist, hist_tmpl, cv2.HISTCMP_CORREL) < 0.10:
                                                continue

                                        cand_norm_box = (
                                            (rx1 + tx) / float(w), (ry1 + ty) / float(h),
                                            (rx1 + tx + real_tw) / float(w), (ry1 + ty + real_th) / float(h)
                                        )

                                        if not self.templates.is_patch_negative(candidate_patch, hist_tmpl, cand_norm_box, score):
                                            raw_matches.append((tx, ty, tx + real_tw, ty + real_th, score))
                    except Exception:
                        pass

                if raw_matches:
                    clusters = []
                    for m in raw_matches:
                        mx1, my1, mx2, my2, msc = m
                        mcx, mcy = (mx1 + mx2) / 2.0, (my1 + my2) / 2.0
                        assigned = False
                        for cl in clusters:
                            cl_cx, cl_cy = cl["center"]
                            if float(np.hypot(mcx - cl_cx, mcy - cl_cy)) < 150.0:
                                cl["boxes"].append(m)
                                cl["x1"] = min(cl["x1"], mx1)
                                cl["y1"] = min(cl["y1"], my1)
                                cl["x2"] = max(cl["x2"], mx2)
                                cl["y2"] = max(cl["y2"], my2)
                                cl["scores"].append(msc)
                                cl["center"] = ((cl["x1"] + cl["x2"]) / 2.0, (cl["y1"] + cl["y2"]) / 2.0)
                                assigned = True
                                break
                        if not assigned:
                            clusters.append({
                                "x1": mx1, "y1": my1, "x2": mx2, "y2": my2,
                                "boxes": [m], "scores": [msc], "center": (mcx, mcy)
                            })

                    for cl in clusters:
                        cl_w = cl["x2"] - cl["x1"]
                        cl_h = cl["y2"] - cl["y1"]
                        if 25 < cl_w < 450 and 25 < cl_h < 450:
                            cl_patch = roi_crop[cl["y1"]:cl["y2"], cl["x1"]:cl["x2"]]
                            cl_norm_box = (
                                (rx1 + cl["x1"]) / float(w), (ry1 + cl["y1"]) / float(h),
                                (rx1 + cl["x2"]) / float(w), (ry1 + cl["y2"]) / float(h)
                            )
                            bonus = min(0.20, len(cl["boxes"]) * 0.04)
                            raw_score = min(0.95, max(cl["scores"]) + bonus)
                            
                            # Veto a nivel de cluster completo (evalúa si el grupo entero es o contiene un negativo)
                            if self.templates.is_patch_negative(cl_patch, None, cl_norm_box, raw_score):
                                continue

                            neg_score = self.templates.get_negative_match_score(cl_patch)
                            adj_score = max(0.0, raw_score - neg_score * 0.70)
                            if adj_score >= eff_threshold:
                                fresh_candidates.append({
                                    "box": (cl["x1"], cl["y1"], cl["x2"], cl["y2"]),
                                    "conf": adj_score,
                                    "mask": None,
                                    "source": "template"
                                })

            # 4. Fusión de Candidatos y Seguimiento Inercial con Rechequeo y Expiración
            is_quiescent = not motion_detected or (effective_motion < self.sensitivity)
            max_quiet_hold = 8.0 if is_quiescent else 2.5

            if fresh_candidates:
                # Ordenar por confianza
                fresh_candidates.sort(key=lambda x: x["conf"], reverse=True)
                top_cand = fresh_candidates[0]
                top_x1, top_y1, top_x2, top_y2 = top_cand["box"]
                top_conf = top_cand["conf"]
                top_mask = top_cand.get("mask")

                target_box = np.array([top_x1, top_y1, max(20, top_x2 - top_x1), max(20, top_y2 - top_y1)], dtype=np.float32)

                if self._smooth_baby_box is not None:
                    prev_cx = self._smooth_baby_box[0] + self._smooth_baby_box[2] / 2.0
                    prev_cy = self._smooth_baby_box[1] + self._smooth_baby_box[3] / 2.0
                    new_cx = top_x1 + (top_x2 - top_x1) / 2.0
                    new_cy = top_y1 + (top_y2 - top_y1) / 2.0
                    dist = float(np.hypot(new_cx - prev_cx, new_cy - prev_cy))

                    prev_w, prev_h = self._smooth_baby_box[2], self._smooth_baby_box[3]
                    new_w, new_h = target_box[2], target_box[3]
                    size_diff = abs(new_w - prev_w) + abs(new_h - prev_h)

                    # Zona muerta (Deadband / Histéresis espacial): anclar la caja ante micro-variaciones
                    if dist < 22.0 and size_diff < 40.0:
                        pass
                    elif dist < 140.0:
                        # Movimiento suave: interpolación estable
                        alpha = 0.15
                        self._smooth_baby_box = alpha * target_box + (1.0 - alpha) * self._smooth_baby_box
                    else:
                        # Cambio de posición significativo
                        self._smooth_baby_box = target_box
                else:
                    self._smooth_baby_box = target_box

                self._active_baby_mask_poly = top_mask.copy() if top_mask is not None else None
                self._last_baby_match_time = now_time
                self._last_best_score = top_conf
                baby_detected = True
            else:
                # No hay detección fresca en este fotograma: aplicar retención en reposo con rechequeo activo
                if self._smooth_baby_box is not None:
                    elapsed = now_time - self._last_baby_match_time

                    # Rechequeo activo del parche actualmente retenido
                    sbx, sby, sbw, sbh = map(int, self._smooth_baby_box)
                    patch = roi_crop[max(0, sby):min(roi_crop.shape[0], sby+sbh), max(0, sbx):min(roi_crop.shape[1], sbx+sbw)]
                    is_patch_valid = True

                    if patch.size == 0 or patch.shape[0] < 12 or patch.shape[1] < 12:
                        is_patch_valid = False
                    else:
                        cand_norm = (
                            (rx1 + sbx) / float(w), (ry1 + sby) / float(h),
                            (rx1 + sbx + sbw) / float(w), (ry1 + sby + sbh) / float(h)
                        )
                        if self.templates.is_patch_negative(patch, None, cand_norm, self._last_best_score):
                            is_patch_valid = False

                    if is_patch_valid and (elapsed < max_quiet_hold):
                        baby_detected = True
                        # Decaimiento suave de confianza en reposo
                        self._last_best_score = max(0.40, self._last_best_score * 0.995)
                        # Desvanecer máscara poligonal tras 2.0s para no dejar contornos rígidos
                        if elapsed > 2.0:
                            self._active_baby_mask_poly = None
                    else:
                        # Expiración limpia
                        self._smooth_baby_box = None
                        self._active_baby_mask_poly = None
                        baby_detected = False
                else:
                    self._smooth_baby_box = None
                    self._active_baby_mask_poly = None
                    baby_detected = False

            # 5. Renderizado de Marcaciones
            smooth_box = self._smooth_baby_box
            is_baby_active = baby_detected and (smooth_box is not None)

            if is_baby_active:
                bx, by, bw, bh = map(int, smooth_box)
                abs_bx1, abs_by1 = rx1 + bx, ry1 + by
                abs_bx2, abs_by2 = rx1 + bx + bw, ry1 + by + bh
                score_val = self._last_best_score
                cv2.rectangle(annotated_frame, (abs_bx1, abs_by1), (abs_bx2, abs_by2), (255, 0, 255), 3)
                cv2.putText(annotated_frame, f"Bebé ({self.baby_name} {score_val*100:.0f}%)", 
                            (abs_bx1, max(abs_by1 - 10, 25)), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 0, 255), 2)

                if self._active_baby_mask_poly is not None and len(self._active_baby_mask_poly) > 0:
                    abs_poly = self._active_baby_mask_poly + np.array([rx1, ry1], dtype=np.int32)
                    cv2.polylines(annotated_frame, [abs_poly], True, (255, 0, 255), 2)

            # Generar Sugerencias Automáticas
            if getattr(self, "suggestions_enabled", False) and (now_time - self._last_candidate_time > 2.5):
                cand_crop = None
                cand_label = ""
                cand_norm = None
                if is_baby_active and smooth_box is not None:
                    sbx, sby, sbw, sbh = map(int, smooth_box)
                    if sbw > 30 and sbh > 30:
                        cand_crop = roi_crop[max(0, sby):min(roi_crop.shape[0], sby+sbh), max(0, sbx):min(roi_crop.shape[1], sbx+sbw)]
                        cand_norm = (
                            (rx1 + sbx) / float(w), (ry1 + sby) / float(h),
                            (rx1 + sbx + sbw) / float(w), (ry1 + sby + sbh) / float(h)
                        )
                        cand_label = f"Bebé ({int(self._last_best_score*100)}%)"
                elif self.last_yolo_boxes:
                    for ybx1, yby1, ybx2, yby2, yconf in self.last_yolo_boxes:
                        yw, yh = ybx2 - ybx1, yby2 - yby1
                        if 30 < yw < 350 and 30 < yh < 350:
                            cand_crop = roi_crop[max(0, yby1):min(roi_crop.shape[0], yby2), max(0, ybx1):min(roi_crop.shape[1], ybx2)]
                            cand_norm = (
                                (rx1 + ybx1) / float(w), (ry1 + yby1) / float(h),
                                (rx1 + ybx2) / float(w), (ry1 + yby2) / float(h)
                            )
                            cand_label = f"IA ({int(yconf*100)}%)"
                            break

                if cand_crop is not None and cand_crop.size > 0 and cand_crop.shape[0] > 25 and cand_crop.shape[1] > 25:
                    if not self.templates.is_patch_negative(cand_crop, None, cand_norm, 0.50):
                        is_dup_cand = False
                        c_small = cv2.resize(cand_crop, (48, 48))
                        for exist_crop, _ in self.recent_candidates:
                            if exist_crop is not None and exist_crop.size > 0:
                                ex_small = cv2.resize(exist_crop, (48, 48))
                                if np.mean(cv2.absdiff(c_small, ex_small)) < 15.0:
                                    is_dup_cand = True
                                    break

                        if not is_dup_cand:
                            self._last_candidate_time = now_time
                            self.recent_candidates.insert(0, (cand_crop.copy(), cand_label))
                            self.recent_candidates = self.recent_candidates[:4]

            if self.show_person_boxes and not baby_detected:
                for (bx1, by1, bx2, by2, conf) in self.last_yolo_boxes:
                    abs_x1, abs_y1 = rx1 + bx1, ry1 + by1
                    abs_x2, abs_y2 = rx1 + bx2, ry1 + by2
                    box_color = (0, 255, 0)
                    cv2.rectangle(annotated_frame, (abs_x1, abs_y1), (abs_x2, abs_y2), box_color, 2)
                    cv2.putText(annotated_frame, f"Persona ({conf*100:.0f}%)", 
                                (abs_x1, max(abs_y1 - 8, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.65, box_color, 2)

            baby_lost_alert = False
            if baby_detected:
                self.last_baby_seen_time = now_time
                self.was_baby_present = True
            else:
                if getattr(self, "was_baby_present", False) and (now_time - getattr(self, "last_baby_seen_time", now_time) > 3.0):
                    baby_lost_alert = True
                    self.was_baby_present = False

        info = {
            "motion_detected": motion_detected,
            "baby_detected": baby_detected,
            "baby_lost_alert": getattr(self, "baby_lost_alert", False),
            "motion_ratio": float(self.motion.last_motion_ratio),
            "score": float(self._last_best_score),
            "baby_score": float(self._last_best_score),
            "roi_coords": (rx1, ry1, rx2, ry2)
        }

        return motion_detected, baby_detected, annotated_frame, info

    def get_vector_overlay_info(self, frame_shape: Tuple[int, int]) -> dict:
        """Retorna datos vectoriales normalizados para renderizado desacoplado en UI."""
        h_f, w_f = frame_shape[:2]
        now_time = time.time()
        last_match_t = self._last_baby_match_time
        smooth_box = self._smooth_baby_box

        roi_norm = self.roi if (self.roi_enabled and self.roi is not None) else None
        baby_box_norm = None
        baby_masks_norm = []

        is_quiescent = not self.motion.motion_detected
        max_seen_sec = 8.0 if is_quiescent else 2.5

        if smooth_box is not None and (now_time - last_match_t < max_seen_sec):
            rx1_px, ry1_px = int(roi_norm[0] * w_f) if roi_norm else 0, int(roi_norm[1] * h_f) if roi_norm else 0
            bx, by, bw, bh = map(float, smooth_box)
            abs_x = (rx1_px + bx) / float(w_f)
            abs_y = (ry1_px + by) / float(h_f)
            abs_w = bw / float(w_f)
            abs_h = bh / float(h_f)
            baby_box_norm = (abs_x, abs_y, abs_w, abs_h)

            if self._active_baby_mask_poly is not None and len(self._active_baby_mask_poly) > 2:
                abs_poly = (self._active_baby_mask_poly + np.array([rx1_px, ry1_px], dtype=np.float32)) / np.array([w_f, h_f], dtype=np.float32)
                baby_masks_norm.append(abs_poly.tolist())

        return {
            "roi_norm": roi_norm,
            "baby_box_norm": baby_box_norm,
            "baby_name": self.baby_name,
            "baby_score": self._last_best_score,
            "baby_masks_norm": baby_masks_norm,
            "motion_ratio": float(self.motion.last_motion_ratio),
            "motion_threshold": float(self.sensitivity)
        }
