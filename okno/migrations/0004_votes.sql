-- Взаимный вердикт (дуэль без судьи): голоса команд.
create table verdict_votes (
    round_id           bigint not null references rounds (id),
    team               text not null check (team in ('team_a', 'team_b')),
    winner_team        text check (winner_team in ('team_a', 'team_b')),   -- null: «не убедил никто»
    opponent_marks     jsonb not null,        -- пять отметок карточки соперника
    challenge_concede  boolean,               -- ответ на предъявленный вызов
    submitted_at       timestamptz not null,
    primary key (round_id, team)
);
