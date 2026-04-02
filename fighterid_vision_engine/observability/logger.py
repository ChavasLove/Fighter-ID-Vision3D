"""
Logger estructurado para el motor de visión FighterID.

Cada línea de log es un objeto JSON con todos los campos necesarios para
rastrear un evento desde su detección hasta su inserción en Supabase.

Campos obligatorios en cada log:
    trace_id    — UUID del ciclo de detección
    source      — "vision_engine"
    model       — nombre/versión del modelo
    event_type  — tipo de evento
    latency_ms  — tiempo desde captura hasta emisión
    timestamp   — ISO 8601 UTC
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Logger Python estándar — escribe a stderr por defecto
_log = logging.getLogger("fighterid.vision")

if not _log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.DEBUG if os.getenv("LOG_DEBUG", "").lower() == "true" else logging.INFO)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StructuredLogger:
    """
    Logger JSON estructurado para el motor de visión.

    Uso:
        logger = StructuredLogger(model="YOLOv8n-pose", model_version="v1.0.0")
        logger.log_event(event, latency_ms=45.2)
        logger.log_error(trace_id="...", error=exc, context={"fight_id": "..."})
    """

    def __init__(self, model: str = "YOLOv8n-pose", model_version: str = "v1.0.0") -> None:
        self.model         = model
        self.model_version = model_version

    def log_event(self, event: Any, latency_ms: float = 0.0) -> None:
        """Registra un CombatEvent procesado exitosamente."""
        record = {
            "level":         "INFO",
            "timestamp":     _utc_now(),
            "trace_id":      getattr(event, "trace_id", ""),
            "source":        getattr(event, "source", "vision_engine"),
            "model":         self.model,
            "model_version": self.model_version,
            "event_type":    getattr(event, "event_type", ""),
            "fight_id":      getattr(event, "fight_id", ""),
            "corner":        getattr(event, "corner", ""),
            "confidence":    getattr(event, "confidence", 0.0),
            "latency_ms":    round(latency_ms, 2),
        }
        _log.info(json.dumps(record))

    def log_error(
        self,
        trace_id: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Registra un error del pipeline con contexto completo."""
        record = {
            "level":         "ERROR",
            "timestamp":     _utc_now(),
            "trace_id":      trace_id,
            "source":        "vision_engine",
            "model":         self.model,
            "model_version": self.model_version,
            "error_type":    type(error).__name__,
            "error_message": str(error),
            "context":       context or {},
        }
        _log.error(json.dumps(record))

    def log_retry(
        self,
        trace_id: str,
        attempt: int,
        max_attempts: int,
        fight_id: str,
        event_id: str,
    ) -> None:
        """Registra un intento de reenvío al buffer de reintentos."""
        record = {
            "level":      "WARN",
            "timestamp":  _utc_now(),
            "trace_id":   trace_id,
            "source":     "vision_engine",
            "model":      self.model,
            "action":     "retry_enqueue",
            "attempt":    attempt,
            "max":        max_attempts,
            "fight_id":   fight_id,
            "event_id":   event_id,
        }
        _log.warning(json.dumps(record))

    def log_buffer_write(self, event_id: str, fight_id: str, path: str) -> None:
        """Registra escritura al buffer local (Supabase no disponible)."""
        record = {
            "level":      "WARN",
            "timestamp":  _utc_now(),
            "source":     "vision_engine",
            "model":      self.model,
            "action":     "buffer_write",
            "event_id":   event_id,
            "fight_id":   fight_id,
            "buffer_path": path,
        }
        _log.warning(json.dumps(record))

    def log_scoring(self, round_score: Any) -> None:
        """Registra el resultado de scoring de un round."""
        record = {
            "level":         "INFO",
            "timestamp":     _utc_now(),
            "source":        "vision_engine",
            "model":         self.model,
            "action":        "round_scored",
            "fight_id":      getattr(round_score, "fight_id", ""),
            "round":         getattr(round_score, "round", 0),
            "red_score":     getattr(round_score, "red_score", 0),
            "blue_score":    getattr(round_score, "blue_score", 0),
            "confidence":    getattr(round_score, "confidence", 0.0),
            "rules_version": getattr(round_score, "rules_version", ""),
        }
        _log.info(json.dumps(record))
