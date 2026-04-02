"""
FighterID — Modelo formal de eventos de combate.

Todo evento detectado por visión se representa como un CombatEvent atómico e
inmutable. Ningún componente externo puede mutar un evento tras su creación.
"""

from .models import CombatEvent, EventType, RoundScore
from .factory import CombatEventFactory
from .validators import validate_event, ValidationError

__all__ = [
    "CombatEvent",
    "EventType",
    "RoundScore",
    "CombatEventFactory",
    "validate_event",
    "ValidationError",
]
