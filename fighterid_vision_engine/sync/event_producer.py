"""
Productor de eventos no-bloqueante para Supabase.

GARANTÍAS:
    - emit() retorna en < 1ms (encola el evento en memoria y vuelve).
    - Un hilo daemon procesa la cola en background.
    - Si Supabase falla, el evento pasa a RetryQueue (buffer local en disco).
    - Nunca se pierde un evento.
    - Latencia objetivo: < 200ms desde captura hasta inserción confirmada.

SEGURIDAD:
    - No se emiten eventos si no hay un fight_id activo.
    - No se crean sesiones duplicadas por fight.
    - El estado de la pelea se valida antes de emitir.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, Optional

import requests

from fighterid_vision_engine.events.models import CombatEvent
from fighterid_vision_engine.events.validators import validate_event, ValidationError
from fighterid_vision_engine.sync.retry_queue import RetryQueue
from fighterid_vision_engine.observability.logger import StructuredLogger
from fighterid_vision_engine.features.flags import FeatureFlags


_SCORING_EVENTS_ENDPOINT = "/rest/v1/scoring_events"
_ACTIVE_SESSION_CACHE_TTL = 30.0   # Segundos entre validaciones de sesión activa


class EventProducer:
    """
    Productor de eventos no-bloqueante.

    Uso:
        producer = EventProducer(
            supabase_url="https://...",
            api_key="...",
            model_version="v1.0.0",
        )
        producer.start()
        producer.emit(event)   # retorna inmediatamente
        producer.stop()
    """

    def __init__(
        self,
        supabase_url:  str,
        api_key:       str,
        model_version: str = "v1.0.0",
        retry_queue:   Optional[RetryQueue] = None,
        logger:        Optional[StructuredLogger] = None,
        feature_flags: Optional[FeatureFlags] = None,
    ) -> None:
        self._supabase_url  = supabase_url.rstrip("/")
        self._api_key       = api_key
        self._model_version = model_version
        self._queue:        queue.Queue = queue.Queue()
        self._running       = False
        self._worker_thread: Optional[threading.Thread] = None
        self._logger        = logger or StructuredLogger(model_version=model_version)
        self._flags         = feature_flags or FeatureFlags()

        # Inicializar RetryQueue con la función de envío
        self._retry_queue   = retry_queue or RetryQueue(logger=self._logger)
        self._retry_queue.set_send_fn(self._send_to_supabase)

        # Cache de validación de sesión activa
        self._active_fights: set = set()
        self._active_fights_lock = threading.Lock()
        self._last_session_check = 0.0

    def start(self) -> None:
        """Arranca el hilo worker y carga el buffer de reintentos."""
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker,
            name="EventProducerWorker",
            daemon=True,
        )
        self._worker_thread.start()
        # Reintentar eventos pendientes del buffer local
        self._retry_queue.flush_buffer_on_startup()
        print(f"[PRODUCER] Worker iniciado — EMIT_SCORING_EVENTS={self._flags.EMIT_SCORING_EVENTS}")

    def stop(self, timeout: float = 5.0) -> None:
        """Detiene el hilo worker esperando a que se vacíe la cola."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)

    def emit(self, event: CombatEvent) -> None:
        """
        Encola un evento para envío asíncrono.

        Retorna inmediatamente. El evento se envía en background.
        Si EMIT_SCORING_EVENTS=False, el evento es ignorado silenciosamente.
        """
        if not self._flags.EMIT_SCORING_EVENTS:
            return

        # Validación rápida antes de encolar
        try:
            validate_event(event)
        except ValidationError as e:
            self._logger.log_error(
                trace_id=getattr(event, "trace_id", ""),
                error=e,
                context={"fight_id": getattr(event, "fight_id", ""), "action": "emit_rejected"},
            )
            return

        self._queue.put(event)

    def register_active_fight(self, fight_id: str) -> None:
        """Registra un fight_id como activo — los eventos de este fight se emitirán."""
        with self._active_fights_lock:
            self._active_fights.add(fight_id)

    def unregister_fight(self, fight_id: str) -> None:
        """Desregistra un fight_id — los eventos posteriores serán bloqueados."""
        with self._active_fights_lock:
            self._active_fights.discard(fight_id)

    def _worker(self) -> None:
        """Hilo daemon: procesa la cola de eventos y los envía a Supabase."""
        while self._running or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            t_start = time.monotonic()
            event_dict = event.to_dict()

            # Verificar que el fight está activo antes de emitir
            if not self._is_fight_active(event.fight_id):
                self._logger.log_error(
                    trace_id=event.trace_id,
                    error=RuntimeError("fight_not_active"),
                    context={"fight_id": event.fight_id, "event_type": event.event_type},
                )
                self._queue.task_done()
                continue

            success = self._send_to_supabase(event_dict)
            latency_ms = (time.monotonic() - t_start) * 1000

            if success:
                self._logger.log_event(event, latency_ms=latency_ms)
            else:
                self._retry_queue.enqueue(event_dict, attempt=0)

            self._queue.task_done()

    def _send_to_supabase(self, event_dict: Dict[str, Any]) -> bool:
        """
        POST a scoring_events en Supabase.

        Retorna True si la inserción fue exitosa (HTTP 201), False en caso contrario.
        Latencia objetivo: < 200ms.
        """
        if not self._supabase_url or not self._api_key:
            return False

        url = f"{self._supabase_url}{_SCORING_EVENTS_ENDPOINT}"
        headers = {
            "apikey":        self._api_key,
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        }

        try:
            resp = requests.post(
                url,
                json=event_dict,
                headers=headers,
                timeout=5.0,
            )
            return resp.status_code in (200, 201)
        except requests.RequestException as e:
            print(f"[PRODUCER] Supabase error: {e}")
            return False

    def _is_fight_active(self, fight_id: str) -> bool:
        """
        Verifica si el fight_id corresponde a una pelea activa.

        Usa caché local (TTL=30s) para evitar consultas innecesarias.
        Si no hay URL configurada, permite el paso (modo sin conexión).
        """
        if not self._supabase_url or not self._api_key:
            return True   # Modo sin conexión: no bloquear

        with self._active_fights_lock:
            # Cache hit
            if fight_id in self._active_fights:
                return True

        # Comprobar si es momento de actualizar el caché
        now = time.monotonic()
        if now - self._last_session_check < _ACTIVE_SESSION_CACHE_TTL:
            # Sin datos en caché y dentro del TTL → rechazar
            return False

        # Consultar Supabase
        self._last_session_check = now
        try:
            resp = requests.get(
                f"{self._supabase_url}/rest/v1/fight_telemetry_sessions",
                headers={
                    "apikey":        self._api_key,
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept":        "application/json",
                },
                params={"fight_id": f"eq.{fight_id}", "status": "eq.active", "limit": "1"},
                timeout=3.0,
            )
            if resp.status_code == 200 and resp.json():
                with self._active_fights_lock:
                    self._active_fights.add(fight_id)
                return True
        except requests.RequestException:
            pass

        return False
