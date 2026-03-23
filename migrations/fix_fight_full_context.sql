-- ═══════════════════════════════════════════════════════════════════════
-- FighterID — Fix fight_full_context VIEW + Schema Normalization
-- Ejecutar en Supabase SQL Editor (Dashboard → SQL → New Query)
-- Idempotente: seguro de re-ejecutar varias veces
--
-- Problema corregido:
--   La VIEW anterior usaba f.fighter_red_id / f.fighter_blue_id, columnas
--   que no existen en la tabla fights. Las columnas reales son
--   fighter_a_id (esquina roja) y fighter_b_id (esquina azul).
--   Además referenciaba la tabla gyms (no creada) y columnas full_name,
--   record, gym_id que no existen en fighter_profiles.
--   Todo esto causaba que los nombres de peleadores aparecieran vacíos.
-- ═══════════════════════════════════════════════════════════════════════


-- ──────────────────────────────────────────────────────────────────────
-- 1. Columnas faltantes en fighter_profiles
--    Agregadas con IF NOT EXISTS — no rompe si ya existen.
-- ──────────────────────────────────────────────────────────────────────
ALTER TABLE fighter_profiles
  ADD COLUMN IF NOT EXISTS full_name      TEXT,
  ADD COLUMN IF NOT EXISTS record         TEXT    DEFAULT '0-0',
  ADD COLUMN IF NOT EXISTS wins           INT     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS losses         INT     NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS ranking_points INT     NOT NULL DEFAULT 0;


-- ──────────────────────────────────────────────────────────────────────
-- 2. Columna lifecycle en fights
--    Estados: SCHEDULED → READY → ACTIVE → FINISHED → PROCESSED
--    Controlada por el motor visión vía UPDATE fights SET lifecycle = ...
-- ──────────────────────────────────────────────────────────────────────
ALTER TABLE fights
  ADD COLUMN IF NOT EXISTS lifecycle TEXT DEFAULT 'SCHEDULED';

ALTER TABLE fights
  DROP CONSTRAINT IF EXISTS fights_lifecycle_check;

ALTER TABLE fights
  ADD CONSTRAINT fights_lifecycle_check
  CHECK (lifecycle IN ('SCHEDULED', 'READY', 'ACTIVE', 'FINISHED', 'PROCESSED'));

COMMENT ON COLUMN fights.lifecycle IS
  'Ciclo de vida controlado por el motor visión.
   SCHEDULED=programada, READY=todo listo, ACTIVE=en curso,
   FINISHED=terminada, PROCESSED=resultado+ranking actualizados.';


-- ──────────────────────────────────────────────────────────────────────
-- 3. Restricción CHECK en fights.status (normalizar valores)
-- ──────────────────────────────────────────────────────────────────────
ALTER TABLE fights
  DROP CONSTRAINT IF EXISTS fights_status_check;

ALTER TABLE fights
  ADD CONSTRAINT fights_status_check
  CHECK (status IN ('pending', 'in_progress', 'ended'));


-- ──────────────────────────────────────────────────────────────────────
-- 4. VIEW fight_full_context — CORREGIDA
--    Cambios clave respecto a la versión anterior:
--      • JOIN usa f.fighter_a_id (rojo) y f.fighter_b_id (azul)
--        en lugar de f.fighter_red_id / f.fighter_blue_id (no existen)
--      • Eliminado JOIN con gyms (tabla no creada)
--        → se usa fighter_profiles.gym (columna TEXT)
--      • COALESCE(full_name, name) para compatibilidad con ambos schemas
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW fight_full_context AS
SELECT
  f.id                                        AS fight_id,
  f.event_id,
  f.status,
  f.lifecycle,

  -- ESQUINA ROJA (fighter_a)
  fr.id                                       AS fighter_red_id,
  COALESCE(fr.full_name, fr.name)             AS fighter_red_name,
  fr.nickname                                 AS fighter_red_nickname,
  fr.record                                   AS fighter_red_record,
  fr.weight_class                             AS fighter_red_weight,
  fr.gym                                      AS fighter_red_gym,

  -- ESQUINA AZUL (fighter_b)
  fb.id                                       AS fighter_blue_id,
  COALESCE(fb.full_name, fb.name)             AS fighter_blue_name,
  fb.nickname                                 AS fighter_blue_nickname,
  fb.record                                   AS fighter_blue_record,
  fb.weight_class                             AS fighter_blue_weight,
  fb.gym                                      AS fighter_blue_gym

FROM fights f
LEFT JOIN fighter_profiles fr ON f.fighter_a_id = fr.id
LEFT JOIN fighter_profiles fb ON f.fighter_b_id = fb.id;

-- Permisos de lectura para los roles anon y authenticated
GRANT SELECT ON fight_full_context TO anon, authenticated;


-- ──────────────────────────────────────────────────────────────────────
-- 5. Tabla fight_results
--    Prerequisito para los triggers de auto-finalización y ranking.
--    Una fila por resultado de pelea (winner + loser).
-- ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fight_results (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  fight_id   UUID        NOT NULL REFERENCES fights(id),
  winner_id  UUID        NOT NULL REFERENCES fighter_profiles(id),
  loser_id   UUID        NOT NULL REFERENCES fighter_profiles(id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE fight_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read fight_results"
  ON fight_results FOR SELECT USING (true);

CREATE POLICY "service write fight_results"
  ON fight_results FOR ALL USING (true) WITH CHECK (true);


-- ──────────────────────────────────────────────────────────────────────
-- 6. Trigger: auto-finalizar pelea al insertar resultado
--    INSERT en fight_results → fights.lifecycle = 'FINISHED', status = 'ended'
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION auto_finish_fight()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  UPDATE fights
  SET lifecycle = 'FINISHED',
      status    = 'ended'
  WHERE id = NEW.fight_id;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_auto_finish ON fight_results;

CREATE TRIGGER trg_auto_finish
  AFTER INSERT ON fight_results
  FOR EACH ROW
  EXECUTE FUNCTION auto_finish_fight();


-- ──────────────────────────────────────────────────────────────────────
-- 7. Trigger: actualizar ranking automáticamente tras fight_results
--    Ganador: +1 win, +10 ranking_points
--    Perdedor: +1 loss
--    Pelea: lifecycle → 'PROCESSED'
-- ──────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_ranking_on_result()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  -- Ganador: +1 victoria, +10 puntos de ranking
  UPDATE fighter_profiles
  SET wins           = COALESCE(wins, 0)           + 1,
      ranking_points = COALESCE(ranking_points, 0) + 10
  WHERE id = NEW.winner_id;

  -- Perdedor: +1 derrota
  UPDATE fighter_profiles
  SET losses = COALESCE(losses, 0) + 1
  WHERE id = NEW.loser_id;

  -- Marcar la pelea como procesada
  UPDATE fights
  SET lifecycle = 'PROCESSED'
  WHERE id = NEW.fight_id;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_ranking_update ON fight_results;

CREATE TRIGGER trg_ranking_update
  AFTER INSERT ON fight_results
  FOR EACH ROW
  EXECUTE FUNCTION update_ranking_on_result();


-- ──────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN — ejecutar estas queries para confirmar éxito
-- ──────────────────────────────────────────────────────────────────────
-- SELECT fight_id, fighter_red_name, fighter_blue_name, status, lifecycle
--   FROM fight_full_context LIMIT 5;
--
-- SELECT fighter_red_id, fighter_blue_id, lifecycle
--   FROM fight_full_context LIMIT 5;
--
-- SELECT * FROM information_schema.triggers
--   WHERE trigger_name IN ('trg_auto_finish', 'trg_ranking_update');
