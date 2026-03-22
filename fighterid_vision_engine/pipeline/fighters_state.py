"""
FighterID Vision Engine — FightersState
Estado en memoria por luchador: golpes, velocidad, posiciones, XP.

Expone:
  fighters_state        → dict compartido RED/BLUE
  reset(start_time)     → reinicia al inicio de sesión
  compute_velocity()    → velocidad Euclídea px/s
  record_position()     → registra posición de muñeca (agility tracking)
  record_strike()       → actualiza punch_count, hits/misses, XP
  compute_stats()       → métricas core por luchador
  aggressiveness/agility/control → índices derivados
  get_level(xp)         → nivel estilo Pokémon
  build_payload()       → payload completo para dashboard
"""

import threading
import time
from collections import deque

_lock = threading.Lock()

fighters_state: dict = {
    "RED": {
        "punch_count":    0,
        "total_velocity": 0.0,
        "last_positions": deque(maxlen=100),
        "hits":           0,
        "misses":         0,
        "xp":             0,
    },
    "BLUE": {
        "punch_count":    0,
        "total_velocity": 0.0,
        "last_positions": deque(maxlen=100),
        "hits":           0,
        "misses":         0,
        "xp":             0,
    },
}

_fight_start_time: float | None = None


def reset(start_time: float | None = None) -> None:
    """Reinicia el estado al comienzo de una nueva sesión de combate."""
    global _fight_start_time
    with _lock:
        for f in fighters_state.values():
            f["punch_count"]    = 0
            f["total_velocity"] = 0.0
            f["last_positions"].clear()
            f["hits"]           = 0
            f["misses"]         = 0
            f["xp"]             = 0
        _fight_start_time = start_time if start_time is not None else time.time()
    print("[STATE] Estado de luchadores reiniciado")


# ── Velocidad ─────────────────────────────────────────────────────────────

def compute_velocity(prev: tuple, curr: tuple, dt: float) -> float:
    """Velocidad Euclídea en píxeles/s. dt en segundos."""
    dx = curr[0] - prev[0]
    dy = curr[1] - prev[1]
    return ((dx ** 2 + dy ** 2) ** 0.5) / max(dt, 1e-6)


# ── Registro ──────────────────────────────────────────────────────────────

def record_position(fighter_id: str, wrist_pos: tuple) -> None:
    """Registra la posición de muñeca del frame actual (para cálculo de agilidad)."""
    with _lock:
        fighters_state[fighter_id]["last_positions"].append(wrist_pos)


def record_strike(fighter_id: str, velocity: float, is_hit: bool) -> None:
    """
    Registra un golpe detectado.
    is_hit=True  → velocidad + distancia al oponente OK (golpe conectado)
    is_hit=False → velocidad OK pero sin oponente o demasiado lejos (fallo)
    """
    with _lock:
        f = fighters_state[fighter_id]
        f["punch_count"]    += 1
        f["total_velocity"] += velocity
        if is_hit:
            f["hits"]   += 1
        else:
            f["misses"] += 1
        # XP dentro del lock (evita llamada externa con lock anidado)
        xp_gain = int(velocity * 10)
        f["xp"] += xp_gain


# ── Métricas core ─────────────────────────────────────────────────────────

def compute_stats(fighter_id: str) -> dict:
    """Métricas core: count, avg_velocity, accuracy, frequency_per_min."""
    elapsed_min = (time.time() - (_fight_start_time or time.time())) / 60.0
    with _lock:
        f       = fighters_state[fighter_id]
        punches = f["punch_count"]
        return {
            "punches":           punches,
            "avg_velocity":      round(f["total_velocity"] / max(punches, 1), 3),
            "accuracy":          round(f["hits"] / max(punches, 1), 3),
            "frequency_per_min": round(punches / max(elapsed_min, 0.001), 2),
        }


# ── Índices derivados ─────────────────────────────────────────────────────

def aggressiveness(f: dict) -> float:
    """Agresividad: golpes / 10."""
    return round(f["punch_count"] / 10, 3)


def agility(f: dict) -> float:
    """Agilidad: posiciones únicas registradas / 20."""
    return round(len(f["last_positions"]) / 20, 3)


def control(f: dict) -> float:
    """Control: tasa de golpes conectados."""
    return round(f["hits"] / max(f["punch_count"], 1), 3)


# ── Gamificación ──────────────────────────────────────────────────────────

def get_level(xp: int) -> int:
    """Nivel a partir de XP acumulado (raíz cuadrada)."""
    return int(xp ** 0.5)


# ── Payload para dashboard ────────────────────────────────────────────────

def build_payload(fight_id: str) -> dict:
    """
    Construye el payload completo para el endpoint /stats del dashboard.
    Thread-safe: adquiere el lock una sola vez.
    """
    now         = time.time()
    elapsed_min = (now - (_fight_start_time or now)) / 60.0

    with _lock:
        payload = {
            "fight_id":  fight_id,
            "timestamp": now,
            "fighters":  {},
        }
        for fid in ("RED", "BLUE"):
            f       = fighters_state[fid]
            punches = f["punch_count"]
            payload["fighters"][fid] = {
                # Core
                "punches":           punches,
                "avg_velocity":      round(f["total_velocity"] / max(punches, 1), 3),
                "accuracy":          round(f["hits"] / max(punches, 1), 3),
                "frequency_per_min": round(punches / max(elapsed_min, 0.001), 2),
                # Derivados
                "aggressiveness":    round(f["punch_count"] / 10, 3),
                "agility":           round(len(f["last_positions"]) / 20, 3),
                "control":           round(f["hits"] / max(punches, 1), 3),
                # Gamificación
                "xp":                f["xp"],
                "level":             get_level(f["xp"]),
            }
    return payload
