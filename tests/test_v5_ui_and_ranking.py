import re

import pytest

from game_logic import end_round, new_lobby, set_podium_visibility, start_round
from leaderboard import leaderboard_rows
from ui import announcement, hero, podium, result_hero, timer_panel

PUZZLES = [
    {"id": "p1", "answers": ["almAfa"]},
    {"id": "p2", "answers": ["kutyaház"]},
    {"id": "p3", "answers": ["napszemüveg"]},
]


def test_leaderboard_deterministic_sort_and_scores():
    records = [
        {"player_id": "a", "name": "Marci", "answers": {"p1": "almafa", "p2": "hiányzik"}},
        {"player_id": "b", "name": "Detti", "answers": {"p1": "almafa", "p2": "kutyahaz", "p3": "napszemuveg"}},
        {"player_id": "c", "name": "Barni", "answers": {"p1": "almafa", "p2": "nem tudom"}},
    ]
    rows = leaderboard_rows(PUZZLES, records)
    assert [row["nev"] for row in rows] == ["Detti", "Barni", "Marci"]
    assert [r["pont"] for r in rows] == [3, 1, 1]
    assert [r["helyezes"] for r in rows] == [1, 2, 3]
    assert rows[0]["vegleges"] == "nem"


def test_public_podium_only_after_finish():
    control = new_lobby()
    assert not control["reveal_podium"]
    with pytest.raises(ValueError):
        set_podium_visibility(control, True)
    start_round(control, 5)
    with pytest.raises(ValueError):
        set_podium_visibility(control, True)
    end_round(control)
    assert set_podium_visibility(control, True)["reveal_podium"]
    assert not set_podium_visibility(control, False)["reveal_podium"]


def test_ui_escapes_names_and_admin_messages():
    malicious = '<img src=x onerror=alert(1)>'
    assert malicious not in hero("hi", malicious, "desc")
    assert "&lt;img" in hero("hi", malicious, "desc")
    assert malicious not in announcement(malicious)
    assert malicious not in result_hero(malicious, 2, 3, 2)
    rows = [{"nev": malicious, "pont": 3}, {"nev": "Anna", "pont": 2}]
    assert malicious not in podium(rows)


def test_countdown_alert_and_lobby_visuals():
    assert "00:29" in timer_panel(29)
    assert "timer-card--urgent" in timer_panel(29)
    assert "timer-card--regular" in timer_panel(31)
    assert "– – : – –" in timer_panel(0, state="lobby")
    assert "00:00" in timer_panel(0, state="finished")


def test_empty_and_partial_podium_safe():
    assert "még nem került" in podium([])
    assert podium([{"nev": "Tomi", "pont": 1}]).count('podium-blank') == 2


def test_saved_assets_present():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert (root / ".streamlit" / "secrets.example.toml").is_file()
    css = (root / "styles" / "modern_party.css").read_text(encoding="utf-8")
    assert ".st-key-puzzle-card" in css
    assert "@media (max-width:640px)" in css
    assert len(list((root / "images").glob("*.png"))) == 5
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'live="1.5s"' in app
    assert 'run_every="1s"' in app
    assert 'run_every="12s"' in app
