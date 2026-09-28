"""Автомат одного раунда.

Раунд — последовательность фаз с дедлайнами. Фаза завершается, когда все, от кого
ждут действия, действовали, ИЛИ истёк дедлайн — что раньше. Здесь только маршрут
по фазам и приём действий; эффекты на трек и реестр применяет Game, получая
список переходов из ``step()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from .types import (
    AporiaReason,
    VerdictVote,
    Challenge,
    Config,
    Deal,
    IllegalAction,
    MarkCode,
    Marks,
    Move,
    Phase,
    Response,
    Statement,
    Summary,
    Team,
    Verdict,
)


@dataclass(frozen=True)
class RoundContext:
    """Что раунду нужно знать о партии, чтобы решить, кого ждать."""

    config: Config
    active_teams: frozenset[Team]
    human_teams: frozenset[Team]  # команды с активными людьми: только они голосуют и судят себя
    judge_active: bool
    journalist_active: bool
    legal_moves: Callable[[Team], tuple[Move, ...]]


@dataclass(frozen=True)
class Transition:
    from_phase: Phase
    to_phase: Phase
    at: datetime
    by_timeout: bool


@dataclass
class Round:
    index: int
    deal: Deal
    opened_at: datetime
    phase: Phase = Phase.OPENING
    phase_started_at: datetime | None = None
    phase_deadline: datetime | None = None
    log: list[Transition] = field(default_factory=list)

    ready: set[Team] = field(default_factory=set)
    statements: dict[Team, Statement] = field(default_factory=dict)
    forfeits: set[Team] = field(default_factory=set)
    responses: dict[Team, Response] = field(default_factory=dict)
    challenges: dict[Team, Challenge] = field(default_factory=dict)
    verdict: Verdict | None = None
    votes: dict[Team, VerdictVote] = field(default_factory=dict)  # взаимный вердикт (judging="mutual")
    marks: dict[Team, Marks] = field(default_factory=dict)
    claim_texts: dict[Team, str] = field(default_factory=dict)  # черновики до закрытия LEDGER
    claim_rejections: dict[Team, int] = field(default_factory=dict)
    move_choice: Move | None = None
    summary: Summary | None = None

    # ----- состояние -----

    @property
    def closed(self) -> bool:
        return self.phase is Phase.CLOSED

    @property
    def is_aporia(self) -> bool:
        return self.verdict is not None and self.verdict.is_aporia

    def time_left(self, now: datetime) -> timedelta | None:
        if self.phase_deadline is None:
            return None
        return max(self.phase_deadline - now, timedelta(0))

    def _expired(self, now: datetime) -> bool:
        return self.phase_deadline is not None and now >= self.phase_deadline

    def _require_phase(self, *phases: Phase) -> None:
        if self.phase not in phases:
            raise IllegalAction(f"раунд {self.index}: фаза {self.phase}, ожидалась {'/'.join(phases)}")

    # ----- кто должен действовать в текущей фазе -----

    def teams_with_statements(self) -> frozenset[Team]:
        return frozenset(self.statements)

    def move_required(self, ctx: RoundContext) -> bool:
        """Нужен ли выбор хода победителем. При вызове ход определён правилами вызова."""
        v = self.verdict
        if v is None or v.winner is None or self.challenges:
            return False
        return len(ctx.legal_moves(v.winner)) > 1

    def pending(self, ctx: RoundContext) -> set[str]:
        """Кого ждём. Пустое множество — фаза завершена по действиям."""
        teams = ctx.active_teams
        match self.phase:
            case Phase.PREP:
                return {t.value for t in teams - self.ready}
            case Phase.STATEMENT:
                return {t.value for t in teams - set(self.statements)}
            case Phase.RESPONSE:
                acted = set(self.responses) | set(self.challenges)
                return {t.value for t in teams - acted}
            case Phase.VERDICT:
                if self.verdict is not None:
                    return set()
                match ctx.config.judging:
                    case "mutual":
                        return {t.value for t in ctx.human_teams - set(self.votes)}
                    case "self":
                        return {t.value for t in ctx.human_teams}
                    case _:
                        return {"judge"} if ctx.judge_active else set()
            case Phase.LEDGER:
                waiting = {t.value for t in (teams & self.teams_with_statements()) - set(self.claim_texts)}
                if self.move_required(ctx) and self.move_choice is None:
                    waiting.add(f"{self.verdict.winner.value}:move")
                return waiting
            case Phase.SUMMARY:
                return {"journalist"} if ctx.journalist_active and self.summary is None else set()
        return set()

    # ----- маршрут -----

    def _enter(self, phase: Phase, ctx: RoundContext, at: datetime, by_timeout: bool) -> None:
        self.log.append(Transition(self.phase, phase, at, by_timeout))
        self.phase = phase
        self.phase_started_at = at
        self.phase_deadline = at + ctx.config.phase_window(phase) if phase in ctx.config.phase_shares else None

    def _next_after(self, phase: Phase, ctx: RoundContext, now: datetime, by_timeout: bool) -> Phase:
        """Куда идти после завершения фазы. Здесь же — обработка таймаутов."""
        match phase:
            case Phase.OPENING:
                return Phase.PREP
            case Phase.PREP:
                return Phase.STATEMENT
            case Phase.STATEMENT:
                self.forfeits = set(ctx.active_teams - set(self.statements))
                if not self.statements:
                    # Обе не сдали: апория, никто не двигается, дальше делать нечего.
                    self.verdict = Verdict(None, True, AporiaReason.NO_STATEMENTS, None, now)
                    self.summary = Summary("Раунд без выступлений", "Ни одна команда не выступила.", "system", now)
                    return Phase.CLOSED
                return Phase.REVEAL
            case Phase.REVEAL:
                if len(self.statements) == 1:
                    # Одна не сдала: обмен проигран без вердикта, отметок нет ни у кого.
                    (winner,) = self.statements
                    self.verdict = Verdict(winner, False, None, None, now, by_forfeit=True)
                    return Phase.LEDGER
                return Phase.RESPONSE
            case Phase.RESPONSE:
                if ctx.config.judging == "judge" and not ctx.judge_active:
                    self.verdict = Verdict(None, True, AporiaReason.NO_VERDICT, None, now)
                    return Phase.LEDGER
                return Phase.VERDICT
            case Phase.VERDICT:
                if self.verdict is None and ctx.config.judging == "mutual":
                    self._resolve_votes(ctx, now)
                if self.verdict is None:
                    # Вердикт не вынесен в срок: апория, отметки за раунд не ставятся.
                    self.verdict = Verdict(None, True, AporiaReason.NO_VERDICT, None, now)
                    self.marks.clear()
                return Phase.LEDGER
            case Phase.LEDGER:
                return Phase.SUMMARY
            case Phase.SUMMARY:
                return Phase.CLOSED
        raise IllegalAction(f"нет перехода из {phase}")

    def step(self, ctx: RoundContext, now: datetime) -> list[Transition]:
        """Продвинуть автомат, пока есть завершённые или просроченные фазы.

        Время перехода: момент действия, для таймаута — дедлайн (а не когда автомат
        это заметил), для мгновенных фаз — момент предыдущего перехода. Так один
        поздний tick корректно проводит раунд через все просроченные окна.
        """
        before = len(self.log)
        at = now
        if self.phase is Phase.OPENING and self.phase_started_at is None:
            self.phase_started_at = at = self.opened_at
        while not self.closed:
            timed = self.phase in ctx.config.phase_shares
            complete = not self.pending(ctx)
            expired = self._expired(now)
            if timed and not complete and not expired:
                break
            by_timeout = timed and not complete and expired
            if by_timeout:
                at = self.phase_deadline
            elif timed:
                at = now
            nxt = self._next_after(self.phase, ctx, at, by_timeout)
            self._enter(nxt, ctx, at, by_timeout)
        return self.log[before:]

    # ----- действия команд -----

    def _require_active_team(self, ctx: RoundContext, team: Team) -> None:
        if team not in ctx.active_teams:
            raise IllegalAction(f"у {team} нет активных игроков")

    def mark_ready(self, ctx: RoundContext, team: Team) -> None:
        self._require_phase(Phase.PREP)
        self._require_active_team(ctx, team)
        self.ready.add(team)

    def submit_statement(self, ctx: RoundContext, team: Team, body: str, author_id: str, now: datetime) -> None:
        self._require_phase(Phase.STATEMENT)
        self._require_active_team(ctx, team)
        if not body.strip():
            raise IllegalAction("пустое выступление")
        prev = self.statements.get(team)
        self.statements[team] = Statement(
            team=team,
            body=body,
            author_id=author_id,
            submitted_at=now,
            prep_seconds=(now - self.opened_at).total_seconds(),
            edit_count=prev.edit_count + 1 if prev else 0,
        )

    def submit_response(self, ctx: RoundContext, team: Team, body: str, now: datetime) -> None:
        self._require_phase(Phase.RESPONSE)
        self._require_active_team(ctx, team)
        if team in self.challenges:
            raise IllegalAction("команда уже заявила вызов вместо реплики")
        self.responses[team] = Response(team, body, now)

    def submit_challenge(
        self, ctx: RoundContext, team: Team, claim_numbers: tuple[int, ...], argument: str, now: datetime
    ) -> None:
        """Вызов заявляется вместо реплики. Существование заявлений проверяет Game."""
        self._require_phase(Phase.RESPONSE)
        self._require_active_team(ctx, team)
        if team in self.responses:
            raise IllegalAction("команда уже сдала реплику; вызов заявляется вместо неё")
        if team in self.challenges:
            raise IllegalAction("вызов уже заявлен")
        if len(set(claim_numbers)) < 2:
            raise IllegalAction("вызов требует минимум двух разных заявлений")
        if not argument.strip():
            raise IllegalAction("вызов требует обоснования несовместимости")
        self.challenges[team] = Challenge(team, tuple(claim_numbers), argument, now)

    def submit_claim(self, ctx: RoundContext, team: Team, text: str) -> None:
        self._require_phase(Phase.LEDGER)
        self._require_active_team(ctx, team)
        if team not in self.statements:
            raise IllegalAction("команда не выступала в этом раунде — опорного заявления нет")
        words = text.split()
        if not words:
            raise IllegalAction("пустое заявление")
        if len(words) > ctx.config.claim_max_words:
            raise IllegalAction(f"заявление длиннее {ctx.config.claim_max_words} слов")
        self.claim_texts[team] = text.strip()

    def choose_move(self, ctx: RoundContext, team: Team, move: Move) -> None:
        self._require_phase(Phase.LEDGER)
        if self.verdict is None or self.verdict.winner is not team:
            raise IllegalAction("ход выбирает победитель обмена")
        if self.challenges:
            raise IllegalAction("при вызове ход определён его исходом")
        if move not in ctx.legal_moves(team):
            raise IllegalAction(f"ход {move} недоступен")
        self.move_choice = move

    # ----- взаимный вердикт (judging="mutual") -----

    def submit_vote(
        self,
        ctx: RoundContext,
        team: Team,
        winner: Team | None,
        opponent_marks: dict[MarkCode, bool],
        now: datetime,
        challenge_concede: bool | None = None,
    ) -> None:
        self._require_phase(Phase.VERDICT)
        if ctx.config.judging != "mutual":
            raise IllegalAction("голосование есть только при взаимном вердикте")
        self._require_active_team(ctx, team)
        if team in self.votes:
            raise IllegalAction("голос уже сдан")
        if set(opponent_marks) != set(MarkCode):
            raise IllegalAction("нужны все пять отметок карточки соперника")
        if team.other in self.challenges and challenge_concede is None:
            raise IllegalAction("вам предъявлен вызов: признайте или отклоните противоречие")
        self.votes[team] = VerdictVote(team, winner, dict(opponent_marks), now, challenge_concede)

    def _resolve_votes(self, ctx: RoundContext, now: datetime) -> None:
        """Свести голоса. Вызов решает ответчик; иначе совпавший победитель — вердикт,
        разошедшиеся голоса — апория несогласия. Неполные голоса оставляют verdict пустым."""
        if set(self.votes) != set(ctx.human_teams) or not self.votes:
            return
        for team, ch in self.challenges.items():
            answer = self.votes.get(team.other)
            if answer is not None and answer.challenge_concede is not None:
                ch.upheld = answer.challenge_concede
                ch.ruled_at = now
        if any(ch.upheld is not None for ch in self.challenges.values()):
            self.verdict = Verdict(None, False, None, None, now)
        else:
            winners = {v.winner for v in self.votes.values()}
            if len(winners) == 1:
                w = winners.pop()
                if w is None:
                    self.verdict = Verdict(None, True, AporiaReason.JUDGE_RULED_NOBODY, None, now)
                else:
                    self.verdict = Verdict(w, False, None, None, now)
            else:
                self.verdict = Verdict(None, True, AporiaReason.NO_CONSENSUS, None, now)
        # отметки — peer-наблюдения: голос команды отмечает карточку соперника
        for team, vote in self.votes.items():
            if team.other in self.statements:
                self.marks[team.other] = Marks(team.other, dict(vote.opponent_marks), f"peer:{team.value}")

    # ----- действия судьи -----

    def rule(
        self,
        ctx: RoundContext,
        judge_id: str,
        now: datetime,
        winner: Team | None,
        marks: dict[Team, dict[MarkCode, bool]],
        challenge_rulings: dict[Team, bool] | None = None,
        fill_seconds: float | None = None,
    ) -> None:
        """Карточка судьи: одно действие — вердикт, отметки обеим командам, решения по вызовам.

        Если заявлен вызов, исход обмена определяют его правила; winner тогда не применяется.
        """
        self._require_phase(Phase.VERDICT)
        if self.verdict is not None:
            raise IllegalAction("вердикт уже вынесен")
        rulings = challenge_rulings or {}
        missing = set(self.challenges) - set(rulings)
        if missing:
            raise IllegalAction(f"нет решения по вызову команды {', '.join(t.value for t in missing)}")
        for team in self.statements:
            if team not in marks or set(marks[team]) != set(MarkCode):
                raise IllegalAction(f"нужны все пять отметок для {team}")
        for team, upheld in rulings.items():
            ch = self.challenges[team]
            ch.upheld = upheld
            ch.ruled_at = now
        if self.challenges:
            self.verdict = Verdict(None, False, None, judge_id, now, fill_seconds=fill_seconds)
        elif winner is None:
            self.verdict = Verdict(None, True, AporiaReason.JUDGE_RULED_NOBODY, judge_id, now, fill_seconds=fill_seconds)
        else:
            if winner not in self.statements:
                raise IllegalAction("победителем названа команда без выступления")
            self.verdict = Verdict(winner, False, None, judge_id, now, fill_seconds=fill_seconds)
        self.marks = {team: Marks(team, dict(values), judge_id) for team, values in marks.items() if team in self.statements}

    def reject_claim(self, team: Team) -> None:
        """Судья отклоняет формулировку как уклончивую: команда пишет заново."""
        self._require_phase(Phase.LEDGER)
        if team not in self.claim_texts:
            raise IllegalAction("нечего отклонять — заявление не подано")
        del self.claim_texts[team]
        self.claim_rejections[team] = self.claim_rejections.get(team, 0) + 1

    # ----- действия журналиста -----

    def publish_summary(self, ctx: RoundContext, headline: str, body: str, now: datetime, author: str = "journalist") -> None:
        self._require_phase(Phase.SUMMARY)
        if self.summary is not None:
            raise IllegalAction("сводка уже опубликована")
        self.summary = Summary(headline, body, author, now)
