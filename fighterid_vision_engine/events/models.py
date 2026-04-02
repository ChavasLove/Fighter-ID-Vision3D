"""
Modelos de datos del sistema de eventos de combate.

REGLA: CombatEvent es frozen=True — NO puede mutarse tras su creación.
Esto garantiza la integridad del registro de eventos deportivos.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class EventType(str, Enum):
    """Tipos de eventos atómicos reconocidos por el motor de visión."""
    HIT_DETECTED         = "hit_detected"
    KNOCKDOWN            = "knockdown"
    ROUND_START          = "round_start"
    ROUND_END            = "round_end"
    FIGHTER_IDENTIFIED   = "fighter_identified"
    INVALID_HIT          = "invalid_hit"
    REFEREE_INTERVENTION = "referee_intervention"


class HitType(str, Enum):
    """Tipos de golpe clasificados por biomecánica."""
    JAB      = "jab"
    CROSS    = "cross"
    HOOK     = "hook"
    UPPERCUT = "uppercut"
    UNKNOWN  = "unknown"


class TargetZone(str, Enum):
    """Zonas de impacto válidas en boxeo profesional."""
    HEAD = "head"
    BODY = "body"


class Corner(str, Enum):
    """Esquinas del ring."""
    RED  = "red"
    BLUE = "blue"


@dataclass(frozen=True)
class CombatEvent:
    """
    Evento atómico e inmutable de combate.

    Restricciones:
    - fight_id y timestamp son OBLIGATORIOS (nunca vacíos).
    - confidence debe estar en el rango [0.0, 1.0].
    - Los eventos NO pueden modificarse tras su creación (frozen=True).
    - Cada evento tiene un trace_id único para rastreabilidad.
    """
    id:            str               # UUID del evento
    fight_id:      str               # UUID de la pelea — NUNCA vacío
    timestamp:     str               # ISO 8601 UTC
    event_type:    str               # Valor de EventType
    confidence:    float             # 0.0 – 1.0
    metadata:      Dict[str, Any]    # Datos del evento (hit_type, target, impact_score…)
    model_version: str               # Versión del modelo de detección, e.g. "v1.0.0"
    rules_version: str               # Versión del motor de reglas, e.g. "v1.0.0"
    trace_id:      str               # UUID por frame de detección
    corner:        str = ""          # "red" | "blue" — vacío para eventos globales
    source:        str = "vision_engine"
    latency_ms:    float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el evento a un diccionario JSON-serializable."""
        return {
            "id":            self.id,
            "fight_id":      self.fight_id,
            "timestamp":     self.timestamp,
            "corner":        self.corner,
            "event_type":    self.event_type,
            "confidence":    round(self.confidence, 4),
            "metadata":      self.metadata,
            "model_version": self.model_version,
            "rules_version": self.rules_version,
            "trace_id":      self.trace_id,
            "source":        self.source,
            "latency_ms":    round(self.latency_ms, 2),
        }


@dataclass(frozen=True)
class RoundScore:
    """
    Resultado de puntuación de un round — producido por BoxingRulesEngine.

    Inmutable: refleja el estado final del round al momento de su cómputo.
    """
    fight_id:      str
    round:         int
    red_score:     int
    blue_score:    int
    confidence:    float
    model_version: str
    rules_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fight_id":      self.fight_id,
            "round":         self.round,
            "red_score":     self.red_score,
            "blue_score":    self.blue_score,
            "confidence":    round(self.confidence, 4),
            "model_version": self.model_version,
            "rules_version": self.rules_version,
        }
