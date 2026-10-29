# Képrejtvény kihívás – 2. mérföldkő

Python + Streamlit demó: véletlen sorrend, visszaszámláló, rejtvények közötti navigálás, válaszmentés és pontozás.

## Helyi indítás (Windows, már meglévő 3.13-as .venv környezetből)

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Az alkalmazás a http://localhost:8501 címen nyílik meg.

## Saját képek használata

1. Másold a PNG/JPG képeket az `images/` mappába.
2. A `puzzles.json` fájlban módosítsd az `image`, `title`, `question`, `answers` mezőket.
3. Minden `id` legyen egyedi, és az `answers` mindig lista maradjon.
4. A játékidő és pontérték az `app.py` elején módosítható.

A program a válaszok összehasonlításakor figyelmen kívül hagyja a szóközöket, írásjeleket, ékezeteket és a kis-/nagybetűket.

**FONTOS:** ez még helyi demonstráció. Nem történik tartós mentés, GitHub-eredményfeltöltés vagy admin jogosultság-ellenőrzés. Az oldal frissítése új munkamenetet indíthat, így elveszhet a folyamat. Az eredeti válaszokat a nyilvános `puzzles.json` tartalmazza; versenyszerű változatban ezeket védeni kell.
