"""Pure game rules. No Streamlit or network dependencies."""

import math
import re
import time
import unicodedata
import uuid

POINTS_PER_CORRECT = 10


def new_lobby(round_number=1):
    return {
        "round_id": uuid.uuid4().hex,
        "round_number": round_number,
        "status": "lobby",  # lobby | running | ended
        "started_at": None,
        "deadline": None,
        "messages": [],
    }


def phase(control, now=None):
    if not control:
        return "unconfigured"
    if control["status"] == "lobby":
        return "lobby"
    if control["status"] == "ended":
        return "finished"
    if control["status"] == "running":
        return "finished" if (now if now is not None else time.time()) >= control["deadline"] else "running"
    raise ValueError("Ismeretlen fordulóállapot")


def remaining_seconds(control, now=None):
    if phase(control, now) != "running":
        return 0
    current = now if now is not None else time.time()
    return max(0, math.ceil(control["deadline"] - current))


def format_seconds(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def normalize_answer(answer):
    value = unicodedata.normalize("NFKD", str(answer).casefold())
    without_accents = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", without_accents)


def is_correct(puzzle, answer):
    value = normalize_answer(answer)
    return bool(value) and any(value == normalize_answer(valid) for valid in puzzle["answers"])


def score(puzzles, answers):
    correct = sum(is_correct(puzzle, answers.get(puzzle["id"], "")) for puzzle in puzzles)
    return {
        "correct": correct,
        "total": len(puzzles),
        "points": correct * POINTS_PER_CORRECT,
        "answered": sum(bool(str(answers.get(puzzle["id"], "")).strip()) for puzzle in puzzles),
    }


def start_round(control, duration_minutes, now=None):
    if phase(control, now) != "lobby":
        raise ValueError("Csak várakozó forduló indítható")
    if not 1 <= duration_minutes <= 180:
        raise ValueError("A játékidő 1 és 180 perc közötti lehet")
    timestamp = now if now is not None else time.time()
    control["status"] = "running"
    control["started_at"] = timestamp
    control["deadline"] = timestamp + duration_minutes * 60
    return control


def set_remaining(control, seconds, now=None):
    if phase(control, now) != "running":
        raise ValueError("Az idő csak aktív, még le nem járt fordulóban módosítható")
    if not 5 <= seconds <= 6 * 3600:
        raise ValueError("A hátralévő idő 5 másodperc és 6 óra közé eshet")
    timestamp = now if now is not None else time.time()
    control["deadline"] = timestamp + seconds
    return control


def end_round(control):
    if control["status"] != "running":
        raise ValueError("Csak aktív forduló zárható le")
    control["status"] = "ended"
    control["deadline"] = time.time()
    return control


def send_message(control, content, now=None):
    message = content.strip()
    if not message or len(message) > 250:
        raise ValueError("Az üzenet 1–250 karakterből állhat")
    entry = {"id": uuid.uuid4().hex, "text": message, "sent_at": now if now is not None else time.time()}
    control["messages"] = (control.get("messages") or [])[-19:] + [entry]
    return control
