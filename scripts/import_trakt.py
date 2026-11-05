"""Importação única Trakt -> TMDB: notas e watchlist.

Entrada: JSON compacto {"ratings":[{"t":"movie|tv","id":<tmdb>,"v":1-10}], "watchlist":[{"t","id"}]}
Uso:     python scripts/import_trakt.py <arquivo.json>
Precisa de TMDB_READ_TOKEN, TMDB_USERNAME, TMDB_PASSWORD. Só imprime contagens (repo público).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from my_stremio.tmdb import TMDB  # noqa: E402


def main() -> None:
    data = json.load(open(sys.argv[1]))
    tmdb = TMDB(os.environ["TMDB_READ_TOKEN"])
    account_id, session_id = tmdb.login(os.environ["TMDB_USERNAME"], os.environ["TMDB_PASSWORD"])
    print(f"::add-mask::{session_id}", flush=True)

    ok = fail = 0
    for r in data["ratings"]:
        resp = tmdb.c.post(f"/{r['t']}/{r['id']}/rating", params={"session_id": session_id}, json={"value": r["v"]})
        if resp.status_code in (200, 201):
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)
    print(f"Notas: {ok} enviadas | {fail} falharam")

    ok = fail = 0
    for w in data["watchlist"]:
        resp = tmdb.c.post(
            f"/account/{account_id}/watchlist",
            params={"session_id": session_id},
            json={"media_type": w["t"], "media_id": w["id"], "watchlist": True},
        )
        if resp.status_code in (200, 201):
            ok += 1
        else:
            fail += 1
        time.sleep(0.15)
    print(f"Watchlist: {ok} adicionados | {fail} falharam")


if __name__ == "__main__":
    main()
