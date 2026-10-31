# 🧩 PUZZLE PARTY — V5 (Modern Party)

Magyar nyelvű, telefonra optimalizált, Python + Streamlit alapú képrejtvényjáték. A V5 **a V4 összes lényeges képességét megtartja**, és teljesen új, vörös–szürke–fekete (Audi/F1 hangulatú) felületet ad hozzá.

## Újdonságok a V5-ben

- Modern Party **reszponzív** megjelenés; különálló, fehér rejtvénykártya a képeknek és a megfejtésnek.
- **Váróterem**, amely a játékvezető rajtjelére automatikusan átvált a rejtvényekre.
- **Játékosfelület**: közös élő visszaszámláló, 5-ös rácsban számozott, tetszőlegesen választható feladatok, előző/következő gombok, automatikus mentés és beküldési visszajelzés (*rossz / közel / helyes*).
- **Admin dashboard**: közös óra, ±1 perc, pontos hátralévő idő, üzenetküldés, élő eredménylista és CSV-export.
- **Játék vége**: a játékos csak a lezárás tényét látja; részletes eredmény kizárólag az admin felületen jelenik meg.
- **Dobogó**: admin az *eredményhirdetéskor* teheti közzé vagy rejtheti el az admin nézetben.
- A HTML-ben szereplő játékosnevek és adminüzenetek biztonságosan HTML-escape-elve vannak.

Megmaradt: játékosonkénti véletlen sorrend, admin által indított közös időzítés, élő időmódosítás, központi adminüzenetek, külön JSON minden játékosnak, privát GitHub-repository, automatikus válaszmentés, személyes visszatérési link/kód, fordulóváltás, ranglista, adminjelszó és játékosok egyedi törlése.

## A V4 frissítése V5-re

1. **Készíts biztonsági másolatot** a V4-es helyi projektedről vagy commitold a jelenlegi változatot.
2. A ZIP-ben lévő fájlokat másold be a meglévő `picture-puzzle-game` mappába; a meglévő fájlok közül az `app.py` és `game_logic.py` lecserélendő, a `storage.py` és `resume_logic.py` kompatibilis a V4-gyel.
3. **Ne írd felül** a saját `.streamlit/secrets.toml` fájlodat, a `.venv/` mappát, illetve a testreszabott `puzzles.json` és `images/` fájlokat.
4. **Új fájlok**: `ui.py`, `leaderboard.py`, `styles/modern_party.css`, `.streamlit/config.toml`, `requirements-dev.txt` és az új teszt.
5. A már létrehozott privát `picture-puzzle-results` GitHub-repository és token továbbra is megfelelő. A korábbi fordulók és játékosfájlok formátumát nem kell migrálni. A `reveal_podium` mező hiánya az előző fordulókban egyszerűen `false` értéknek számít.

Projektstruktúra:

```text
picture-puzzle-game/
├── app.py
├── game_logic.py
├── leaderboard.py
├── resume_logic.py
├── storage.py
├── ui.py
├── puzzles.json
├── images/
│   └── saját képek (23 db, például 01_solution-name.png ... 23_solution-name.png)
├── styles/
│   └── modern_party.css
├── .streamlit/
│   ├── config.toml
│   └── secrets.example.toml
├── tests/
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── README.md
```

## Indítás Windows / VS Code alatt

A projekt gyökérmappájából, a Python 3.13-as `.venv` virtuális környezeteddel:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Böngésző: `http://localhost:8501`.

Ha még nincs `.streamlit/secrets.toml`, készíts másolatot a `.streamlit/secrets.example.toml` fájlról:

```toml
STORAGE_MODE = "local"
ADMIN_PASSWORD = "CSERELD_EROS_JELSZORA_123"
```

GitHub-adattároláshoz a saját (NEM nyilvános!) secrets fájlodban:

```toml
STORAGE_MODE = "github"
ADMIN_PASSWORD = "legalabb_12_karakteres_jelszo"
GITHUB_OWNER = "sajat_github_felhasznalonev"
GITHUB_REPO = "picture-puzzle-results"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = "github_pat_..."
```

A `secrets.toml` a `.gitignore` szabályával ki van zárva a feltöltésből. **Soha ne másold bele a tokent a `secrets.example.toml` vagy a `config.toml` fájlba!**

## Első V5 játék tesztelése

1. Nyisd meg a játékot **két külön böngésző-munkamenetben** (például normál és inkognitóablak), az admin és a játékos részére.
2. A bal felső menün keresztül válts az **Admin** nézetre, és jelentkezz be a jelszóval.
3. Hozz létre egy fordulót; a játékos ablakában add meg a nevet. A játékos **váróterembe** kerül.
4. Admin indítsa el az 5 perces játékot. A játékosnál a képrejtvények megnyílnak (néhány másodpercen belül).
5. Írj be egy választ; várj kb. **1 másodpercet**, hogy az automatikus mentés lefusson. Próbáld a számozott feladatugrást, a visszalépést és a Beküldés gombot is; a Beküldés külön visszajelzést ad (*rossz / közel / helyes*), de nem mutat teljes eredményt.
6. Mentsd el a játékos teljes `?round=...&resume=...` címét. Frissítés, bezárás, majd a link újranyitása után ugyanazok a válaszok és feladatsorrend jöjjön vissza.
7. Admin változtassa meg az időt, és küldjön üzenetet. A közös óra és üzenet a játékosnál frissül.
8. Várd meg a végét vagy zárd le adminból. A játékosnál csak a lezárás jelenjen meg, részletes pontszám és megoldáslista nélkül.
9. Admin nézetben ellenőrizd a **ranglistát és a dobogót**, majd válaszd a **Dobogó közzététele** funkciót.
10. Hozz létre új fordulót; annak a ranglistája legyen üres, a korábbi JSON-fájlok maradjanak meg a privát repositoryban.

## GitHub + Streamlit Cloud publikálás

Ha helyben minden működik:

```powershell
git status
git ls-files -- .streamlit/secrets.toml
# Az előző parancs kimenete legyen üres!
git add .
git commit -m "Modern Party V5 interface and podium"
git push
```

A Streamlit Community Cloud a publikus játékrepositoryból frissíti a futó alkalmazást. A Cloud **App settings → Secrets** beállításai maradjanak a korábban megadott értékeken; az adatokat továbbra is a privát `picture-puzzle-results` repository tárolja.

## Saját rejtvények

A `puzzles.json` lista minden eleme `id`, `title`, `image`, `question`, `answers` mezőket tartalmaz. Az `answers` listába több elfogadott változat is kerülhet. A válaszellenőrzés figyelmen kívül hagyja az ékezeteket, a nagybetűket, a szóközöket és egyes írásjeleket. Az `id`-k legyenek egyediek; **futó forduló alatt ne változtasd a rejtvények számát vagy sorrendjét**. A képfájlok elérési útjai a projekt gyökeréhez képest értendők.

## Mitől élő a rendszer?

A számlálót a Streamlit `st.fragment(run_every="1s")` frissíti; a központi óra admin által tárolt `deadline` időbélyegből számolódik. Az adminüzenetek és az időmódosítás az időnként lekért `control.json`-on keresztül jut el a játékosokhoz. Nem valódi WebSocket push: tipikusan néhány másodperces késés várható. A ranglista frissítése adminnál 30 másodperces, az egyes eredményfájlok lekérésén 25 másodperces cache van; kézi frissítés is elérhető.

## Fontos korlátok

- **GitHub Contents API ≠ adatbázis.** A JSON-fájlok külön mentődnek, de 10–20 játékossal is érdemes éles főpróbát tartani; gyors gépelés, sok mentés vagy ütköző műveletek esetén API-korlátok léphetnek fel.
- Az automatikus mentés **1 másodperces gépelési szünet után** indul; ha valaki gyorsan bezárja a böngészőt vagy lejár az idő, a legutóbbi néhány karakter elveszhet. A Beküldés gomb menti az aktuális mezőt, majd azonnali *rossz / közel / helyes* visszajelzést ad az aktuális feladványra.
- Az `app.py` és a `puzzles.json` a publikus kódrepositoriban **bárki számára olvasható**. Baráti játékra jó kompromisszum, de komoly, csalásbiztos versenyhez privát válaszellenőrzés és valódi backend szükséges.
- **Visszatérési kód**: titkos jogosultsági kulcs, aki ismeri, hozzáférhet a mentett játékhoz. A közös QR-kódba csak a Streamlit app alap URL-jét tedd.
- A GitHub-kapcsolat és a Streamlit feldolgozás időigénye miatt az idő lejárásának pillanatában lehet egy rövid versenyhelyzet. A program ellenőrzi az aktív fordulót mentés előtt, de garantáltan csalásbiztos megoldáshoz adatbázis-tranzakció kellene.
- Egy korábbi commit a GitHubon törölt eredmények adatait továbbra is tartalmazhatja, ezért érdemes csak beceneveket gyűjteni.
- A felhasználói felület **nem lett valós böngészőben end-to-end tesztelve ezen a készítési környezeten belül**; a projekt szintaxisa, backendje és HTML-generálása automatikusan tesztelve van. Éles parti előtt futtasd végig a fenti próbafordulót.

## Automatizált tesztek

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

A tesztek a közös időt, a késleltetett válaszok elutasítását, a pontozást, a lokális/GitHub JSON-kezelést, a visszacsatlakozási kulcsot, az adatok megőrzését, a dobogó közzétételi szabályát és a HTML-szövegek escape-elését vizsgálják.
