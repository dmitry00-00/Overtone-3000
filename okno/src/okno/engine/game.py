"""Партия: состав, раунды, трек, реестр, разбор.

Game принимает действия игроков, продвигает автомат текущего раунда и применяет
эффекты переходов к треку и реестру. Все методы принимают ``now`` явно —
часов внутри нет, поэтому любой сценарий воспроизводим скриптом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from .round import Round, RoundContext, Transition
from .track import Track
from .types import (
    AporiaReason,
    Config,
    Deal,
    DebriefNote,
    GameOutcome,
    GameStatus,
    IllegalAction,
    LedgerClaim,
    MarkCode,
    Move,
    Phase,
    Player,
    Role,
    StructuralEvent,
    Summary,
    Team,
    TrackCause,
    Verdict,
)

RETRACTION_ATOM = "revise_under_evidence"  # «Пересмотреть под свидетельством»


class Dealer(Protocol):
    """Источник карт. В Фазе 0 — колоды из реестра; в Фазе 2 обстоятельства генерирует ИИ."""

    def deal_projects(self) -> dict[Team, tuple[str, int]]:
        """team -> (код проекта, стартовая позиция)."""
        ...

    def deal_round(self, index: int) -> Deal: ...


SummaryFallback = Callable[[Round], tuple[str, str]]


def system_summary(rnd: Round) -> tuple[str, str]:
    """Заглушка на месте ИИ-журналиста (Фаза 2). Ничего не искажает — просто фиксирует факт."""
    return ("Сводка не опубликована", f"Раунд {rnd.index}: журналист не опубликовал сводку в срок.")


@dataclass
class Game:
    id: str
    config: Config
    dealer: Dealer
    summary_fallback: SummaryFallback = system_summary
    status: GameStatus = GameStatus.LOBBY
    created_at: datetime | None = None
    players: dict[str, Player] = field(default_factory=dict)
    projects: dict[Team, str] = field(default_factory=dict)
    project_swapped: set[Team] = field(default_factory=set)
    track: Track = field(default_factory=Track)
    rounds: list[Round] = field(default_factory=list)
    ledger: list[LedgerClaim] = field(default_factory=list)
    structural: list[StructuralEvent] = field(default_factory=list)
    debrief_started_at: datetime | None = None
    debrief_deadline: datetime | None = None
    debrief_notes: dict[str, DebriefNote] = field(default_factory=dict)
    debrief_completed_at: datetime | None = None
    outcome: GameOutcome | None = None
    technical_aporia_from: int | None = None

    def __post_init__(self) -> None:
        self.track = Track(size=self.config.track_size)

    # ------------------------------------------------------------------ состав

    def join(self, player_id: str, role: Role, display_name: str = "") -> None:
        if self.status is not GameStatus.LOBBY:
            raise IllegalAction("состав меняется только до старта")
        if role in (Role.JUDGE, Role.JOURNALIST) and any(p.role is role for p in self.players.values()):
            raise IllegalAction(f"роль {role} уже занята")
        self.players[player_id] = Player(player_id, role, display_name)

    def drop_player(self, player_id: str, now: datetime) -> None:
        """Игрок выбыл. Команда продолжает в меньшем составе; при нуле активных — техническая апория."""
        p = self._player(player_id)
        if not p.active:
            return
        p.dropped_at = now
        if self.status is GameStatus.IN_PROGRESS:
            team = p.role.team
            if team is not None and not self.active_players(team):
                self._technical_aporia(now)
            else:
                self._advance(now)
        elif self.status is GameStatus.DEBRIEF:
            self._check_debrief_complete(now)

    def active_players(self, team: Team | None = None) -> list[Player]:
        return [p for p in self.players.values() if p.active and (team is None or p.role.team is team)]

    def _player(self, player_id: str) -> Player:
        try:
            return self.players[player_id]
        except KeyError:
            raise IllegalAction(f"игрок {player_id} не в партии") from None

    def _role_holder(self, role: Role) -> Player | None:
        return next((p for p in self.players.values() if p.role is role and p.active), None)

    def _require_team_member(self, player_id: str, team: Team) -> Player:
        p = self._player(player_id)
        if not p.active or p.role.team is not team:
            raise IllegalAction(f"{player_id} не активный игрок {team}")
        return p

    def _require_judge(self, player_id: str) -> Player:
        p = self._player(player_id)
        if not p.active or p.role is not Role.JUDGE:
            raise IllegalAction(f"{player_id} не судья")
        return p

    # ------------------------------------------------------------------ старт

    def start(self, now: datetime) -> None:
        if self.status is not GameStatus.LOBBY:
            raise IllegalAction("партия уже начата")
        for team in Team:
            if not self.active_players(team):
                raise IllegalAction(f"в {team} нет игроков")
        if self._role_holder(Role.JUDGE) is None:
            raise IllegalAction("нет судьи")
        self.created_at = now
        if not self.projects:
            self.draw_projects()
        self.status = GameStatus.IN_PROGRESS
        self._open_round(now)
        self._advance(now)

    def draw_projects(self) -> None:
        for team, (code, start) in self.dealer.deal_projects().items():
            self.projects[team] = code
            self.track.set_start(team, start)

    def swap_project(self, team: Team) -> None:
        """Один обмен карты проекта до первого раунда. Повторно нельзя."""
        if self.status is not GameStatus.LOBBY:
            raise IllegalAction("обмен проекта возможен только до старта")
        if team in self.project_swapped:
            raise IllegalAction("обмен уже использован")
        if not self.projects:
            self.draw_projects()
        code, start = self.dealer.deal_projects()[team]
        self.projects[team] = code
        self.track.set_start(team, start)
        self.project_swapped.add(team)

    # ------------------------------------------------------------------ раунды

    @property
    def round(self) -> Round:
        if not self.rounds or self.status is not GameStatus.IN_PROGRESS:
            raise IllegalAction("нет текущего раунда")
        return self.rounds[-1]

    def _ctx(self) -> RoundContext:
        return RoundContext(
            config=self.config,
            active_teams=frozenset(t for t in Team if self.active_players(t)),
            judge_active=self._role_holder(Role.JUDGE) is not None,
            journalist_active=self._role_holder(Role.JOURNALIST) is not None,
            legal_moves=self.track.legal_moves,
        )

    def _open_round(self, at: datetime) -> None:
        index = len(self.rounds) + 1
        self.rounds.append(Round(index=index, deal=self.dealer.deal_round(index), opened_at=at))

    def tick(self, now: datetime) -> None:
        """Продвинуть время. Единственный источник таймаутов."""
        if self.status is GameStatus.IN_PROGRESS:
            self._advance(now)
        if self.status is GameStatus.DEBRIEF and self.debrief_deadline and now >= self.debrief_deadline:
            self.status = GameStatus.UNCOUNTED

    def _advance(self, now: datetime) -> None:
        """Прогнать автомат до состояния, в котором кого-то ждут. Один поздний tick
        проводит через любое число просроченных фаз и раундов."""
        while self.status is GameStatus.IN_PROGRESS:
            rnd = self.rounds[-1]
            for tr in rnd.step(self._ctx(), now):
                self._apply(rnd, tr)
            if not rnd.closed:
                break
            self._after_round(rnd.log[-1].at)

    def _apply(self, rnd: Round, tr: Transition) -> None:
        """Эффекты переходов на трек и реестр. Маршрут решает Round, последствия — здесь."""
        now = tr.at
        if tr.to_phase is Phase.LEDGER:
            self._resolve_exchange(rnd, now)
        elif tr.from_phase is Phase.LEDGER:
            self._close_ledger(rnd, now)
        elif tr.to_phase is Phase.CLOSED:
            if tr.from_phase is Phase.STATEMENT:
                self.track.record_exchange(None)
            if rnd.summary is None:
                headline, body = self.summary_fallback(rnd)
                rnd.summary = Summary(headline, body, "ai", now)

    def _resolve_exchange(self, rnd: Round, now: datetime) -> None:
        """Итог обмена: серии, вызовы. Ход победителя без вызова применяется при закрытии реестра."""
        v = rnd.verdict
        assert v is not None
        if not rnd.challenges:
            self.track.record_exchange(v.winner)
            return
        # Вызов вместо реплики: исход обмена определяют правила вызова, вердикт «кто убедил» не применяется.
        won: set[Team] = set()
        for team in Team:
            ch = rnd.challenges.get(team)
            if ch is None or ch.upheld is None:
                continue
            won.add(team if ch.upheld else team.other)
        for team in Team:
            self.track.streak[team] = self.track.streak[team] + 1 if team in won else 0
        for team in Team:
            ch = rnd.challenges.get(team)
            if ch is None or ch.upheld is None:
                continue
            if ch.upheld:
                # соперник не двигается и откатывается; вызывающий получает шаг
                self.track.push_back(team.other, rnd.index, now, TrackCause.CHALLENGE_UPHELD)
                self.track.advance(team, rnd.index, now, TrackCause.CHALLENGE_UPHELD)
                for claim in self._claims(team.other, ch.claim_numbers):
                    claim.challenged_in_round = rnd.index
            else:
                # вызывающий теряет ход, соперник получает шаг бесплатно
                self.track.advance(team.other, rnd.index, now, TrackCause.CHALLENGE_REJECTED)

    def _close_ledger(self, rnd: Round, now: datetime) -> None:
        ctx = self._ctx()
        for team in Team:
            if team not in rnd.statements or team not in ctx.active_teams:
                continue
            text = rnd.claim_texts.get(team)
            weak = text is None
            self.ledger.append(
                LedgerClaim(
                    team=team,
                    round_index=rnd.index,
                    number=self._next_claim_number(team),
                    text=text if text is not None else "команда не сформулировала опору",
                    weak=weak,
                )
            )
        v = rnd.verdict
        if v is not None and v.winner is not None and not rnd.challenges:
            move = rnd.move_choice or self.track.default_move(v.winner)
            v.move = move
            if move is not None:
                self.track.apply_move(v.winner, move, rnd.index, now)

    def _after_round(self, now: datetime) -> None:
        norm = self.track.reached_norm() if self.config.end_on_norm else None
        if len(self.rounds) >= self.config.rounds or norm is not None:
            self._enter_debrief(now)
        else:
            self._open_round(now)

    def _technical_aporia(self, now: datetime) -> None:
        """У команды не осталось игроков: текущий раунд закрывается как есть, партия уходит в разбор.

        Уже вынесенный вердикт остаётся; если раунд стоял в LEDGER, реестр закрывается
        штатно (ход победителя, опоры). Без вердикта раунд получает апорию TECHNICAL.
        """
        rnd = self.rounds[-1]
        self.technical_aporia_from = rnd.index
        if not rnd.closed:
            if rnd.verdict is None:
                rnd.verdict = Verdict(None, True, AporiaReason.TECHNICAL, None, now)
                self.track.record_exchange(None)
            elif rnd.phase is Phase.LEDGER:
                self._close_ledger(rnd, now)
            if rnd.summary is None:
                rnd.summary = Summary("Партия прервана", "У одной из команд не осталось активных игроков.", "system", now)
            rnd.log.append(Transition(rnd.phase, Phase.CLOSED, now, False))
            rnd.phase = Phase.CLOSED
            rnd.phase_started_at = now
            rnd.phase_deadline = None
        self._enter_debrief(now)

    # ------------------------------------------------------------------ действия команд

    def mark_ready(self, player_id: str, team: Team, now: datetime) -> None:
        self._require_team_member(player_id, team)
        self.round.mark_ready(self._ctx(), team)
        self._advance(now)

    def submit_statement(self, player_id: str, team: Team, body: str, now: datetime) -> None:
        self._require_team_member(player_id, team)
        self.round.submit_statement(self._ctx(), team, body, player_id, now)
        self._advance(now)

    def submit_response(self, player_id: str, team: Team, body: str, now: datetime) -> None:
        self._require_team_member(player_id, team)
        self.round.submit_response(self._ctx(), team, body, now)
        self._advance(now)

    def submit_challenge(self, player_id: str, team: Team, claim_numbers: tuple[int, ...], argument: str, now: datetime) -> None:
        self._require_team_member(player_id, team)
        for claim in self._claims(team.other, claim_numbers):
            if claim.retracted:
                raise IllegalAction(f"заявление {claim.number} отозвано — вызов на него невозможен")
        self.round.submit_challenge(self._ctx(), team, claim_numbers, argument, now)
        self._advance(now)

    def submit_claim(self, player_id: str, team: Team, text: str, now: datetime) -> None:
        self._require_team_member(player_id, team)
        self.round.submit_claim(self._ctx(), team, text)
        self._advance(now)

    def choose_move(self, player_id: str, team: Team, move: Move, now: datetime) -> None:
        self._require_team_member(player_id, team)
        self.round.choose_move(self._ctx(), team, move)
        self._advance(now)

    def retract_claim(self, player_id: str, team: Team, number: int, now: datetime) -> None:
        """Отзыв заявления: публично, стоит шага назад, в структурном счёте — плюс."""
        if self.status is not GameStatus.IN_PROGRESS:
            raise IllegalAction("отзыв возможен только во время партии")
        self._require_team_member(player_id, team)
        (claim,) = self._claims(team, (number,))
        if claim.retracted:
            raise IllegalAction("заявление уже отозвано")
        rnd = self.rounds[-1]
        claim.retracted_at = now
        claim.retracted_in_round = rnd.index
        self.track.push_back(team, rnd.index, now, TrackCause.RETRACTION)
        self.structural.append(StructuralEvent(rnd.index, team, player_id, RETRACTION_ATOM, now))

    # ------------------------------------------------------------------ судья и журналист

    def rule(
        self,
        judge_id: str,
        now: datetime,
        winner: Team | None,
        marks: dict[Team, dict[MarkCode, bool]],
        challenge_rulings: dict[Team, bool] | None = None,
        fill_seconds: float | None = None,
    ) -> None:
        self._require_judge(judge_id)
        self.round.rule(self._ctx(), judge_id, now, winner, marks, challenge_rulings, fill_seconds)
        self._advance(now)

    def reject_claim(self, judge_id: str, team: Team, now: datetime) -> None:
        self._require_judge(judge_id)
        self.round.reject_claim(team)
        self._advance(now)

    def publish_summary(self, player_id: str, headline: str, body: str, now: datetime) -> None:
        p = self._player(player_id)
        if not p.active or p.role is not Role.JOURNALIST:
            raise IllegalAction(f"{player_id} не журналист")
        self.round.publish_summary(self._ctx(), headline, body, now)
        self._advance(now)

    # ------------------------------------------------------------------ реестр

    def claims(self, team: Team | None = None) -> list[LedgerClaim]:
        return [c for c in self.ledger if team is None or c.team is team]

    def _next_claim_number(self, team: Team) -> int:
        return len(self.claims(team)) + 1

    def _claims(self, team: Team, numbers: tuple[int, ...]) -> list[LedgerClaim]:
        by_number = {c.number: c for c in self.claims(team)}
        missing = [n for n in numbers if n not in by_number]
        if missing:
            raise IllegalAction(f"у {team} нет заявлений с номерами {missing}")
        return [by_number[n] for n in numbers]

    def contradiction_hint(self, team: Team) -> int:
        """Сколько пар в реестре соперника требуют проверки. Только число — никогда пары.

        В Фазе 0 кандидатов некому искать: возвращаем 0. Интерфейс метода зафиксирован,
        чтобы Фаза 2 подключила модель без изменения вызывающего кода.
        """
        return 0

    # ------------------------------------------------------------------ разбор

    def _enter_debrief(self, now: datetime) -> None:
        self.status = GameStatus.DEBRIEF
        self.debrief_started_at = now
        self.debrief_deadline = now + self.config.debrief_window
        self.outcome = self._compute_outcome()
        self._check_debrief_complete(now)

    def _compute_outcome(self) -> GameOutcome:
        positions = {t: self.track.positions[t] for t in Team}
        deltas = {t: self.track.delta(t) for t in Team}
        score = deltas if self.config.scoring == "delta" else positions
        if score[Team.A] == score[Team.B]:
            return GameOutcome(None, True, AporiaReason.TIE, positions, deltas)
        winner = Team.A if score[Team.A] > score[Team.B] else Team.B
        return GameOutcome(winner, False, None, positions, deltas)

    def submit_debrief_note(self, player_id: str, atom_worked: str, atom_missed: str, now: datetime) -> None:
        if self.status is not GameStatus.DEBRIEF:
            raise IllegalAction("разбор ещё не начался или уже закрыт")
        p = self._player(player_id)
        if not p.active:
            raise IllegalAction("выбывший игрок не участвует в разборе")
        self.debrief_notes[player_id] = DebriefNote(player_id, atom_worked, atom_missed, now)
        self._check_debrief_complete(now)

    def _check_debrief_complete(self, now: datetime) -> None:
        active = self.active_players()
        if active and all(p.id in self.debrief_notes for p in active):
            self.debrief_completed_at = now
            self.status = GameStatus.COMPLETED

    @property
    def export_allowed(self) -> bool:
        """Партия отдаёт данные в профиль только после завершённого разбора."""
        return self.status is GameStatus.COMPLETED and self.debrief_completed_at is not None

    def track_replay(self) -> list[tuple]:
        """Проигрыш трека: каждый сдвиг и выступление, которое его вызвало."""
        replay = []
        for ev in self.track.events:
            rnd = self.rounds[ev.round_index - 1]
            st = rnd.statements.get(ev.team)
            replay.append((ev, st.body if st else None))
        return replay
