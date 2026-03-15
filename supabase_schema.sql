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

-- ============================================================
--  FIGHTER TELEMETRY — profiles, sessions, events, stats
-- ============================================================

-- ------------------------------------------------------------
--  TABLE: fighter_profiles
--  One row per registered fighter.
-- ------------------------------------------------------------
create table if not exists public.fighter_profiles (
    id              uuid        primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    name            text        not null,
    nickname        text,
    weight_class    text,
    gym             text,
    country         text,
    -- career totals (updated by finalize-fight-ai-stats)
    total_fights    int         not null default 0,
    total_strikes   int         not null default 0,
    total_jabs      int         not null default 0,
    total_hooks     int         not null default 0,
    total_power     int         not null default 0,
    accuracy        real        not null default 0   -- 0.0–1.0
);

alter table public.fighter_profiles enable row level security;
create policy "public read fighter_profiles"
    on public.fighter_profiles for select using (true);
create policy "service write fighter_profiles"
    on public.fighter_profiles for all using (true) with check (true);

-- ------------------------------------------------------------
--  TABLE: fight_telemetry_sessions
--  One row per fight. HUD creates it; vision engine connects.
-- ------------------------------------------------------------
create table if not exists public.fight_telemetry_sessions (
    id              uuid        primary key default gen_random_uuid(),
    created_at      timestamptz not null default now(),
    fight_id        text        unique,
    session_token   text        unique,
    status          text        not null default 'pending',  -- pending | active | ended
    hud_connected   boolean     not null default false,
    vision_connected boolean    not null default false,
    last_heartbeat  timestamptz,
    fighter_red_id  uuid        references public.fighter_profiles(id),
    fighter_blue_id uuid        references public.fighter_profiles(id),
    model_version   text,
    total_rounds    int         not null default 3,
    winner_corner   text,                                    -- red | blue | draw
    ended_at        timestamptz
);

alter table public.fight_telemetry_sessions enable row level security;
create policy "public read fight_telemetry_sessions"
    on public.fight_telemetry_sessions for select using (true);
create policy "service write fight_telemetry_sessions"
    on public.fight_telemetry_sessions for all using (true) with check (true);

-- ------------------------------------------------------------
--  TABLE: fight_telemetry_events
--  One row per detected strike. High-volume insert path.
-- ------------------------------------------------------------
create table if not exists public.fight_telemetry_events (
    id              bigserial   primary key,
    inserted_at     timestamptz not null default now(),
    session_id      uuid        not null references public.fight_telemetry_sessions(id),
    fighter_id      uuid        references public.fighter_profiles(id),
    fighter_corner  text        not null,   -- red | blue
    round           int         not null default 1,
    strike_type     text        not null,   -- jab | cross | hook | uppercut | body_kick | other
    event_type      text        not null default 'strike_attempted', -- strike_attempted | strike_connected
    confidence      real        not null default 0,
    timestamp_video real,                   -- seconds since fight start
    speed_ms        real,
    extension_m     real,
    face_hit        boolean     not null default false,
    body_hit        boolean     not null default false,
    elbow_angle     real,
    model_version   text
);

alter table public.fight_telemetry_events enable row level security;
create policy "public read fight_telemetry_events"
    on public.fight_telemetry_events for select using (true);
create policy "service write fight_telemetry_events"
    on public.fight_telemetry_events for all using (true) with check (true);

-- ------------------------------------------------------------
--  TABLE: fighter_statistics
--  Aggregated per-fight stats. Written by finalize-fight-ai-stats.
-- ------------------------------------------------------------
create table if not exists public.fighter_statistics (
    id              bigserial   primary key,
    inserted_at     timestamptz not null default now(),
    fighter_id      uuid        not null references public.fighter_profiles(id),
    session_id      uuid        not null references public.fight_telemetry_sessions(id),
    total_strikes   int         not null default 0,
    total_connected int         not null default 0,
    total_jabs      int         not null default 0,
    total_hooks     int         not null default 0,
    total_power     int         not null default 0,
    accuracy        real        not null default 0,
    unique (fighter_id, session_id)
);

alter table public.fighter_statistics enable row level security;
create policy "public read fighter_statistics"
    on public.fighter_statistics for select using (true);
create policy "service write fighter_statistics"
    on public.fighter_statistics for all using (true) with check (true);

-- ------------------------------------------------------------
--  REALTIME — telemetry tables
-- ------------------------------------------------------------
alter publication supabase_realtime add table public.fight_telemetry_sessions;
alter publication supabase_realtime add table public.fight_telemetry_events;

-- ------------------------------------------------------------
--  INDEXES — telemetry
-- ------------------------------------------------------------
create index if not exists idx_telemetry_sessions_status
    on public.fight_telemetry_sessions (status);
create index if not exists idx_telemetry_sessions_token
    on public.fight_telemetry_sessions (session_token);
create index if not exists idx_telemetry_events_session
    on public.fight_telemetry_events (session_id);
create index if not exists idx_telemetry_events_fighter
    on public.fight_telemetry_events (fighter_id);
create index if not exists idx_fighter_stats_fighter
    on public.fighter_statistics (fighter_id);
