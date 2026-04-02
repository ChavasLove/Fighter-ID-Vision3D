"""
Tests del motor de reglas de boxeo profesional.

Verifica:
- Filtro de confianza mínima (0.75)
- Deduplicación temporal (< 300ms)
- Sistema de puntuación (clean +1, dominant +2, knockdown +10)
- Override de round por knockdown
- Zonas de impacto válidas
"""

import time
from datetime import datetime, timezone, timedelta

import pytest

from fighterid_vision_engine.events.factory import CombatEventFactory
from fighterid_vision_engine.scoring.rules_engine import (
    BoxingRulesEngine, MIN_CONFIDENCE, DEDUP_WINDOW_S, POINTS,
)

FIGHT_ID = "fight-rules-test"
MV = "v1.0.0"
RV = "v1.0.0"


def _ts(offset_ms: float = 0) -> str:
    """Genera un timestamp UTC con offset en ms desde ahora."""
    dt = datetime.now(timezone.utc) + timedelta(milliseconds=offset_ms)
    return dt.isoformat()


def _make_hit(corner="red", confidence=0.88, target="head",
              impact_score=3.0, round_num=1, ts_offset_ms=0):
    """Factory helper para crear hits con timestamp controlado."""
    from fighterid_vision_engine.events.models import CombatEvent, EventType
    import uuid
    return CombatEvent(
        id=str(uuid.uuid4()),
        fight_id=FIGHT_ID,
        timestamp=_ts(ts_offset_ms),
        corner=corner,
        event_type=EventType.HIT_DETECTED.value,
        confidence=confidence,
        metadata={"hit_type": "jab", "target": target,
                  "impact_score": impact_score, "round": round_num},
        model_version=MV,
        rules_version=RV,
        trace_id=str(uuid.uuid4()),
    )


class TestConfidenceFilter:
    def test_high_confidence_accepted(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(confidence=0.80)
        result = engine.process_event(event)
        assert result.accepted
        assert result.points > 0

    def test_exact_threshold_accepted(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(confidence=MIN_CONFIDENCE)
        result = engine.process_event(event)
        assert result.accepted

    def test_below_threshold_rejected(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(confidence=0.74)
        result = engine.process_event(event)
        assert not result.accepted
        assert "low_confidence" in result.reason

    def test_zero_confidence_rejected(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(confidence=0.0)
        result = engine.process_event(event)
        assert not result.accepted


class TestTargetZoneFilter:
    def test_head_target_accepted(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(target="head")
        result = engine.process_event(event)
        assert result.accepted

    def test_body_target_accepted(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(target="body")
        result = engine.process_event(event)
        assert result.accepted

    def test_unknown_target_rejected(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(target="unknown")
        result = engine.process_event(event)
        assert not result.accepted
        assert "invalid_target" in result.reason

    def test_empty_target_rejected(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(target="")
        result = engine.process_event(event)
        assert not result.accepted


class TestDeduplification:
    def test_second_hit_within_300ms_rejected(self):
        """Dos golpes del mismo corner en < 300ms → el segundo es duplicado."""
        engine = BoxingRulesEngine()
        now_ms = 0
        hit1   = _make_hit(corner="red", ts_offset_ms=now_ms)
        hit2   = _make_hit(corner="red", ts_offset_ms=now_ms + 100)  # 100ms después
        result1 = engine.process_event(hit1)
        result2 = engine.process_event(hit2)
        assert result1.accepted
        assert not result2.accepted
        assert "duplicate" in result2.reason

    def test_hit_after_300ms_accepted(self):
        """Golpe del mismo corner después de 300ms → NO es duplicado."""
        engine = BoxingRulesEngine()
        now_ms = 0
        hit1   = _make_hit(corner="red", ts_offset_ms=now_ms)
        hit2   = _make_hit(corner="red", ts_offset_ms=now_ms + 350)  # 350ms después
        engine.process_event(hit1)
        result2 = engine.process_event(hit2)
        assert result2.accepted

    def test_different_corners_not_deduped(self):
        """Golpes de corners distintos NO se afectan entre sí."""
        engine  = BoxingRulesEngine()
        now_ms  = 0
        hit_red  = _make_hit(corner="red",  ts_offset_ms=now_ms)
        hit_blue = _make_hit(corner="blue", ts_offset_ms=now_ms + 50)
        res_red  = engine.process_event(hit_red)
        res_blue = engine.process_event(hit_blue)
        assert res_red.accepted
        assert res_blue.accepted

    def test_dedup_resets_after_round(self):
        """Después de reset_dedup_state(), el mismo corner puede golpear de nuevo."""
        engine = BoxingRulesEngine()
        now_ms = 0
        hit1   = _make_hit(corner="red", ts_offset_ms=now_ms)
        engine.process_event(hit1)
        engine.reset_dedup_state()
        hit2   = _make_hit(corner="red", ts_offset_ms=now_ms + 50)
        result = engine.process_event(hit2)
        assert result.accepted


class TestScoring:
    def test_clean_hit_gives_1_point(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(impact_score=2.0)  # bajo umbral dominante (5.0)
        result = engine.process_event(event)
        assert result.accepted
        assert result.points == POINTS["clean_hit"]  # 1

    def test_dominant_hit_gives_2_points(self):
        engine = BoxingRulesEngine()
        event  = _make_hit(impact_score=6.0)  # sobre umbral dominante (5.0)
        result = engine.process_event(event)
        assert result.accepted
        assert result.points == POINTS["dominant_hit"]  # 2

    def test_knockdown_gives_10_points(self):
        engine = BoxingRulesEngine()
        kd     = CombatEventFactory.knockdown(
            fight_id=FIGHT_ID, corner="red", confidence=0.99,
            round_num=1, model_version=MV, rules_version=RV,
        )
        result = engine.process_event(kd)
        assert result.accepted
        assert result.points     == POINTS["knockdown"]  # 10
        assert result.is_knockdown

    def test_non_scoring_event_gives_0_points(self):
        engine = BoxingRulesEngine()
        event  = CombatEventFactory.round_start(
            fight_id=FIGHT_ID, round_num=1, model_version=MV, rules_version=RV,
        )
        result = engine.process_event(event)
        assert not result.accepted
        assert result.points == 0


class TestComputeRoundScore:
    def test_round_score_with_clean_hits(self):
        """Red lanza 3 golpes limpios, Blue 1 → red_score=3, blue_score=1."""
        engine = BoxingRulesEngine()
        events = [
            _make_hit("red",  0.85, ts_offset_ms=i * 400)  # 400ms entre cada uno
            for i in range(3)
        ] + [
            _make_hit("blue", 0.85, ts_offset_ms=1200 + i * 400)
            for i in range(1)
        ]
        score = engine.compute_round_score(
            events, round_num=1, fight_id=FIGHT_ID,
            model_version=MV, rules_version=RV,
        )
        assert score.fight_id   == FIGHT_ID
        assert score.red_score  == 3
        assert score.blue_score == 1
        assert 0.0 <= score.confidence <= 1.0

    def test_knockdown_overrides_round_score(self):
        """Knockdown por Red → red=10, blue=0 aunque Blue tuviera golpes."""
        engine = BoxingRulesEngine()
        kd = CombatEventFactory.knockdown(
            fight_id=FIGHT_ID, corner="red", confidence=0.99,
            round_num=1, model_version=MV, rules_version=RV,
        )
        blue_hits = [
            _make_hit("blue", 0.85, ts_offset_ms=i * 400)
            for i in range(5)
        ]
        score = engine.compute_round_score(
            [kd] + blue_hits, round_num=1, fight_id=FIGHT_ID,
            model_version=MV, rules_version=RV,
        )
        assert score.red_score  == 10
        assert score.blue_score == 0

    def test_low_confidence_hits_excluded(self):
        """Golpes con confidence < 0.75 no deben contar."""
        engine = BoxingRulesEngine()
        events = [
            _make_hit("red", confidence=0.60, ts_offset_ms=i * 400)
            for i in range(5)
        ]
        score = engine.compute_round_score(
            events, round_num=1, fight_id=FIGHT_ID,
            model_version=MV, rules_version=RV,
        )
        assert score.red_score  == 0
        assert score.blue_score == 0

    def test_empty_events_gives_zero_score(self):
        engine = BoxingRulesEngine()
        score  = engine.compute_round_score(
            [], round_num=1, fight_id=FIGHT_ID,
            model_version=MV, rules_version=RV,
        )
        assert score.red_score  == 0
        assert score.blue_score == 0
        assert score.confidence == 0.0
