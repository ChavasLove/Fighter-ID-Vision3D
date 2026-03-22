-- ═══════════════════════════════════════════════════════════════════════
-- FighterID — Unified Fight Context View + Lifecycle + Ranking Trigger
-- Ejecutar en Supabase SQL Editor (Dashboard → SQL → New Query)
-- Idempotente: seguro de re-ejecutar varias veces
-- ═══════════════════════════════════════════════════════════════════════

-- ──────────────────────────────────────────────────────────────────────
-- 1. VIEW: fight_full_context
--    Fuente única de verdad para motor visión, frontend y HUD.
--    Usa COALESCE(full_name, name) para compatibilidad con ambos schemas.
--    JOIN LEFT para no perder peleas sin gimnasio asignado.
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW fight_full_context AS
SELECT
  f.id                                          AS fight_id,
  f.event_id,
  f.status,
  f.lifecycle,

  -- RED CORNER
  fr.id                                         AS fighter_red_id,
  COALESCE(fr.full_name, fr.name)               AS fighter_red_name,
  fr.nickname                                   AS fighter_red_nickname,
  fr.record                                     AS fighter_red_record,
  fr.weight_class                               AS fighter_red_weight,
  gr.name                                       AS fighter_red_gym,

  -- BLUE CORNER
  fb.id                                         AS fighter_blue_id,
  COALESCE(fb.full_name, fb.name)               AS fighter_blue_name,
  fb.nickname                                   AS fighter_blue_nickname,
  fb.record                                     AS fighter_blue_record,
  fb.weight_class                               AS fighter_blue_weight,
  gb.name                                       AS fighter_blue_gym

FROM fights f
LEFT JOIN fighter_profiles fr ON f.fighter_red_id  = fr.id
LEFT JOIN fighter_profiles fb ON f.fighter_blue_id = fb.id
LEFT JOIN gyms gr ON fr.gym_id = gr.id
LEFT JOIN gyms gb ON fb.gym_id = gb.id;

-- Permisos de lectura para el rol anon y authenticated
GRANT SELECT ON fight_full_context TO anon, authenticated;


-- ──────────────────────────────────────────────────────────────────────
-- 2. COLUMNA lifecycle EN fights
--    Estados: SCHEDULED → READY → ACTIVE → FINISHED → PROCESSED
--    Controlada por el motor visión (UPDATE fights SET lifecycle = ...)
--    ADD COLUMN IF NOT EXISTS es idempotente desde PG 9.6
-- ──────────────────────────────────────────────────────────────────────
ALTER TABLE fights
  ADD COLUMN IF NOT EXISTS lifecycle TEXT
  DEFAULT 'SCHEDULED'
  CHECK (lifecycle IN ('SCHEDULED', 'READY', 'ACTIVE', 'FINISHED', 'PROCESSED'));

COMMENT ON COLUMN fights.lifecycle IS
  'Estado del ciclo de vida controlado por el motor visión.
   SCHEDULED=programada, READY=todo listo, ACTIVE=en curso,
   FINISHED=terminada, PROCESSED=resultado+ranking actualizados.';


-- ──────────────────────────────────────────────────────────────────────
-- 3. TRIGGER: actualizar ranking automáticamente tras fight_results
--    Se dispara con INSERT en fight_results (winner_id / loser_id / fight_id).
--    Asume que fighter_profiles tiene: wins, losses, ranking_points.
--    Ajusta los nombres de columna si tu schema usa nombres distintos.
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_ranking_on_result()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  -- Ganador: +1 victoria, +10 puntos de ranking
  UPDATE fighter_profiles
  SET
    wins           = COALESCE(wins, 0)           + 1,
    ranking_points = COALESCE(ranking_points, 0) + 10
  WHERE id = NEW.winner_id;

  -- Perdedor: +1 derrota
  UPDATE fighter_profiles
  SET
    losses = COALESCE(losses, 0) + 1
  WHERE id = NEW.loser_id;

  -- Marcar la pelea como procesada
  UPDATE fights
  SET lifecycle = 'PROCESSED'
  WHERE id = NEW.fight_id;

  RETURN NEW;
END;
$$;

-- Eliminar trigger previo si existe (evita error de duplicado)
DROP TRIGGER IF EXISTS trg_ranking_update ON fight_results;

CREATE TRIGGER trg_ranking_update
  AFTER INSERT ON fight_results
  FOR EACH ROW
  EXECUTE FUNCTION update_ranking_on_result();


-- ──────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN — ejecutar después para confirmar
-- ──────────────────────────────────────────────────────────────────────
-- SELECT * FROM fight_full_context LIMIT 5;
-- SELECT fighter_red_id, fighter_blue_id, lifecycle FROM fights LIMIT 5;
-- SELECT * FROM information_schema.triggers WHERE trigger_name = 'trg_ranking_update';
