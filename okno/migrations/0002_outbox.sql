-- Исходящая очередь уведомлений. Пишет API и планировщик, читает бот.
-- Очередь в Postgres, а не брокер: монолит по антитребованиям промпта.

create table outbox (
    id          bigserial primary key,
    game_id     text not null references games (id),
    player_id   text references players (id),   -- null: всем участникам партии
    kind        text not null,                  -- phase_changed | your_turn | game_started | debrief | ...
    payload     jsonb not null default '{}',
    created_at  timestamptz not null default now(),
    sent_at     timestamptz
);

create index outbox_unsent_idx on outbox (created_at) where sent_at is null;
