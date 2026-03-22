-- Migración completa: añadir todas las columnas opcionales a fighter_profiles
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- ADD COLUMN IF NOT EXISTS es idempotente — seguro re-ejecutar.

ALTER TABLE public.fighter_profiles
    ADD COLUMN IF NOT EXISTS gym          text,
    ADD COLUMN IF NOT EXISTS total_fights int  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_strikes int NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_jabs   int  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_hooks  int  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_power  int  NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS accuracy     real NOT NULL DEFAULT 0;
