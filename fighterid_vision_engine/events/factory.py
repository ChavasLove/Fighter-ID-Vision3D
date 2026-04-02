"""
Fábrica de eventos de combate.

CombatEventFactory provee constructores con tipado fuerte para cada EventType.
Centraliza la lógica de generación de UUIDs, timestamps y versiones.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from .models import CombatEvent, EventType


def _utc_now() -> str:
    """Retorna el timestamp actual en formato ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class CombatEventFactory:
    """
    Constructores tipados para cada EventType.

    Uso:
        event = CombatEventFactory.hit_detected(
            fight_id="...",
            corner="red",
            confidence=0.88,
            hit_type="jab",
            target="head",
            impact_score=4.2,
            round_num=3,
            model_version="v1.0.0",
            rules_version="v1.0.0",
        )
    """

    @staticmethod
    def hit_detected(
        fight_id:      str,
        corner:        str,
        confidence:    float,
        hit_type:      str,
        target:        str,
        impact_score:  float,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
        latency_ms:    float = 0.0,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        corner,
            event_type=    EventType.HIT_DETECTED.value,
            confidence=    confidence,
            metadata={
                "hit_type":     hit_type,
                "target":       target,
                "impact_score": impact_score,
                "round":        round_num,
            },
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
            latency_ms=    latency_ms,
        )

    @staticmethod
    def knockdown(
        fight_id:      str,
        corner:        str,
        confidence:    float,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
        latency_ms:    float = 0.0,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        corner,
            event_type=    EventType.KNOCKDOWN.value,
            confidence=    confidence,
            metadata={
                "round": round_num,
                "target": "head",
                "hit_type": "knockdown",
                "impact_score": 0.0,
            },
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
            latency_ms=    latency_ms,
        )

    @staticmethod
    def round_start(
        fight_id:      str,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        "",
            event_type=    EventType.ROUND_START.value,
            confidence=    1.0,
            metadata={"round": round_num},
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
        )

    @staticmethod
    def round_end(
        fight_id:      str,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        "",
            event_type=    EventType.ROUND_END.value,
            confidence=    1.0,
            metadata={"round": round_num},
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
        )

    @staticmethod
    def fighter_identified(
        fight_id:      str,
        corner:        str,
        fighter_id:    str,
        confidence:    float,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        corner,
            event_type=    EventType.FIGHTER_IDENTIFIED.value,
            confidence=    confidence,
            metadata={"fighter_id": fighter_id},
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
        )

    @staticmethod
    def invalid_hit(
        fight_id:      str,
        corner:        str,
        reason:        str,
        confidence:    float,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        corner,
            event_type=    EventType.INVALID_HIT.value,
            confidence=    confidence,
            metadata={
                "reason":   reason,
                "round":    round_num,
                "hit_type": "unknown",
                "target":   "unknown",
                "impact_score": 0.0,
            },
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
        )

    @staticmethod
    def referee_intervention(
        fight_id:      str,
        reason:        str,
        round_num:     int,
        model_version: str,
        rules_version: str,
        trace_id:      Optional[str] = None,
    ) -> CombatEvent:
        return CombatEvent(
            id=            _new_uuid(),
            fight_id=      fight_id,
            timestamp=     _utc_now(),
            corner=        "",
            event_type=    EventType.REFEREE_INTERVENTION.value,
            confidence=    1.0,
            metadata={
                "reason": reason,
                "round":  round_num,
            },
            model_version= model_version,
            rules_version= rules_version,
            trace_id=      trace_id or _new_uuid(),
        )
