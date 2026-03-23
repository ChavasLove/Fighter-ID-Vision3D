"""
FighterID Vision Engine — HeatmapEngine

Acumula posiciones de impacto y renderiza un overlay térmico sobre el frame.
El mapa es un array float32 de las mismas dimensiones que el frame de cámara.
Cada punto de impacto suma una unidad; la visualización aplica blur gaussiano
y COLORMAP_JET para producir el efecto de calor.

Thread-safe: _lock protege _map contra escrituras concurrentes del hilo de
detección y lecturas del hilo de render.
"""

import threading

import cv2
import numpy as np


class HeatmapEngine:
    """
    Mantiene un mapa de calor acumulativo de zonas de impacto.

    Uso:
        heatmap = HeatmapEngine(height=720, width=1280)
        heatmap.add_point(x, y)          # llamar cuando hit=True
        frame_with_heatmap = heatmap.render(frame)  # en cada frame de display
    """

    def __init__(self, height: int = 720, width: int = 1280,
                 blur_radius: int = 30):
        self._map            = np.zeros((height, width), dtype=np.float32)
        self._lock           = threading.Lock()
        # El kernel de GaussianBlur debe ser impar
        self._blur           = blur_radius if blur_radius % 2 == 1 else blur_radius + 1
        # Cache del overlay renderizado; se recalcula solo cuando _dirty=True
        self._dirty          = False
        self._cached_overlay: np.ndarray | None = None

    def add_point(self, x: int, y: int, intensity: float = 1.0) -> None:
        """
        Añade un pulso en la coordenada (x, y) del frame.
        Llamado desde el hilo de detección cuando se confirma un golpe.
        x, y: coordenadas de píxel (columna, fila).
        """
        h, w = self._map.shape
        if not (0 <= x < w and 0 <= y < h):
            return
        with self._lock:
            self._map[y, x] += intensity
            self._dirty = True

    def render(self, frame: np.ndarray, alpha: float = 0.35) -> np.ndarray:
        """
        Retorna frame + overlay térmico blended.
        No modifica el frame original; retorna una copia blended.
        Si no hay datos en el mapa, retorna frame sin modificar.
        El GaussianBlur solo se recalcula cuando se añade un nuevo punto (_dirty).
        """
        with self._lock:
            if self._map.max() == 0:
                return frame
            if self._dirty:
                snap = self._map.copy()
                self._dirty = False
            else:
                snap = None

        if snap is not None:
            blurred    = cv2.GaussianBlur(snap, (self._blur, self._blur), 0)
            normalized = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
            colored    = cv2.applyColorMap(normalized.astype(np.uint8),
                                           cv2.COLORMAP_JET)
            mask = (normalized > 10).astype(np.uint8)
            self._cached_overlay = cv2.bitwise_and(colored, colored, mask=mask)

        if self._cached_overlay is None:
            return frame
        return cv2.addWeighted(frame, 1.0 - alpha, self._cached_overlay, alpha, 0)

    def reset(self) -> None:
        """Reinicia el mapa — llamar al inicio de cada nueva sesión."""
        with self._lock:
            self._map[:] = 0
            self._dirty = False
            self._cached_overlay = None
