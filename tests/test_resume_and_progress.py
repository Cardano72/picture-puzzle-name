import pytest
from resume_logic import (
    mark_final, new_resume_credentials, recover_player_id,
    valid_order, verify_resume, with_answer, with_position,
)
from storage import LocalStore, StorageError


def sample_record(round_id, player_id, digest):
    return {
        "round_id": round_id, "player_id": player_id, "resume_hash": digest,
        "name": "Detti", "order": [2, 0, 1], "position": 0,
        "answers": {}, "final": False,
    }


def test_resume_secret_is_not_saved_in_json(tmp_path):
    token, player_id, digest = new_resume_credentials()
    assert len(token) == 43
    assert len(player_id) == 32
    assert recover_player_id(token) == player_id
    assert recover_player_id("invalid token") is None
    store = LocalStore(tmp_path)
    record = sample_record("a" * 32, player_id, digest)
    store.create_player(record)
    restored = store.read_player("a" * 32, recover_player_id(token))
    assert verify_resume(restored, token)
    assert token not in str(restored)
    assert not verify_resume(restored, new_resume_credentials()[0])
    assert not verify_resume(restored, "foo")


def test_reconnect_returns_same_answers_and_order(tmp_path):
    token, player_id, digest = new_resume_credentials()
    round_id = "b" * 32
    store = LocalStore(tmp_path)
    store.create_player(sample_record(round_id, player_id, digest))
    store.update_player(round_id, player_id, lambda r: with_answer(r, "p1", "kávé"))
    store.update_player(round_id, player_id, lambda r: with_position(r, 2))
    restored = store.read_player(round_id, recover_player_id(token))
    assert verify_resume(restored, token)
    assert restored["answers"]["p1"] == "kávé"
    assert restored["order"] == [2, 0, 1]
    assert restored["position"] == 2
    assert valid_order(restored["order"], 3)


def test_answers_are_patched_not_replaced_even_with_two_open_tabs(tmp_path):
    token, player_id, digest = new_resume_credentials()
    rid = "c" * 32
    store = LocalStore(tmp_path)
    store.create_player(sample_record(rid, player_id, digest))
    stale_in_tab_a = store.read_player(rid, player_id)
    stale_in_tab_b = store.read_player(rid, player_id)
    store.update_player(rid, player_id, lambda record: with_answer(record, "p1", "alma"))
    # b fül ugyanabból a régi képernyő-állapotból küld be egy MÁSIK feladatot.
    assert not stale_in_tab_b["answers"]
    store.update_player(rid, player_id, lambda record: with_answer(record, "p2", "kávé"))
    saved = store.read_player(rid, player_id)
    assert saved["answers"] == {"p1": "alma", "p2": "kávé"}
    assert not stale_in_tab_a["answers"]


def test_final_prevents_further_edits(tmp_path):
    token, player_id, digest = new_resume_credentials()
    rid = "d" * 32
    store = LocalStore(tmp_path)
    store.create_player(sample_record(rid, player_id, digest))
    store.update_player(rid, player_id, mark_final)
    with pytest.raises(ValueError):
        store.update_player(rid, player_id, lambda r: with_answer(r, "p1", "late"))
    with pytest.raises(ValueError):
        store.update_player(rid, player_id, lambda r: with_position(r, 1))
    assert store.read_player(rid, player_id)["final"]


def test_invalid_order_and_missing_record(tmp_path):
    assert not valid_order([0, 0, 1], 3)
    assert not valid_order([1, 2], 3)
    store = LocalStore(tmp_path)
    with pytest.raises(StorageError):
        store.update_player("e" * 32, "f" * 32, mark_final)


def test_duplicate_join_is_rejected(tmp_path):
    token, player_id, digest = new_resume_credentials()
    store = LocalStore(tmp_path)
    record = sample_record("f" * 32, player_id, digest)
    store.create_player(record)
    with pytest.raises(StorageError):
        store.create_player(record)
