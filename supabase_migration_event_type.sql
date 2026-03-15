-- ============================================================
--  FighterID Vision3D — Migration: add event_type column
--  Run this in Supabase SQL Editor if you get PGRST204 error
--  "Could not find the 'event_type' column of 'fight_telemetry_events'"
-- ============================================================

-- 1) Add event_type column if it doesn't exist
ALTER TABLE public.fight_telemetry_events
    ADD COLUMN IF NOT EXISTS event_type text NOT NULL DEFAULT 'strike_attempted';

-- 2) After running, reload PostgREST schema cache in Supabase dashboard:
--    Settings → API → Reload schema
--    (or send a NOTIFY to pg_notify: SELECT pg_notify('pgrst', 'reload schema');)

-- Verify the column was added
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'fight_telemetry_events'
ORDER BY ordinal_position;
