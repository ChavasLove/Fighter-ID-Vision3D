"""
Motor de Reglas de Boxeo Profesional.

Transforma CombatEvents en scoring válido aplicando las reglas de la
Federación Internacional de Boxeo (IBF/WBC/WBA/WBO).

REGLAS IMPLEMENTADAS:
    1. Solo golpes con confidence >= MIN_CONFIDENCE (0.75) cuentan.
    2. Solo zonas válidas: head y body.
    3. Deduplicación: descartar golpes del mismo corner en ventana < DEDUP_WINDOW_MS (300ms).
    4. Scoring: golpe limpio = +1, golpe dominante = +2, knockdown = +10 (override del round).
    5. Knockdown: el round se adjudica automáticamente al atacante (red/blue que lanzó el KD).

FUENTE DE VERDAD: Los eventos son inmutables. Este motor SOLO PRODUCE datos —
no modifica estados globales ni accede a la base de datos directamente.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from fighterid_vision_engine.events.models import CombatEvent, EventType, RoundScore


# ── Constantes del motor de reglas ────────────────────────────────────────────
MIN_CONFIDENCE    = 0.75    # Umbral mínimo de confianza para que un golpe cuente
DEDUP_WINDOW_S    = 0.300   # Ventana de deduplicación: 300ms entre golpes del mismo corner
DOMINANT_THRESHOLD = 5.0   # impact_score >= este valor → golpe dominante (+2 pts)

POINTS = {
    "knockdown":     10,    # Override del round
    "dominant_hit":  2,
    "clean_hit":     1,
}


@dataclass
class ScoringResult:
    """Resultado de procesar un evento individual por el motor de reglas."""
    event_id:    str
    fight_id:    str
    corner:      str
    round:       int
    points:      int           # Puntos otorgados (0 si el evento fue filtrado)
    accepted:    bool          # True si el evento pasó todos los filtros
    reason:      str           # Por qué fue aceptado/rechazado
    is_knockdown: bool = False


class BoxingRulesEngine:
    """
    Motor de reglas de boxeo profesional.

    Thread-safe: puede recibir eventos desde múltiples hilos de cámara.

    Uso:
        engine = BoxingRulesEngine()
        result = engine.process_event(event)
        if result.accepted:
            # emitir a Supabase
        round_score = engine.compute_round_score(events, round_num=1)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # corner → timestamp del último golpe aceptado (para dedup)
        self._last_hit_ts: Dict[str, float] = defaultdict(float)
        # fight_id → corner con knockdown en cada round (round_num → corner)
        self._knockdowns: Dict[str, Dict[int, str]] = defaultdict(dict)

    def process_event(self, event: CombatEvent) -> ScoringResult:
        """
        Aplica las reglas de boxeo al evento.

        Retorna un ScoringResult que indica si fue aceptado, cuántos puntos
        otorga y el motivo de la decisión.
        """
        # Solo hit_detected y knockdown generan scoring
        if event.event_type not in (
            EventType.HIT_DETECTED.value,
            EventType.KNOCKDOWN.value,
        ):
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False, reason="non_scoring_event",
            )

        # Validar corner
        if event.corner not in ("red", "blue"):
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False, reason="invalid_corner",
            )

        # Knockdown: override del round, sin filtros de confianza ni zona
        if event.event_type == EventType.KNOCKDOWN.value:
            return self._process_knockdown(event)

        # Filtro 1: confianza mínima
        if event.confidence < MIN_CONFIDENCE:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False,
                reason=f"low_confidence:{event.confidence:.3f}<{MIN_CONFIDENCE}",
            )

        # Filtro 2: zona válida (head o body)
        target = event.metadata.get("target", "")
        if target not in ("head", "body"):
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False,
                reason=f"invalid_target_zone:{target}",
            )

        # Filtro 3: deduplicación temporal (< 300ms desde último golpe del mismo corner)
        duplicate_check = self._check_duplicate(event)
        if duplicate_check is not None:
            return duplicate_check

        # Determinar puntos
        impact_score = float(event.metadata.get("impact_score", 0.0))
        if impact_score >= DOMINANT_THRESHOLD:
            points = POINTS["dominant_hit"]
            reason = f"dominant_hit:impact={impact_score:.2f}"
        else:
            points = POINTS["clean_hit"]
            reason = f"clean_hit:impact={impact_score:.2f}"

        return ScoringResult(
            event_id=event.id, fight_id=event.fight_id,
            corner=event.corner, round=event.metadata.get("round", 0),
            points=points, accepted=True, reason=reason,
        )

    def _process_knockdown(self, event: CombatEvent) -> ScoringResult:
        """Procesa un evento de knockdown — override del round para el atacante."""
        round_num = int(event.metadata.get("round", 0))
        with self._lock:
            if event.fight_id not in self._knockdowns:
                self._knockdowns[event.fight_id] = {}
            self._knockdowns[event.fight_id][round_num] = event.corner

        return ScoringResult(
            event_id=event.id, fight_id=event.fight_id,
            corner=event.corner, round=round_num,
            points=POINTS["knockdown"], accepted=True,
            reason=f"knockdown:round={round_num}",
            is_knockdown=True,
        )

    def _check_duplicate(self, event: CombatEvent) -> Optional[ScoringResult]:
        """
        Verifica si el golpe es un duplicado dentro de la ventana de 300ms.

        Retorna ScoringResult de rechazo si es duplicado, None si es válido.
        Thread-safe: usa lock interno.
        """
        # Obtener timestamp desde metadata o usar 0 (sin timestamp → siempre pasa)
        event_ts = _parse_timestamp(event.timestamp)
        dedup_key = f"{event.fight_id}:{event.corner}"

        with self._lock:
            last_ts = self._last_hit_ts[dedup_key]
            delta   = event_ts - last_ts

            if last_ts > 0 and delta < DEDUP_WINDOW_S:
                return ScoringResult(
                    event_id=event.id, fight_id=event.fight_id,
                    corner=event.corner, round=event.metadata.get("round", 0),
                    points=0, accepted=False,
                    reason=f"duplicate:delta_ms={int(delta*1000)}<{int(DEDUP_WINDOW_S*1000)}",
                )

            self._last_hit_ts[dedup_key] = event_ts
            return None

    def compute_round_score(
        self,
        events: List[CombatEvent],
        round_num: int,
        fight_id: str,
        model_version: str = "v1.0.0",
        rules_version: str = "v1.0.0",
    ) -> RoundScore:
        """
        Agrega una lista de eventos y devuelve el score final del round.

        Si hubo knockdown en el round, el atacante recibe 10 puntos y el
        oponente 0, independientemente de los golpes previos.

        Los eventos pasados aquí NO modifican el estado interno de dedup —
        son procesados de forma independiente para cómputo offline/batch.
        """
        red_pts  = 0
        blue_pts = 0
        confidences: List[float] = []
        knockdown_corner: Optional[str] = None

        # Crear una instancia temporal sin estado para el cómputo batch
        _tmp = _StatelessRulesEvaluator()

        for ev in events:
            if ev.metadata.get("round") != round_num:
                continue
            result = _tmp.evaluate(ev)
            if not result.accepted:
                continue
            if result.is_knockdown:
                knockdown_corner = result.corner
            elif result.corner == "red":
                red_pts += result.points
                confidences.append(ev.confidence)
            elif result.corner == "blue":
                blue_pts += result.points
                confidences.append(ev.confidence)

        # Override por knockdown
        if knockdown_corner == "red":
            red_pts  = POINTS["knockdown"]
            blue_pts = 0
        elif knockdown_corner == "blue":
            blue_pts = POINTS["knockdown"]
            red_pts  = 0

        avg_conf = float(sum(confidences) / len(confidences)) if confidences else 0.0

        return RoundScore(
            fight_id=      fight_id,
            round=         round_num,
            red_score=     red_pts,
            blue_score=    blue_pts,
            confidence=    avg_conf,
            model_version= model_version,
            rules_version= rules_version,
        )

    def reset_dedup_state(self) -> None:
        """Limpia el estado de deduplicación — llamar al inicio de cada round."""
        with self._lock:
            self._last_hit_ts.clear()


class _StatelessRulesEvaluator:
    """
    Evaluador sin estado para cómputo batch de rounds.

    Mantiene su propio contador de dedup pero no persiste entre llamadas
    a compute_round_score.
    """

    def __init__(self) -> None:
        self._last_hit_ts: Dict[str, float] = defaultdict(float)

    def evaluate(self, event: CombatEvent) -> ScoringResult:
        if event.event_type == EventType.KNOCKDOWN.value:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=POINTS["knockdown"], accepted=True,
                reason="knockdown", is_knockdown=True,
            )

        if event.event_type != EventType.HIT_DETECTED.value:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False, reason="non_scoring_event",
            )

        if event.corner not in ("red", "blue"):
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False, reason="invalid_corner",
            )

        if event.confidence < MIN_CONFIDENCE:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False,
                reason=f"low_confidence:{event.confidence:.3f}",
            )

        target = event.metadata.get("target", "")
        if target not in ("head", "body"):
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False, reason=f"invalid_target:{target}",
            )

        event_ts  = _parse_timestamp(event.timestamp)
        dedup_key = f"{event.fight_id}:{event.corner}"
        last_ts   = self._last_hit_ts[dedup_key]
        delta     = event_ts - last_ts

        if last_ts > 0 and delta < DEDUP_WINDOW_S:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=0, accepted=False,
                reason=f"duplicate:{int(delta*1000)}ms",
            )

        self._last_hit_ts[dedup_key] = event_ts

        impact_score = float(event.metadata.get("impact_score", 0.0))
        if impact_score >= DOMINANT_THRESHOLD:
            return ScoringResult(
                event_id=event.id, fight_id=event.fight_id,
                corner=event.corner, round=event.metadata.get("round", 0),
                points=POINTS["dominant_hit"], accepted=True,
                reason=f"dominant_hit:{impact_score:.2f}",
            )
        return ScoringResult(
            event_id=event.id, fight_id=event.fight_id,
            corner=event.corner, round=event.metadata.get("round", 0),
            points=POINTS["clean_hit"], accepted=True,
            reason=f"clean_hit:{impact_score:.2f}",
        )


def _parse_timestamp(ts_str: str) -> float:
    """
    Convierte un timestamp ISO 8601 a epoch (float).
    Retorna 0.0 si el formato es inválido — el evento pasa el filtro de dedup.
    """
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0
