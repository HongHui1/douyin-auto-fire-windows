import builtins
import random
from datetime import date, timedelta

import pytest

from app import copywriting
from app.models import Message
from app.sender import resolve_streak_message


def test_entire_reviewed_bank_is_safe_and_unique():
    entries = [text for bank in copywriting.BANK.values() for text in bank]
    assert len(entries) == len(set(entries)) == 70
    assert all(copywriting.is_safe_message(text) for text in entries)
    poems = [text for text in entries if text.startswith("【十四行诗")]
    assert len(poems) == 2
    # The messages now quote excerpts of real sonnets, not full original poems.
    assert all("英文原文节选" in text for text in poems)
    for text in copywriting.BANK["literary"]:
        assert "\n——" in text
        assert "原创" not in text and "拟莎体" not in text and "俳句风" not in text


@pytest.mark.parametrize("text", [
    "", None, " \n ", "x" * 361, "\n".join(["诗"] * 19),
    "我想你了", "普通朋友也可以暧昧一下", "给你比心", "余生一起走",
    "想 \u200b你", "ＬＯＶＥ", "💘", "陪你看月亮",
])
def test_rejects_inappropriate_or_invalid_copy(text):
    assert not copywriting.is_safe_message(text)


def test_rotation_is_stable_safe_varied_and_has_rare_eggs():
    start = date(2026, 1, 1)
    all_entries = {text for bank in copywriting.BANK.values() for text in bank}
    categories = {text: category for category, bank in copywriting.BANK.items() for text in bank}
    counts = dict.fromkeys(copywriting.BANK, 0)
    for friend in range(10):
        previous = None
        for offset in range(1000):
            day = (start + timedelta(days=offset)).isoformat()
            text = copywriting.generate_message(run_date=day, context=f"friend-{friend}")
            assert text == copywriting.generate_message(run_date=day, context=f"friend-{friend}")
            assert text in all_entries
            assert text != previous
            assert copywriting.is_safe_message(text)
            counts[categories[text]] += 1
            previous = text
    assert 50 <= counts["easter_egg"] <= 150
    for category, weight in copywriting.CATEGORY_WEIGHTS.items():
        assert abs(counts[category] / 10000 - weight / 100) < 0.02


def test_does_not_change_global_random_state():
    state = random.getstate()
    copywriting.generate_message(run_date="2026-10-21", context="friend")
    assert random.getstate() == state


@pytest.mark.parametrize("bad_result", [None, "", "想你了", "x" * 500])
def test_bad_generation_falls_back(monkeypatch, bad_result):
    monkeypatch.setattr(copywriting, "generate_message", lambda **kwargs: bad_result)
    result = resolve_streak_message(Message(type="streak"))
    assert result.type == "text"
    assert result.content == "🔥 今日续火打卡，祝今天顺顺利利！"


def test_empty_bank_and_bad_date_fall_back(monkeypatch):
    monkeypatch.setattr(copywriting, "BANK", dict.fromkeys(copywriting.BANK, ()))
    for run_date in ("2026-10-21", "broken-date"):
        result = resolve_streak_message(Message(type="streak"), run_date=run_date)
        assert result.content == "🔥 今日续火打卡，祝今天顺顺利利！"


def test_missing_engine_falls_back(monkeypatch):
    original = builtins.__import__

    def broken_import(name, *args, **kwargs):
        if name == "app.copywriting":
            raise ImportError("engine unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_import)
    assert resolve_streak_message(Message(type="streak")).content == "🔥 今日续火打卡，祝今天顺顺利利！"


def test_nested_random_resolves_streak_and_preserves_existing_messages():
    text = Message(type="text", content="existing")
    result = resolve_streak_message(
        Message(type="random", choices=(text, Message(type="streak"))),
        run_date="2026-10-21", context="friend",
    )
    assert result.choices[0] is text
    assert result.choices[1].type == "text"
    assert copywriting.is_safe_message(result.choices[1].content)
