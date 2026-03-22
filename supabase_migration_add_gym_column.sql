-- Migración: añadir columna 'gym' a fighter_profiles
-- Ejecutar en: Supabase Dashboard → SQL Editor
-- Si la columna ya existe, ADD COLUMN IF NOT EXISTS no hace nada.

ALTER TABLE public.fighter_profiles
    ADD COLUMN IF NOT EXISTS gym text;
