"""Képrejtvény: közös admin-időzítés, üzenetek, tartós eredmények."""

import csv
import hmac
import io
import json
import random
import time
import uuid
from pathlib import Path

import streamlit as st

from game_logic import (
    end_round,
    format_seconds,
    new_lobby,
    phase,
    remaining_seconds,
    score,
    send_message,
    set_remaining,
    start_round,
)
from storage import GitHubStore, LocalStore, StorageError

BASE_DIR = Path(__file__).resolve().parent
POLL_CACHE_SECONDS = 3.5  # GitHub API-t a felhasználók között közösen cache-eljük.

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
    """1 közös GitHub-lekérés / ~4 mp / Streamlit szerverfolyamat."""
    return store().read_control()


def change_control(transform):
    updated = store().update_control(transform)
    cached_control.clear()
    return updated


def load_puzzles():
    with (BASE_DIR / "puzzles.json").open(encoding="utf-8") as handle:
        result = json.load(handle)
    if not result or len({p["id"] for p in result}) != len(result):
        raise ValueError("Nem üres, egyedi ID-kat tartalmazó puzzles.json szükséges")
    return result


PUZZLES = load_puzzles()


def player_record(final=False):
    """Egyedi játékosfájl: minden mentéskor ugyanaz a fájl frissül."""
    return {
        "round_id": st.session_state.round_id,
        "player_id": st.session_state.player_id,
        "name": st.session_state.player_name,
        "answers": dict(st.session_state.answers),
        "final": bool(final),
        "updated_at": time.time(),
    }


def enroll_player(control, name):
    """Új vagy új fordulóba átlépő játékos."""
    old_state = {
        key: st.session_state.get(key)
        for key in ("player_id", "player_name", "round_id", "order", "position", "answers", "finished", "final_uploaded", "seen_message")
    }
    st.session_state.player_id = uuid.uuid4().hex
    st.session_state.player_name = name.strip()
    st.session_state.round_id = control["round_id"]
    st.session_state.order = random.sample(range(len(PUZZLES)), len(PUZZLES))
    st.session_state.position = 0
    st.session_state.answers = {}
    st.session_state.finished = False
    st.session_state.final_uploaded = False
    st.session_state.seen_message = None
    try:
        store().save_player(player_record())
    except StorageError:
        for key, value in old_state.items():
            if value is None:
                st.session_state.pop(key, None)
            else:
                st.session_state[key] = value
        raise


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
    """Közös óra és adminüzenetek; a feladatbeviteli formhoz nem nyúl."""
    try:
        latest = cached_control()
    except StorageError as exc:
        st.warning(f"A központi idő és az üzenetek átmenetileg nem érhetők el: {exc}")
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
            st.rerun()  # A váróképernyőt teljes játékfelületté váltjuk.
        remaining = remaining_seconds(latest)
        st.metric("⏳ Közös hátralévő idő", format_seconds(remaining))
        show_messages(latest)
        return
    # Expirációnál friss (nem cache-elt) ellenőrzés: az admin közben meghosszabbíthatta.
    # Sikertelen hálózatnál nem pontozunk feltételezett lejárat alapján.
    if time.time() - st.session_state.get("last_end_check", 0.0) < 4:
        st.warning("Lejárat ellenőrzése…")
        return
    st.session_state.last_end_check = time.time()
    try:
        authoritative = store().read_control()
    except StorageError:
        st.warning("Kapcsolati hiba: a játék lezárását újraellenőrizzük.")
        return
    if authoritative and authoritative["round_id"] == st.session_state.round_id and phase(authoritative) == "finished":
        st.session_state.finished = True
        st.rerun()
    if authoritative and authoritative["round_id"] != st.session_state.round_id:
        st.rerun()
    st.info("Az admin időmódosításának ellenőrzése folyamatban…")


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
    result = score(PUZZLES, st.session_state.answers)
    one, two = st.columns(2)
    one.metric("Helyes megfejtés", f"{result['correct']} / {result['total']}")
    two.metric("Pontszám", result["points"])
    if not st.session_state.get("final_uploaded", False):
        try:
            store().save_player(player_record(final=True))
            st.session_state.final_uploaded = True
        except StorageError as exc:
            st.error(f"Az eredmény még nincs véglegesen elmentve: {exc}")
            if st.button("🔄 Eredmény újraküldése"):
                st.rerun()
    if st.session_state.get("final_uploaded"):
        st.caption("✅ Az eredmény a közös adattárba került.")
    with st.expander("Megoldásaim"):
        for position in st.session_state.order:
            puzzle = PUZZLES[position]
            answer = st.session_state.answers.get(puzzle["id"], "")
            from game_logic import is_correct
            symbol = "✅" if is_correct(puzzle, answer) else "❌"
            st.write(f"{symbol} **{puzzle['title']}** — {answer or 'nincs válasz'} · helyes: {puzzle['answers'][0]}")
    st.info("Az új fordulót az admin indítja. A fordulóváltást az alkalmazás automatikusan érzékeli.")
    finished_round_watcher()


def render_game():
    st.write(f"Játékos: **{st.session_state.player_name}**")
    live_player_panel()
    if st.session_state.get("finished", False):
        return
    order = st.session_state.order
    index = st.session_state.position
    puzzle = PUZZLES[order[index]]
    answered = sum(bool(str(st.session_state.answers.get(p["id"], "")).strip()) for p in PUZZLES)
    st.progress(answered / len(PUZZLES), text=f"Mentett válaszok: {answered}/{len(PUZZLES)}")
    st.subheader(f"{index + 1}. rejtvény / {len(PUZZLES)}")
    picture = BASE_DIR / puzzle["image"]
    if picture.is_file():
        st.image(str(picture), use_container_width=True)
    else:
        st.warning(f"Hiányzó képfájl: {puzzle['image']}")
    st.write(puzzle.get("question", "Mi a megfejtés?"))
    with st.form(f"answer_{st.session_state.round_id}_{puzzle['id']}"):
        answer = st.text_input(
            "Megfejtés", value=st.session_state.answers.get(puzzle["id"], ""),
            placeholder="Írd ide a választ…", max_chars=120,
        )
        left, middle, right = st.columns(3)
        previous = left.form_submit_button("⬅ Előző", disabled=index == 0, use_container_width=True)
        save = middle.form_submit_button("💾 Mentés", use_container_width=True)
        following = right.form_submit_button("Következő ➡", disabled=index == len(order) - 1, use_container_width=True)
        target = st.selectbox("Ugrás másik rejtvényhez", options=range(len(order)), index=index, format_func=lambda p: f"{p + 1}. rejtvény")
        jump = st.form_submit_button("Ugrás és mentés")
    if not any((previous, save, following, jump)):
        st.caption("A gombok mentik az aktuális választ. Lejáratkor a legutolsó mentett állapot számít.")
        return
    try:
        latest = store().read_control()  # A mentés előtt szerveroldali időellenőrzés.
        if not latest or latest["round_id"] != st.session_state.round_id or phase(latest) != "running":
            st.warning("A forduló már nem aktív, új választ nem mentünk.")
            cached_control.clear()
            st.rerun()
        updated_answers = dict(st.session_state.answers)
        updated_answers[puzzle["id"]] = answer.strip()
        record = player_record(final=False)
        record["answers"] = updated_answers
        store().save_player(record)
        st.session_state.answers = updated_answers
        if previous:
            st.session_state.position -= 1
        elif following:
            st.session_state.position += 1
        elif jump:
            st.session_state.position = target
        st.rerun()
    except StorageError as exc:
        st.error(f"Mentési hiba: {exc}. Ellenőrizd a kapcsolatot, majd nyomd meg újra a Mentés gombot.")


def render_player():
    st.header("🎮 Játék")
    if MODE == "local":
        st.caption("🧪 Helyi tesztmód — az eredmények csak ezen a gépen tárolódnak.")
    try:
        control = cached_control()
    except StorageError as exc:
        st.error(f"Nem sikerült elérni a központi játékállapotot: {exc}")
        return
    if not control:
        st.info("A játék még nincs beállítva. Az admin felületen hozd létre az első fordulót.")
        return
    if "player_name" not in st.session_state:
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
        return

    if st.session_state.get("round_id") != control["round_id"]:
        try:
            enroll_player(control, st.session_state.player_name)
        except StorageError as exc:
            st.error(f"Új fordulóba belépés sikertelen: {exc}")
            return
        st.rerun()

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
        # A lejáratot friss GitHub-olvasással ellenőrizzük a fragmentben.
        # Ha az admin közben hosszabbított, visszaváltunk a feladatokra.
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
