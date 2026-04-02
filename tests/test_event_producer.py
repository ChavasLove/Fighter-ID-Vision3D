"""
Tests del EventProducer y RetryQueue.

Verifica:
- emit() es no-bloqueante
- Validación falla silenciosamente (no lanza excepción)
- Buffer local se escribe cuando Supabase falla
- Retry queue reintenta con backoff
"""

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fighterid_vision_engine.events.factory import CombatEventFactory
from fighterid_vision_engine.sync.retry_queue import RetryQueue
from fighterid_vision_engine.sync.event_producer import EventProducer
from fighterid_vision_engine.features.flags import FeatureFlags

FIGHT_ID = "fight-producer-test"
MV = "v1.0.0"
RV = "v1.0.0"


def _make_hit(corner="red"):
    return CombatEventFactory.hit_detected(
        fight_id=FIGHT_ID, corner=corner, confidence=0.90,
        hit_type="jab", target="head", impact_score=4.0,
        round_num=1, model_version=MV, rules_version=RV,
    )


class TestRetryQueue:
    def test_enqueue_writes_to_buffer(self, tmp_path):
        buffer_file = tmp_path / "test_buffer.jsonl"
        with patch.dict(os.environ, {"RETRY_BUFFER_PATH": str(buffer_file)}):
            # Importar módulo de nuevo para que tome la nueva ruta
            from importlib import reload
            import fighterid_vision_engine.sync.retry_queue as rq_module
            reload(rq_module)

            queue = rq_module.RetryQueue(send_fn=lambda e: False)
            event = _make_hit()
            queue.enqueue(event.to_dict(), attempt=0)

            time.sleep(0.1)  # dar tiempo al write
            assert buffer_file.exists()
            content = buffer_file.read_text()
            assert FIGHT_ID in content

    def test_successful_send_removes_from_buffer(self, tmp_path):
        buffer_file = tmp_path / "test_buffer.jsonl"
        with patch.dict(os.environ, {"RETRY_BUFFER_PATH": str(buffer_file)}):
            from importlib import reload
            import fighterid_vision_engine.sync.retry_queue as rq_module
            reload(rq_module)

            event_dict = _make_hit().to_dict()
            sent_events = []

            def mock_send(e):
                sent_events.append(e)
                return True  # éxito en el reintento

            queue = rq_module.RetryQueue(send_fn=mock_send)
            queue.enqueue(event_dict, attempt=0)
            time.sleep(1.5)  # esperar al primer reintento (1s backoff)

            assert len(sent_events) == 1
            # El buffer debe estar vacío (evento eliminado)
            content = buffer_file.read_text() if buffer_file.exists() else ""
            assert event_dict["id"] not in content

    def test_pending_count_reflects_buffer(self, tmp_path):
        buffer_file = tmp_path / "test_buffer.jsonl"
        with patch.dict(os.environ, {"RETRY_BUFFER_PATH": str(buffer_file)}):
            from importlib import reload
            import fighterid_vision_engine.sync.retry_queue as rq_module
            reload(rq_module)

            queue = rq_module.RetryQueue(send_fn=lambda e: False)
            assert queue.pending_count == 0


class TestEventProducer:
    def _make_producer(self, send_fn=None):
        """Crea un EventProducer con send_fn mockeada."""
        flags = FeatureFlags()
        flags.EMIT_SCORING_EVENTS = True
        producer = EventProducer(
            supabase_url="http://localhost",
            api_key="test-key",
            model_version=MV,
            feature_flags=flags,
        )
        if send_fn:
            producer._send_to_supabase = send_fn
        # Bypass validación de fight activo para tests
        producer._is_fight_active = lambda fid: True
        return producer

    def test_emit_is_nonblocking(self):
        """emit() debe retornar en < 10ms."""
        sent = []
        producer = self._make_producer(send_fn=lambda e: sent.append(e) or True)
        producer.start()
        producer.register_active_fight(FIGHT_ID)

        event = _make_hit()
        t0 = time.monotonic()
        producer.emit(event)
        elapsed_ms = (time.monotonic() - t0) * 1000

        producer.stop(timeout=1.0)
        assert elapsed_ms < 10, f"emit() tardó {elapsed_ms:.1f}ms — debe ser < 10ms"

    def test_emit_sends_event_to_supabase(self):
        """Verificar que el evento llega a la función de envío."""
        sent = []
        producer = self._make_producer(send_fn=lambda e: sent.append(e) or True)
        producer.start()
        producer.register_active_fight(FIGHT_ID)

        event = _make_hit()
        producer.emit(event)
        producer.stop(timeout=2.0)

        assert len(sent) == 1
        assert sent[0]["fight_id"] == FIGHT_ID

    def test_failed_send_goes_to_retry_queue(self, tmp_path):
        """Cuando Supabase falla, el evento debe ir al buffer local."""
        buffer_file = tmp_path / "retry_test.jsonl"
        with patch.dict(os.environ, {"RETRY_BUFFER_PATH": str(buffer_file)}):
            from importlib import reload
            import fighterid_vision_engine.sync.retry_queue as rq_module
            reload(rq_module)

            from fighterid_vision_engine.sync.retry_queue import RetryQueue as RQ
            retry_q = RQ(send_fn=lambda e: False)  # siempre falla

            flags = FeatureFlags()
            flags.EMIT_SCORING_EVENTS = True
            producer = EventProducer(
                supabase_url="http://localhost",
                api_key="test-key",
                model_version=MV,
                feature_flags=flags,
                retry_queue=retry_q,
            )
            producer._send_to_supabase = lambda e: False  # fallo
            producer._is_fight_active  = lambda fid: True
            producer.start()
            producer.register_active_fight(FIGHT_ID)

            event = _make_hit()
            producer.emit(event)
            producer.stop(timeout=2.0)

            # Buffer debe contener el evento
            time.sleep(0.3)
            assert buffer_file.exists()
            content = buffer_file.read_text()
            assert FIGHT_ID in content

    def test_invalid_event_not_emitted(self):
        """Un evento con fight_id vacío no debe llegar al backend."""
        from fighterid_vision_engine.events.models import CombatEvent, EventType
        import uuid
        sent = []
        producer = self._make_producer(send_fn=lambda e: sent.append(e) or True)
        producer.start()
        producer.register_active_fight(FIGHT_ID)

        # Evento inválido — fight_id vacío
        bad_event = CombatEvent(
            id=str(uuid.uuid4()), fight_id="",  # inválido
            timestamp="2024-01-01T00:00:00+00:00",
            corner="red", event_type=EventType.HIT_DETECTED.value,
            confidence=0.8,
            metadata={"hit_type": "jab", "target": "head", "impact_score": 1.0, "round": 1},
            model_version=MV, rules_version=RV,
            trace_id=str(uuid.uuid4()),
        )
        producer.emit(bad_event)
        producer.stop(timeout=1.0)

        assert len(sent) == 0

    def test_feature_flag_off_suppresses_emit(self):
        """Con FF_EMIT_SCORING_EVENTS=False, ningún evento debe llegar al backend."""
        sent = []
        flags = FeatureFlags()
        flags.EMIT_SCORING_EVENTS = False
        producer = EventProducer(
            supabase_url="http://localhost", api_key="key",
            model_version=MV, feature_flags=flags,
        )
        producer._send_to_supabase = lambda e: sent.append(e) or True
        producer._is_fight_active  = lambda fid: True
        producer.start()
        producer.register_active_fight(FIGHT_ID)

        producer.emit(_make_hit())
        producer.stop(timeout=1.0)

        assert len(sent) == 0
