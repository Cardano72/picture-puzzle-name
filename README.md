# 🧩 Képrejtvény-kihívás – V4

**Új a V3-hoz képest:** újracsatlakozás azonos játékosként és automatikus válaszmentés. Megmaradt a közös admin által indított időzítő, élő időmódosítás, üzenetküldés és külön privát GitHub-repositoryban tárolt eredmények rendszere.

## 1. Frissítés a V3-ról

1. Csomagold ki a ZIP-et, és **a meglévő `picture-puzzle-game` projektbe** másold át a fájlokat (az új `resume_logic.py` is fontos). A `.venv/` mappát és a saját `.streamlit/secrets.toml` fájlt **ne írd felül**.
2. A VS Code termináljában:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m streamlit run app.py
   ```

3. Indíts új fordulót az adminfelületen. **A V3 alatt létrehozott játékosrekordokhoz nincs visszatérési kód**, ezért az új csatlakozási funkció csak az V4-ben létrehozott játékosokra vonatkozik.
4. Ha helyben működik, `git add .`, `git commit -m "Add player resume and autosave"`, `git push`. A Streamlit Cloud a publikus kódrepo változásából frissül; nincs szükség új GitHub-tokenre.
5. **FONTOS:** a V4 `streamlit>=1.64,<2` csomagot kíván. A `st.text_input(live="1.5s")` korábbi Streamlit-verzióval hibát ad.

## 2. Játékosok újracsatlakozása

- A V4 csatlakozáskor generál egy **véletlen, 43 karakteres visszatérési kódot**, és beleírja az oldal címébe (`?round=...&resume=...`).
- Könyvjelzőzéssel, a cím elmentésével **ugyanazon a mobilon, oldalfrissítés után is** folytatható a játék; másik eszközön a teljes link megnyitásával vagy az elmentett kód beírásával is.
- A privát GitHub-adattárba **csak a kód SHA-256 lenyomata** kerül, az eredeti kód nem. Az eredményfájl neve a lenyomat 32 karakteres előtagja, így a név továbbra sem ütközik.
- Ugyanazok a válaszok, ugyanaz a véletlenszerű sorrend és az utolsó rejtvénypozíció töltődik vissza. A közös lejárati idő nem indul újra!
- Ha a közös forduló már lejárt, ugyanazzal a linkkel visszatérve a **végső eredmény** tekinthető meg.
- Egy új adminforduló **új belépést** kér. Régi linkkel nem lehet az új forduló régi válaszait felülírni.
- **A visszatérési kód titkos:** aki birtokolja a linket vagy a kódot, hozzáférhet ahhoz a játékosrekordhoz. Ne oszd meg nyilvános csoportban!
- **A közös QR-kódba kizárólag az alkalmazás alapcíme kerüljön**, például `https://keprejtveny-party.streamlit.app/` — **ne** a játékos személyes `?round=...&resume=...` címe!

## 3. Válaszok automatikus mentése

- A beviteli mező `live="1.5s"` beállításával a Streamlit **1,5 másodperc gépelési szünet után** elküldi az új szöveget a szervernek. A callback az adott rejtvény válaszát menti a privát GitHub JSON-fájlba, nem a teljes válaszlistát írja felül.
- Az **Előző / Következő / Ugrás / Mentés** gombok a mező aktuális értékét azonnal elküldik. Csak sikeres mentés után navigálunk.
- A képernyőn `✅ Automatikusan elmentve` vagy `⚠️ Nincs elmentve` és **Mentés újrapróbálása** jelenik meg.
- Ha egy másik lapon vagy eszközön ugyanazzal a visszatérési kóddal játszanak, a különböző rejtvények mentéseit **mezőnként egyesítjük**, így nem írják felül egymás válaszlistáját. **Ugyanazon feladatra** versengő írások közül a későbbi mentés lesz érvényes.
- A játék végén a **GitHubon ténylegesen mentett** válaszokat számoljuk. Ha a böngészőt az utolsó 1,5 másodperces gépelési szünet előtt bezárják, az utolsó néhány karakter elveszhet. Ezért a **Mentés** gombot is meghagytuk, főleg az utolsó másodpercekhez.
- GitHub-kapcsolati hiba esetén nem állítjuk, hogy mentettünk; a mező szövege helyben megmarad és újra küldhető, amíg a forduló aktív.

## 4. Teszteld ezt a forgatókönyvet

1. Indíts egy üres fordulót az adminfelületen, csatlakozz játékosként (a játékos böngészőben **mentsd el a linket**).
2. Admin oldalon indítsd el a fordulót 5 percre.
3. Írj be egy megfejtést; várj legalább 2 másodpercet. A mező alatt jelenjen meg a mentési visszajelzés, a privát repositoryban frissüljön a játékos JSON-jának `answers` mezője.
4. Ugrás a 3. rejtvényre, írj be még egy választ, majd nyomd meg a **Mentés** gombot.
5. **Frissítsd a játékos böngészőjét**. Ugyanazzal a névvel, válaszokkal, sorrenddel és pozícióval kell visszalépnie; az idő **nem** nullázódik.
6. A mentett linket próbáld ki inkognitóablakban is. Ott is ugyanaz a játékos nyíljon meg (ez bizonyítja, hogy a folytatás nem csak helyi cookie-n múlik).
7. Admin oldalon módosítsd a közös időt, küldj üzenetet, majd hagyd lejárni a fordulót. A játékos visszatérő linkje a végső eredményt mutassa.
8. Indíts új adminfordulót, és nyisd meg a régi mentett linket: a V4 jelezze, hogy az **előző fordulóhoz tartozik**.

## 5. Figyelmeztetések

- A GitHub Contents API nem valódi adatbázis. 10–20 játékosnak általában megfelelő, de a 1,5 másodperces debouncing ellenére sok gyors mentés API-korlátba ütközhet. A teljes terhelést teszteljétek egy éles próbafordulóban.
- A játékosok az `app.py` és `puzzles.json` publikus fájljait megtekinthetik. A helyes megoldások így megismerhetők. A baráti, kötetlen játékban ez tudatos kompromisszum.
- A GitHub-fájlokat a korábbi commitok is megőrizhetik. Használj beceneveket, ne gyűjts érzékeny személyes adatokat.
- Az admin központi időmódosítása és az üzenetek megjelenése továbbra is néhány másodpercet késhet; nem valódi push rendszer.
- Ha a forduló **lejárta után** érkezik meg egy válasz, azt a V4 elutasítja. Az ellenőrzés és a GitHub-írás között marad egy rövid technikai versenyhelyzet; komoly versenyhez valódi backend/adatbázis kell.
- A régi V3 rekordok formátuma nincs felülírva. Ha az újracsatlakozást akarod kipróbálni, **új fordulóban, új V4 játékosként lépj be**.

## 6. Tesztek

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest -q
```
