-- ============================================================
--  FighterID Vision3D — Supabase Schema
--  fighter-id.org live streaming integration
-- ============================================================

-- Enable UUID extension (already available in Supabase)
-- create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
--  TABLE: live_session
--  Updated every ~1.5s with real-time fighter stats.
--  Supabase Realtime broadcasts changes to web subscribers.
-- ------------------------------------------------------------
create table if not exists public.live_session (
    session_id      text        primary key,
    updated_at      timestamptz not null default now(),
    round           int         not null default 1,
    phase           text        not null default 'IDLE',   -- IDLE | ROUND | REST
    elapsed_s       real        not null default 0,
    mode            text        not null default 'FIGHT',  -- FIGHT | TEST

    -- Red fighter
    red_aggr        int         not null default 0,
    red_aggr_score  real        not null default 0,
    red_evad_score  real        not null default 0,
    red_raw_score   real        not null default 0,
    red_max_spd     real        not null default 0,
    red_dodges      int         not null default 0,
    red_strikes     int         not null default 0,
    red_connected   int         not null default 0,

    -- Blue fighter
    blue_aggr       int         not null default 0,
    blue_aggr_score real        not null default 0,
    blue_evad_score real        not null default 0,
    blue_raw_score  real        not null default 0,
    blue_max_spd    real        not null default 0,
    blue_dodges     int         not null default 0,
    blue_strikes    int         not null default 0,
    blue_connected  int         not null default 0
);

-- Allow anonymous reads (public scoreboard)
alter table public.live_session enable row level security;

create policy "public read live_session"
    on public.live_session for select
    using (true);

create policy "service write live_session"
    on public.live_session for all
    using (true)
    with check (true);

-- ------------------------------------------------------------
--  TABLE: round_results
--  One row per round, inserted when a round ends.
-- ------------------------------------------------------------
create table if not exists public.round_results (
    id              bigserial   primary key,
    session_id      text        not null,
    round           int         not null,
    mode            text        not null default 'FIGHT',
    inserted_at     timestamptz not null default now(),

    -- Red fighter
    red_aggr        int         not null default 0,
    red_aggr_score  real        not null default 0,
    red_evad_score  real        not null default 0,
    red_raw_score   real        not null default 0,
    red_max_spd     real        not null default 0,
    red_dodges      int         not null default 0,
    red_strikes     int         not null default 0,
    red_connected   int         not null default 0,
    red_pts         int         not null default 10,

    -- Blue fighter
    blue_aggr       int         not null default 0,
    blue_aggr_score real        not null default 0,
    blue_evad_score real        not null default 0,
    blue_raw_score  real        not null default 0,
    blue_max_spd    real        not null default 0,
    blue_dodges     int         not null default 0,
    blue_strikes    int         not null default 0,
    blue_connected  int         not null default 0,
    blue_pts        int         not null default 10,

    -- Round winner
    winner          text        not null default 'DRAW',   -- RED | BLUE | DRAW

    unique (session_id, round)
);

alter table public.round_results enable row level security;

create policy "public read round_results"
    on public.round_results for select
    using (true);

create policy "service write round_results"
    on public.round_results for all
    using (true)
    with check (true);

-- ------------------------------------------------------------
--  REALTIME — enable broadcast for both tables
-- ------------------------------------------------------------
-- Run these in the Supabase dashboard → Table Editor → Realtime
-- or via the SQL editor:

alter publication supabase_realtime add table public.live_session;
alter publication supabase_realtime add table public.round_results;

-- ------------------------------------------------------------
--  INDEXES for performance
-- ------------------------------------------------------------
create index if not exists idx_round_results_session
    on public.round_results (session_id);

create index if not exists idx_live_session_updated
    on public.live_session (updated_at desc);
