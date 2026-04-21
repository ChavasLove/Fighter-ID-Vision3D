"""
FighterID Vision Engine — PersistentTracker
Asignación persistente de identidades RED/BLUE usando el algoritmo húngaro.

Ventajas sobre SimpleTracker (orden horizontal):
  - Mantiene identidades estables cuando los luchadores se cruzan
  - Tolera detecciones perdidas hasta MAX_LOST frames
  - Fallback automático a orden horizontal cuando no hay tracks previos

SimpleTracker se conserva para compatibilidad/referencia.
"""

import cv2
import numpy as np

try:
    from scipy.optimize import linear_sum_assignment
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False

from fighterid_vision_engine.config.settings import (
    KP_L_WRIST, KP_R_WRIST,
    GLOVE_R_LO1, GLOVE_R_HI1, GLOVE_R_LO2, GLOVE_R_HI2,
    GLOVE_B_LO, GLOVE_B_HI,
    GLOVE_W_S_MAX, GLOVE_W_V_MIN,
    GLOVE_COLOR_MIN_FRAC, GLOVE_ROI_R,
)


def classify_glove(frame: np.ndarray, x: int, y: int,
                   r: int = GLOVE_ROI_R) -> dict:
    """Sample an ROI around wrist pixel (x, y) and classify glove color."""
    h, w = frame.shape[:2]
    roi = frame[max(0, y - r):min(h, y + r), max(0, x - r):min(w, x + r)]
    if roi.size == 0:
        return {"red": False, "blue": False, "white": False}
    small = cv2.resize(roi, (48, 48), interpolation=cv2.INTER_LINEAR)
    hsv   = cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2HSV)
    s_ch, v_ch = hsv[:, :, 1], hsv[:, :, 2]
    min_px = max(1, int(48 * 48 * GLOVE_COLOR_MIN_FRAC))

    white_mask = (s_ch < GLOVE_W_S_MAX) & (v_ch > GLOVE_W_V_MIN)
    white      = int(np.sum(white_mask)) > min_px

    r_lo1, r_hi1 = np.array(GLOVE_R_LO1, np.uint8), np.array(GLOVE_R_HI1, np.uint8)
    r_lo2, r_hi2 = np.array(GLOVE_R_LO2, np.uint8), np.array(GLOVE_R_HI2, np.uint8)
    red_mask = cv2.bitwise_or(cv2.inRange(hsv, r_lo1, r_hi1),
                              cv2.inRange(hsv, r_lo2, r_hi2))
    red_mask[white_mask] = 0
    red = int(np.sum(red_mask > 0)) > min_px

    b_lo, b_hi = np.array(GLOVE_B_LO, np.uint8), np.array(GLOVE_B_HI, np.uint8)
    blue_mask = cv2.inRange(hsv, b_lo, b_hi)
    blue_mask[white_mask] = 0
    blue = int(np.sum(blue_mask > 0)) > min_px

    return {"red": red, "blue": blue, "white": white}


def _centroid(person: dict) -> np.ndarray:
    x1, y1, x2, y2 = person["bbox"]
    return np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=float)


def _iou(bbox_a: list, bbox_b: list) -> float:
    """Intersection-over-Union entre dos bounding boxes [x1,y1,x2,y2]."""
    ax1, ay1, ax2, ay2 = bbox_a
    bx1, by1, bx2, by2 = bbox_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0.0


def _horizontal_assign(persons: list) -> dict:
    """Asignación por posición horizontal (SimpleTracker legacy)."""
    if not persons:
        return {}
    if len(persons) == 1:
        return {"red": persons[0]}
    sorted_p = sorted(persons[:2], key=lambda p: (p["bbox"][0] + p["bbox"][2]) / 2)
    return {"red": sorted_p[0], "blue": sorted_p[1]}


def _color_assign(persons: list, frame: np.ndarray) -> dict:
    """
    Assign corners by glove color. Returns {} when assignment is ambiguous
    so the caller can fall back to position-based assignment.
    """
    if not persons:
        return {}

    def _sample(person):
        kps = person.get("keypoints")
        if kps is None or len(kps) < 11:
            return {"red": False, "blue": False, "white": False}
        out = {"red": False, "blue": False, "white": False}
        for idx in (KP_L_WRIST, KP_R_WRIST):
            x, y = int(kps[idx, 0]), int(kps[idx, 1])
            if x == 0 and y == 0:
                continue
            c = classify_glove(frame, x, y)
            out["red"]   = out["red"]   or c["red"]
            out["blue"]  = out["blue"]  or c["blue"]
            out["white"] = out["white"] or c["white"]
        return out

    if len(persons) == 1:
        c = _sample(persons[0])
        if c["red"] and not c["blue"]:
            return {"red": persons[0]}
        if c["blue"] and not c["red"]:
            return {"blue": persons[0]}
        return {}

    colors = [_sample(p) for p in persons[:2]]
    p0r, p0b = colors[0]["red"], colors[0]["blue"]
    p1r, p1b = colors[1]["red"], colors[1]["blue"]

    # Both fighters show different, unambiguous colors
    if p0r and not p0b and p1b and not p1r:
        return {"red": persons[0], "blue": persons[1]}
    if p1r and not p1b and p0b and not p0r:
        return {"red": persons[1], "blue": persons[0]}

    # Only one fighter shows a color signal
    if p0r and not p0b and not p1r and not p1b:
        return {"red": persons[0], "blue": persons[1]}
    if p1r and not p1b and not p0r and not p0b:
        return {"red": persons[1], "blue": persons[0]}
    if p0b and not p0r and not p1r and not p1b:
        return {"red": persons[1], "blue": persons[0]}
    if p1b and not p1r and not p0r and not p0b:
        return {"red": persons[0], "blue": persons[1]}

    return {}  # ambiguous — fall back to position


class PersistentTracker:
    """
    Tracker con IDs persistentes usando el algoritmo húngaro.

    Estado interno:
      _tracks["red" | "blue"]:
        {"centroid": np.array, "bbox": list, "lost": int}

    API: assign(persons) → {"red": person, "blue": person}
    """

    MAX_LOST     = 10    # frames antes de resetear un track perdido
    DIST_WEIGHT  = 0.6   # peso de distancia euclidiana en la matriz de costo
    IOU_WEIGHT   = 0.4   # peso de IoU (inversamente)

    def __init__(self):
        self._tracks: dict = {}   # "red"/"blue" → track state
        self._initialized = False

    def assign(self, persons: list,
               frame: "np.ndarray | None" = None) -> dict:
        """
        Retorna {"red": person, "blue": person}.
        Puede devolver subconjunto si hay menos de 2 detecciones.
        Cuando se pasa frame, usa color de guantes para la asignación inicial.
        """
        if not persons:
            # Incrementar frames perdidos de tracks existentes
            for corner in list(self._tracks.keys()):
                self._tracks[corner]["lost"] += 1
                if self._tracks[corner]["lost"] > self.MAX_LOST:
                    del self._tracks[corner]
            return {}

        # Inicialización: sin tracks previos → color primero, luego posición horizontal
        if not self._initialized or not self._tracks or not _SCIPY_OK:
            if frame is not None and persons:
                result = _color_assign(persons, frame)
                if result:
                    self._update_tracks_from_assignment(result)
                    self._initialized = True
                    return result
            result = _horizontal_assign(persons)
            self._update_tracks_from_assignment(result)
            self._initialized = True
            return result

        # ── Algoritmo húngaro ────────────────────────────────────────────
        corners    = list(self._tracks.keys())          # ["red"] o ["red","blue"]
        candidates = persons[:2]                         # máximo 2 personas

        n_tracks   = len(corners)
        n_persons  = len(candidates)
        size       = max(n_tracks, n_persons)

        # Obtener escala de imagen para normalizar distancias
        # (usa bbox del primer candidato como referencia)
        scale = max(candidates[0]["bbox"][2] - candidates[0]["bbox"][0], 1.0)

        cost = np.full((size, size), 1e6)
        for i, corner in enumerate(corners):
            track = self._tracks[corner]
            for j, person in enumerate(candidates):
                c = _centroid(person)
                dist = float(np.linalg.norm(c - track["centroid"])) / scale
                iou  = _iou(track["bbox"], person["bbox"])
                cost[i, j] = self.DIST_WEIGHT * dist + self.IOU_WEIGHT * (1.0 - iou)

        row_ind, col_ind = linear_sum_assignment(cost)

        result = {}
        for i, j in zip(row_ind, col_ind):
            if i < n_tracks and j < n_persons and cost[i, j] < 1e5:
                corner = corners[i]
                result[corner] = candidates[j]

        # Luchadores no asignados en ningún track → asignar al primer corner libre
        assigned_persons = set(id(result[c]) for c in result)
        for person in candidates:
            if id(person) not in assigned_persons:
                if "red" not in result:
                    result["red"] = person
                elif "blue" not in result:
                    result["blue"] = person

        # Si no hay "red" pero sí "blue", intercambiar (mantener convención rojo=izq)
        if "blue" in result and "red" not in result:
            result["red"] = result.pop("blue")

        # Actualizar tracks y contar frames perdidos
        self._update_tracks_from_assignment(result)
        for corner in corners:
            if corner not in result:
                self._tracks[corner]["lost"] += 1
                if self._tracks[corner]["lost"] > self.MAX_LOST:
                    del self._tracks[corner]

        return result

    def _update_tracks_from_assignment(self, assignment: dict) -> None:
        for corner, person in assignment.items():
            self._tracks[corner] = {
                "centroid": _centroid(person),
                "bbox":     list(person["bbox"]),
                "lost":     0,
            }


# ── Clase legacy — mantenida para compatibilidad ───────────────────────
class SimpleTracker:
    """
    Asigna esquinas a personas detectadas por posición horizontal.
    El luchador más a la izquierda = rojo, más a la derecha = azul.
    Conservada como fallback — usar PersistentTracker para producción.
    """

    def assign(self, persons: list) -> dict:
        return _horizontal_assign(persons)
