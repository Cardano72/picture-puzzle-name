"""Képrejtvény V4 – közös időzítő, automatikus mentés, biztonságos visszacsatlakozás."""

import csv
import hmac
import io
import json
import random
import time
from pathlib import Path

import streamlit as st

from game_logic import (
    end_round, format_seconds, new_lobby, phase, remaining_seconds,
    score, send_message, set_remaining, start_round,
)
from resume_logic import (
    mark_final, new_resume_credentials, recover_player_id,
    valid_order, verify_resume, with_answer, with_position,
)
from storage import GitHubStore, LocalStore, StorageError

BASE_DIR = Path(__file__).resolve().parent
POLL_CACHE_SECONDS = 3.5  # Több munkamenetnek közös cache, GitHub-kímélő lekérdezés.

st.set_page_config(page_title="Képrejtvény kihívás", page_icon="🧩", layout="centered")


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
        # Ne engedjük egy már lezárt fordulóba késve beérkező módosítást.
        control = store().read_control()
        if not control or control["round_id"] != st.session_state.round_id or phase(control) != "running":
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
    messages = control.get("messages") or []
    if not messages:
        return
    latest = messages[-1]
    if st.session_state.get("seen_message") != latest["id"]:
        st.session_state.seen_message = latest["id"]
        st.toast("📣 Új adminüzenet érkezett!", icon="📣")
    st.info(f"📣 **Adminüzenet:** {latest['text']}")
    with st.expander("Korábbi adminüzenetek"):
        for msg in reversed(messages[:-1]):
            st.write(f"• {msg['text']}")


@st.fragment(run_every="1s")
def live_player_panel():
    """A számláló fragmentként frissül, nem írja át az aktív szövegmezőt."""
    try:
        latest = cached_control()
    except StorageError as exc:
        st.warning(f"A közös idő és az üzenetek átmenetileg nem érhetők el: {exc}")
        return
    if not latest:
        st.warning("Adminisztrátori beállításra várunk.")
        return
    if st.session_state.round_id != latest["round_id"]:
        st.rerun()
    current_phase = phase(latest)
    if current_phase == "lobby":
        st.info("⏳ Várakozás: az admin még nem indította el a fordulót.")
        show_messages(latest)
        return
    if current_phase == "running":
        if st.session_state.pop("was_waiting", False):
            st.rerun()
        st.metric("⏳ Közös hátralévő idő", format_seconds(remaining_seconds(latest)))
        show_messages(latest)
        return
    # A lejárást nem elég a cache-ből megállapítani, admin közben módosíthatta.
    if time.time() - st.session_state.get("last_end_check", 0) < 4:
        st.caption("Lejárat ellenőrzése…")
        return
    st.session_state.last_end_check = time.time()
    try:
        authoritative = store().read_control()
    except StorageError:
        st.warning("Kapcsolati hiba: a játék lezárását újraellenőrizzük.")
        return
    if authoritative and authoritative["round_id"] != st.session_state.round_id:
        st.rerun()
    if authoritative and phase(authoritative) == "finished":
        st.session_state.finished = True
        st.rerun()
    st.caption("Időmódosítás ellenőrzése…")


@st.fragment(run_every="3s")
def finished_round_watcher():
    try:
        latest = cached_control()
        if latest and latest["round_id"] != st.session_state.round_id:
            st.rerun()
        if latest:
            show_messages(latest)
    except StorageError:
        st.caption("A következő forduló ellenőrzése átmenetileg nem sikerült.")


def render_results():
    st.success(f"Véget ért a forduló, {st.session_state.player_name}!")
    try:
        # Kizárólag a távolról, sikeresen mentett válaszokat pontozzuk.
        saved = store().update_player(
            st.session_state.round_id, st.session_state.player_id, mark_final
        )
        st.session_state.answers = saved.get("answers") or {}
        st.session_state.finished = True
        st.caption("✅ Az eredmény központilag elmentve.")
    except (StorageError, ValueError) as exc:
        st.error(f"Nem sikerült véglegesíteni az eredményt: {exc}")
        if st.button("🔄 Véglegesítés újrapróbálása"):
            st.rerun()
        return
    result = score(PUZZLES, st.session_state.answers)
    one, two = st.columns(2)
    one.metric("Helyes megfejtés", f"{result['correct']} / {result['total']}")
    two.metric("Pontszám", result["points"])
    with st.expander("Megoldásaim"):
        from game_logic import is_correct
        for position in st.session_state.order:
            puzzle = PUZZLES[position]
            answer = st.session_state.answers.get(puzzle["id"], "")
            symbol = "✅" if is_correct(puzzle, answer) else "❌"
            st.write(f"{symbol} **{puzzle['title']}** — {answer or 'nincs válasz'} · helyes: {puzzle['answers'][0]}")
    st.info("A következő fordulót az admin indítja; az új fordulóhoz majd újra csatlakozhatsz.")
    finished_round_watcher()


def render_game():
    st.write(f"Játékos: **{st.session_state.player_name}**")
    live_player_panel()
    if st.session_state.get("finished"):
        return
    order = st.session_state.order
    index = st.session_state.position
    puzzle = PUZZLES[order[index]]
    answered = sum(bool(str(st.session_state.answers.get(p["id"], "")).strip()) for p in PUZZLES)
    st.progress(answered / len(PUZZLES), text=f"Sikeresen mentett válaszok: {answered}/{len(PUZZLES)}")
    st.subheader(f"{index + 1}. rejtvény / {len(PUZZLES)}")
    picture = BASE_DIR / puzzle["image"]
    if picture.is_file():
        st.image(str(picture), use_container_width=True)
    else:
        st.warning(f"Hiányzó képfájl: {puzzle['image']}")
    st.write(puzzle.get("question", "Mi a megfejtés?"))

    # A legutolsó, helyben szerkesztett választ a widget tartja meg egy mentési hiba esetén is.
    field_key = f"answer_{puzzle['id']}"
    if field_key not in st.session_state:
        st.session_state[field_key] = st.session_state.answers.get(puzzle["id"], "")
    st.text_input(
        "Megfejtés", key=field_key, max_chars=120,
        placeholder="Írd ide a választ…", live="1.5s",
        on_change=on_answer_change, args=(puzzle["id"], field_key),
        help="Rövid gépelési szünet után automatikusan a központi adattárba mentjük.",
    )
    if st.session_state.get("save_error"):
        st.error(f"⚠️ Nincs elmentve: {st.session_state.save_error}")
        if st.button("🔄 Mentés újrapróbálása", key=f"retry_{puzzle['id']}"):
            if save_answer(puzzle["id"], field_key):
                st.rerun()
    elif st.session_state.get("last_saved") and st.session_state.get("last_saved_puzzle") == puzzle["id"]:
        st.caption(f"✅ Automatikusan elmentve · {st.session_state.last_saved}")
    else:
        st.caption("A válasz beírása után kb. 1,5 másodperccel automatikus mentés történik.")

    left, mid, right = st.columns(3)
    back = left.button("⬅ Előző", disabled=index == 0, use_container_width=True)
    save = mid.button("💾 Mentés", use_container_width=True)
    next_ = right.button("Következő ➡", disabled=index == len(order) - 1, use_container_width=True)
    target = st.selectbox("Ugrás másik rejtvényhez", range(len(order)), index=index, format_func=lambda p: f"{p + 1}. rejtvény")
    jump = st.button("Ugrás", use_container_width=True)

    if back or next_ or jump or save:
        dest = index - 1 if back else index + 1 if next_ else target if jump else index
        if save_answer(puzzle["id"], field_key, position=dest):
            st.rerun()
        else:
            st.warning("Az oldalváltás előtt mentsd el a választ; ellenőrizd a kapcsolatot.")

    with st.expander("🔑 Visszatérés másik böngészőből"):
        st.write("Könyvjelzőzd ezt az oldalt, vagy másold le az alábbi visszatérési kódot. A kód birtokában bárki hozzáférhet a mentett játékmenetedhez!")
        st.code(st.session_state.resume_token, language=None)
        st.caption("A jelenlegi oldal URL-jében is szerepel a visszatérési kód. Ne oszd meg nyilvánosan.")


def render_player():
    st.header("🎮 Játék")
    if MODE == "local":
        st.caption("🧪 Helyi tesztmód — a mentés csak ezen a gépen történik.")
    try:
        control = cached_control()
    except StorageError as exc:
        st.error(f"Nem sikerült elérni a központi játékállapotot: {exc}")
        return
    if not control:
        st.info("A játék még nincs beállítva. Az admin felületen hozd létre az első fordulót.")
        return
    try:
        logged_in = try_restore(control)
    except StorageError as exc:
        st.error(f"A játékos visszaállítása sikertelen: {exc}")
        return
    if not logged_in:
        if phase(control) == "finished":
            st.info("Ez a forduló már véget ért. A következőre várunk.")
            return
        st.write(f"**{len(PUZZLES)} rejtvény** · Közös, admin által vezérelt időkeret")
        if phase(control) == "running":
            st.warning(f"A játék már elkezdődött. Becsatlakozhatsz, de csak {format_seconds(remaining_seconds(control))} időd marad.")
        with st.form("player_join"):
            name = st.text_input("Játékos neve", max_chars=30)
            join = st.form_submit_button("Csatlakozás", type="primary", use_container_width=True)
        if join:
            if not name.strip():
                st.warning("Adj meg egy nevet!")
            else:
                try:
                    enroll_player(control, name)
                    st.rerun()
                except StorageError as exc:
                    st.error(f"Nem sikerült a belépés mentése: {exc}")
        with st.expander("🔑 Már játszottam — visszalépés kóddal"):
            with st.form("resume_code_form"):
                entered = st.text_input("Visszatérési kód", type="password", max_chars=43)
                submit_resume = st.form_submit_button("Folytatás")
            if submit_resume:
                st.query_params.from_dict({"round": control["round_id"], "resume": entered.strip()})
                st.rerun()
        return

    st.write(f"Üdv, **{st.session_state.player_name}**!")
    if st.session_state.get("finished"):
        render_results()
        return
    if phase(control) == "lobby":
        st.session_state.was_waiting = True
        live_player_panel()
        st.caption("A játék az admin indításakor automatikusan megjelenik.")
        return
    if phase(control) == "finished":
        st.session_state.was_waiting = True
        live_player_panel()
        return
    render_game()

@st.fragment(run_every="1s")
def admin_live_status():
    try:
        control = cached_control()
        if not control:
            st.info("Nincs még létrehozott forduló")
            return
        current = phase(control)
        text = {"lobby": "Várakozás", "running": "Folyamatban", "finished": "Lezárult"}[current]
        st.write(f"**{control['round_number']}. forduló – {text}**")
        if current == "running":
            st.metric("Közös hátralévő idő", format_seconds(remaining_seconds(control)))
        st.caption(f"Fordulóazonosító: {control['round_id'][:8]}")
    except StorageError as exc:
        st.warning(f"Nem elérhető: {exc}")


def admin_action(callable_):
    try:
        callable_()
        st.rerun()
    except (ValueError, StorageError) as exc:
        st.error(str(exc))


def csv_bytes(records):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["helyezes", "nev", "helyes", "osszes", "pont", "megmentett_valaszok", "vegleges"])
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8-sig")


@st.fragment(run_every="30s")
def admin_leaderboard():
    try:
        control = cached_control()
        if not control:
            return
        st.button("🔄 Ranglista frissítése")  # Egy kattintás újrafuttatja a fragmentet.
        files = store().list_players(control["round_id"])
        rows = []
        for record in files:
            result = score(PUZZLES, record.get("answers") or {})
            rows.append({
                "nev": record.get("name", "?"), "helyes": result["correct"],
                "osszes": result["total"], "pont": result["points"],
                "megmentett_valaszok": result["answered"],
                "vegleges": "igen" if record.get("final") else "nem",
            })
        rows.sort(key=lambda r: (-r["pont"], -r["megmentett_valaszok"], r["nev"].casefold()))
        for rank, row in enumerate(rows, 1):
            row["helyezes"] = rank
        st.caption(f"{len(rows)} regisztrált játékos · A félkész eredmények is szerepelnek, a véglegesek külön jelölve.")
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
            st.download_button("⬇️ Ranglista CSV letöltése", csv_bytes(rows), file_name=f"ranglista-{control['round_id'][:8]}.csv", mime="text/csv")
            if phase(control) == "finished":
                with st.expander("🗑 Egyedi eredmény törlése (csak lezárt forduló)"):
                    records_by_id = {r["player_id"]: r for r in files}
                    selected_id = st.selectbox(
                        "Törlendő játékos", list(records_by_id.keys()),
                        format_func=lambda pid: f"{records_by_id[pid].get('name', '?')} ({pid[:8]})",
                    )
                    approve = st.checkbox("Megerősítem az eredmény törlését")
                    if st.button("Végleges eltávolítás az aktuális ranglistából", disabled=not approve):
                        try:
                            store().delete_player(control["round_id"], selected_id)
                            st.rerun()
                        except StorageError as exc:
                            st.error(f"Törlés sikertelen: {exc}")
        else:
            st.info("Még nem csatlakozott játékos.")
    except StorageError as exc:
        st.error(f"Nem sikerült lekérni az eredményeket: {exc}")


def render_admin():
    st.header("🔐 Adminisztráció")
    if not st.session_state.get("admin_authenticated"):
        with st.form("admin_signin"):
            password = st.text_input("Adminjelszó", type="password")
            login = st.form_submit_button("Belépés")
        if login:
            if hmac.compare_digest(password, ADMIN_PASSWORD):
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Hibás adminjelszó")
        return
    if st.button("🚪 Admin kijelentkezés"):
        st.session_state.admin_authenticated = False
        st.rerun()
    admin_live_status()
    try:
        control = cached_control()
    except StorageError as exc:
        st.error(f"Nem sikerült betölteni a játékállapotot: {exc}")
        return

    if not control:
        st.info("A játék első indítása előtt hozz létre egy üres fordulót.")
        if st.button("➕ Első forduló létrehozása", type="primary"):
            admin_action(lambda: change_control(lambda old: old or new_lobby()))
        return

    state = phase(control)
    st.subheader("⏱ Közös időzítés")
    if state == "lobby":
        with st.form("start_round"):
            minutes = st.number_input("Játékidő (perc)", min_value=1, max_value=180, value=5, step=1)
            start = st.form_submit_button("▶️ Forduló indítása", type="primary")
        if start:
            admin_action(lambda: change_control(lambda c: start_round(c, int(minutes))))
    elif state == "running":
        first, second = st.columns(2)
        if first.button("➕ +1 perc", use_container_width=True):
            admin_action(lambda: change_control(lambda c: set_remaining(c, remaining_seconds(c) + 60)))
        if second.button("➖ −1 perc", use_container_width=True):
            admin_action(lambda: change_control(lambda c: set_remaining(c, max(5, remaining_seconds(c) - 60))))
        with st.form("custom_duration"):
            minutes = st.number_input("Beállított hátralévő perc", min_value=0, max_value=360, value=5, step=1)
            seconds = st.number_input("És másodperc", min_value=0, max_value=59, value=0, step=1)
            set_clock = st.form_submit_button("Hátralévő idő beállítása")
        if set_clock:
            admin_action(lambda: change_control(lambda c: set_remaining(c, int(minutes) * 60 + int(seconds))))
        if st.button("⏹ Forduló azonnali lezárása"):
            admin_action(lambda: change_control(end_round))
    else:
        st.success("Az aktuális forduló véget ért.")

    st.subheader("📣 Üzenetküldés minden játékosnak")
    with st.form("broadcast", clear_on_submit=True):
        message = st.text_area("Üzenet", max_chars=250, height=90, placeholder="Például: Még két percetek van!")
        send = st.form_submit_button("📨 Üzenet küldése")
    if send:
        admin_action(lambda: change_control(lambda c: send_message(c, message)))
    if control.get("messages"):
        st.caption(f"Legutóbbi üzenet: {control['messages'][-1]['text']}")

    st.subheader("🏆 Közös ranglista")
    admin_leaderboard()

    st.subheader("🔄 Új forduló")
    st.caption("Az új forduló új azonosítót és üres ranglistát kap; a korábbi játékosfájlokat megőrizzük.")
    confirm = st.checkbox("Megerősítem, hogy új fordulót szeretnék indítani")
    if st.button("🆕 Új, üres forduló létrehozása", disabled=not confirm):
        admin_action(lambda: change_control(lambda c: new_lobby(c["round_number"] + 1)))


st.title("🧩 Képrejtvény kihívás")
if not ADMIN_PASSWORD:
    st.error("Hiányzik az ADMIN_PASSWORD. Másold a .streamlit/secrets.example.toml fájlt .streamlit/secrets.toml néven és állítsd be a jelszót.")
    st.stop()
if MODE == "github" and len(ADMIN_PASSWORD) < 12:
    st.error("Éles GitHub-módban legalább 12 karakteres adminjelszó szükséges.")
    st.stop()
if MODE == "local":
    st.sidebar.warning("🧪 Helyi tárolás (nem felhőbe való)")
try:
    store()  # Korán jelezzük a konfigurációs hibákat.
except StorageError as exc:
    st.error(str(exc))
    st.stop()
view = st.sidebar.radio("Nézet", ["🎮 Játékos", "🔐 Admin"], key="view")
if view == "🔐 Admin":
    render_admin()
else:
    render_player()
