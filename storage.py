"""Shared JSON storage: GitHub Contents API or local development files."""

import base64
import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter


class StorageError(RuntimeError):
    pass


class GitHubStore:
    def __init__(self, owner, repo, token, branch="main"):
        if not (owner and repo and token):
            raise StorageError("Hiányzó GITHUB_OWNER, GITHUB_REPO vagy GITHUB_TOKEN beállítás")
        self.api = f"https://api.github.com/repos/{owner}/{repo}/contents"
        self.token = token
        self.branch = branch
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _request(self, method, path, *, payload=None, allow_missing=False):
        url = f"{self.api}/{quote(path, safe='/')}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        # Tesztekben a storage.requests.request van mockolva; productionben maradjon a Session-pooling.
        request_fn = requests.request if requests.request is not requests.api.request else self.session.request
        try:
            response = request_fn(
                method, url, headers=headers, params={"ref": self.branch} if method == "GET" else None,
                json=payload, timeout=15,
            )
        except requests.RequestException as exc:
            raise StorageError(f"GitHub hálózati hiba: {exc}") from exc
        if response.status_code == 404 and allow_missing:
            return None
        if response.status_code in (409,):
            raise ConflictError("GitHub fájlütközés (409)")
        if not response.ok:
            detail = response.json().get("message", "") if response.headers.get("content-type", "").startswith("application/json") else response.text[:120]
            raise StorageError(f"GitHub API hiba ({response.status_code}): {detail}")
        return response.json()

    def _read(self, path):
        item = self._request("GET", path, allow_missing=True)
        if item is None:
            return None, None
        if not isinstance(item, dict) or item.get("type") != "file":
            raise StorageError(f"Nem fájl az elérési út: {path}")
        if item.get("encoding") == "base64":
            raw = base64.b64decode(item["content"])
        else:
            raise StorageError(f"Nem támogatott GitHub tartalom: {path}")
        return json.loads(raw.decode("utf-8")), item["sha"]

    def read_control(self):
        value, _ = self._read("control.json")
        return value

    def _write(self, path, value, sha, message):
        content = base64.b64encode(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
        body = {"message": message, "content": content, "branch": self.branch}
        if sha is not None:
            body["sha"] = sha
        return self._request("PUT", path, payload=body)

    def update_control(self, transform):
        for attempt in range(5):
            state, sha = self._read("control.json")
            updated = transform(copy.deepcopy(state))
            if updated is None:
                raise StorageError("A vezérlőállapot nem lehet üres")
            try:
                self._write("control.json", updated, sha, "Update puzzle game control")
                return updated
            except ConflictError:
                time.sleep(0.15 * (attempt + 1))
        raise StorageError("A központi vezérlés módosítása ütközött. Próbáld újra.")

    def read_player(self, round_id, player_id):
        self._validate_ids(round_id, player_id)
        record, _ = self._read(f"results/{round_id}/{player_id}.json")
        return record

    @staticmethod
    def _validate_ids(round_id, player_id):
        if not all(len(x) == 32 and all(c in "0123456789abcdef" for c in x)
                   for x in (round_id, player_id)):
            raise StorageError("Érvénytelen forduló- vagy játékosazonosító")

    def create_player(self, record):
        """Create without replacing an existing player's record."""
        rid, pid = record["round_id"], record["player_id"]
        self._validate_ids(rid, pid)
        if self.read_player(rid, pid) is not None:
            raise StorageError("Ez a játékosazonosító már foglalt")
        try:
            self._write(f"results/{rid}/{pid}.json", record, None,
                        f"Enroll player {pid[:8]}")
        except (ConflictError, StorageError) as exc:
            raise StorageError("Nem sikerült az új játékos biztonságos létrehozása") from exc

    def update_player(self, round_id, player_id, transform):
        """Read-modify-write by SHA; concurrent edits to other answers are preserved."""
        self._validate_ids(round_id, player_id)
        path = f"results/{round_id}/{player_id}.json"
        for attempt in range(5):
            old, sha = self._read(path)
            if old is None:
                raise StorageError("Nem található a játékos mentett rekordja")
            updated = transform(copy.deepcopy(old))
            if updated is None:
                raise StorageError("A játékosrekord nem lehet üres")
            if updated["round_id"] != round_id or updated["player_id"] != player_id:
                raise StorageError("Nem módosítható a rekord azonosítója")
            if updated == old:
                return updated
            try:
                self._write(path, updated, sha, f"Update player {player_id[:8]}")
                return updated
            except ConflictError:
                time.sleep(0.15 * (attempt + 1))
        raise StorageError("A játékos mentése ütközött. Próbáld újra.")

    def save_player(self, record):
        rid, pid = record["round_id"], record["player_id"]
        if not all(len(x) == 32 and all(c in "0123456789abcdef" for c in x) for x in (rid, pid)):
            raise StorageError("Érvénytelen forduló- vagy játékosazonosító")
        path = f"results/{rid}/{pid}.json"
        for attempt in range(5):
            _, sha = self._read(path)
            try:
                self._write(path, record, sha, f"Save player {pid[:8]} in round {rid[:8]}")
                return
            except ConflictError:
                time.sleep(0.15 * (attempt + 1))
        raise StorageError("Az eredmény mentése ütközött. Próbáld újra.")

    def delete_player(self, round_id, player_id):
        if not all(len(x) == 32 and all(c in "0123456789abcdef" for c in x) for x in (round_id, player_id)):
            raise StorageError("Érvénytelen azonosító")
        path = f"results/{round_id}/{player_id}.json"
        for attempt in range(5):
            _, sha = self._read(path)
            if sha is None:
                return
            try:
                self._request("DELETE", path, payload={
                    "message": f"Delete player {player_id[:8]}", "sha": sha, "branch": self.branch,
                })
                return
            except ConflictError:
                time.sleep(0.15 * (attempt + 1))
        raise StorageError("A törlés ütközött. Próbáld újra.")

    def list_players(self, round_id):
        directory = self._request("GET", f"results/{round_id}", allow_missing=True)
        if directory is None:
            return []
        if not isinstance(directory, list):
            raise StorageError("A forduló eredménymappája nem könyvtár")
        files = [entry for entry in directory if entry["type"] == "file" and entry["name"].endswith(".json")]
        if len(files) >= 1000:
            raise StorageError("Túl sok játékosfájl egy mappában (1000+)")
        return [self._read(entry["path"])[0] for entry in files]


class ConflictError(StorageError):
    pass


_local_lock = threading.RLock()


class LocalStore:
    """For local testing only. Never use as permanent storage in Streamlit Cloud."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _file(self, key):
        return self.directory / key

    def _read(self, key):
        path = self._file(key)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def _write(self, key, value):
        path = self._file(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def read_control(self):
        with _local_lock:
            return self._read("control.json")

    def update_control(self, transform):
        with _local_lock:
            state = self._read("control.json")
            updated = transform(copy.deepcopy(state))
            self._write("control.json", updated)
            return updated

    def read_player(self, round_id, player_id):
        with _local_lock:
            return self._read(f"results/{round_id}/{player_id}.json")

    def create_player(self, record):
        with _local_lock:
            key = f"results/{record['round_id']}/{record['player_id']}.json"
            if self._file(key).is_file():
                raise StorageError("Ez a játékosazonosító már foglalt")
            self._write(key, record)

    def update_player(self, round_id, player_id, transform):
        with _local_lock:
            key = f"results/{round_id}/{player_id}.json"
            record = self._read(key)
            if record is None:
                raise StorageError("Nem található a játékos mentett rekordja")
            updated = transform(copy.deepcopy(record))
            if updated is None or updated["round_id"] != round_id or updated["player_id"] != player_id:
                raise StorageError("Érvénytelen játékosrekord")
            if updated != record:
                self._write(key, updated)
            return updated

    def save_player(self, record):
        with _local_lock:
            self._write(f"results/{record['round_id']}/{record['player_id']}.json", record)

    def delete_player(self, round_id, player_id):
        with _local_lock:
            self._file(f"results/{round_id}/{player_id}.json").unlink(missing_ok=True)

    def list_players(self, round_id):
        with _local_lock:
            directory = self._file(f"results/{round_id}")
            return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))] if directory.is_dir() else []
