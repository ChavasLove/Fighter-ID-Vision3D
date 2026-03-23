-- ============================================================
--  FighterID — ai_strike_events
--  Tabla canónica para escrituras del Contrato de API de Visión IA.
--  Una fila por golpe confirmado recibido del motor de visión.
--
--  Contrato del motor visión:
--    POST /ai-strike-ingest/event
--    { fight_id, corner, confidence, strike_type }
--
--  El fighter_id es resuelto server-side (Edge Function) desde corner.
--  El motor visión NUNCA envía fighter_id directamente.
--
--  Idempotente: seguro de re-ejecutar.
-- ============================================================

CREATE TABLE IF NOT EXISTS public.ai_strike_events (
    id          BIGSERIAL    PRIMARY KEY,
    -- fight_id como TEXT para compatibilidad con fight_telemetry_sessions.fight_id TEXT
    -- Si fights.id es UUID, cambiar a UUID y ajustar el FK.
    fight_id    TEXT         NOT NULL,
    session_id  UUID         REFERENCES public.fight_telemetry_sessions(id)
                                ON DELETE SET NULL,
    corner      TEXT         NOT NULL
                                CHECK (corner IN ('red', 'blue')),
    fighter_id  UUID         REFERENCES public.fighter_profiles(id)
                                ON DELETE SET NULL,
    strike_type TEXT         NOT NULL DEFAULT 'punch',
    confidence  REAL         NOT NULL DEFAULT 0,
    inserted_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ── RLS ──────────────────────────────────────────────────────────────────────

ALTER TABLE public.ai_strike_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read ai_strike_events"
    ON public.ai_strike_events FOR SELECT
    USING (true);

CREATE POLICY "service write ai_strike_events"
    ON public.ai_strike_events FOR ALL
    USING (true)
    WITH CHECK (true);

-- ── Índices de rendimiento ────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_ai_strike_events_fight_id
    ON public.ai_strike_events (fight_id);

CREATE INDEX IF NOT EXISTS idx_ai_strike_events_session_id
    ON public.ai_strike_events (session_id);

CREATE INDEX IF NOT EXISTS idx_ai_strike_events_inserted_at
    ON public.ai_strike_events (inserted_at DESC);

-- ── Realtime (opcional — habilita dashboards en vivo) ─────────────────────────
-- Descomentar para activar Realtime en esta tabla:
-- ALTER PUBLICATION supabase_realtime ADD TABLE public.ai_strike_events;

-- ── Verificación ─────────────────────────────────────────────────────────────
-- Ejecutar después de aplicar para confirmar:
-- SELECT table_name, column_name, data_type
--   FROM information_schema.columns
--   WHERE table_name = 'ai_strike_events'
--   ORDER BY ordinal_position;
