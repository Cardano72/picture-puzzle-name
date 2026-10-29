"""Képrejtvény-kihívás – 2. mérföldkő: helyi játékmenet és pontozás."""

import json
import math
import random
import re
import time
import unicodedata
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
GAME_DURATION_SECONDS = 5 * 60  # Itt állítható a játékidő.
POINTS_PER_CORRECT = 10         # Itt állítható az egy feladatért járó pont.


def load_puzzles():
    with (BASE_DIR / "puzzles.json").open(encoding="utf-8") as file:
        puzzles = json.load(file)
    if not puzzles or len({p["id"] for p in puzzles}) != len(puzzles):
        raise ValueError("A rejtvénylistának nem üresnek kell lennie, egyedi id-kkel.")
    return puzzles


def normalize_answer(answer):
    """Kis-/nagybetűk, ékezetek, szóközök és írásjelek figyelmen kívül hagyása."""
    decomposed = unicodedata.normalize("NFKD", answer.casefold())
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", without_accents)


def is_correct(puzzle, answer):
    if not answer.strip():
        return False
    normalized = normalize_answer(answer)
    return any(normalized == normalize_answer(valid) for valid in puzzle["answers"])


def start_game(name, number_of_puzzles):
    st.session_state.player_name = name.strip()
    st.session_state.order = random.sample(range(number_of_puzzles), number_of_puzzles)
    st.session_state.position = 0
    st.session_state.answers = {}
    st.session_state.deadline = time.time() + GAME_DURATION_SECONDS
    st.session_state.finished = False


@st.fragment(run_every="1s")
def countdown():
    remaining = max(0, math.ceil(st.session_state.deadline - time.time()))
    if remaining == 0:
        st.session_state.finished = True
        st.rerun()  # Teljes alkalmazás-frissítés az eredményképernyőhöz.
    st.metric("⏳ Hátralévő idő", f"{remaining // 60:02d}:{remaining % 60:02d}")


st.set_page_config(page_title="Képrejtvény kihívás", page_icon="🧩", layout="centered")
puzzles = load_puzzles()
st.title("🧩 Képrejtvény kihívás")

# 1. BELÉPÉS
if "player_name" not in st.session_state:
    st.write("Add meg a neved, majd oldd meg a rejtvényeket a rendelkezésre álló idő alatt!")
    st.info(f"{len(puzzles)} rejtvény · {GAME_DURATION_SECONDS // 60} perc · {POINTS_PER_CORRECT} pont / helyes válasz")
    with st.form("login_form"):
        name = st.text_input("Játékos neve", max_chars=30)
        start = st.form_submit_button("Játék indítása", type="primary", use_container_width=True)
    if start:
        if name.strip():
            start_game(name, len(puzzles))
            st.rerun()
        else:
            st.warning("Adj meg egy játékosnevet!")
    st.stop()

# 2. EREDMÉNYEK (időlejáratkor vagy kézi befejezéskor)
if time.time() >= st.session_state.deadline:
    st.session_state.finished = True

if st.session_state.finished:
    correct = sum(
        is_correct(puzzle, st.session_state.answers.get(puzzle["id"], ""))
        for puzzle in puzzles
    )
    total = len(puzzles)
    st.success(f"Játék vége, {st.session_state.player_name}!")
    col1, col2 = st.columns(2)
    col1.metric("Helyes válaszok", f"{correct} / {total}")
    col2.metric("Pontszám", f"{correct * POINTS_PER_CORRECT}")

    with st.expander("Válaszaim és megoldások"):
        for puzzle_index in st.session_state.order:
            puzzle = puzzles[puzzle_index]
            answer = st.session_state.answers.get(puzzle["id"], "")
            symbol = "✅" if is_correct(puzzle, answer) else "❌"
            st.write(f"{symbol} **{puzzle['title']}** — válaszod: {answer or '–'}; helyes: {puzzle['answers'][0]}")

    st.caption("Ez a fejlesztési verzió még nem küldi fel az eredményt a GitHub-ranglistára.")
    if st.button("Új játék indítása"):
        for key in ("player_name", "order", "position", "answers", "deadline", "finished"):
            st.session_state.pop(key, None)
        st.rerun()
    st.stop()

# 3. JÁTÉKKÉPERNYŐ
st.write(f"Játékos: **{st.session_state.player_name}**")
countdown()

order = st.session_state.order
position = st.session_state.position
puzzle = puzzles[order[position]]
answered = sum(bool(str(x).strip()) for x in st.session_state.answers.values())
st.progress(answered / len(puzzles), text=f"Megválaszolt rejtvények: {answered}/{len(puzzles)}")
st.subheader(f"{position + 1}. rejtvény a {len(puzzles)}-ből")

image_path = BASE_DIR / puzzle["image"]
if image_path.is_file():
    st.image(image_path, width="stretch", alt="Képrejtvény")
else:
    st.warning(f"A képfájl nem található: {puzzle['image']}")

st.write(puzzle.get("question", "Mi a képrejtvény megfejtése?"))

# A form elküldése egyetlen műveletben menti a választ ÉS navigál.
with st.form(key=f"puzzle_form_{puzzle['id']}"):
    answer = st.text_input(
        "Megfejtés",
        value=st.session_state.answers.get(puzzle["id"], ""),
        placeholder="Írd ide a megfejtésed…",
    )

    prev_col, save_col, next_col = st.columns(3)
    with prev_col:
        previous = st.form_submit_button("⬅ Előző", disabled=(position == 0), use_container_width=True)
    with save_col:
        save = st.form_submit_button("💾 Mentés", use_container_width=True)
    with next_col:
        following = st.form_submit_button(
            "Következő ➡", disabled=(position == len(puzzles) - 1), use_container_width=True
        )

    jump_position = st.selectbox(
        "Ugrás másik rejtvényhez",
        options=list(range(len(puzzles))),
        index=position,
        format_func=lambda x: f"{x + 1}. rejtvény",
    )
    jump = st.form_submit_button("Ugrás a kiválasztott rejtvényhez")
    finish = st.form_submit_button("🏁 Játék befejezése és pontozás")

if previous or save or following or jump or finish:
    # Már lejárt játékhoz nem fogadunk el további választ.
    if time.time() < st.session_state.deadline:
        st.session_state.answers[puzzle["id"]] = answer.strip()
        if previous:
            st.session_state.position -= 1
        elif following:
            st.session_state.position += 1
        elif jump:
            st.session_state.position = jump_position
    if finish or time.time() >= st.session_state.deadline:
        st.session_state.finished = True
    st.rerun()

st.caption("A Mentés / Előző / Következő / Ugrás gombok mind rögzítik az aktuális választ. Az idő lejártakor csak a már mentett válaszok számítanak.")
