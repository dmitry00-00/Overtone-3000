-- «Окно», схема БД. Производна от автомата (src/okno/engine): каждая таблица —
-- один dataclass из engine/types.py или одно поле-коллекция Game/Round.
--
-- Отступления от раздела 3 промпта помечены «+» (добавлено) и «~» (изменено).

-- ---------------------------------------------------------------- справочники колод

create table projects (
    code         text primary key,               -- П-01
    title        text not null,
    start        smallint not null check (start between 0 and 3),
    objection_1  text not null,
    objection_2  text not null
);

create table carriers (
    code     text primary key,                   -- Н-01
    title    text not null,
    benefit  text not null,
    danger   text not null
);

create table frames (
    code      text primary key,                  -- Р-1
    title     text not null,
    to_prove  text not null,
    trap      text not null
);

create table circumstances (
    code     text primary key,                   -- О-01
    event    text not null,
    changes  text not null
);

create table audiences (
    code     text primary key,                   -- Пб-1
    mood     text not null,
    accepts  text not null,
    rejects  text not null
);

-- ---------------------------------------------------------------- партия

create table games (
    id                     text primary key,
    status                 text not null check (status in ('lobby', 'in_progress', 'debrief', 'completed', 'uncounted')),
    created_at             timestamptz,          -- момент старта; null в лобби
    config_json            jsonb not null,
    ontology_version       text,                 -- версия пакета онтологии (Фаза 3)
    outcome_json           jsonb,                -- + GameOutcome, считается при входе в разбор
    technical_aporia_from  smallint,             -- + раунд, с которого партия прервана технически
    updated_at             timestamptz not null default now()
);

create table players (
    id            text primary key,              -- в Фазе 1 — tg:<tg_id>
    tg_id         bigint unique,
    display_name  text not null default ''
);

create table memberships (
    game_id     text not null references games (id),
    player_id   text not null references players (id),
    role        text not null check (role in ('team_a', 'team_b', 'judge', 'journalist')),
    joined_at   timestamptz not null default now(),
    dropped_at  timestamptz,
    primary key (game_id, player_id)
);

create index memberships_player_idx on memberships (player_id);

-- ~ track_position и серия для 0 → 1 хранятся здесь же: у команды одна фишка на партию
create table game_projects (
    game_id         text not null references games (id),
    team            text not null check (team in ('team_a', 'team_b')),
    project_code    text not null references projects (code),
    start_position  smallint not null check (start_position between 0 and 5),
    track_position  smallint not null check (track_position between 0 and 5),
    streak          smallint not null default 0,  -- + выигранных обменов подряд
    swapped         boolean not null default false,
    primary key (game_id, team)
);

-- ---------------------------------------------------------------- раунд

create table rounds (
    id                 bigserial primary key,
    game_id            text not null references games (id),
    index              smallint not null,
    circumstance_code  text not null,            -- без FK: в Фазе 2 обстоятельства генерируются
    audience_code      text not null references audiences (code),
    phase              text not null check (phase in ('opening', 'prep', 'statement', 'reveal', 'response', 'verdict', 'ledger', 'summary', 'closed')),
    phase_started_at   timestamptz,
    phase_deadline     timestamptz,
    opened_at          timestamptz not null,
    ready_teams        text[] not null default '{}',   -- + готовность в PREP
    forfeit_teams      text[] not null default '{}',   -- + кто не сдал выступление
    move_choice        text check (move_choice in ('advance', 'push_back')),  -- + выбор победителя до закрытия LEDGER
    unique (game_id, index)
);

-- + журнал переходов: время каждого перехода и был ли он по таймауту
create table round_transitions (
    round_id    bigint not null references rounds (id),
    seq         smallint not null,
    from_phase  text not null,
    to_phase    text not null,
    at          timestamptz not null,
    by_timeout  boolean not null,
    primary key (round_id, seq)
);

create table round_hands (
    round_id      bigint not null references rounds (id),
    team          text not null check (team in ('team_a', 'team_b')),
    carrier_code  text not null references carriers (code),
    frame_code    text not null references frames (code),
    primary key (round_id, team)
);

-- Полные тексты выступлений хранятся навсегда: на таблицу нет ни одного delete.
create table statements (
    round_id      bigint not null references rounds (id),
    team          text not null check (team in ('team_a', 'team_b')),
    body          text not null,
    submitted_at  timestamptz not null,
    author_id     text not null references players (id),
    edit_count    smallint not null default 0,
    prep_seconds  double precision not null,
    primary key (round_id, team)
);

create table responses (
    round_id      bigint not null references rounds (id),
    team          text not null check (team in ('team_a', 'team_b')),
    body          text not null,
    submitted_at  timestamptz not null,
    primary key (round_id, team)
);

-- ~ claim_ids → claim_numbers: заявления адресуются номером в реестре команды-соперника
create table challenges (
    round_id       bigint not null references rounds (id),
    team           text not null check (team in ('team_a', 'team_b')),   -- кто вызывает
    claim_numbers  smallint[] not null,
    argument       text not null,
    submitted_at   timestamptz not null,
    upheld         boolean,                      -- null: судья не рассмотрел
    ruled_at       timestamptz,
    primary key (round_id, team)
);

create table verdicts (
    round_id       bigint primary key references rounds (id),
    winner_team    text check (winner_team in ('team_a', 'team_b')),
    is_aporia      boolean not null,
    aporia_reason  text check (aporia_reason in ('no_statements', 'no_verdict', 'judge_ruled_nobody', 'technical')),
    judge_id       text references players (id),   -- null: вердикт системный (таймаут, форфейт)
    ruled_at       timestamptz not null,
    by_forfeit     boolean not null default false,
    fill_seconds   double precision,             -- проверка приёмки: медиана ≤ 60
    move           text check (move in ('advance', 'push_back'))
);

-- Структурные отметки. Отдельная сущность от трека: никогда не суммируются с ним.
create table marks (
    round_id     bigint not null references rounds (id),
    team         text not null check (team in ('team_a', 'team_b')),
    mark_code    text not null check (mark_code in ('opora', 'steelman', 'level', 'ledger', 'condition')),
    value        boolean not null,               -- судейская; в профиль идёт она
    draft_value  boolean,                        -- + предзаполнение ИИ (Фаза 2)
    judge_id     text not null references players (id),
    primary key (round_id, team, mark_code)
);

-- + черновик опоры внутри окна LEDGER; в реестр попадает при закрытии фазы
create table round_claim_drafts (
    round_id    bigint not null references rounds (id),
    team        text not null check (team in ('team_a', 'team_b')),
    text        text,                            -- null: отклонено судьёй, ждём новую
    rejections  smallint not null default 0,
    primary key (round_id, team)
);

create table ledger_claims (
    game_id              text not null references games (id),
    team                 text not null check (team in ('team_a', 'team_b')),
    number               smallint not null,      -- сквозной в пределах команды, не переиспользуется
    round_index          smallint not null,
    text                 text not null,
    weak                 boolean not null default false,   -- + «команда не сформулировала опору»
    retracted_at         timestamptz,
    retracted_in_round   smallint,               -- +
    challenged_in_round  smallint,               -- + засчитанный вызов, где фигурировало
    primary key (game_id, team, number)
);

create table summaries (
    round_id      bigint primary key references rounds (id),
    headline      text not null,
    body          text not null,
    author        text not null check (author in ('journalist', 'ai', 'system')),
    published_at  timestamptz not null
);

-- + события трека: проигрыш трека в разборе строится отсюда
create table track_events (
    game_id        text not null references games (id),
    seq            smallint not null,
    round_index    smallint not null,
    team           text not null check (team in ('team_a', 'team_b')),
    position_from  smallint not null,
    position_to    smallint not null,
    cause          text not null check (cause in ('exchange_won', 'pushed_back', 'challenge_upheld', 'challenge_rejected', 'retraction', 'streak_progress')),
    at             timestamptz not null,
    primary key (game_id, seq)
);

-- + плюсы прибора мимо карточки судьи (отзыв заявления → «пересмотреть под свидетельством»)
create table structural_events (
    game_id      text not null references games (id),
    seq          smallint not null,
    round_index  smallint not null,
    team         text not null check (team in ('team_a', 'team_b')),
    player_id    text not null references players (id),
    atom         text not null,
    at           timestamptz not null,
    primary key (game_id, seq)
);

-- ---------------------------------------------------------------- разбор и экспорт

-- ~ track_replay_json не хранится: проигрыш трека выводится из track_events + statements
create table debriefs (
    game_id       text primary key references games (id),
    started_at    timestamptz not null,
    deadline      timestamptz not null,
    completed_at  timestamptz                    -- пусто, пока не отметились все активные
);

create table debrief_notes (
    game_id       text not null references games (id),
    player_id     text not null references players (id),
    atom_worked   text not null,
    atom_missed   text not null,
    at            timestamptz not null,
    primary key (game_id, player_id)
);

-- Фаза 3. Создаётся сейчас, чтобы контракт был виден в схеме.
create table exports (
    id           bigserial primary key,
    game_id      text not null references games (id),
    player_id    text not null references players (id),
    operation    text not null,
    value        double precision not null,      -- theta
    se           double precision not null,      -- theta_se
    exported_at  timestamptz not null default now()
);
