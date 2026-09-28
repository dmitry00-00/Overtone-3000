"""Прогон трёх сценариев из раздела 12 промпта с печатью протокола.

    .venv/bin/python scripts/run_scenarios.py

1. нормальная партия;
2. партия, в которой судья пропустил вердикт;
3. партия целиком по таймаутам.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from okno.engine import Game, GameStatus, Move, Phase, Team
from okno.sim import Sim

W = 78


def header(title: str) -> None:
    print("\n" + "=" * W)
    print(title)
    print("=" * W)


def fmt(dt) -> str:
    return dt.strftime("%d.%m %H:%M")


def positions_after(game: Game, index: int) -> dict[Team, int]:
    pos = dict(game.track.start)
    for ev in game.track.events:
        if ev.round_index <= index:
            pos[ev.team] = ev.position_to
    return pos


def dump_round(game: Game, index: int) -> None:
    rnd = game.rounds[index - 1]
    v = rnd.verdict
    print(f"\n--- Раунд {rnd.index} · {rnd.deal.circumstance_code} · публика {rnd.deal.audience_code} · открыт {fmt(rnd.opened_at)}")
    for tr in rnd.log:
        flag = "  ⏱ таймаут" if tr.by_timeout else ""
        print(f"  {fmt(tr.at)}  {tr.from_phase.value:>9} → {tr.to_phase.value:<9}{flag}")
    if v is None:
        print("  вердикт: —")
    elif v.is_aporia:
        print(f"  вердикт: апория ({v.aporia_reason.value})")
    elif v.winner is None:
        print("  вердикт: исход определён вызовом")
    else:
        how = " (без выступления соперника)" if v.by_forfeit else ""
        move = f", ход: {v.move.value}" if v.move else ""
        print(f"  вердикт: убедила {v.winner.value}{how}{move}")
    for team, ch in rnd.challenges.items():
        state = {True: "засчитан", False: "отклонён", None: "не рассмотрен"}[ch.upheld]
        print(f"  вызов {team.value} на {ch.claim_numbers}: {state}")
    if rnd.marks:
        for team, m in rnd.marks.items():
            on = [code.value for code, val in m.values.items() if val]
            print(f"  отметки {team.value}: {', '.join(on) or '—'}")
    else:
        print("  отметки: не ставились")
    if rnd.summary:
        print(f"  сводка ({rnd.summary.author}): {rnd.summary.headline}")
    pos = positions_after(game, rnd.index)
    print(f"  трек после раунда: A={pos[Team.A]} B={pos[Team.B]}")


def dump_game(game: Game) -> None:
    for i in range(1, len(game.rounds) + 1):
        dump_round(game, i)
    print("\n--- Реестр")
    for c in game.ledger:
        notes = []
        if c.weak:
            notes.append("слабое")
        if c.retracted:
            notes.append(f"отозвано в р.{c.retracted_in_round}")
        if c.challenged_in_round:
            notes.append(f"вызов засчитан в р.{c.challenged_in_round}")
        print(f"  {c.team.value} #{c.number} (р.{c.round_index}): {c.text}" + (f"  [{'; '.join(notes)}]" if notes else ""))
    if not game.ledger:
        print("  пусто")
    print("\n--- Проигрыш трека")
    for ev, body in game.track_replay():
        print(f"  р.{ev.round_index} {ev.team.value}: {ev.position_from} → {ev.position_to} ({ev.cause.value})")
    if not game.track.events:
        print("  фишки не двигались")
    o = game.outcome
    print(f"\n--- Итог: статус {game.status.value}")
    if o:
        if o.is_aporia:
            print(f"  партия закончилась ничем ({o.aporia_reason.value}); позиции A={o.positions[Team.A]} B={o.positions[Team.B]}")
        else:
            print(f"  дальше провела проект {o.winner.value}: сдвиг A={o.deltas[Team.A]:+d} B={o.deltas[Team.B]:+d}")
    print(f"  экспорт в профиль: {'разрешён' if game.export_allowed else 'закрыт'}")


# ----------------------------------------------------------------------------- сценарии


def scenario_normal() -> Game:
    header("Сценарий 1. Нормальная партия: A стартует с 0, B с 2")
    sim = Sim(starts={Team.A: 0, Team.B: 2})
    sim.start()
    # р.1: A выигрывает — из 0 это первая из двух побед
    sim.advance(hours=3)
    sim.play_round(Team.A, Move.ADVANCE)
    # р.2: A снова — фишка выходит на 1
    sim.advance(hours=5)
    sim.play_round(Team.A, Move.ADVANCE)
    # р.3: B выигрывает и откатывает A
    sim.advance(hours=4)
    sim.play_round(Team.B, Move.PUSH_BACK)
    # р.4: A подаёт вызов на заявления B №1 и №2 — засчитан
    sim.advance(hours=6)
    sim.ready()
    sim.statement(Team.A)
    sim.statement(Team.B)
    sim.challenge(Team.A, (1, 2), "В р.1 B опиралась на цену, в р.2 — на то, что цена не важна")
    sim.response(Team.B)
    sim.rule(None, rulings={Team.A: True}, fill_seconds=51)
    sim.claim(Team.A)
    sim.claim(Team.B)
    sim.summary()
    # р.5: B отзывает своё заявление №2 — шаг назад, плюс в прибор
    sim.advance(hours=2)
    sim.game.retract_claim("b1", Team.B, 2, sim.now)
    sim.play_round(None)  # судья: не убедил никто
    # р.6, р.7: B выигрывает оба
    sim.play_round(Team.B, Move.ADVANCE)
    sim.play_round(Team.B, Move.ADVANCE)
    sim.debrief_all()
    dump_game(sim.game)
    return sim.game


def scenario_judge_silent() -> Game:
    header("Сценарий 2. Судья пропускает вердикт в раундах 2 и 5")
    sim = Sim(starts={Team.A: 1, Team.B: 1})
    sim.start()
    sim.play_round(Team.A, Move.ADVANCE)
    for _ in range(2):
        sim.ready()
        sim.statement(Team.A)
        sim.statement(Team.B)
        sim.response(Team.A)
        sim.response(Team.B)
        sim.expire_phase()  # VERDICT истёк: апория, отметок нет
        sim.claim(Team.A)
        sim.claim(Team.B)
        sim.summary()
        sim.play_round(Team.B, Move.ADVANCE)
    sim.play_round(Team.A, Move.ADVANCE)
    sim.play_round(Team.A, Move.ADVANCE)
    sim.debrief_all()
    dump_game(sim.game)
    return sim.game


def scenario_all_timeouts() -> Game:
    header("Сценарий 3. Партия целиком по таймаутам: никто не заходил")
    sim = Sim(starts={Team.A: 2, Team.B: 2})
    sim.start()
    sim.advance(days=30)  # один tick спустя месяц
    dump_game(sim.game)
    return sim.game


if __name__ == "__main__":
    g1 = scenario_normal()
    g2 = scenario_judge_silent()
    g3 = scenario_all_timeouts()
    assert g1.status is GameStatus.COMPLETED and g1.export_allowed
    assert g2.status is GameStatus.COMPLETED
    assert g3.status is GameStatus.UNCOUNTED and not g3.export_allowed
    assert all(r.phase is Phase.CLOSED for g in (g1, g2, g3) for r in g.rounds)
    print("\nВсе три партии закрыты корректно.")
