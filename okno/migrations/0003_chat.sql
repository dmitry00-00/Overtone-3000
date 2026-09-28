-- Партия живёт в телеграм-чате: бот публикует туда ритм раунда.
alter table games add column chat_id bigint;
create index games_chat_idx on games (chat_id) where chat_id is not null;
