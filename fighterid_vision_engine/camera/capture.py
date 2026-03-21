"""
FighterID Vision Engine — CameraStream
Captura continua sin bloquear el loop principal.
Extraído de vision_motor_v1.py.
"""

import threading
import time

import cv2
import numpy as np

from fighterid_vision_engine.config.settings import CAM_W, CAM_H


class CameraStream:
    """
    Hilo de captura continua.
    read() devuelve el último frame sin bloquear.
    """

    def __init__(self, idx: int):
        self.idx      = idx
        self._cap     = None
        self._frame: np.ndarray | None = None
        self._ts      = 0.0
        self._lock    = threading.Lock()
        self._running = False
        self._open()

    def _open(self) -> None:
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self.idx, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(3):
                cap.read()
            time.sleep(0.25)
            self._cap = cap
            bk = {cv2.CAP_DSHOW: "DSHOW", cv2.CAP_MSMF: "MSMF",
                  cv2.CAP_ANY:   "ANY"}.get(backend, str(backend))
            print(f"[CAM {self.idx}] abierta  backend={bk}  "
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
                  f"{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
            return
        print(f"[CAM {self.idx}] ERROR — no se pudo abrir con ningún backend")

    def start(self) -> "CameraStream":
        self._running = True
        threading.Thread(
            target=self._update,
            daemon=True,
            name=f"CamStream{self.idx}",
        ).start()
        return self

    def _update(self) -> None:
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.05)
                continue
            ret, frame = self._cap.read()
            if ret and frame is not None:
                with self._lock:
                    self._frame = frame
                    self._ts    = time.perf_counter()
            else:
                time.sleep(0.005)

    def read(self):
        """Returns (frame, timestamp) — frame puede ser None si aún no está listo."""
        with self._lock:
            return self._frame, self._ts

    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()
