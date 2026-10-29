"""Secure but simple resume tokens and player progress updates (no Streamlit dependency)."""

import hashlib
import hmac
import re
import secrets
import time

TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")


def new_resume_credentials():
    """URL bearer secret; store only its digest, not the secret itself."""
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return token, digest[:32], digest


def recover_player_id(token):
    if not isinstance(token, str) or not TOKEN_PATTERN.fullmatch(token):
        return None
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return digest[:32]


def verify_resume(record, token):
    if not isinstance(record, dict) or recover_player_id(token) is None:
        return False
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return bool(record.get("resume_hash")) and hmac.compare_digest(record["resume_hash"], digest) and record.get("player_id") == digest[:32]


def valid_order(order, count):
    return isinstance(order, list) and sorted(order) == list(range(count))


def with_answer(record, puzzle_id, answer):
    """Patch one answer only, avoiding loss of other tabs' answers."""
    if record.get("final"):
        raise ValueError("Ez a játék már véglegesítve lett")
    answers = dict(record.get("answers") or {})
    answers[puzzle_id] = answer.strip()[:120]
    record["answers"] = answers
    record["updated_at"] = time.time()
    return record


def with_position(record, position):
    if record.get("final"):
        raise ValueError("Ez a játék már véglegesítve lett")
    record["position"] = int(position)
    record["updated_at"] = time.time()
    return record


def mark_final(record):
    if not record.get("final"):
        record["final"] = True
        record["updated_at"] = time.time()
    return record
