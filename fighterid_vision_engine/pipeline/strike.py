"""
FighterID Vision Engine — StrikeDetector
Detecta golpes usando velocidad de muñeca + distancia al oponente.
Reglas biomecánicas sin ML — calibradas por umbrales físicos.
Extraído de vision_motor_v1.py.
"""

import time

import numpy as np

from fighterid_vision_engine.config.settings import (
    STRIKE_SPEED_MS,
    STRIKE_DIST_M,
    STRIKE_COOL_S,
    PIX_PER_M,
    KP_NOSE,
    KP_L_WRIST,
    KP_R_WRIST,
)
from fighterid_vision_engine.pipeline import fighters_state as _fs


class StrikeDetector:
    """
    Detecta golpes usando velocidad de muñeca y distancia al oponente.

    Returns de detect():
      (strike: bool, speed_ms: float, confidence: float)
      speed_ms:    velocidad máxima de muñeca en m/s
      confidence:  0.0–1.0, escalada por velocidad
    """

    def __init__(self):
        self._prev: dict = {}   # corner → (lw, rw, timestamp)
        self._last: dict = {}   # corner → timestamp del último golpe detectado

    def detect(self, corner: str, person: dict, opponent: dict | None = None):
        kps = person["keypoints"]
        lw  = kps[KP_L_WRIST, :2].copy()
        rw  = kps[KP_R_WRIST, :2].copy()
        now = time.time()

        # Cooldown — evita golpes duplicados
        if now - self._last.get(corner, 0) < STRIKE_COOL_S:
            self._prev[corner] = (lw, rw, now)
            return False, 0.0, 0.0

        prev = self._prev.get(corner)
        self._prev[corner] = (lw, rw, now)

        if prev is None:
            return False, 0.0, 0.0

        prev_lw, prev_rw, prev_t = prev
        dt = now - prev_t
        if dt < 0.005:
            return False, 0.0, 0.0

        speed_l = float(np.linalg.norm(lw - prev_lw)) / dt / PIX_PER_M
        speed_r = float(np.linalg.norm(rw - prev_rw)) / dt / PIX_PER_M
        speed   = max(speed_l, speed_r)

        # Registrar posición de muñeca dominante para tracking de agilidad
        faster_wrist = rw if speed_r >= speed_l else lw
        _fs.record_position(corner.upper(), (float(faster_wrist[0]), float(faster_wrist[1])))

        if speed < STRIKE_SPEED_MS:
            return False, speed, 0.0

        # Verificar distancia al oponente si está disponible
        is_hit = False
        if opponent is not None:
            opp_nose = opponent["keypoints"][KP_NOSE, :2]
            dist     = float(np.linalg.norm(faster_wrist - opp_nose)) / PIX_PER_M
            if dist > STRIKE_DIST_M:
                # Velocidad suficiente pero demasiado lejos → miss
                _fs.record_strike(corner.upper(), speed, is_hit=False)
                return False, speed, 0.0
            is_hit = True
        else:
            # Sin oponente detectado → contabilizar como miss (velocidad válida)
            is_hit = False

        _fs.record_strike(corner.upper(), speed, is_hit=is_hit)
        confidence = min(speed / 8.0, 1.0)
        self._last[corner] = now
        return True, speed, confidence
