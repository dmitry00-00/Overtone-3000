"""Репозиторий партии: Game ↔ таблицы.

Единица работы — вся партия. ``save`` делает upsert всех записей в одной
транзакции; ``load`` собирает Game обратно. На таблицы выступлений, заявлений
и событий нет ни одного delete: черновик опоры при отклонении судьёй остаётся
строкой с ``text = null``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import psycopg
from psycopg.rows import dict_row

from ..decks import DeckDealer, Decks
from ..engine.game import Game, SummaryFallback, system_summary
from ..engine.round import Round, Transition
from ..engine.types import (
    AporiaReason,
    Challenge,
    Config,
    Deal,
    DebriefNote,
    GameOutcome,
    GameStatus,
    LedgerClaim,
    MarkCode,
    Marks,
    Move,
    Phase,
    Player,
    Response,
    Role,
    Statement,
    StructuralEvent,
    Summary,
    Team,
    TrackCause,
    TrackEvent,
    Verdict,
    VerdictVote,
)

# ------------------------------------------------------------------ конфиг ↔ json


def config_to_json(cfg: Config) -> dict:
    return {
        "rounds": cfg.rounds,
        "round_duration_s": cfg.round_duration.total_seconds(),
        "phase_shares": {p.value: v for p, v in cfg.phase_shares.items()},
        "debrief_window_s": cfg.debrief_window.total_seconds(),
        "end_on_norm": cfg.end_on_norm,
        "scoring": cfg.scoring,
        "judging": cfg.judging,
        "claim_max_words": cfg.claim_max_words,
        "track_size": cfg.track_size,
    }


def config_from_json(d: dict) -> Config:
    return Config(
        rounds=d["rounds"],
        round_duration=timedelta(seconds=d["round_duration_s"]),
        phase_shares={Phase(p): v for p, v in d["phase_shares"].items()},
        debrief_window=timedelta(seconds=d["debrief_window_s"]),
        end_on_norm=d["end_on_norm"],
        scoring=d["scoring"],
        judging=d.get("judging", "judge"),
        claim_max_words=d["claim_max_words"],
        track_size=d["track_size"],
    )


def _outcome_to_json(o: GameOutcome | None) -> str | None:
    if o is None:
        return None
    return json.dumps(
        {
            "winner": o.winner.value if o.winner else None,
            "is_aporia": o.is_aporia,
            "aporia_reason": o.aporia_reason.value if o.aporia_reason else None,
            "positions": {t.value: p for t, p in o.positions.items()},
            "deltas": {t.value: d for t, d in o.deltas.items()},
        }
    )


def _outcome_from_json(d: dict | None) -> GameOutcome | None:
    if d is None:
        return None
    return GameOutcome(
        winner=Team(d["winner"]) if d["winner"] else None,
        is_aporia=d["is_aporia"],
        aporia_reason=AporiaReason(d["aporia_reason"]) if d["aporia_reason"] else None,
        positions={Team(t): p for t, p in d["positions"].items()},
        deltas={Team(t): p for t, p in d["deltas"].items()},
    )


def _team(v: str | None) -> Team | None:
    return Team(v) if v else None


# ------------------------------------------------------------------ репозиторий


class Repository:
    def __init__(self, conn: psycopg.Connection, decks: Decks, summary_fallback: SummaryFallback = system_summary):
        self.conn = conn
        self.decks = decks
        self.summary_fallback = summary_fallback

    # ----- сохранение -----

    def save(self, game: Game) -> None:
        with self.conn.transaction():
            self._save_game(game)
            self._save_players(game)
            self._save_projects(game)
            for rnd in game.rounds:
                self._save_round(game, rnd)
            self._save_ledger(game)
            self._save_events(game)
            self._save_debrief(game)

    def _save_game(self, g: Game) -> None:
        self.conn.execute(
            """
            insert into games (id, status, created_at, config_json, outcome_json, technical_aporia_from, updated_at)
            values (%s, %s, %s, %s, %s, %s, now())
            on conflict (id) do update set
                status = excluded.status, created_at = excluded.created_at, config_json = excluded.config_json,
                outcome_json = excluded.outcome_json, technical_aporia_from = excluded.technical_aporia_from,
                updated_at = now()
            """,
            (g.id, g.status.value, g.created_at, json.dumps(config_to_json(g.config)), _outcome_to_json(g.outcome), g.technical_aporia_from),
        )

    def _save_players(self, g: Game) -> None:
        for p in g.players.values():
            self.conn.execute(
                """
                insert into players (id, display_name) values (%s, %s)
                on conflict (id) do update set display_name = excluded.display_name
                """,
                (p.id, p.display_name),
            )
            self.conn.execute(
                """
                insert into memberships (game_id, player_id, role, dropped_at) values (%s, %s, %s, %s)
                on conflict (game_id, player_id) do update set role = excluded.role, dropped_at = excluded.dropped_at
                """,
                (g.id, p.id, p.role.value, p.dropped_at),
            )

    def _save_projects(self, g: Game) -> None:
        for team, code in g.projects.items():
            self.conn.execute(
                """
                insert into game_projects (game_id, team, project_code, start_position, track_position, streak, swapped)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (game_id, team) do update set
                    project_code = excluded.project_code, start_position = excluded.start_position,
                    track_position = excluded.track_position, streak = excluded.streak, swapped = excluded.swapped
                """,
                (g.id, team.value, code, g.track.start[team], g.track.positions[team], g.track.streak[team], team in g.project_swapped),
            )

    def _save_round(self, g: Game, r: Round) -> None:
        row = self.conn.execute(
            """
            insert into rounds (game_id, index, circumstance_code, audience_code, phase, phase_started_at, phase_deadline,
                                opened_at, ready_teams, forfeit_teams, move_choice)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (game_id, index) do update set
                phase = excluded.phase, phase_started_at = excluded.phase_started_at, phase_deadline = excluded.phase_deadline,
                ready_teams = excluded.ready_teams, forfeit_teams = excluded.forfeit_teams, move_choice = excluded.move_choice
            returning id
            """,
            (
                g.id, r.index, r.deal.circumstance_code, r.deal.audience_code, r.phase.value, r.phase_started_at,
                r.phase_deadline, r.opened_at, sorted(t.value for t in r.ready), sorted(t.value for t in r.forfeits),
                r.move_choice.value if r.move_choice else None,
            ),
        ).fetchone()
        rid = row[0]
        for seq, tr in enumerate(r.log):
            self.conn.execute(
                """
                insert into round_transitions (round_id, seq, from_phase, to_phase, at, by_timeout)
                values (%s, %s, %s, %s, %s, %s) on conflict do nothing
                """,
                (rid, seq, tr.from_phase.value, tr.to_phase.value, tr.at, tr.by_timeout),
            )
        for team, (carrier, frame) in r.deal.hands.items():
            self.conn.execute(
                "insert into round_hands (round_id, team, carrier_code, frame_code) values (%s, %s, %s, %s) on conflict do nothing",
                (rid, team.value, carrier, frame),
            )
        for team, st in r.statements.items():
            self.conn.execute(
                """
                insert into statements (round_id, team, body, submitted_at, author_id, edit_count, prep_seconds)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (round_id, team) do update set
                    body = excluded.body, submitted_at = excluded.submitted_at, author_id = excluded.author_id,
                    edit_count = excluded.edit_count, prep_seconds = excluded.prep_seconds
                """,
                (rid, team.value, st.body, st.submitted_at, st.author_id, st.edit_count, st.prep_seconds),
            )
        for team, resp in r.responses.items():
            self.conn.execute(
                """
                insert into responses (round_id, team, body, submitted_at) values (%s, %s, %s, %s)
                on conflict (round_id, team) do update set body = excluded.body, submitted_at = excluded.submitted_at
                """,
                (rid, team.value, resp.body, resp.submitted_at),
            )
        for team, ch in r.challenges.items():
            self.conn.execute(
                """
                insert into challenges (round_id, team, claim_numbers, argument, submitted_at, upheld, ruled_at)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (round_id, team) do update set upheld = excluded.upheld, ruled_at = excluded.ruled_at
                """,
                (rid, team.value, list(ch.claim_numbers), ch.argument, ch.submitted_at, ch.upheld, ch.ruled_at),
            )
        for team, vote in r.votes.items():
            self.conn.execute(
                """
                insert into verdict_votes (round_id, team, winner_team, opponent_marks, challenge_concede, submitted_at)
                values (%s, %s, %s, %s, %s, %s) on conflict (round_id, team) do nothing
                """,
                (
                    rid, team.value, vote.winner.value if vote.winner else None,
                    json.dumps({c.value: v for c, v in vote.opponent_marks.items()}),
                    vote.challenge_concede, vote.submitted_at,
                ),
            )
        if r.verdict is not None:
            v = r.verdict
            self.conn.execute(
                """
                insert into verdicts (round_id, winner_team, is_aporia, aporia_reason, judge_id, ruled_at, by_forfeit, fill_seconds, move)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (round_id) do update set
                    winner_team = excluded.winner_team, is_aporia = excluded.is_aporia, aporia_reason = excluded.aporia_reason,
                    judge_id = excluded.judge_id, ruled_at = excluded.ruled_at, by_forfeit = excluded.by_forfeit,
                    fill_seconds = excluded.fill_seconds, move = excluded.move
                """,
                (
                    rid, v.winner.value if v.winner else None, v.is_aporia, v.aporia_reason.value if v.aporia_reason else None,
                    v.judge_id, v.ruled_at, v.by_forfeit, v.fill_seconds, v.move.value if v.move else None,
                ),
            )
        for team, m in r.marks.items():
            for code, value in m.values.items():
                draft = m.draft.get(code) if m.draft else None
                self.conn.execute(
                    """
                    insert into marks (round_id, team, mark_code, value, draft_value, judge_id) values (%s, %s, %s, %s, %s, %s)
                    on conflict (round_id, team, mark_code) do update set value = excluded.value, draft_value = excluded.draft_value
                    """,
                    (rid, team.value, code.value, value, draft, m.judge_id),
                )
        for team in set(r.claim_texts) | set(r.claim_rejections):
            self.conn.execute(
                """
                insert into round_claim_drafts (round_id, team, text, rejections) values (%s, %s, %s, %s)
                on conflict (round_id, team) do update set text = excluded.text, rejections = excluded.rejections
                """,
                (rid, team.value, r.claim_texts.get(team), r.claim_rejections.get(team, 0)),
            )
        if r.summary is not None:
            s = r.summary
            self.conn.execute(
                """
                insert into summaries (round_id, headline, body, author, published_at) values (%s, %s, %s, %s, %s)
                on conflict (round_id) do nothing
                """,
                (rid, s.headline, s.body, s.author, s.published_at),
            )

    def _save_ledger(self, g: Game) -> None:
        for c in g.ledger:
            self.conn.execute(
                """
                insert into ledger_claims (game_id, team, number, round_index, text, weak, retracted_at, retracted_in_round, challenged_in_round)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (game_id, team, number) do update set
                    retracted_at = excluded.retracted_at, retracted_in_round = excluded.retracted_in_round,
                    challenged_in_round = excluded.challenged_in_round
                """,
                (g.id, c.team.value, c.number, c.round_index, c.text, c.weak, c.retracted_at, c.retracted_in_round, c.challenged_in_round),
            )

    def _save_events(self, g: Game) -> None:
        for seq, ev in enumerate(g.track.events):
            self.conn.execute(
                """
                insert into track_events (game_id, seq, round_index, team, position_from, position_to, cause, at)
                values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict do nothing
                """,
                (g.id, seq, ev.round_index, ev.team.value, ev.position_from, ev.position_to, ev.cause.value, ev.at),
            )
        for seq, ev in enumerate(g.structural):
            self.conn.execute(
                """
                insert into structural_events (game_id, seq, round_index, team, player_id, atom, at)
                values (%s, %s, %s, %s, %s, %s, %s) on conflict do nothing
                """,
                (g.id, seq, ev.round_index, ev.team.value, ev.player_id, ev.atom, ev.at),
            )

    def _save_debrief(self, g: Game) -> None:
        if g.debrief_started_at is None:
            return
        self.conn.execute(
            """
            insert into debriefs (game_id, started_at, deadline, completed_at) values (%s, %s, %s, %s)
            on conflict (game_id) do update set completed_at = excluded.completed_at
            """,
            (g.id, g.debrief_started_at, g.debrief_deadline, g.debrief_completed_at),
        )
        for n in g.debrief_notes.values():
            self.conn.execute(
                """
                insert into debrief_notes (game_id, player_id, atom_worked, atom_missed, at) values (%s, %s, %s, %s, %s)
                on conflict (game_id, player_id) do update set
                    atom_worked = excluded.atom_worked, atom_missed = excluded.atom_missed, at = excluded.at
                """,
                (g.id, n.player_id, n.atom_worked, n.atom_missed, n.at),
            )

    # ----- загрузка -----

    def _rows(self, sql: str, *params) -> list[dict]:
        with self.conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(sql, params).fetchall()

    def _one(self, sql: str, *params) -> dict | None:
        rows = self._rows(sql, *params)
        return rows[0] if rows else None

    def load(self, game_id: str, for_update: bool = False) -> Game | None:
        """Собрать партию из таблиц. ``for_update`` блокирует строку games до конца транзакции."""
        lock = " for update" if for_update else ""
        gr = self._one(f"select * from games where id = %s{lock}", game_id)
        if gr is None:
            return None
        config = config_from_json(gr["config_json"])
        game = Game(id=game_id, config=config, dealer=None, summary_fallback=self.summary_fallback)  # type: ignore[arg-type]
        game.status = GameStatus(gr["status"])
        game.created_at = gr["created_at"]
        game.outcome = _outcome_from_json(gr["outcome_json"])
        game.technical_aporia_from = gr["technical_aporia_from"]

        for m in self._rows(
            "select m.player_id, m.role, m.dropped_at, p.display_name from memberships m join players p on p.id = m.player_id "
            "where m.game_id = %s order by m.joined_at, m.player_id",
            game_id,
        ):
            game.players[m["player_id"]] = Player(m["player_id"], Role(m["role"]), m["display_name"], m["dropped_at"])

        for gp in self._rows("select * from game_projects where game_id = %s", game_id):
            team = Team(gp["team"])
            game.projects[team] = gp["project_code"]
            game.track.start[team] = gp["start_position"]
            game.track.positions[team] = gp["track_position"]
            game.track.streak[team] = gp["streak"]
            if gp["swapped"]:
                game.project_swapped.add(team)

        for rr in self._rows("select * from rounds where game_id = %s order by index", game_id):
            game.rounds.append(self._load_round(rr))

        for c in self._rows("select * from ledger_claims where game_id = %s order by team, number", game_id):
            game.ledger.append(
                LedgerClaim(
                    Team(c["team"]), c["round_index"], c["number"], c["text"], c["weak"],
                    c["retracted_at"], c["retracted_in_round"], c["challenged_in_round"],
                )
            )
        # порядок реестра — хронологический (как в памяти): по раунду, затем по команде
        game.ledger.sort(key=lambda c: (c.round_index, c.team.value))

        for e in self._rows("select * from track_events where game_id = %s order by seq", game_id):
            game.track.events.append(
                TrackEvent(e["round_index"], Team(e["team"]), e["position_from"], e["position_to"], TrackCause(e["cause"]), e["at"])
            )
        for e in self._rows("select * from structural_events where game_id = %s order by seq", game_id):
            game.structural.append(StructuralEvent(e["round_index"], Team(e["team"]), e["player_id"], e["atom"], e["at"]))

        d = self._one("select * from debriefs where game_id = %s", game_id)
        if d:
            game.debrief_started_at, game.debrief_deadline, game.debrief_completed_at = d["started_at"], d["deadline"], d["completed_at"]
            for n in self._rows("select * from debrief_notes where game_id = %s", game_id):
                game.debrief_notes[n["player_id"]] = DebriefNote(n["player_id"], n["atom_worked"], n["atom_missed"], n["at"])

        game.dealer = self._dealer_for(game)
        return game

    def _load_round(self, rr: dict) -> Round:
        rid = rr["id"]
        hands = {Team(h["team"]): (h["carrier_code"], h["frame_code"]) for h in self._rows("select * from round_hands where round_id = %s", rid)}
        r = Round(
            index=rr["index"],
            deal=Deal(rr["circumstance_code"], rr["audience_code"], hands),
            opened_at=rr["opened_at"],
            phase=Phase(rr["phase"]),
            phase_started_at=rr["phase_started_at"],
            phase_deadline=rr["phase_deadline"],
            ready={Team(t) for t in rr["ready_teams"]},
            forfeits={Team(t) for t in rr["forfeit_teams"]},
            move_choice=Move(rr["move_choice"]) if rr["move_choice"] else None,
        )
        r.log = [
            Transition(Phase(t["from_phase"]), Phase(t["to_phase"]), t["at"], t["by_timeout"])
            for t in self._rows("select * from round_transitions where round_id = %s order by seq", rid)
        ]
        for s in self._rows("select * from statements where round_id = %s", rid):
            r.statements[Team(s["team"])] = Statement(Team(s["team"]), s["body"], s["author_id"], s["submitted_at"], s["prep_seconds"], s["edit_count"])
        for s in self._rows("select * from responses where round_id = %s", rid):
            r.responses[Team(s["team"])] = Response(Team(s["team"]), s["body"], s["submitted_at"])
        for c in self._rows("select * from challenges where round_id = %s", rid):
            r.challenges[Team(c["team"])] = Challenge(Team(c["team"]), tuple(c["claim_numbers"]), c["argument"], c["submitted_at"], c["upheld"], c["ruled_at"])
        for vt in self._rows("select * from verdict_votes where round_id = %s order by team", rid):
            r.votes[Team(vt["team"])] = VerdictVote(
                Team(vt["team"]), _team(vt["winner_team"]),
                {MarkCode(c): val for c, val in vt["opponent_marks"].items()},
                vt["submitted_at"], vt["challenge_concede"],
            )
        v = self._one("select * from verdicts where round_id = %s", rid)
        if v:
            r.verdict = Verdict(
                _team(v["winner_team"]), v["is_aporia"], AporiaReason(v["aporia_reason"]) if v["aporia_reason"] else None,
                v["judge_id"], v["ruled_at"], v["by_forfeit"], v["fill_seconds"], Move(v["move"]) if v["move"] else None,
            )
        for m in self._rows("select * from marks where round_id = %s order by team, mark_code", rid):
            team = Team(m["team"])
            marks = r.marks.setdefault(team, Marks(team, {}, m["judge_id"]))
            marks.values[MarkCode(m["mark_code"])] = m["value"]
            if m["draft_value"] is not None:
                marks.draft = marks.draft or {}
                marks.draft[MarkCode(m["mark_code"])] = m["draft_value"]
        for d in self._rows("select * from round_claim_drafts where round_id = %s", rid):
            team = Team(d["team"])
            if d["text"] is not None:
                r.claim_texts[team] = d["text"]
            if d["rejections"]:
                r.claim_rejections[team] = d["rejections"]
        s = self._one("select * from summaries where round_id = %s", rid)
        if s:
            r.summary = Summary(s["headline"], s["body"], s["author"], s["published_at"])
        return r

    def _dealer_for(self, game: Game) -> DeckDealer:
        """Раздающий, который знает уже вышедшие карты: колоды не повторяются после перезагрузки."""
        return DeckDealer(
            self.decks,
            used_projects=set(game.projects.values()),
            used_circumstances={r.deal.circumstance_code for r in game.rounds},
            used_audiences={r.deal.audience_code for r in game.rounds},
            used_carriers={h[0] for r in game.rounds for h in r.deal.hands.values()},
            used_frames={t: [r.deal.hands[t][1] for r in game.rounds if t in r.deal.hands] for t in Team},
        )

    # ----- справочники -----

    def import_decks(self) -> None:
        d = self.decks
        with self.conn.transaction():
            for p in d.projects.values():
                self.conn.execute(
                    """
                    insert into projects (code, title, start, objection_1, objection_2) values (%s, %s, %s, %s, %s)
                    on conflict (code) do update set title = excluded.title, start = excluded.start,
                        objection_1 = excluded.objection_1, objection_2 = excluded.objection_2
                    """,
                    (p.code, p.title, p.start, *p.objections),
                )
            for c in d.carriers.values():
                self.conn.execute(
                    "insert into carriers values (%s, %s, %s, %s) on conflict (code) do update set title = excluded.title, benefit = excluded.benefit, danger = excluded.danger",
                    (c.code, c.title, c.benefit, c.danger),
                )
            for f in d.frames.values():
                self.conn.execute(
                    "insert into frames values (%s, %s, %s, %s) on conflict (code) do update set title = excluded.title, to_prove = excluded.to_prove, trap = excluded.trap",
                    (f.code, f.title, f.to_prove, f.trap),
                )
            for c in d.circumstances.values():
                self.conn.execute(
                    "insert into circumstances values (%s, %s, %s) on conflict (code) do update set event = excluded.event, changes = excluded.changes",
                    (c.code, c.event, c.changes),
                )
            for a in d.audiences.values():
                self.conn.execute(
                    "insert into audiences values (%s, %s, %s, %s) on conflict (code) do update set mood = excluded.mood, accepts = excluded.accepts, rejects = excluded.rejects",
                    (a.code, a.mood, a.accepts, a.rejects),
                )
