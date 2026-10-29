# 🧩 Képrejtvény-kihívás – 3. mérföldkő

**Streamlit + közös admin által indított forduló + közös időzítő + adminüzenetek + privát GitHub JSON-eredmények.**

## Hogyan működik?

- A játékos nevet ír be, egyedi játékosazonosítóval csatlakozik a közös fordulóhoz.
- Az **admin egyetlen közös fordulót indít**. Az összes játékos ugyanahhoz a `deadline` időponthoz igazodik, függetlenül attól, mikor csatlakozott.
- Az admin aktív fordulóban ±1 perccel, illetve megadott percre/másodpercre állíthatja a hátralévő időt. Az óra a játékosoknál automatikusan igazodik.
- Az admin a forduló során 250 karakteres üzeneteket küldhet. A játékosoknál a legutóbbi üzenet és az előzmények automatikusan frissülnek.
- A válaszokat **a Mentés / Előző / Következő / Ugrás** műveletek elküldik a közös adattárba. A játékos minden mentéskor a saját JSON-fájlját frissíti.
- A lejáratkor a játékos saját pontszámot lát; a korábban mentett válaszok akkor is megmaradnak, ha a böngészőt bezárja.
- Az admin ranglistája az aktuális forduló JSON-fájljait olvassa (automatikus frissítés 30 másodpercenként és kézi gombbal), CSV-be exportálható.
- **Új forduló:** új `round_id`, üres ranglista; a régi fájlok megmaradnak az archívumban. Lezárt fordulóban az admin egyedi eredményt is törölhet a ranglistából.

**Üzenet / óra:** a Streamlit `st.fragment` másodpercenként újrarajzolja a kijelzőt. A központi állapotot a szerver maximum kb. 3,5 másodpercig cache-eli, így egy új adminüzenet vagy időmódosítás tipikusan 1–5 másodpercen belül látszik. Ez nem WebSocket-alapú azonnali push.

## 1. Helyi teszt – GitHub-token nélkül

A `picture-puzzle-game` VS Code mappádban cseréld le / másold be e csomag fájljait (a `.venv` mappát hagyd meg).

1. Hozd létre a `.streamlit` könyvtárat (a csomagban már megvan).
2. Másold a `.streamlit/secrets.example.toml` fájlt `.streamlit/secrets.toml` névre.
3. Helyi teszthez maradjon `STORAGE_MODE = "local"`; írd át az `ADMIN_PASSWORD` értékét egy saját, hosszú jelszóra.
4. A VS Code PowerShell termináljában:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

5. `http://localhost:8501` → oldalsáv **Admin** → jelszó → **Első forduló létrehozása** → másik böngésző / inkognitó ablakban játékosként csatlakozás → adminnál **Forduló indítása**.
6. Játék közben próbáld az időmódosítást és az üzenetküldést. Egy második, privát ablakban megnyithatod másik játékosként is.

Helyi módban a közös állapotot és a ranglistát `local_data/` mappában tároljuk. Ez a mappa a `.gitignore` miatt nem kerül fel GitHubra.

## 2. Éles telepítés GitHub-adattárral

A **már meglévő, publikus** `picture-puzzle-game` (Python-kód) mellé hozz létre egy **privát** repositoryt, például `picture-puzzle-results` néven. Létrehozáskor legyen **README fájlja**, hogy létezzen a `main` branch.

1. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens** → **Generate new token**.
2. Repository access: **Only select repositories** → kizárólag `picture-puzzle-results`.
3. Permissions → Repository permissions → **Contents: Read and write**. Ha a GitHub alapból megad egy `Metadata: Read` jogosultságot, az normális.
4. Válassz lejárati időt és generáld le a tokent. Biztonságosan mentsd el; a repo fájljaiba **soha ne másold be**.
5. A helyi `.streamlit/secrets.toml` tartalmát állítsd át az alábbira:

```toml
STORAGE_MODE = "github"
ADMIN_PASSWORD = "ide_egy_sajat_eros_legalabb_12_karakteres_jelszo"
GITHUB_OWNER = "SAJAT_GITHUB_FELHASZNALONEVED"
GITHUB_REPO = "picture-puzzle-results"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = "github_pat_..."
```

6. **Indítsd újra** a Streamlit szervert (`Ctrl+C`, majd `streamlit run`), hogy biztosan az új titkos beállítások lépjenek életbe.
7. Tesztelj: admin hozza létre a fordulót, egy játékos csatlakozik. A privát repo automatikusan létrehozza a `control.json` és `results/<round_id>/<player_id>.json` fájlokat.
8. Publikálás: kódcommit és push a **publikus kódrepo** `main` ágára, majd a [Streamlit Community Cloud](https://share.streamlit.io/) oldalán válaszd ezt a repositoryt, a fő fájl `app.py`.
9. A Streamlit Cloud alkalmazás **Advanced settings / Secrets** részébe másold át az 5 GitHub-beállítást és az adminjelszót a TOML-ból, majd Deploy. **Az adatokat tároló privát repositoryt nem kell hozzákapcsolni a Cloudhoz**: az alkalmazás a privát token segítségével kommunikál vele.
10. A kapott `*.streamlit.app` linkből QR-kódot készíthetsz.

A helyi `.streamlit/secrets.toml` **szigorúan privát**, a `.gitignore` kizárja a Gitről.

## Fájlstruktúra

```
picture-puzzle-game/
├── app.py                  # Streamlit UI (játék és admin)
├── game_logic.py           # időzítés, pontozás, üzenetlogika
├── storage.py              # GitHub / helyi JSON adattár
├── puzzles.json            # rejtvények és helyes válaszok
├── images/                 # képrejtvények
├── .streamlit/
│   ├── secrets.example.toml # sablon, verziókövetett
│   └── secrets.toml         # saját titkos beállítás; NEM verziókövetett
├── requirements.txt
├── .gitignore
└── tests/                  # ellenőrző tesztek
```

## Megfontolások és korlátok

- A válaszok csak **gombnyomáskor** kerülnek szerverre; az utoljára beírt, még nem mentett karakterek lejáratkor nem számítanak.
- Ha a játékos bezárja a böngészőt a lejárat előtt, a **legutolsó mentett** válaszok megmaradnak az admin ranglistájában; az eredmény `vegleges = nem` jelzést kap, mivel a böngésző már nem tud automatikusan véglegesíteni.
- A böngészőfrissítés új Streamlit-munkamenetet hozhat létre. Az előző eredmények a privát adattárban megmaradnak, de a játékos jelenleg **nem tud automatikusan ugyanazzal az azonosítóval visszalépni**; az új névvel történő belépés duplikált rekordot hozhat létre.
- Ha többen ugyanazt a nevet írják be, külön rekordokként szerepelnek (az egyedi ID miatt). Szükség esetén később bevezethető regisztrációs kód vagy névellenőrzés.
- Az adminisztrátori jogosultság **jelszavas, baráti társaságra szánt**. Nem nyilvános nagy versenyekhez, ahol több jogosultsági szint és teljes audit szükséges.
- A privát GitHub repo nem valódi realtime adatbázis: kisebb csoporthoz és rövidebb alkalmi játékhoz célszerű. A központi állapot rövid cache-elése csökkenti az API-kéréseket, de sok egyidejű játékos vagy nagyon gyors mentési ritmus GitHub API-korlátokhoz vezethet.
- Az admin **lejárat előtt** hosszabbíthat. Ha a lejárat már megtörtént, a játéknak vége; új fordulót kell indítani. Az utolsó néhány másodpercben beállított időcsere néhány kliensnél késleltetve jelenhet meg, ezért érdemes előbb hosszabbítani.
- A publikus kódrepo `puzzles.json` fájljából a helyes válaszok megismerhetők. Komoly versenyben ezt külön privát tárba kell helyezni.
- A Streamlit Cloud szabad erőforrásai / app-alvás miatt az oldal felébredése késleltethet. A közös lejárati idő ettől nem tolódik el, de a beérkező adminüzenetek megjelenése késhet.
- A GitHub által törölt fájlok a commit-történetben megmaradnak. A **következő forduló** ezért nem törléssel, hanem új azonosítóval indul.

## Egyszerű tesztek

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```
