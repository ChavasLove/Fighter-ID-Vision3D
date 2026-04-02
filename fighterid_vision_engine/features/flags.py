"""
Feature Flags del motor de visión.

Permite activar/desactivar subsistemas sin deployar nuevo código.
Todos los flags se leen desde variables de entorno con valores por defecto seguros.

Uso:
    from fighterid_vision_engine.features import FeatureFlags
    flags = FeatureFlags()
    if flags.NEW_SCORING_ENGINE:
        ...
"""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _bool_env(key: str, default: bool) -> bool:
    val = os.getenv(key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


class FeatureFlags:
    """
    Feature flags leídas desde variables de entorno al instanciar.

    Flags disponibles:
        FF_NEW_SCORING_ENGINE   — nuevo motor de reglas de boxeo (default: True)
        FF_NEW_HIT_FILTERS      — nuevos filtros de golpes (default: True)
        FF_NEW_DETECTION_MODEL  — nuevo modelo de detección (default: False)
        FF_EMIT_SCORING_EVENTS  — emitir eventos a scoring_events en Supabase (default: True)
    """

    def __init__(self) -> None:
        self.NEW_SCORING_ENGINE:  bool = _bool_env("FF_NEW_SCORING_ENGINE",  True)
        self.NEW_HIT_FILTERS:     bool = _bool_env("FF_NEW_HIT_FILTERS",     True)
        self.NEW_DETECTION_MODEL: bool = _bool_env("FF_NEW_DETECTION_MODEL", False)
        self.EMIT_SCORING_EVENTS: bool = _bool_env("FF_EMIT_SCORING_EVENTS", True)

    def __repr__(self) -> str:
        return (
            f"FeatureFlags("
            f"NEW_SCORING_ENGINE={self.NEW_SCORING_ENGINE}, "
            f"NEW_HIT_FILTERS={self.NEW_HIT_FILTERS}, "
            f"NEW_DETECTION_MODEL={self.NEW_DETECTION_MODEL}, "
            f"EMIT_SCORING_EVENTS={self.EMIT_SCORING_EVENTS})"
        )
