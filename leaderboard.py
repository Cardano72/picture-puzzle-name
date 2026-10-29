"""Sorting and ranking game results. Pure, testable functions."""
from game_logic import score


def leaderboard_rows(puzzles, records):
    rows = []
    for record in records:
        results = score(puzzles, record.get("answers") or {})
        rows.append({
            "player_id": record.get("player_id", ""),
            "nev": record.get("name", "?"),
            "helyes": results["correct"],
            "osszes": results["total"],
            "pont": results["points"],
            "megmentett_valaszok": results["answered"],
            "vegleges": "igen" if record.get("final") else "nem",
        })
    rows.sort(key=lambda r: (-r["pont"], -r["megmentett_valaszok"], r["nev"].casefold()))
    for place, row in enumerate(rows, 1):
        row["helyezes"] = place
    return rows
