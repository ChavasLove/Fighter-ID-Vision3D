"""
FighterID Vision Engine — VideoRecorder
Graba el stream de cámara principal en MP4.
El nombre de archivo usa el fight_id que viene de la web — nunca un uuid4 local.
Extraído de vision_motor_v1.py.
"""

import cv2
import numpy as np

from fighterid_vision_engine.config.settings import CAM_W, CAM_H


class VideoRecorder:
    """Graba el stream de cámara principal en MP4."""

    def __init__(self, fight_id: str, round_num: int = 1,
                 fps: int = 30, size: tuple = (CAM_W, CAM_H)):
        # Nombre usa fight_id de la web — nunca uuid4 local
        self.filename = f"{fight_id}_round{round_num}.mp4"
        self._writer  = cv2.VideoWriter(
            self.filename,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            size,
        )
        print(f"[REC] Grabando → {self.filename}")

    def write(self, frame: np.ndarray) -> None:
        if frame is not None:
            self._writer.write(frame)

    def stop(self) -> None:
        self._writer.release()
        print(f"[REC] Guardado → {self.filename}")
