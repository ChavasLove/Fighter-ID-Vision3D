"""
Cola de reintentos con buffer local para eventos de combate.

PRINCIPIO CRÍTICO: Nunca perder un evento.

Flujo:
    1. EventProducer llama enqueue() cuando Supabase falla.
    2. El evento se persiste INMEDIATAMENTE en el buffer JSONL local.
    3. Se programa un reintento con backoff exponencial (1, 2, 4, 8, 16 segundos).
    4. Si el reintento tiene éxito, el evento se elimina del buffer.
    5. Al arrancar el motor, se cargan y reintentan los eventos pendientes.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_BUFFER_PATH  = Path(os.getenv("RETRY_BUFFER_PATH", "buffer/pending_events.jsonl"))
_MAX_RETRIES  = int(os.getenv("RETRY_MAX_ATTEMPTS", "5"))
_BACKOFF_S    = [1, 2, 4, 8, 16]   # segundos de espera entre reintentos


class RetryQueue:
    """
    Buffer local de eventos con reintento automático.

    El buffer se escribe en disco antes de programar el reintento —
    esto garantiza que los eventos sobrevivan un crash del proceso.

    Thread-safe: múltiples hilos pueden llamar enqueue() simultáneamente.

    Args:
        send_fn: función que recibe un dict de evento y retorna True si tuvo éxito.
                 Se debe inyectar desde EventProducer.
        logger:  instancia opcional de StructuredLogger.
    """

    def __init__(
        self,
        send_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        logger:  Optional[Any] = None,
    ) -> None:
        self._send_fn = send_fn
        self._logger  = logger
        self._lock    = threading.Lock()
        _BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)

    def set_send_fn(self, send_fn: Callable[[Dict[str, Any]], bool]) -> None:
        """Inyecta la función de envío después de construir la cola."""
        self._send_fn = send_fn

    def enqueue(self, event_dict: Dict[str, Any], attempt: int = 0) -> None:
        """
        Persiste el evento en buffer local y programa su reintento.

        Este método es NO-BLOQUEANTE — retorna inmediatamente.
        """
        self._write_to_buffer(event_dict)
        if self._logger:
            self._logger.log_buffer_write(
                event_id=event_dict.get("id", ""),
                fight_id=event_dict.get("fight_id", ""),
                path=str(_BUFFER_PATH),
            )
        delay = _BACKOFF_S[min(attempt, len(_BACKOFF_S) - 1)]
        timer = threading.Timer(
            interval=delay,
            function=self._retry,
            args=(event_dict, attempt),
        )
        timer.daemon = True
        timer.start()

    def _retry(self, event_dict: Dict[str, Any], attempt: int) -> None:
        """Intenta reenviar el evento. Si falla y hay reintentos, vuelve a encolar."""
        if self._send_fn is None:
            return

        try:
            success = self._send_fn(event_dict)
        except Exception:
            success = False

        if success:
            self._remove_from_buffer(event_dict.get("id", ""))
            return

        next_attempt = attempt + 1
        if next_attempt < _MAX_RETRIES:
            if self._logger:
                self._logger.log_retry(
                    trace_id=event_dict.get("trace_id", ""),
                    attempt=next_attempt,
                    max_attempts=_MAX_RETRIES,
                    fight_id=event_dict.get("fight_id", ""),
                    event_id=event_dict.get("id", ""),
                )
            delay = _BACKOFF_S[min(next_attempt, len(_BACKOFF_S) - 1)]
            timer = threading.Timer(
                interval=delay,
                function=self._retry,
                args=(event_dict, next_attempt),
            )
            timer.daemon = True
            timer.start()

    def flush_buffer_on_startup(self) -> None:
        """
        Carga y reintenta todos los eventos del buffer local al arrancar.

        Llamar desde EventProducer.__init__() o al iniciar el motor.
        """
        pending = self._load_buffer()
        if pending:
            print(f"[RETRY] {len(pending)} evento(s) pendientes en buffer — reintentando...")
            for event_dict in pending:
                self.enqueue(event_dict, attempt=0)

    def _write_to_buffer(self, event_dict: Dict[str, Any]) -> None:
        """Añade el evento al archivo JSONL local de forma atómica."""
        with self._lock:
            try:
                with open(_BUFFER_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")
            except OSError as e:
                print(f"[RETRY] Error escribiendo buffer: {e}")

    def _remove_from_buffer(self, event_id: str) -> None:
        """Elimina un evento del buffer JSONL por su ID."""
        if not event_id:
            return
        with self._lock:
            try:
                if not _BUFFER_PATH.exists():
                    return
                lines = _BUFFER_PATH.read_text(encoding="utf-8").splitlines()
                kept  = [
                    line for line in lines
                    if line.strip() and json.loads(line).get("id") != event_id
                ]
                _BUFFER_PATH.write_text("\n".join(kept) + ("\n" if kept else ""),
                                         encoding="utf-8")
            except (OSError, json.JSONDecodeError) as e:
                print(f"[RETRY] Error limpiando buffer: {e}")

    def _load_buffer(self) -> List[Dict[str, Any]]:
        """Carga todos los eventos del buffer JSONL."""
        if not _BUFFER_PATH.exists():
            return []
        events = []
        try:
            for line in _BUFFER_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except OSError:
            pass
        return events

    @property
    def pending_count(self) -> int:
        """Número de eventos pendientes en el buffer local."""
        return len(self._load_buffer())
