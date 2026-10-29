import base64
import json
from urllib.parse import unquote
from storage import GitHubStore


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body
        self.ok = 200 <= status < 300
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self.body


class FakeGithub:
    def __init__(self):
        self.files = {}
        self.next_revision = 0

    def request(self, method, url, headers, params=None, json=None, timeout=15):
        key = unquote(url.split("/contents/")[1])
        if method == "GET":
            if key in self.files:
                data, sha = self.files[key]
                return Response(200, {
                    "type": "file", "encoding": "base64", "sha": sha,
                    "content": base64.b64encode(__import__("json").dumps(data).encode()).decode(),
                })
            prefix = key + "/"
            matches = [p for p in self.files if p.startswith(prefix)]
            if matches:
                return Response(200, [
                    {"type": "file", "name": p[len(prefix):], "path": p}
                    for p in matches
                ])
            return Response(404, {"message": "Not Found"})
        if method == "PUT":
            exists = self.files.get(key)
            if (exists and exists[1] != json.get("sha")) or (not exists and json.get("sha")):
                return Response(409, {"message": "Conflict"})
            self.next_revision += 1
            self.files[key] = (__import__("json").loads(base64.b64decode(json["content"])), str(self.next_revision))
            return Response(201, {"content": {"sha": str(self.next_revision)}})
        if method == "DELETE":
            self.files.pop(key, None)
            return Response(200, {"commit": {}})
        raise AssertionError(method)


def test_github_round_and_player_files(monkeypatch):
    fake = FakeGithub()
    monkeypatch.setattr("storage.requests.request", fake.request)
    s = GitHubStore("sample", "sample-data", "token", "main")
    assert s.read_control() is None
    state = s.update_control(lambda previous: {"round_id": "a" * 32, "status": "lobby"})
    assert s.read_control() == state
    state = s.update_control(lambda previous: {**previous, "status": "running"})
    assert state["status"] == "running"
    a = {"round_id": "a" * 32, "player_id": "b" * 32, "name": "Anna", "answers": {}}
    b = {"round_id": "a" * 32, "player_id": "c" * 32, "name": "Barni", "answers": {}}
    s.save_player(a)
    s.save_player(b)
    a["answers"] = {"almafa": "almafa"}
    s.save_player(a)
    players = s.list_players("a" * 32)
    assert len(players) == 2
    assert [p for p in players if p["name"] == "Anna"][0]["answers"]["almafa"] == "almafa"
    s.delete_player("a" * 32, "b" * 32)
    assert len(s.list_players("a" * 32)) == 1


def test_github_read_and_patch_preserve_other_answers(monkeypatch):
    from resume_logic import with_answer, mark_final
    fake = FakeGithub()
    monkeypatch.setattr("storage.requests.request", fake.request)
    s = GitHubStore("owner", "private", "token")
    rid, pid = "a" * 32, "b" * 32
    record = {"round_id": rid, "player_id": pid, "name": "Tomi", "answers": {}, "final": False}
    s.create_player(record)
    assert s.read_player(rid, pid)["name"] == "Tomi"
    s.update_player(rid, pid, lambda r: with_answer(r, "p1", "x"))
    s.update_player(rid, pid, lambda r: with_answer(r, "p2", "y"))
    assert s.read_player(rid, pid)["answers"] == {"p1": "x", "p2": "y"}
    final = s.update_player(rid, pid, mark_final)
    assert final["final"] is True
    with __import__("pytest").raises(ValueError):
        s.update_player(rid, pid, lambda r: with_answer(r, "p1", "late"))
