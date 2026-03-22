"""
FighterID Vision Engine — ReplayEngine

Buffer circular de frames para reproducción automática al detectar un golpe fuerte.

Flujo:
  1. add_frame(frame)  →  llamar en cada frame del loop principal
  2. trigger()         →  llamar cuando speed >= REPLAY_SPEED_THRESHOLD
  3. tick()            →  llamar en cada iteración de display; retorna frame de
                          replay con estampa "REPLAY" o None si no hay replay activo

El caller muestra el frame retornado por tick() en una ventana separada.
La ventana se destruye automáticamente al terminar el replay.
"""

import time
import threading
from collections import deque

import cv2
import numpy as np


class ReplayEngine:
    """
    Buffer circular de frames con playback en cámara lenta.

    Parámetros:
        buffer_size:   número máximo de frames en el buffer (~4s @ 30fps = 120)
        playback_fps:  velocidad de reproducción (por defecto 15fps = cámara lenta 2x)
    """

    WINDOW = "FighterID REPLAY"

    def __init__(self, buffer_size: int = 120, playback_fps: int = 15):
        self._buffer      = deque(maxlen=buffer_size)
        self._replay      = []       # snapshot congelado del buffer
        self._idx         = 0
        self._playing     = False
        self._frame_dt    = 1.0 / max(playback_fps, 1)
        self._last_t      = 0.0
        self._lock        = threading.Lock()

    # ──────────────────────────────────────────────────────────────────
    def add_frame(self, frame: np.ndarray) -> None:
        """
        Añade frame al buffer circular. Thread-safe.
        Llamar en cada iteración del loop de detección.
        """
        with self._lock:
            self._buffer.append(frame.copy())

    def trigger(self) -> None:
        """
        Congela el buffer actual como secuencia de replay e inicia el playback.
        Si ya hay un replay activo, lo interrumpe y empieza uno nuevo.
        """
        with self._lock:
            self._replay = list(self._buffer)
        self._idx     = 0
        self._playing = True
        self._last_t  = time.time()

    def tick(self) -> "np.ndarray | None":
        """
        Retorna el frame actual del replay, o None si no hay replay activo.
        Avanza al siguiente frame según playback_fps.
        Destruye la ventana al terminar la secuencia.
        """
        if not self._playing or not self._replay:
            return None

        now = time.time()
        if now - self._last_t >= self._frame_dt:
            self._last_t  = now
            self._idx    += 1
            if self._idx >= len(self._replay):
                self._playing = False
                self._idx     = 0
                cv2.destroyWindow(self.WINDOW)
                return None

        frame = self._replay[self._idx].copy()

        # Estampa "REPLAY" sobre el frame con estilo broadcast
        cv2.putText(frame, "\u25c4 REPLAY", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 255, 255), 3)
        # Barra de progreso
        progress = self._idx / max(len(self._replay) - 1, 1)
        bar_w    = frame.shape[1] - 40
        cv2.rectangle(frame, (20, frame.shape[0] - 15),
                      (20 + bar_w, frame.shape[0] - 8), (60, 60, 60), -1)
        cv2.rectangle(frame, (20, frame.shape[0] - 15),
                      (20 + int(bar_w * progress), frame.shape[0] - 8),
                      (0, 255, 255), -1)
        return frame

    @property
    def is_playing(self) -> bool:
        return self._playing
