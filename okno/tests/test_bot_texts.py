from okno.bot.texts import notification


def test_phase_notification_names_who_is_awaited():
    t = notification("phase_changed", {"round_index": 3, "phase": "ledger", "pending": ["team_a", "team_a:move", "team_b"], "deadline": None})
    assert t.startswith("Раунд 3.")
    assert "команда А — выбор хода" in t and "команда Б" in t


def test_timeout_and_terminal_texts():
    assert "(по таймауту)" in notification("phase_changed", {"round_index": 1, "phase": "statement", "pending": [], "by_timeout": True})
    assert "не засчитана" in notification("game_uncounted", {})
    assert "не закрыта, пока" in notification("debrief_started", {})
