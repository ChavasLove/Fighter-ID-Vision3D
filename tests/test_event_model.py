"""
Tests del modelo de eventos de combate.

Verifica:
- Inmutabilidad (frozen dataclass)
- Campos obligatorios
- Validación de esquema
- Serialización correcta
"""

import pytest

from fighterid_vision_engine.events.models import CombatEvent, EventType, RoundScore
from fighterid_vision_engine.events.factory import CombatEventFactory
from fighterid_vision_engine.events.validators import validate_event, ValidationError


FIGHT_ID      = "fight-001-test"
MODEL_VERSION = "v1.0.0"
RULES_VERSION = "v1.0.0"


class TestCombatEventImmutability:
    def test_event_is_frozen(self):
        event = CombatEventFactory.hit_detected(
            fight_id="f1", corner="red", confidence=0.9,
            hit_type="jab", target="head", impact_score=4.0,
            round_num=1, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        with pytest.raises((AttributeError, TypeError)):
            event.fight_id = "modified"  # type: ignore

    def test_metadata_is_accessible(self):
        event = CombatEventFactory.hit_detected(
            fight_id="f1", corner="blue", confidence=0.85,
            hit_type="cross", target="body", impact_score=3.5,
            round_num=2, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.metadata["hit_type"] == "cross"
        assert event.metadata["target"]   == "body"
        assert event.metadata["round"]    == 2

    def test_to_dict_is_serializable(self):
        import json
        event = CombatEventFactory.round_start(
            fight_id="f1", round_num=1,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        d = event.to_dict()
        # Debe ser JSON-serializable
        serialized = json.dumps(d)
        assert "f1" in serialized
        assert "round_start" in serialized


class TestCombatEventFactory:
    def test_hit_detected_has_required_fields(self):
        event = CombatEventFactory.hit_detected(
            fight_id=FIGHT_ID, corner="red", confidence=0.88,
            hit_type="hook", target="head", impact_score=5.2,
            round_num=3, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.fight_id   == FIGHT_ID
        assert event.corner     == "red"
        assert event.event_type == EventType.HIT_DETECTED.value
        assert event.confidence == 0.88
        assert event.id         != ""
        assert event.timestamp  != ""
        assert event.trace_id   != ""

    def test_knockdown_event(self):
        event = CombatEventFactory.knockdown(
            fight_id=FIGHT_ID, corner="red", confidence=0.99,
            round_num=5, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type == EventType.KNOCKDOWN.value
        assert event.metadata["round"] == 5

    def test_round_start_event(self):
        event = CombatEventFactory.round_start(
            fight_id=FIGHT_ID, round_num=1,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type        == EventType.ROUND_START.value
        assert event.corner            == ""
        assert event.metadata["round"] == 1
        assert event.confidence        == 1.0

    def test_round_end_event(self):
        event = CombatEventFactory.round_end(
            fight_id=FIGHT_ID, round_num=1,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type == EventType.ROUND_END.value

    def test_fighter_identified_event(self):
        event = CombatEventFactory.fighter_identified(
            fight_id=FIGHT_ID, corner="blue", fighter_id="uuid-fighter",
            confidence=0.95, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type               == EventType.FIGHTER_IDENTIFIED.value
        assert event.metadata["fighter_id"]   == "uuid-fighter"

    def test_invalid_hit_event(self):
        event = CombatEventFactory.invalid_hit(
            fight_id=FIGHT_ID, corner="red", reason="low_blow",
            confidence=0.80, round_num=2,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type          == EventType.INVALID_HIT.value
        assert event.metadata["reason"]  == "low_blow"

    def test_referee_intervention_event(self):
        event = CombatEventFactory.referee_intervention(
            fight_id=FIGHT_ID, reason="clinch", round_num=4,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        assert event.event_type         == EventType.REFEREE_INTERVENTION.value
        assert event.corner             == ""
        assert event.metadata["reason"] == "clinch"


class TestEventValidation:
    def _make_hit(self, **overrides):
        defaults = dict(
            fight_id=FIGHT_ID, corner="red", confidence=0.88,
            hit_type="jab", target="head", impact_score=4.0,
            round_num=1, model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        defaults.update(overrides)
        return CombatEventFactory.hit_detected(**defaults)

    def test_valid_event_passes(self):
        event = self._make_hit()
        validate_event(event)  # no debe lanzar

    def test_empty_fight_id_fails(self):
        event = CombatEventFactory.round_start(
            fight_id="", round_num=1,
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "fight_id"

    def test_confidence_out_of_range_fails(self):
        # Crear evento con confianza inválida directamente (bypassing factory)
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=1.5,  # inválido
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "confidence"

    def test_negative_confidence_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=-0.1,
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError):
            validate_event(event)

    def test_invalid_corner_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="green",  # inválido
            event_type=EventType.HIT_DETECTED.value,
            confidence=0.8,
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "corner"

    def test_invalid_event_type_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type="suplex",  # inválido
            confidence=0.8, metadata={},
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "event_type"

    def test_missing_metadata_fields_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=0.8, metadata={},  # faltan campos
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "metadata"

    def test_invalid_version_format_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=0.8,
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version="1.0.0",  # falta la 'v' al inicio
            rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "model_version"

    def test_invalid_timestamp_fails(self):
        event = CombatEvent(
            id="test-id", fight_id=FIGHT_ID,
            timestamp="not-a-timestamp",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=0.8,
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version=MODEL_VERSION, rules_version=RULES_VERSION,
            trace_id="trace-1",
        )
        with pytest.raises(ValidationError) as exc_info:
            validate_event(event)
        assert exc_info.value.field == "timestamp"
