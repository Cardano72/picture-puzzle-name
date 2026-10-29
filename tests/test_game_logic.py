from game_logic import (
    end_round, format_seconds, is_correct, new_lobby, phase,
    remaining_seconds, score, send_message, set_remaining, start_round,
)
from storage import LocalStore
import pytest


def test_common_timer_and_changes():
    game = new_lobby()
    assert phase(game, now=1_000) == "lobby"
    start_round(game, 5, now=1_000)
    assert remaining_seconds(game, now=1_020) == 280
    assert phase(game, now=1_299) == "running"
    assert phase(game, now=1_300) == "finished"
    set_remaining(game, 90, now=1_100)
    assert game["deadline"] == 1_190
    assert remaining_seconds(game, now=1_150) == 40
    with pytest.raises(ValueError):
        set_remaining(game, 60, now=1_200)
    assert format_seconds(90) == "01:30"


def test_messages_and_new_round():
    game = new_lobby()
    send_message(game, " Indulunk! ", now=101)
    assert game["messages"][-1]["text"] == "Indulunk!"
    another = new_lobby(round_number=2)
    assert another["round_id"] != game["round_id"]
    assert another["messages"] == []


def test_scoring():
    puzzles = [{"id": "a", "answers": ["napszemüveg"]}, {"id": "b", "answers": ["almafa"]}]
    assert is_correct(puzzles[0], "NAP SZEMÜVEG!!")
    result = score(puzzles, {"a": "nap szemuveg", "b": "rossz"})
    assert result == {"correct": 1, "total": 2, "points": 10, "answered": 2}


def test_local_store_round_isolation(tmp_path):
    storage = LocalStore(tmp_path)
    state = storage.update_control(lambda x: x or new_lobby())
    pid = "a" * 32
    storage.save_player({"round_id": state["round_id"], "player_id": pid, "name": "Anna", "answers": {}})
    assert len(storage.list_players(state["round_id"])) == 1
    newer = storage.update_control(lambda old: new_lobby(old["round_number"] + 1))
    assert newer["round_id"] != state["round_id"]
    assert storage.list_players(newer["round_id"]) == []
    assert len(storage.list_players(state["round_id"])) == 1


def test_local_store_delete(tmp_path):
    storage = LocalStore(tmp_path)
    record = {"round_id": "a" * 32, "player_id": "b" * 32, "name": "Béla", "answers": {}}
    storage.save_player(record)
    assert len(storage.list_players(record["round_id"])) == 1
    storage.delete_player(record["round_id"], record["player_id"])
    assert storage.list_players(record["round_id"]) == []
