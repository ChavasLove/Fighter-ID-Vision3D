-- ─────────────────────────────────────────────────────────────────────────────
-- MIGRACIÓN: fight_results
-- Resultados de scoring por round, computados EXCLUSIVAMENTE desde scoring_events.
--
-- REGLA CRÍTICA:
--   - El motor de visión NUNCA escribe en esta tabla directamente.
--   - Los registros se crean/actualizan automáticamente via trigger
--     después de cada INSERT en scoring_events.
--   - Un par (fight_id, round) es único — no puede haber duplicados.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS fight_results (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    fight_id      TEXT        NOT NULL,
    round         INTEGER     NOT NULL CHECK (round >= 1),
    red_score     INTEGER     NOT NULL DEFAULT 0 CHECK (red_score >= 0),
    blue_score    INTEGER     NOT NULL DEFAULT 0 CHECK (blue_score >= 0),
    confidence    FLOAT       CHECK (confidence BETWEEN 0.0 AND 1.0),
    model_version TEXT,
    rules_version TEXT,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(fight_id, round)
);

CREATE INDEX IF NOT EXISTS idx_fight_results_fight_id
    ON fight_results(fight_id);

CREATE INDEX IF NOT EXISTS idx_fight_results_computed_at
    ON fight_results(computed_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- TRIGGER: Recomputar fight_results después de cada INSERT en scoring_events
-- Solo se ejecuta para hit_detected y knockdown (eventos que impactan el score).
-- ─────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION recompute_fight_results()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_round       INTEGER;
    v_fight_id    TEXT;
    v_red_score   INTEGER := 0;
    v_blue_score  INTEGER := 0;
    v_avg_conf    FLOAT   := 0.0;
    v_model_ver   TEXT;
    v_rules_ver   TEXT;
    v_knockdown   RECORD;
    v_kd_corner   TEXT    := NULL;
BEGIN
    v_fight_id  := NEW.fight_id;
    v_round     := (NEW.metadata->>'round')::INTEGER;

    -- Si el round no es un entero válido, no hacer nada
    IF v_round IS NULL OR v_round < 1 THEN
        RETURN NEW;
    END IF;

    -- Verificar si hubo knockdown en este round (tiene prioridad sobre todo)
    SELECT corner INTO v_kd_corner
    FROM scoring_events
    WHERE fight_id   = v_fight_id
      AND event_type = 'knockdown'
      AND (metadata->>'round')::INTEGER = v_round
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_kd_corner IS NOT NULL THEN
        -- Knockdown: el atacante obtiene 10 puntos, el oponente 0
        v_red_score  := CASE WHEN v_kd_corner = 'red'  THEN 10 ELSE 0 END;
        v_blue_score := CASE WHEN v_kd_corner = 'blue' THEN 10 ELSE 0 END;
        v_avg_conf   := 1.0;
    ELSE
        -- Sumar golpes válidos (confidence >= 0.75, target = head o body)
        SELECT
            COALESCE(SUM(CASE WHEN corner = 'red' THEN
                CASE WHEN (metadata->>'impact_score')::FLOAT >= 5.0 THEN 2 ELSE 1 END
            ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN corner = 'blue' THEN
                CASE WHEN (metadata->>'impact_score')::FLOAT >= 5.0 THEN 2 ELSE 1 END
            ELSE 0 END), 0),
            COALESCE(AVG(confidence), 0.0)
        INTO v_red_score, v_blue_score, v_avg_conf
        FROM scoring_events
        WHERE fight_id   = v_fight_id
          AND event_type = 'hit_detected'
          AND (metadata->>'round')::INTEGER = v_round
          AND confidence >= 0.75
          AND metadata->>'target' IN ('head', 'body');
    END IF;

    -- Obtener versiones del evento más reciente
    SELECT model_version, rules_version
    INTO v_model_ver, v_rules_ver
    FROM scoring_events
    WHERE fight_id = v_fight_id
      AND (metadata->>'round')::INTEGER = v_round
    ORDER BY created_at DESC
    LIMIT 1;

    -- UPSERT: insertar o actualizar el resultado del round
    INSERT INTO fight_results (
        fight_id, round, red_score, blue_score,
        confidence, model_version, rules_version, computed_at
    )
    VALUES (
        v_fight_id, v_round, v_red_score, v_blue_score,
        v_avg_conf, v_model_ver, v_rules_ver, NOW()
    )
    ON CONFLICT (fight_id, round)
    DO UPDATE SET
        red_score     = EXCLUDED.red_score,
        blue_score    = EXCLUDED.blue_score,
        confidence    = EXCLUDED.confidence,
        model_version = EXCLUDED.model_version,
        rules_version = EXCLUDED.rules_version,
        computed_at   = NOW();

    RETURN NEW;
END;
$$;

-- El trigger se activa solo para eventos que afectan el score
CREATE TRIGGER trigger_recompute_fight_results
    AFTER INSERT ON scoring_events
    FOR EACH ROW
    WHEN (NEW.event_type IN ('hit_detected', 'knockdown'))
    EXECUTE FUNCTION recompute_fight_results();

-- Row Level Security
ALTER TABLE fight_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "fight_results_read_public"
    ON fight_results FOR SELECT
    USING (true);

-- Solo service role puede modificar (via trigger)
CREATE POLICY "fight_results_write_service"
    ON fight_results FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');

-- Habilitar Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE fight_results;

COMMENT ON TABLE fight_results IS
    'Resultados de scoring por round, computados automáticamente desde scoring_events. '
    'El motor de visión NO escribe aquí directamente.';
