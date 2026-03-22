-- ============================================================
--  FighterID Vision3D — Migration: create fights table
--  Ejecutar en Supabase SQL Editor (una sola vez).
--
--  Dependencias previas:
--    public.fighter_profiles  (definida en supabase_schema.sql)
--
--  Nota: event_id es uuid nullable sin FK por ahora.
--  Cuando se cree la tabla boxing_events, añadir:
--    ALTER TABLE public.fights
--        ADD CONSTRAINT fights_event_id_fkey
--        FOREIGN KEY (event_id) REFERENCES public.boxing_events(id);
-- ============================================================

-- ------------------------------------------------------------
--  TABLE: fights
--  Una fila por pelea. Creada por el motor vía vision_sync.py.
--  Arquitectura: MOTOR escribe → WEB lee.
-- ------------------------------------------------------------
create table if not exists public.fights (
    id           uuid        primary key default gen_random_uuid(),

    -- Evento de boxeo al que pertenece esta pelea.
    -- Nullable: no existe tabla boxing_events todavía.
    event_id     uuid,

    -- Peleadores — deben existir en fighter_profiles.
    fighter_a_id uuid        not null references public.fighter_profiles(id),
    fighter_b_id uuid        not null references public.fighter_profiles(id),

    -- Estado del ciclo de vida de la pelea.
    --   pending     → creada, esperando inicio
    --   in_progress → motor activo, golpes siendo enviados
    --   ended       → pelea finalizada
    status       text        not null default 'pending',

    created_at   timestamptz not null default now()
);

-- ------------------------------------------------------------
--  ROW LEVEL SECURITY
-- ------------------------------------------------------------
alter table public.fights enable row level security;

create policy "public read fights"
    on public.fights for select
    using (true);

create policy "service write fights"
    on public.fights for all
    using (true)
    with check (true);

-- ------------------------------------------------------------
--  REALTIME — el HUD y la web reciben cambios en tiempo real
-- ------------------------------------------------------------
alter publication supabase_realtime add table public.fights;

-- ------------------------------------------------------------
--  INDEXES
-- ------------------------------------------------------------
create index if not exists idx_fights_status
    on public.fights (status);

create index if not exists idx_fights_fighter_a
    on public.fights (fighter_a_id);

create index if not exists idx_fights_fighter_b
    on public.fights (fighter_b_id);

-- ------------------------------------------------------------
--  VERIFICACIÓN — confirma que la tabla fue creada correctamente
-- ------------------------------------------------------------
select column_name, data_type, column_default, is_nullable
from information_schema.columns
where table_schema = 'public'
  and table_name = 'fights'
order by ordinal_position;
