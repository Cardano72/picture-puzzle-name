"""PUZZLE PARTY V5 – reszponzív játék és közös GitHub-alapú forduló."""

import csv
import hmac
import io
import json
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import streamlit as st

from game_logic import (
    end_round, format_seconds, new_lobby, phase, remaining_seconds,
    send_message, set_remaining, start_round, set_podium_visibility,
)
from resume_logic import (
    mark_final, new_resume_credentials, recover_player_id,
    valid_order, verify_resume, with_answer, with_position,
)
from storage import GitHubStore, LocalStore, StorageError
from leaderboard import leaderboard_rows
from ui import (header, hero, section_title, mini_label, timer_panel,
                status_banner, announcement, stat_card, podium, safe)

BASE_DIR = Path(__file__).resolve().parent
POLL_CACHE_SECONDS = 3.5  # Shared control cache across active sessions.

st.set_page_config(
    page_title="Puzzle Party | Képrejtvény kihívás", page_icon="🧩",
    layout="wide", initial_sidebar_state="collapsed",
)
st.html(BASE_DIR / "styles" / "modern_party.css")


def read_settings():
    try:
        return dict(st.secrets)
    except FileNotFoundError:
        return {}


SETTINGS = read_settings()
MODE = str(SETTINGS.get("STORAGE_MODE", "local")).lower()
ADMIN_PASSWORD = str(SETTINGS.get("ADMIN_PASSWORD", ""))


@st.cache_resource(show_spinner=False)
def store_factory(mode, owner="", repo="", branch="main", _token=""):
    if mode == "local":
        return LocalStore(BASE_DIR / "local_data")
    if mode == "github":
        return GitHubStore(owner, repo, _token, branch)
    raise StorageError("STORAGE_MODE csak 'local' vagy 'github' lehet")


def store():
    return store_factory(
        MODE, str(SETTINGS.get("GITHUB_OWNER", "")),
        str(SETTINGS.get("GITHUB_REPO", "")),
        str(SETTINGS.get("GITHUB_BRANCH", "main")),
        _token=str(SETTINGS.get("GITHUB_TOKEN", "")),
    )


@st.cache_data(ttl=POLL_CACHE_SECONDS, show_spinner=False)
def cached_control():
    return store().read_control()


@st.cache_data(ttl=25, show_spinner=False)
def cached_players(round_id):
    return store().list_players(round_id)


def change_control(transform):
    updated = store().update_control(transform)
    cached_control.clear()
    return updated


def load_puzzles():
    with (BASE_DIR / "puzzles.json").open(encoding="utf-8") as handle:
        puzzles = json.load(handle)
    if not puzzles or len({p["id"] for p in puzzles}) != len(puzzles):
        raise ValueError("Nem üres, egyedi ID-kat tartalmazó puzzles.json szükséges")
    return puzzles


PUZZLES = load_puzzles()
PUZZLE_IDS = {p["id"] for p in PUZZLES}


def load_record_to_session(record, token):
    """Játékos állapotának helyreállítása a PRIVÁT GitHub-adatból."""
    if not valid_order(record.get("order"), len(PUZZLES)):
        raise StorageError("A mentett sorrend érvénytelen; ellenőrizd, változott-e a puzzles.json")
    st.session_state.player_id = record["player_id"]
    st.session_state.player_name = record["name"]
    st.session_state.round_id = record["round_id"]
    st.session_state.order = record["order"]
    st.session_state.position = max(0, min(int(record.get("position", 0)), len(PUZZLES) - 1))
    st.session_state.answers = dict(record.get("answers") or {})
    st.session_state.finished = bool(record.get("final"))
    st.session_state.resume_token = token
    st.session_state.seen_message = None
    st.session_state.save_error = None
    st.session_state.last_saved = None
    st.session_state.last_saved_puzzle = None
    # A text_input widget-állapotát a legutóbbi GitHub-mentés alapján építjük fel.
    for puzzle in PUZZLES:
        st.session_state[f"answer_{puzzle['id']}"] = st.session_state.answers.get(puzzle["id"], "")


def enroll_player(control, name):
    """A visszatérési kulcs SOHA nem kerül a GitHub JSON-fájlba."""
    token, player_id, digest = new_resume_credentials()
    record = {
        "round_id": control["round_id"],
        "player_id": player_id,
        "resume_hash": digest,
        "name": name.strip(),
        "order": random.sample(range(len(PUZZLES)), len(PUZZLES)),
        "position": 0,
        "answers": {},
        "final": False,
        "updated_at": time.time(),
    }
    store().create_player(record)
    cached_players.clear()
    load_record_to_session(record, token)
    st.query_params.from_dict({"round": control["round_id"], "resume": token})


def try_restore(control):
    """URL-ből visszatérő játékos. Új fordulóban NEM léptetünk be automatikusan."""
    if (st.session_state.get("round_id") == control["round_id"]
            and st.session_state.get("player_id")
            and st.session_state.get("resume_token")
            and st.session_state.get("resume_token") == st.query_params.get("resume", "")):
        return True
    st.session_state.pop("player_id", None)
    token = st.query_params.get("resume", "")
    old_round = st.query_params.get("round", "")
    if not token:
        return False
    if old_round != control["round_id"]:
        st.warning("Ez egy korábbi forduló visszatérési linkje. Az új fordulóhoz újra csatlakozhatsz.")
        if st.button("🆕 Csatlakozás az aktuális fordulóhoz"):
            st.query_params.clear()
            for key in ("round_id", "player_name", "answers", "position", "resume_token"):
                st.session_state.pop(key, None)
            st.rerun()
        st.stop()
    player_id = recover_player_id(token)
    if not player_id:
        st.error("Érvénytelen visszatérési kód.")
        if st.button("Új játékosként csatlakozom"):
            st.query_params.clear()
            st.rerun()
        st.stop()
    record = store().read_player(control["round_id"], player_id)
    if not record or not verify_resume(record, token):
        st.error("A mentett játékosrekord nem található, vagy a visszatérési kód nem megfelelő.")
        if st.button("Új játékosként csatlakozom"):
            st.query_params.clear()
            st.rerun()
        st.stop()
    load_record_to_session(record, token)
    return True


def save_answer(puzzle_id, field_key, *, position=None):
    """Egyetlen feladatot írunk át (és esetleg a pozíciót) — többi válasz megmarad."""
    answer = str(st.session_state.get(field_key, "")).strip()
    if len(answer) > 120 or puzzle_id not in PUZZLE_IDS:
        st.session_state.save_error = "Érvénytelen megfejtés."
        return False
    current_answer = st.session_state.get("answers", {}).get(puzzle_id, "")
    current_position = st.session_state.get("position", 0)
    if answer == current_answer and (position is None or position == current_position) and not st.session_state.get("save_error"):
        return True
    try:
        # Alapesetben cache-ből döntünk; ez jelentősen csökkenti az API-hívások számát.
        control = cached_control()
        if not control or control["round_id"] != st.session_state.round_id or phase(control) != "running":
            st.session_state.save_error = "A forduló már nem aktív; új válasz nem menthető."
            cached_control.clear()
            return False
        # Lejárat közelében kérjünk közvetlen, hiteles állapotot, így nem csúszik át késői mentés.
        if remaining_seconds(control) <= int(POLL_CACHE_SECONDS) + 1:
            authoritative = store().read_control()
            if (not authoritative
                    or authoritative["round_id"] != st.session_state.round_id
                    or phase(authoritative) != "running"):
                st.session_state.save_error = "A forduló már nem aktív; új válasz nem menthető."
                cached_control.clear()
                return False

        def patch(record):
            if puzzle_id in PUZZLE_IDS and (answer != (record.get("answers") or {}).get(puzzle_id, "")):
                record = with_answer(record, puzzle_id, answer)
            if position is not None and record.get("position", 0) != position:
                record = with_position(record, position)
            return record

        record = store().update_player(st.session_state.round_id, st.session_state.player_id, patch)
        st.session_state.answers = record.get("answers") or {}
        st.session_state.position = record.get("position", current_position)
        st.session_state.save_error = None
        st.session_state.last_saved = time.strftime("%H:%M:%S")
        st.session_state.last_saved_puzzle = puzzle_id
        return True
    except (StorageError, ValueError) as exc:
        st.session_state.save_error = str(exc)
        return False


def on_answer_change(puzzle_id, field_key):
    """A st.text_input(live='1.5s') szünetenként automatikusan hívja."""
    save_answer(puzzle_id, field_key)



def show_messages(control):
    """Announcement from central control (already escaped inside ui.announcement)."""
    messages = control.get("messages") or []
    if not messages:
        return
    latest = messages[-1]
    if st.session_state.get("seen_message") != latest["id"]:
        st.session_state.seen_message = latest["id"]
        st.toast("Új üzenet a játékvezetőtől!", icon="📣")
    st.html(announcement(latest["text"], datetime.fromtimestamp(latest["sent_at"], ZoneInfo("Europe/Budapest")).strftime("%H:%M")))
    if len(messages) > 1:
        with st.expander("Korábbi játékvezetői üzenetek"):
            for msg in reversed(messages[:-1]):
                st.markdown(f"**{datetime.fromtimestamp(msg['sent_at'], ZoneInfo('Europe/Budapest')).strftime('%H:%M')}** · {msg['text']}")


def current_phase_verified(control):
    """A cached expiration must be checked against storage before finalizing."""
    if phase(control) != "finished":
        return phase(control)
    authoritative = store().read_control()
    if not authoritative or authoritative["round_id"] != control["round_id"]:
        cached_control.clear()
        st.rerun()
    actual = phase(authoritative)
    if actual != "finished":
        cached_control.clear()
        st.rerun()
    return "finished"


@st.fragment(run_every="1s")
def live_player_panel():
    """Live, independent refresh; typing is not interrupted by the timer."""
    try:
        control = cached_control()
    except StorageError:
        st.html(status_banner("warn", "A közös óra szinkronizálása átmenetileg nem sikerült."))
        return
    if not control or control["round_id"] != st.session_state.round_id:
        st.rerun()
    state = phase(control)
    if state != st.session_state.get("_screen_phase"):
        if state == "finished":
            # Admin may have extended the clock just after cache expiry.
            fresh = store().read_control()
            if fresh and phase(fresh) != "finished":
                cached_control.clear()
                return
        st.rerun()
    st.html(timer_panel(remaining_seconds(control), state))
    show_messages(control)


@st.fragment(run_every="6s")
def round_change_watcher():
    """Finished players keep their result while a new round is announced."""
    try:
        current = cached_control()
        if current and current["round_id"] != st.session_state.round_id:
            st.html(status_banner("info", "Új forduló indult! Nyisd meg újra az alaplinket a csatlakozáshoz."))
    except StorageError:
        st.caption("A következő forduló ellenőrzése nem sikerült.")


@st.fragment(run_every="12s")
def lobby_population(round_id):
    try:
        count = len(cached_players(round_id))
        st.html(mini_label("Csatlakozott játékosok", count, "lime"))
    except StorageError:
        st.caption("A játékoslétszám átmenetileg nem érhető el.")


def render_results():
    st.html(hero("GAME OVER", "Véget ért a játék!", "A játék lezárult. A részletes eredmények csak az admin felületén láthatók.", compact=True))
    try:
        # Persisted answers are the only inputs to scoring. A final record is idempotent.
        saved = store().update_player(
            st.session_state.round_id, st.session_state.player_id, mark_final
        )
        st.session_state.answers = saved.get("answers") or {}
        st.session_state.finished = True
    except (StorageError, ValueError) as exc:
        st.error(f"Az eredmény véglegesítése nem sikerült: {exc}")
        if st.button("Újrapróbálom a véglegesítést", type="primary"):
            st.rerun()
        return
    st.html(status_banner("ok", "A játékod lezárva és mentve. Az eredményt a játékvezető látja az admin nézetben."))
    with st.expander("🔑 Visszatérési link és kód"):
        st.caption("Mentsd el a jelenlegi oldal teljes URL-jét, vagy ezt a kódot. Ne oszd meg nyilvánosan!")
        st.code(st.session_state.resume_token, language=None)
    round_change_watcher()


def save_and_navigate(puzzle_id, field_key, destination):
    if save_answer(puzzle_id, field_key, position=destination):
        st.rerun()
    else:
        st.warning("A navigáláshoz előbb sikeresen el kell menteni a választ.")


def render_game():
    order = st.session_state.order
    index = st.session_state.position
    puzzle = PUZZLES[order[index]]
    answered = sum(bool(str(st.session_state.answers.get(p["id"], "")).strip()) for p in PUZZLES)

    st.html(hero("PUZZLE CHALLENGE", f"Hajrá, {st.session_state.player_name}!", "Fejtsd meg a képeket, és gyűjtsd a pontokat. Az óra mindenkinek közös.", "A játék folyamatban", compact=True))
    live_player_panel()
    st.html('<div class="mini-grid">' +
            mini_label("Aktuális feladat", f"{index + 1} / {len(order)}") +
            mini_label("Mentett válaszok", f"{answered} / {len(PUZZLES)}", "lime") +
            mini_label("Pontozás", "1 / helyes") + '</div>')
    st.caption("Minden megszerzett tárgy 3 pont.")
    st.progress(answered / len(PUZZLES))

    with st.container(key="puzzle-card"):
        st.html(f'<div class="puzzle-title"><span class="puzzle-kicker">{index + 1}. KÉPREJTVÉNY / {len(order)}</span><span class="puzzle-points">★ 1 PONT</span></div>')
        picture = BASE_DIR / puzzle["image"]
        if picture.is_file():
            st.image(str(picture), use_container_width=True)
        else:
            st.warning(f"A kép nem található: {puzzle['image']}")
        st.html(f'<div class="puzzle-question">{safe(puzzle.get("question", "Mi a megfejtés?"))}</div>')
        field_key = f"answer_{puzzle['id']}"
        saved_answer = st.session_state.answers.get(puzzle["id"], "")
        last_puzzle_id = st.session_state.get("active_puzzle_id")
        # Puzzleváltáskor mindig a mentett értéket mutassuk, ne egy korábban beragadt widget-state-et.
        if last_puzzle_id != puzzle["id"]:
            st.session_state[field_key] = saved_answer
            st.session_state.active_puzzle_id = puzzle["id"]
        elif field_key not in st.session_state:
            st.session_state[field_key] = saved_answer
        st.text_input(
            "Megfejtés", key=field_key, max_chars=120,
            placeholder="Írd ide a megfejtést…", live="1.5s",
            on_change=on_answer_change, args=(puzzle["id"], field_key),
            help="Gépelési szünet után a rendszer központilag elmenti a választ.",
        )
        if st.session_state.get("save_error"):
            st.html(status_banner("warn", f"Nincs elmentve: {st.session_state.save_error}"))
            if st.button("🔄 Mentés újrapróbálása", key=f"retry_{puzzle['id']}"):
                save_answer(puzzle["id"], field_key)
                st.rerun()
        elif st.session_state.get("last_saved") and st.session_state.get("last_saved_puzzle") == puzzle["id"]:
            st.html(status_banner("ok", f"Mentve · {st.session_state.last_saved}"))
        else:
            st.html(status_banner("info", "Automatikus mentés gépelés után, vagy a Mentés gombbal."))

    st.html(section_title("Haladás", "Szabadon lépkedhetsz a rejtvények között", "↗"))
    with st.container(key="game-controls"):
        left, middle, right = st.columns(3, gap="small", vertical_alignment="center", wrap=True)
        if left.button("← Előző", disabled=index == 0, use_container_width=True):
            save_and_navigate(puzzle["id"], field_key, index - 1)
        if middle.button("Mentés", use_container_width=True):
            save_and_navigate(puzzle["id"], field_key, index)
        if right.button("Következő →", disabled=index == len(order) - 1, type="primary", use_container_width=True):
            save_and_navigate(puzzle["id"], field_key, index + 1)

    st.html('<div class="puzzle-jump-hint">Válassz feladatot · ✓ = már van elmentett válasz</div>')
    # Mobilon is tördülhessen, ne okozzon vízszintes görgetést.
    with st.container(key="jump-grid"):
        for start in range(0, len(order), 5):
            cols = st.columns(5, gap="small", wrap=True)
            for offset, col in enumerate(cols):
                target = start + offset
                if target >= len(order):
                    continue
                selected_puzzle = PUZZLES[order[target]]
                has_answer = bool(str(st.session_state.answers.get(selected_puzzle["id"], "")).strip())
                label = f"{target + 1}{' ✓' if has_answer else ''}"
                if col.button(label, key=f"jump_{target}", type="primary" if target == index else "secondary", use_container_width=True):
                    save_and_navigate(puzzle["id"], field_key, target)

    with st.expander("🔑 Visszatérési link / kód"):
        st.write("Mentsd el a jelenlegi oldal teljes címét, vagy az alábbi kódot, így ugyanoda térhetsz vissza.")
        st.code(st.session_state.resume_token, language=None)
        st.caption("A visszatérési link titkos: aki megszerzi, hozzáférhet a válaszaidhoz.")


def render_player():
    if MODE == "local":
        st.html('<div class="mode-banner">🧪 HELYI TESZTMÓD · Az adatok csak ezen a gépen maradnak.</div>')
    try:
        control = cached_control()
    except StorageError as exc:
        st.error(f"A közös játékállapot nem érhető el: {exc}")
        return
    if not control:
        st.html(hero("WELCOME TO THE PARTY", "Képrejtvény kihívás", "A játékvezető hamarosan létrehozza az első fordulót. Addig is készüljetek a fejtörésre!"))
        st.info("A forduló előkészítésére várunk. A játékvezető az Admin nézetben indíthatja el.")
        return
    try:
        logged_in = try_restore(control)
    except StorageError as exc:
        st.error(f"A játékos visszaállítása sikertelen: {exc}")
        return
    if not logged_in:
        if phase(control) == "finished":
            st.html(hero("ROUND COMPLETE", "Erre a fordulóra már nem lehet belépni", "Várd meg, amíg a játékvezető új kört nyit!"))
            return
        st.html(hero("READY, SET, RIDDLE!", "Lakásavató Pesterzsi 2026", "Tök durva, hogy végre ez is összejött, köszi, hogy itt vagy!", f"{len(PUZZLES)} rejtvény · 1 pont / helyes + 3 pont / begyűjtött tárgy"))
        st.html('<div class="mini-grid mini-grid--duo">' +
                mini_label("Játék típusa", "Riddle") +
            mini_label("Hátralévő idő", "Admin indítja", "lime") + '</div>')
        if phase(control) == "running":
            st.warning(f"A forduló már fut. Most még beszállhatsz, de csak {format_seconds(remaining_seconds(control))} van hátra!")
        with st.container(key="auth-card"):
            st.html(section_title("Ide majd be kell írni a neved, remélem elég egyértelmű", "Pro Tip: Az Admin sörrel lekenyerezhető, de az sem hátrány, ha a felesége vagy", "✦"))
            with st.form("player_join"):
                name = st.text_input("Adj egy nevet, buszra kell", max_chars=30, placeholder="Például: Abdul (csak érted, inkább a sajátod legyen, ne az hogy Abdul, mert annak úgy semmi értelme)")
                join = st.form_submit_button("Indulhat a játék! →", type="primary", use_container_width=True)
            if join:
                normalized_name = name.strip().casefold()
                if not normalized_name:
                    st.warning("Adj már meg egy nevet!")
                elif normalized_name == "abdul":
                    st.warning("De baszki mit nem értettél abból, hogy nem Abdul, hanem a saját neved kell?")
                else:
                    try:
                        enroll_player(control, name)
                        st.rerun()
                    except StorageError as exc:
                        st.error(f"Nem sikerült csatlakozni: {exc}")
            with st.expander("🔑 Már játszottam · visszalépés kóddal"):
                with st.form("resume_form"):
                    entered = st.text_input("Visszatérési kód", type="password", max_chars=43)
                    submit = st.form_submit_button("Folytatás")
                if submit:
                    st.query_params.from_dict({"round": control["round_id"], "resume": entered.strip()})
                    st.rerun()
        return

    if st.session_state.get("finished"):
        render_results()
        return
    actual_state = current_phase_verified(control)
    st.session_state._screen_phase = actual_state
    if actual_state == "finished":
        render_results()
        return
    if actual_state == "lobby":
        st.html(hero("VÁRÓTEREM · LOBBY", f"Mek mek, {st.session_state.player_name}!", "You are in the end game now. Figyelj az adminra, hogy mikor kezdünk.", "De tényleg figyelj. Nem fogom többször elmagyarázni.", compact=False))
        live_player_panel()
        st.html(section_title("Megint csak olvasol, de nem figyelsz.", "Jó, ha olvasol akkor legalább hozz egy sört.", "◷"))
        lobby_population(control["round_id"])
        st.html(status_banner("info", "A játék automatikusan megjelenik, amint a játékvezető elindítja."))
        with st.expander("🔑 Visszatérési kód"):
            st.code(st.session_state.resume_token, language=None)
            st.caption("Az oldal teljes URL-jét is elmentheted – titkos visszatérési hivatkozás.")
        return
    render_game()


@st.fragment(run_every="1s")
def admin_live_status():
    try:
        control = cached_control()
        if not control:
            return
        state = phase(control)
        time_value = format_seconds(remaining_seconds(control)) if state == "running" else ("–" if state == "lobby" else "00:00")
        try:
            players = len(cached_players(control["round_id"]))
        except StorageError:
            players = "–"
        st.html('<div class="stats-grid">' +
                stat_card("Játékosok", players, "violet") +
                stat_card("Közös idő", time_value, "lime") +
                stat_card("Forduló", f"#{control.get('round_number', 1)}", "blue") + '</div>')
    except StorageError as exc:
        st.warning(f"Az állapot átmenetileg nem elérhető: {exc}")


def admin_action(action):
    try:
        action()
        cached_players.clear()
        st.rerun()
    except (ValueError, StorageError) as exc:
        st.error(str(exc))


def csv_bytes(rows):
    output = io.StringIO()
    fields = ["helyezes", "nev", "helyes", "osszes", "pont", "megmentett_valaszok", "vegleges"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


@st.fragment(run_every="30s")
def admin_leaderboard():
    try:
        control = cached_control()
        if not control:
            return
        if st.button("↻ Ranglista frissítése", key="refresh_scores"):
            cached_players.clear()
            st.rerun(scope="fragment")
        records = cached_players(control["round_id"])
        rows = leaderboard_rows(PUZZLES, records)
        st.caption(f"{len(rows)} regisztrált játékos · a folyamatban lévő eredmények is látszanak.")
        if not rows:
            st.html('<div class="empty-state">Még nincs csatlakozott játékos.</div>')
            return
        st.dataframe([{k: row[k] for k in ("helyezes", "nev", "helyes", "osszes", "pont", "megmentett_valaszok", "vegleges")}
                      for row in rows], use_container_width=True, hide_index=True)
        st.download_button("↓ Ranglista letöltése (CSV)", csv_bytes(rows),
                           file_name=f"ranglista-{control['round_id'][:8]}.csv", mime="text/csv")
        st.html(podium(rows, "Élő top 3" if phase(control) == "running" else "A forduló dobogója"))
        if phase(control) == "finished":
            with st.expander("🗑 Egy játékos eredményének törlése"):
                by_id = {r["player_id"]: r for r in records}
                selected_id = st.selectbox("Játékos", list(by_id),
                    format_func=lambda p: f"{by_id[p].get('name', '?')} ({p[:8]})")
                confirm = st.checkbox("Megerősítem a törlést", key="delete_confirm")
                if st.button("Eredmény törlése", disabled=not confirm):
                    try:
                        store().delete_player(control["round_id"], selected_id)
                        cached_players.clear()
                        st.rerun(scope="fragment")
                    except StorageError as exc:
                        st.error(f"Törlési hiba: {exc}")
    except StorageError as exc:
        st.error(f"Ranglista hiba: {exc}")


def render_admin():
    st.html(hero("GAME MASTER MODE", "Irányítópult", "Kezeld a fordulókat, az órát és a játékvezetői üzeneteket egy helyen.", "🔒 Védett adminfelület", compact=True))
    if not st.session_state.get("admin_authenticated"):
        with st.container(key="auth-card"):
            st.html(section_title("Admin bejelentkezés", "Csak a játékvezető léphet be", "♜"))
            with st.form("admin_signin"):
                password = st.text_input("Adminjelszó", type="password")
                login = st.form_submit_button("Belépés →", type="primary", use_container_width=True)
            if login:
                if ADMIN_PASSWORD and hmac.compare_digest(password, ADMIN_PASSWORD):
                    st.session_state.admin_authenticated = True
                    st.rerun()
                else:
                    st.error("Hibás adminjelszó")
        return

    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("Kijelentkezés", key="admin_logout"):
            st.session_state.admin_authenticated = False
            st.rerun()
    try:
        control = cached_control()
    except StorageError as exc:
        st.error(f"A központi vezérlés nem érhető el: {exc}")
        return
    if not control:
        st.html(section_title("Első forduló", "Indíts egy új játékot", "◈"))
        with st.container(key="admin-panel"):
            st.info("Még nincs forduló. Hozd létre az első, várakozó játékot.")
            if st.button("+ Első forduló létrehozása", type="primary"):
                admin_action(lambda: change_control(lambda old: old or new_lobby()))
        return

    state = phase(control)
    text = {"lobby": "Rajtra vár", "running": "Folyamatban", "finished": "Lezárult"}[state]
    st.html(section_title(f"{control.get('round_number', 1)}. forduló · {text}", f"Azonosító: {control['round_id'][:8]}", "◉"))
    admin_live_status()

    left, right = st.columns([1, 1], gap="medium")
    with left:
        st.html(section_title("Játékvezérlés", "Közös idő és rajt", "◷"))
        with st.container(key="admin-panel"):
            if state == "lobby":
                with st.form("start_round"):
                    minutes = st.number_input("Játékidő (perc)", min_value=1, max_value=180, value=5)
                    if st.form_submit_button("▶ Forduló indítása", type="primary", use_container_width=True):
                        admin_action(lambda: change_control(lambda c: start_round(c, int(minutes))))
            elif state == "running":
                st.html(status_banner("info", "Az óra közös: minden játékos ugyanazt az időt látja."))
                plus, minus = st.columns(2, wrap=False)
                if plus.button("+1 perc", use_container_width=True):
                    admin_action(lambda: change_control(lambda c: set_remaining(c, remaining_seconds(c) + 60)))
                if minus.button("−1 perc", use_container_width=True):
                    admin_action(lambda: change_control(lambda c: set_remaining(c, max(5, remaining_seconds(c) - 60))))
                with st.form("set_clock"):
                    minutes = st.number_input("Hátralévő perc", min_value=0, max_value=360, value=5)
                    seconds = st.number_input("Hátralévő másodperc", min_value=0, max_value=59, value=0)
                    if st.form_submit_button("Hátralévő idő beállítása", use_container_width=True):
                        admin_action(lambda: change_control(lambda c: set_remaining(c, int(minutes) * 60 + int(seconds))))
                with st.expander("⏹ Forduló lezárása"):
                    if st.button("Forduló azonnali lezárása", key="stop_round"):
                        admin_action(lambda: change_control(end_round))
            else:
                st.success("Ez a forduló véget ért.")
                visible = bool(control.get("reveal_podium", False))
                if st.button("🏆 Dobogó elrejtése" if visible else "🏆 Dobogó közzététele", type="primary", use_container_width=True):
                    admin_action(lambda: change_control(lambda c: set_podium_visibility(c, not visible)))
                st.caption("A közzétett dobogót a játékosok az eredményoldalukon láthatják.")

    with right:
        st.html(section_title("Üzenet a játékosoknak", "Automatikus frissítés néhány másodpercenként", "✉"))
        with st.container(key="admin-messages"):
            with st.form("broadcast", clear_on_submit=True):
                message = st.text_area("Üzenet", max_chars=250, height=110, placeholder="Például: Még két percetek van, hajrá!")
                if st.form_submit_button("📣 Üzenet küldése", type="primary", use_container_width=True):
                    admin_action(lambda: change_control(lambda c: send_message(c, message)))
            if control.get("messages"):
                st.html(announcement(control["messages"][-1]["text"]))
                with st.expander("Korábbi üzenetek"):
                    for msg in reversed(control["messages"][:-1]):
                        st.write(msg["text"])

    st.html(section_title("Ranglista és dobogó", "Automatikus és kézi frissítéssel", "★"))
    with st.container(key="admin-table"):
        admin_leaderboard()

    st.html(section_title("Fordulókezelés", "Az előző eredmények nem vesznek el", "↻"))
    with st.container(key="admin-danger"):
        st.caption("Új forduló → új azonosító, tiszta eredménylista. A korábbi JSON-fájlok megmaradnak a privát repositoryban.")
        confirmed = st.checkbox("Megerősítem, hogy új fordulót szeretnék")
        if st.button("+ Új, üres forduló létrehozása", disabled=not confirmed, use_container_width=True):
            admin_action(lambda: change_control(lambda c: new_lobby(c["round_number"] + 1)))


# ---------- Entry point ----------
if not ADMIN_PASSWORD:
    st.error("Az ADMIN_PASSWORD nincs beállítva. Hozd létre a .streamlit/secrets.toml fájlt a minta alapján.")
    st.stop()
if MODE == "github" and len(ADMIN_PASSWORD) < 12:
    st.error("Éles GitHub-módban legalább 12 karakteres adminjelszó kell.")
    st.stop()
try:
    store()
except StorageError as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.html('<div class="party-caption">NÉZETVÁLASZTÁS</div>')
    if MODE == "local":
        st.caption("🧪 Helyi tesztmód")
    view = st.radio("Nézet", ["🎮 Játékos", "🔐 Admin"], label_visibility="collapsed", key="view")
    st.caption("PUZZLE PARTY · V5")
st.html(header(admin=(view == "🔐 Admin")))
if view == "🔐 Admin":
    render_admin()
else:
    render_player()
