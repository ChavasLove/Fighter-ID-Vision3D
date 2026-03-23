"""
FighterID Vision Engine — TemporalStrikeAnalyzer
Motor de detección de golpes en 3 capas:

  Capa 1 — Percepción:       buffer rolling de posiciones de muñeca (N frames)
  Capa 2 — Dinámica temporal: velocidad + aceleración + firma de golpe
  Capa 3 — Evento físico:    clasificación (jab/cross/hook/uppercut) + validación

Reemplaza al StrikeDetector single-frame. API compatible: detect() retorna
(strike, speed_ms, confidence, punch_type) — callers que ignoran el 4° valor
no se rompen.
"""

import time
from collections import deque

import numpy as np

from fighterid_vision_engine.config.settings import (
    STRIKE_SPEED_MS,
    STRIKE_DIST_M,
    STRIKE_COOL_S,
    PIX_PER_M,
    TEMPORAL_WINDOW_FRAMES,
    STRIKE_ACCEL_THRESHOLD,
    STRIKE_DECEL_REQUIRED,
    JAB_MAX_EXTENSION_M,
    CROSS_MIN_EXTENSION_M,
    HOOK_LATERAL_RATIO,
    UPPERCUT_VERTICAL_RATIO,
    KP_NOSE,
    KP_L_WRIST,
    KP_R_WRIST,
    KP_L_SHOULDER,
    KP_R_SHOULDER,
    KP_L_ELBOW,
    KP_R_ELBOW,
)
from fighterid_vision_engine.pipeline import fighters_state as _fs

# Mínimo de frames en el buffer antes de activar análisis temporal
_MIN_BUFFER = 5


class _WristBuffer:
    """Buffer rolling de posiciones de una muñeca para un luchador."""

    def __init__(self):
        self._buf: deque = deque(maxlen=TEMPORAL_WINDOW_FRAMES)

    def push(self, pos: np.ndarray, ts: float) -> None:
        """Agrega posición (x, y) en píxeles + timestamp."""
        self._buf.append((pos.copy(), ts))

    def snapshot(self) -> list:
        """Copia única del buffer — pasar a velocities/avg_dt/trajectory_vector
        para evitar múltiples conversiones deque→list por frame."""
        return list(self._buf)

    def velocities(self, snap: list | None = None) -> list[float]:
        """
        Lista de velocidades en m/s entre frames consecutivos.
        Retorna lista vacía si hay < 2 muestras.
        """
        buf = snap if snap is not None else list(self._buf)
        vels = []
        for i in range(1, len(buf)):
            pos1, t1 = buf[i - 1]
            pos2, t2 = buf[i]
            dt = t2 - t1
            if dt < 0.001:
                continue
            vels.append(float(np.linalg.norm(pos2 - pos1)) / dt / PIX_PER_M)
        return vels

    def accelerations(self, vels: list[float], dt_avg: float) -> list[float]:
        """Derivada primera de velocidades → aceleración en m/s²."""
        if len(vels) < 2 or dt_avg < 1e-6:
            return []
        return [(vels[i] - vels[i - 1]) / dt_avg for i in range(1, len(vels))]

    def avg_dt(self, snap: list | None = None) -> float:
        """Intervalo promedio entre frames del buffer."""
        buf = snap if snap is not None else list(self._buf)
        if len(buf) < 2:
            return 1.0 / 30.0  # default 30 fps
        dts = [buf[i][1] - buf[i - 1][1] for i in range(1, len(buf))]
        return float(np.mean(dts))

    def trajectory_vector(self, snap: list | None = None) -> np.ndarray:
        """
        Vector de trayectoria del primer al último punto del buffer.
        Útil para clasificación de golpe.
        """
        buf = snap if snap is not None else list(self._buf)
        if len(buf) < 2:
            return np.zeros(2)
        return buf[-1][0] - buf[0][0]

    def __len__(self) -> int:
        return len(self._buf)


def _detect_punch_signature(vels: list[float], accels: list[float]) -> tuple[bool, float]:
    """
    Detecta la firma cinemática de un golpe real:
      1. Velocidad pico ≥ umbral
      2. Aceleración antes del pico ≥ umbral
      3. (Opcional) desaceleración después del pico

    Retorna (es_golpe: bool, velocidad_pico: float).
    """
    if not vels:
        return False, 0.0

    peak_idx = int(np.argmax(vels))
    peak_vel = vels[peak_idx]

    if peak_vel < STRIKE_SPEED_MS:
        return False, peak_vel

    # Capa 2a: aceleración antes del pico
    if accels and peak_idx > 0 and peak_idx - 1 < len(accels):
        accel_before = accels[peak_idx - 1]
        if accel_before < STRIKE_ACCEL_THRESHOLD:
            return False, peak_vel

    # Capa 2b: desaceleración después del pico (opcional)
    if STRIKE_DECEL_REQUIRED and accels:
        after_indices = [i for i in range(peak_idx, len(accels))]
        if after_indices:
            avg_decel = float(np.mean([accels[i] for i in after_indices]))
            if avg_decel >= 0:
                # Sin desaceleración detectada → probablemente no es golpe
                return False, peak_vel

    return True, peak_vel


def _classify_punch(traj: np.ndarray, active_wrist: str,
                    kps: np.ndarray, depth_extension: float = 0.0) -> str:
    """
    Clasifica el tipo de golpe basado en la trayectoria de la muñeca.

    traj:            vector 2D (dx, dy) de trayectoria en píxeles
    active_wrist:    'left' o 'right'
    kps:             keypoints COCO (17, 3) para contexto biomecánico
    depth_extension: extensión en el eje Z (metros, de 3D si disponible)
    """
    total_dist = float(np.linalg.norm(traj))
    if total_dist < 1e-6:
        return "punch"

    dx = float(traj[0])   # positivo = derecha
    dy = float(traj[1])   # positivo = abajo (coordenadas imagen)

    lateral_ratio  = abs(dx) / total_dist
    vertical_ratio = -dy / total_dist  # negativo dy = muñeca sube = uppercut

    # Hook: componente lateral dominante
    if lateral_ratio >= HOOK_LATERAL_RATIO:
        return "hook"

    # Uppercut: componente vertical ascendente dominante
    if vertical_ratio >= UPPERCUT_VERTICAL_RATIO:
        return "uppercut"

    # Cross vs Jab: distinción por extensión en profundidad
    if depth_extension >= CROSS_MIN_EXTENSION_M:
        return "cross"
    if depth_extension <= JAB_MAX_EXTENSION_M:
        return "jab"

    return "punch"


class TemporalStrikeAnalyzer:
    """
    Motor de detección de golpes con análisis temporal multi-frame.

    Expone la misma API que StrikeDetector para compatibilidad:
      detect(corner, person, opponent) → (hit, speed_ms, confidence, punch_type)

    El 4° valor (punch_type) es nuevo — callers existentes que solo usan
    los primeros 3 no se rompen.
    """

    def __init__(self):
        # Buffers por esquina × muñeca
        self._lw: dict[str, _WristBuffer] = {}
        self._rw: dict[str, _WristBuffer] = {}
        self._last_strike: dict[str, float] = {}

    def _get_buffers(self, corner: str) -> tuple[_WristBuffer, _WristBuffer]:
        if corner not in self._lw:
            self._lw[corner] = _WristBuffer()
            self._rw[corner] = _WristBuffer()
        return self._lw[corner], self._rw[corner]

    def detect(self, corner: str, person: dict,
               opponent: dict | None = None) -> tuple[bool, float, float, str]:
        """
        Detecta golpes usando análisis temporal de N frames.

        Retorna (strike, speed_ms, confidence, punch_type).
        Si el buffer está vacío (<_MIN_BUFFER frames), usa fallback single-frame.
        """
        kps = person["keypoints"]
        lw  = kps[KP_L_WRIST, :2].copy()
        rw  = kps[KP_R_WRIST, :2].copy()
        now = time.time()

        # Cooldown
        if now - self._last_strike.get(corner, 0) < STRIKE_COOL_S:
            lw_buf, rw_buf = self._get_buffers(corner)
            lw_buf.push(lw, now)
            rw_buf.push(rw, now)
            return False, 0.0, 0.0, ""

        lw_buf, rw_buf = self._get_buffers(corner)
        lw_buf.push(lw, now)
        rw_buf.push(rw, now)

        # Registrar posición para stats de agilidad
        _fs.record_position(corner.upper(), (float(lw[0]), float(lw[1])))

        # ── Análisis temporal ────────────────────────────────────────────
        hit      = False
        speed    = 0.0
        conf     = 0.0
        punch_type = ""
        active_wrist = ""

        for wrist_id, buf, wrist_pos in (("left", lw_buf, lw), ("right", rw_buf, rw)):
            if len(buf) < _MIN_BUFFER:
                # Fallback single-frame para warm-up del buffer
                continue

            snap   = buf.snapshot()
            vels   = buf.velocities(snap)
            dt_avg = buf.avg_dt(snap)
            accels = buf.accelerations(vels, dt_avg)

            is_punch, peak_vel = _detect_punch_signature(vels, accels)
            if is_punch and peak_vel > speed:
                speed        = peak_vel
                hit          = True
                active_wrist = wrist_id

        # Si buffer muy pequeño en ambas muñecas → fallback básico
        if len(lw_buf) < _MIN_BUFFER and len(rw_buf) < _MIN_BUFFER:
            speed_l = _single_frame_speed(lw_buf, lw)
            speed_r = _single_frame_speed(rw_buf, rw)
            speed   = max(speed_l, speed_r)
            if speed >= STRIKE_SPEED_MS:
                hit          = True
                active_wrist = "right" if speed_r >= speed_l else "left"

        if not hit:
            return False, speed, 0.0, ""

        # ── Verificar distancia al oponente ──────────────────────────────
        faster_wrist_pos = rw if active_wrist == "right" else lw
        is_hit = False

        if opponent is not None:
            opp_nose = opponent["keypoints"][KP_NOSE, :2]
            dist     = float(np.linalg.norm(faster_wrist_pos - opp_nose)) / PIX_PER_M
            if dist > STRIKE_DIST_M:
                _fs.record_strike(corner.upper(), speed, is_hit=False)
                return False, speed, 0.0, ""
            is_hit = True
        else:
            is_hit = False

        # ── Clasificar golpe ─────────────────────────────────────────────
        buf  = rw_buf if active_wrist == "right" else lw_buf
        traj = buf.trajectory_vector(buf.snapshot())
        punch_type = _classify_punch(traj, active_wrist, kps)

        _fs.record_strike(corner.upper(), speed, is_hit=is_hit)
        conf = min(speed / 8.0, 1.0)
        self._last_strike[corner] = now
        return True, speed, conf, punch_type


def _single_frame_speed(buf: _WristBuffer, current: np.ndarray) -> float:
    """Velocidad instantánea usando último punto del buffer (fallback warm-up)."""
    b = list(buf._buf)
    if len(b) < 1:
        return 0.0
    prev_pos, prev_t = b[-1]
    dt = time.time() - prev_t
    if dt < 0.005:
        return 0.0
    return float(np.linalg.norm(current - prev_pos)) / dt / PIX_PER_M
