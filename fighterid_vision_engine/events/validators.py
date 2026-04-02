"""
Validadores de eventos de combate.

REGLA CRÍTICA: Todo evento debe pasar validate_event() ANTES de ser emitido.
Esto garantiza la integridad del registro deportivo.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from .models import CombatEvent, EventType


class ValidationError(ValueError):
    """Error de validación de un CombatEvent — indica un problema de integridad."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"[VALIDATION] Campo '{field}': {message}")


# ── Valores permitidos ────────────────────────────────────────────────────────
_VALID_EVENT_TYPES = {e.value for e in EventType}
_VALID_CORNERS     = {"red", "blue", ""}   # "" permitido en eventos globales
_VALID_HIT_TYPES   = {"jab", "cross", "hook", "uppercut", "knockdown", "unknown"}
_VALID_TARGETS     = {"head", "body", "unknown"}

# Campos de metadata requeridos por tipo de evento
_REQUIRED_METADATA: Dict[str, list] = {
    EventType.HIT_DETECTED.value:         ["hit_type", "target", "impact_score", "round"],
    EventType.KNOCKDOWN.value:             ["round"],
    EventType.ROUND_START.value:           ["round"],
    EventType.ROUND_END.value:             ["round"],
    EventType.FIGHTER_IDENTIFIED.value:    ["fighter_id"],
    EventType.INVALID_HIT.value:           ["reason", "round"],
    EventType.REFEREE_INTERVENTION.value:  ["reason", "round"],
}


def validate_event(event: CombatEvent) -> None:
    """
    Valida un CombatEvent contra todas las reglas de integridad.

    Lanza ValidationError (subclase de ValueError) si alguna regla falla.
    Si el evento es válido, retorna None silenciosamente.
    """
    _check_required_strings(event)
    _check_timestamp(event)
    _check_corner(event)
    _check_event_type(event)
    _check_confidence(event)
    _check_versions(event)
    _check_metadata(event)


def validate_event_dict(data: Dict[str, Any]) -> None:
    """
    Valida un diccionario de evento (pre-serialización a Supabase).

    Comprueba tipos, campos obligatorios y valores permitidos sin instanciar
    CombatEvent — útil para validar payloads que llegan de fuera.
    """
    required_fields = [
        "id", "fight_id", "timestamp", "event_type",
        "confidence", "metadata", "model_version", "rules_version", "trace_id",
    ]
    for f in required_fields:
        if f not in data:
            raise ValidationError(f, "campo obligatorio ausente en el diccionario")
        if data[f] is None:
            raise ValidationError(f, "valor nulo no permitido")

    if not isinstance(data["confidence"], (int, float)):
        raise ValidationError("confidence", "debe ser un número")
    if not (0.0 <= float(data["confidence"]) <= 1.0):
        raise ValidationError("confidence", f"debe estar en [0,1], recibido {data['confidence']}")

    if data["event_type"] not in _VALID_EVENT_TYPES:
        raise ValidationError("event_type",
                               f"'{data['event_type']}' no está en {_VALID_EVENT_TYPES}")

    corner = data.get("corner", "")
    if corner not in _VALID_CORNERS:
        raise ValidationError("corner", f"'{corner}' no es 'red', 'blue' ni ''")


# ── Checks internos ───────────────────────────────────────────────────────────

def _check_required_strings(event: CombatEvent) -> None:
    if not event.id or not event.id.strip():
        raise ValidationError("id", "no puede estar vacío")
    if not event.fight_id or not event.fight_id.strip():
        raise ValidationError("fight_id", "no puede estar vacío — todo evento requiere fight_id")
    if not event.trace_id or not event.trace_id.strip():
        raise ValidationError("trace_id", "no puede estar vacío")
    if not event.model_version or not event.model_version.strip():
        raise ValidationError("model_version", "no puede estar vacío")
    if not event.rules_version or not event.rules_version.strip():
        raise ValidationError("rules_version", "no puede estar vacío")


def _check_timestamp(event: CombatEvent) -> None:
    if not event.timestamp:
        raise ValidationError("timestamp", "no puede estar vacío")
    try:
        datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("timestamp",
                               f"'{event.timestamp}' no es un timestamp ISO 8601 válido")


def _check_corner(event: CombatEvent) -> None:
    if event.corner not in _VALID_CORNERS:
        raise ValidationError("corner",
                               f"'{event.corner}' no es 'red', 'blue' ni '' (vacío para eventos globales)")


def _check_event_type(event: CombatEvent) -> None:
    if event.event_type not in _VALID_EVENT_TYPES:
        raise ValidationError("event_type",
                               f"'{event.event_type}' no está en {_VALID_EVENT_TYPES}")


def _check_confidence(event: CombatEvent) -> None:
    if not isinstance(event.confidence, (int, float)):
        raise ValidationError("confidence", "debe ser un número")
    if not (0.0 <= event.confidence <= 1.0):
        raise ValidationError("confidence",
                               f"debe estar en [0.0, 1.0], recibido {event.confidence}")


def _check_versions(event: CombatEvent) -> None:
    for vfield, vval in [("model_version", event.model_version),
                          ("rules_version", event.rules_version)]:
        if not vval.startswith("v"):
            raise ValidationError(vfield,
                                   f"'{vval}' debe tener formato 'vX.Y.Z' (ej. 'v1.0.0')")


def _check_metadata(event: CombatEvent) -> None:
    required_keys = _REQUIRED_METADATA.get(event.event_type, [])
    for key in required_keys:
        if key not in event.metadata:
            raise ValidationError(
                "metadata",
                f"campo obligatorio '{key}' ausente en metadata para event_type='{event.event_type}'"
            )

    # Validaciones adicionales para hit_detected
    if event.event_type == EventType.HIT_DETECTED.value:
        hit_type = event.metadata.get("hit_type", "")
        if hit_type not in _VALID_HIT_TYPES:
            raise ValidationError("metadata.hit_type",
                                   f"'{hit_type}' no está en {_VALID_HIT_TYPES}")

        target = event.metadata.get("target", "")
        if target not in _VALID_TARGETS:
            raise ValidationError("metadata.target",
                                   f"'{target}' no está en {_VALID_TARGETS}")

        impact = event.metadata.get("impact_score")
        if not isinstance(impact, (int, float)) or impact < 0:
            raise ValidationError("metadata.impact_score",
                                   "debe ser un número >= 0")

        round_num = event.metadata.get("round")
        if not isinstance(round_num, int) or round_num < 1:
            raise ValidationError("metadata.round",
                                   "debe ser un entero >= 1")
