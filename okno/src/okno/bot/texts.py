"""Тексты бота. Нейтральный тон протокола: ни азарта, ни морализаторства."""

from __future__ import annotations

PHASE_LINES = {
    "prep": "Подготовка. Команды совещаются приватно.",
    "statement": "Выступления. Сдаются вслепую — соперник не видит до раскрытия.",
    "response": "Реплики. Здесь же заявляется вызов на противоречие.",
    "verdict": "Вердикт. Судья выносит решение и заполняет карточки.",
    "ledger": "Реестр. Команды записывают опорное заявление.",
    "summary": "Сводка. Журналист публикует, что дошло до публики.",
    "closed": "Раунд закрыт.",
}

TEAM_NAMES = {"team_a": "команда А", "team_b": "команда Б"}


def who(pending: list[str]) -> str:
    names = []
    for p in pending:
        if p == "judge":
            names.append("судья")
        elif p == "journalist":
            names.append("журналист")
        elif p.endswith(":move"):
            names.append(f"{TEAM_NAMES[p[:-5]]} — выбор хода")
        else:
            names.append(TEAM_NAMES.get(p, p))
    return ", ".join(names)


def deadline_line(iso: str | None) -> str:
    if not iso:
        return ""
    from datetime import datetime

    dt = datetime.fromisoformat(iso).astimezone()
    return f"Окно закрывается {dt:%d.%m в %H:%M}."


def notification(kind: str, payload: dict) -> str:
    rnd = payload.get("round_index")
    phase = payload.get("phase")
    pending = payload.get("pending") or []
    timeout = " (по таймауту)" if payload.get("by_timeout") else ""
    match kind:
        case "game_started":
            head = f"Партия началась. Раунд {rnd}."
        case "phase_changed":
            head = f"Раунд {rnd}{timeout}."
        case "debrief_started":
            return "Партия сыграна. Открыт разбор — партия не закрыта, пока каждый не оставит отметку в приложении."
        case "game_completed":
            return "Разбор завершён. Партия засчитана."
        case "game_uncounted":
            return "Разбор не состоялся в срок. Партия закрыта и не засчитана."
        case _:
            head = f"Партия: {payload.get('status')}."
    lines = [head, PHASE_LINES.get(phase, "")]
    if pending:
        lines.append(f"Ждём: {who(pending)}.")
    lines.append(deadline_line(payload.get("deadline")))
    return "\n".join(l for l in lines if l)


START_PRIVATE = (
    "«Окно». Асинхронная командная игра: две команды проводят каждая свой проект "
    "по треку общественного мнения. Всё сказанное — под запись.\n\n"
    "Партия живёт в групповом чате: добавьте бота в чат и напишите там /new. "
    "Интерфейс — в приложении, кнопка ниже."
)

START_GROUP = "Чтобы начать партию в этом чате: /new. Открыть текущую: /game."
