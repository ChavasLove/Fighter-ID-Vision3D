-- ─────────────────────────────────────────────────────────────────────────────
-- MIGRACIÓN: scoring_events
-- Tabla canónica de eventos atómicos de combate.
--
-- PRINCIPIO: Esta tabla es la FUENTE DE VERDAD del motor de visión.
-- - El motor inserta aquí TODOS los eventos crudos detectados.
-- - fight_results se computa SOLO desde esta tabla (via trigger/edge function).
-- - Los registros son inmutables (no hay UPDATE — solo INSERT).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scoring_events (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fight_id      TEXT        NOT NULL,
    timestamp     TIMESTAMPTZ NOT NULL,
    corner        TEXT        CHECK (corner IN ('red', 'blue', '')),
    event_type    TEXT        NOT NULL CHECK (event_type IN (
                                  'hit_detected',
                                  'knockdown',
                                  'round_start',
                                  'round_end',
                                  'fighter_identified',
                                  'invalid_hit',
                                  'referee_intervention'
                              )),
    confidence    FLOAT       CHECK (confidence BETWEEN 0.0 AND 1.0),
    metadata      JSONB       NOT NULL DEFAULT '{}',
    model_version TEXT        NOT NULL,
    rules_version TEXT        NOT NULL,
    trace_id      TEXT,
    source        TEXT        NOT NULL DEFAULT 'vision_engine',
    latency_ms    FLOAT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices de performance
CREATE INDEX IF NOT EXISTS idx_scoring_events_fight_id
    ON scoring_events(fight_id);

CREATE INDEX IF NOT EXISTS idx_scoring_events_timestamp
    ON scoring_events(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_scoring_events_event_type
    ON scoring_events(event_type);

CREATE INDEX IF NOT EXISTS idx_scoring_events_fight_round
    ON scoring_events(fight_id, (metadata->>'round'));

-- Row Level Security
ALTER TABLE scoring_events ENABLE ROW LEVEL SECURITY;

-- Lectura pública (transparencia del scoreboard)
CREATE POLICY "scoring_events_read_public"
    ON scoring_events FOR SELECT
    USING (true);

-- Escritura solo para service role (motor de visión)
CREATE POLICY "scoring_events_insert_service"
    ON scoring_events FOR INSERT
    WITH CHECK (true);

-- Habilitar Realtime para que el dashboard reciba eventos en tiempo real
ALTER PUBLICATION supabase_realtime ADD TABLE scoring_events;

COMMENT ON TABLE scoring_events IS
    'Eventos atómicos de combate emitidos por el motor de visión FighterID. '
    'Fuente de verdad del sistema. Inmutables tras su inserción.';
