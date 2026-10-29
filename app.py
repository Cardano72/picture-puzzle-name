
import streamlit as st

# Oldal beállításai
st.set_page_config(
    page_title="Képrejtvény kihívás",
    page_icon="🧩",
    layout="centered"
)

# Játékos állapotának inicializálása
if "player" not in st.session_state:
    st.session_state.player = None

st.title("🧩 Képrejtvény kihívás")

# Belépőképernyő
if st.session_state.player is None:

    st.write("Üdvözlünk a játékban!")
    st.write("Add meg a neved a kezdéshez.")

    with st.form("login_form"):
        name = st.text_input("Játékos neve")
        submitted = st.form_submit_button(
            "Játék indítása",
            use_container_width=True
        )

    if submitted:
        if name.strip():
            st.session_state.player = name.strip()
            st.rerun()
        else:
            st.warning("Kérlek, adj meg egy nevet!")

# Játékos képernyője
else:

    st.success(f"Szia, {st.session_state.player}! 🎉")

    st.subheader("Készen állsz a játékra?")

    st.info(
        "Hamarosan itt jelennek meg a képrejtvények, "
        "a visszaszámláló és a pontszámok."
    )

    if st.button("Kilépés"):
        st.session_state.player = None
        st.rerun()
