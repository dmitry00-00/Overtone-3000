-- Взаимные отметки дуэли пишутся с judge_id вида 'peer:team_a' — это источник отметки,
-- а не игрок. FK на players снимается; для судейских партий значение остаётся id судьи.
alter table marks drop constraint marks_judge_id_fkey;
