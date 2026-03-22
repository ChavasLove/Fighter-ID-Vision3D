"""
FighterID Vision Engine — PersistentTracker
Asignación persistente de identidades RED/BLUE usando el algoritmo húngaro.

Ventajas sobre SimpleTracker (orden horizontal):
  - Mantiene identidades estables cuando los luchadores se cruzan
  - Tolera detecciones perdidas hasta MAX_LOST frames
  - Fallback automático a orden horizontal cuando no hay tracks previos

SimpleTracker se conserva para compatibilidad/referencia.
"""

import numpy as np

try:
    from scipy.optimize import linear_sum_assignment
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False


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

    def assign(self, persons: list) -> dict:
        """
        Retorna {"red": person, "blue": person}.
        Puede devolver subconjunto si hay menos de 2 detecciones.
        """
        if not persons:
            # Incrementar frames perdidos de tracks existentes
            for corner in list(self._tracks.keys()):
                self._tracks[corner]["lost"] += 1
                if self._tracks[corner]["lost"] > self.MAX_LOST:
                    del self._tracks[corner]
            return {}

        # Inicialización: sin tracks previos → orden horizontal
        if not self._initialized or not self._tracks or not _SCIPY_OK:
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
