"""
Gestor de plantillas fotográficas del bebé y falsos positivos vetados (Lista Negra).
Maneja la inserción FIFO, caché binaria serializada (.pkl) y cotejo multi-escala / contención.
"""
import os
import cv2
import numpy as np
import time
import pickle
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger("BabyDetector.Templates")

class TemplateManager:
    """
    Administra las plantillas positivas (álbum del bebé) y negativas (falsos positivos vetados).
    Garantiza inserción FIFO (nuevas en índice 0), cuota máxima (15 pos / 8 neg) y caché binaria ultrarrápida.
    """
    def __init__(self, templates_dir: str = "templates", negatives_dir: str = "templates_negatives"):
        self.templates_dir = templates_dir
        self.negatives_dir = negatives_dir
        os.makedirs(self.templates_dir, exist_ok=True)
        os.makedirs(self.negatives_dir, exist_ok=True)

        self.target_templates: List[Tuple[str, np.ndarray, np.ndarray]] = []
        self.negative_templates: List[Tuple[str, np.ndarray, np.ndarray, Optional[Tuple[float, float, float, float]]]] = []

        self.load_target_templates()
        self.load_negative_templates()

    @staticmethod
    def are_crops_visually_similar(crop1: np.ndarray, crop2: np.ndarray, threshold: float = 0.70, max_diff: float = 28.0) -> bool:
        """Determina si dos recortes son visualmente duplicados o idénticos."""
        if crop1 is None or crop2 is None or crop1.size == 0 or crop2.size == 0:
            return False
        try:
            r1 = cv2.resize(crop1, (64, 64))
            r2 = cv2.resize(crop2, (64, 64))
            score = cv2.matchTemplate(r1, r2, cv2.TM_CCOEFF_NORMED)[0][0]
            if score >= threshold:
                return True
            diff = np.mean(cv2.absdiff(r1, r2))
            if diff <= max_diff:
                return True
        except Exception:
            pass
        return False

    def save_target_template(self, crop: np.ndarray) -> bool:
        """
        Guarda una nueva foto/ángulo del bebé en la carpeta templates/ y actualiza la caché binaria.
        Inserta en índice 0 (nuevo al frente) y previene duplicados visuales.
        """
        try:
            if crop is not None and crop.size > 0:
                os.makedirs(self.templates_dir, exist_ok=True)
                
                h, w = crop.shape[:2]
                aspect = w / float(h)
                if aspect > 3.5 or aspect < 0.28:
                    logger.warning(f"Recorte con proporción extrema {aspect:.2f} (pliegue/tira). Omitiendo.")
                    return False

                max_dim = max(h, w)
                if max_dim > 240:
                    scale = 240.0 / float(max_dim)
                    crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

                # Evitar únicamente duplicados casi idénticos con fotos existentes en el álbum
                for _, s_img, _ in self.target_templates:
                    if self.are_crops_visually_similar(crop, s_img, threshold=0.92, max_diff=10.0):
                        logger.info("Plantilla casi idéntica ya registrada en el álbum. Omitiendo duplicado.")
                        return True

                filename = f"baby_angle_{int(time.time())}.jpg"
                filepath = os.path.join(self.templates_dir, filename)
                cv2.imwrite(filepath, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                self.target_templates.insert(0, (filename, crop.copy(), hist))

                # Limitar a máximo 30 plantillas maestras en memoria y disco
                while len(self.target_templates) > 30:
                    oldest = self.target_templates.pop(-1)
                    old_path = os.path.join(self.templates_dir, oldest[0])
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

                self._save_target_cache()
                logger.info(f"Nueva foto de bebé guardada en {filepath}. Total: {len(self.target_templates)}")
                return True
        except Exception as e:
            logger.error(f"Error al guardar foto de bebé: {e}")
        return False

    def delete_target_template(self, filename: str) -> bool:
        """Elimina una foto del álbum y del disco de forma segura."""
        try:
            safe_name = os.path.basename(filename)
            filepath = os.path.join(self.templates_dir, safe_name)
            if os.path.exists(filepath):
                os.remove(filepath)
            self.target_templates = [t for t in self.target_templates if os.path.basename(t[0]) != safe_name]
            self._save_target_cache()
            logger.info(f"Foto de bebé eliminada: {safe_name}. Restantes: {len(self.target_templates)}")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar foto {filename}: {e}")
            return False

    def save_negative_template(self, crop: np.ndarray, roi_coords: Optional[Tuple[float, float, float, float]] = None) -> bool:
        """
        Guarda un recorte de falso positivo (madera, pared, almohada, sábana, adulto) en templates_negatives/ para ser vetado.
        Inserta en índice 0 (nuevo al frente) y previene duplicados visuales.
        """
        try:
            if crop is not None and crop.size > 0:
                os.makedirs(self.negatives_dir, exist_ok=True)
                
                h, w = crop.shape[:2]
                max_dim = max(h, w)
                if max_dim > 240:
                    scale = 240.0 / float(max_dim)
                    crop = cv2.resize(crop, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

                # Evitar únicamente duplicados casi idénticos con falsos positivos ya vetados
                for item in self.negative_templates:
                    ex_img = item[1]
                    if self.are_crops_visually_similar(crop, ex_img, threshold=0.92, max_diff=10.0):
                        logger.info("Falso positivo casi idéntico ya vetado. Omitiendo duplicado.")
                        return True

                # Si se veta un recorte, limpiar cualquier plantilla positiva en conflicto visual
                conflict_targets = [
                    t for t in self.target_templates
                    if self.are_crops_visually_similar(crop, t[1], threshold=0.90, max_diff=12.0)
                ]
                for ct in conflict_targets:
                    self.delete_target_template(ct[0])

                filename = f"negative_ignore_{int(time.time())}.jpg"
                filepath = os.path.join(self.negatives_dir, filename)
                cv2.imwrite(filepath, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
                
                hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                crop_64 = cv2.resize(crop, (64, 64))
                self.negative_templates.insert(0, (filename, crop.copy(), hist, roi_coords, crop_64))

                # Limitar a máximo 30 negativos en memoria y disco
                while len(self.negative_templates) > 30:
                    oldest = self.negative_templates.pop(-1)
                    old_path = os.path.join(self.negatives_dir, oldest[0])
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass

                self._save_negative_cache()
                logger.info(f"Falso positivo vetado guardado en {filepath}. Total negativas: {len(self.negative_templates)}")
                return True
        except Exception as e:
            logger.error(f"Error al guardar negativo: {e}")
        return False

    def delete_negative_template(self, filename: str) -> bool:
        """Elimina un objeto vetado de la lista negra y del disco de forma segura."""
        try:
            safe_name = os.path.basename(filename)
            filepath = os.path.join(self.negatives_dir, safe_name)
            if os.path.exists(filepath):
                os.remove(filepath)
            self.negative_templates = [t for t in self.negative_templates if os.path.basename(t[0]) != safe_name]
            self._save_negative_cache()
            logger.info(f"Falso positivo desvetado: {safe_name}. Restantes: {len(self.negative_templates)}")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar negativo {filename}: {e}")
            return False

    def get_negative_match_score(self, patch: np.ndarray) -> float:
        """
        Calcula la máxima coincidencia del parche contra la lista negra de negativos,
        evaluando coincidencia directa 64x64 y contención rápida.
        """
        if not self.negative_templates or patch is None or patch.size == 0:
            return 0.0
        ph, pw = patch.shape[:2]
        if ph < 8 or pw < 8:
            return 0.0

        best_neg = 0.0
        p_64 = cv2.resize(patch, (64, 64))

        for neg_item in self.negative_templates:
            neg_img = neg_item[1] if len(neg_item) > 1 else None
            neg_64 = neg_item[4] if len(neg_item) > 4 and neg_item[4] is not None else (
                cv2.resize(neg_img, (64, 64)) if neg_img is not None else None
            )

            # 1. Match normalizado 64x64 ultra-rápido (< 0.1ms)
            if neg_64 is not None:
                try:
                    r = cv2.matchTemplate(p_64, neg_64, cv2.TM_CCOEFF_NORMED)[0][0]
                    if not np.isnan(r):
                        best_neg = max(best_neg, float(r))
                except Exception:
                    pass

            # 2. Contención rápida si el parche es significativamente mayor
            if neg_img is not None and pw > 70 and ph > 70:
                nh, nw = neg_img.shape[:2]
                if nw < pw and nh < ph:
                    try:
                        scale_f = 120.0 / float(max(pw, ph)) if max(pw, ph) > 120 else 1.0
                        s_p = cv2.resize(patch, (int(pw * scale_f), int(ph * scale_f))) if scale_f != 1.0 else patch
                        s_n = cv2.resize(neg_img, (max(8, int(nw * scale_f)), max(8, int(nh * scale_f))))
                        if s_n.shape[0] < s_p.shape[0] and s_n.shape[1] < s_p.shape[1]:
                            res = cv2.matchTemplate(s_p, s_n, cv2.TM_CCOEFF_NORMED)
                            _, mv, _, _ = cv2.minMaxLoc(res)
                            if not np.isnan(mv):
                                best_neg = max(best_neg, float(mv))
                    except Exception:
                        pass

        return best_neg

    def is_patch_negative(self, candidate_patch: np.ndarray, hist_cand: Optional[np.ndarray], 
                          norm_box: Optional[Tuple[float, float, float, float]], match_score: float) -> bool:
        """
        Evalúa si un parche candidato corresponde a un falso positivo vetado (sábanas, almohadas, adultos).
        Aplica cotejo competitivo: un negativo con fuerte correlación o contención (>0.60) anula el parche.
        """
        if not self.negative_templates or candidate_patch is None or candidate_patch.size == 0:
            return False

        c_h, c_w = candidate_patch.shape[:2]
        if c_h < 8 or c_w < 8:
            return True

        neg_score = self.get_negative_match_score(candidate_patch)

        # Veto definitivo si la coincidencia con el objeto vetado es muy alta
        if neg_score >= 0.65:
            return True

        # Veto competitivo: si se parece más al negativo que al bebé
        if neg_score >= 0.52 and neg_score >= (match_score - 0.08):
            return True

        return False

    def load_target_templates(self):
        """Carga fotos de plantillas de disco o caché binaria (.pkl), filtrando duplicados."""
        self.target_templates = []
        cache_path = os.path.join(self.templates_dir, "templates_cache.pkl")

        if os.path.exists(self.templates_dir):
            files = [f for f in os.listdir(self.templates_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(self.templates_dir, f)), reverse=True)

            dir_mtime = max([os.path.getmtime(os.path.join(self.templates_dir, f)) for f in files], default=0.0)
            if os.path.exists(cache_path) and os.path.getmtime(cache_path) >= dir_mtime and files:
                try:
                    with open(cache_path, "rb") as f:
                        cached = pickle.load(f)
                    if len(cached) == len(files):
                        self.target_templates = cached
                        logger.info(f"⚡ CACHÉ BINARIA CARGADA INSTANTÁNEAMENTE: {len(self.target_templates)} fotos de bebé")
                        return
                except Exception as e:
                    logger.warning(f"No se pudo leer caché binaria: {e}")

            loaded = []
            for file in files[:30]:
                filepath = os.path.join(self.templates_dir, file)
                try:
                    img = cv2.imread(filepath)
                    if img is not None:
                        h, w = img.shape[:2]
                        if max(h, w) > 240:
                            scale = 240.0 / float(max(h, w))
                            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                        
                        # Omitir si ya cargamos una foto visualmente idéntica
                        is_dup = any(self.are_crops_visually_similar(img, t[1], threshold=0.70, max_diff=26.0) for t in loaded)
                        if is_dup:
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
                            continue

                        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                        hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                        loaded.append((file, img, hist))
                except Exception as e:
                    logger.error(f"Error cargando plantilla {file}: {e}")

            self.target_templates = loaded
            self._save_target_cache()

    def load_negative_templates(self):
        """Carga falsos positivos vetados de disco o caché binaria (.pkl), filtrando duplicados."""
        self.negative_templates = []
        neg_cache_path = os.path.join(self.negatives_dir, "negatives_cache.pkl")

        if os.path.exists(self.negatives_dir):
            neg_files = [f for f in os.listdir(self.negatives_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
            neg_files.sort(key=lambda f: os.path.getmtime(os.path.join(self.negatives_dir, f)), reverse=True)

            dir_mtime = max([os.path.getmtime(os.path.join(self.negatives_dir, f)) for f in neg_files], default=0.0)
            if os.path.exists(neg_cache_path) and os.path.getmtime(neg_cache_path) >= dir_mtime and neg_files:
                try:
                    with open(neg_cache_path, "rb") as f:
                        cached_neg = pickle.load(f)
                    if len(cached_neg) == len(neg_files):
                        self.negative_templates = cached_neg
                        logger.info(f"🚫 Caché de falsos positivos vetados cargada ({len(self.negative_templates)} negativos)")
                        return
                except Exception:
                    pass

            loaded = []
            for file in neg_files[:30]:
                filepath = os.path.join(self.negatives_dir, file)
                try:
                    img = cv2.imread(filepath)
                    if img is not None:
                        h, w = img.shape[:2]
                        if max(h, w) > 240:
                            scale = 240.0 / float(max(h, w))
                            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

                        # Omitir si ya cargamos un falso positivo visualmente idéntico
                        is_dup = any(self.are_crops_visually_similar(img, n[1], threshold=0.70, max_diff=26.0) for n in loaded)
                        if is_dup:
                            try:
                                os.remove(filepath)
                            except Exception:
                                pass
                            continue

                        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                        hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                        crop_64 = cv2.resize(img, (64, 64))
                        loaded.append((file, img, hist, None, crop_64))
                except Exception as e:
                    logger.error(f"Error cargando negativo {file}: {e}")

            self.negative_templates = loaded
            self._save_negative_cache()

    def _save_target_cache(self):
        cache_path = os.path.join(self.templates_dir, "templates_cache.pkl")
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(self.target_templates, f)
        except Exception:
            pass

    def _save_negative_cache(self):
        cache_path = os.path.join(self.negatives_dir, "negatives_cache.pkl")
        try:
            with open(cache_path, "wb") as f:
                pickle.dump(self.negative_templates, f)
        except Exception:
            pass

    def rebuild_all_caches(self) -> Tuple[int, int, int, int]:
        """Optimiza y deduplica positivos y negativos por nitidez y diversidad de histograma."""
        # 1. Negativos
        os.makedirs(self.negatives_dir, exist_ok=True)
        neg_files = [f for f in os.listdir(self.negatives_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        neg_files.sort()
        
        raw_negatives = []
        for file in neg_files:
            filepath = os.path.join(self.negatives_dir, file)
            try:
                img = cv2.imread(filepath)
                if img is not None and img.shape[0] > 15 and img.shape[1] > 15:
                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                    raw_negatives.append((file, img, hist, None))
            except Exception as e:
                logger.error(f"Error procesando negativo {file}: {e}")

        self.negative_templates = []
        for n_item in raw_negatives:
            n_file, n_img, n_hist, _ = n_item
            is_dup = False
            for _, _, s_hist, _ in self.negative_templates:
                if cv2.compareHist(n_hist, s_hist, cv2.HISTCMP_CORREL) > 0.98:
                    is_dup = True
                    break
            if not is_dup:
                self.negative_templates.append(n_item)
                if len(self.negative_templates) >= 30:
                    break

        self._save_negative_cache()

        # 2. Positivos
        os.makedirs(self.templates_dir, exist_ok=True)
        files = [f for f in os.listdir(self.templates_dir) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
        files.sort()
        
        candidates = []
        for file in files:
            filepath = os.path.join(self.templates_dir, file)
            try:
                img = cv2.imread(filepath)
                if img is not None and img.shape[0] > 20 and img.shape[1] > 20:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    if sharpness < 10.0:
                        continue

                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [18, 25], [0, 180, 0, 256])
                    cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
                    candidates.append((file, img, hist, sharpness))
            except Exception as e:
                logger.error(f"Error procesando {file}: {e}")

        candidates.sort(key=lambda x: x[3], reverse=True)
        selected_masters = []
        for c_file, c_img, c_hist, c_sharp in candidates:
            is_redundant = False
            for _, _, s_hist in selected_masters:
                if cv2.compareHist(c_hist, s_hist, cv2.HISTCMP_CORREL) > 0.92:
                    is_redundant = True
                    break
            if not is_redundant:
                selected_masters.append((c_file, c_img, c_hist))
                if len(selected_masters) >= 30:
                    break

        self.target_templates = selected_masters[:30]
        self._save_target_cache()

        return len(files), len(self.target_templates), len(neg_files), len(self.negative_templates)

