-- Sprint 3: pre-generated neighborhood noise profiles
-- Run in Supabase SQL editor after 002_match_embeddings_rpc.sql

create table if not exists profiles (
    id              uuid primary key default uuid_generate_v4(),
    neighborhood_id uuid not null references neighborhoods(id) on delete cascade,
    profile_text    text not null,
    model           text not null default 'gpt-4o-mini',
    generated_at    timestamptz not null default now()
);

create index if not exists profiles_neighborhood_idx on profiles(neighborhood_id);
create index if not exists profiles_generated_at_idx on profiles(generated_at desc);

-- Latest profile per neighborhood — read by the UI for click-to-profile
create or replace view latest_profiles as
select distinct on (neighborhood_id)
    p.id,
    p.neighborhood_id,
    p.profile_text,
    p.model,
    p.generated_at,
    n.name as neighborhood_name,
    n.slug as neighborhood_slug
from profiles p
join neighborhoods n on n.id = p.neighborhood_id
order by neighborhood_id, generated_at desc;

-- RLS
alter table profiles enable row level security;
create policy "public read profiles" on profiles for select using (true);
