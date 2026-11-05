"""Pipeline diário: sinais -> perfil -> candidatos -> scoring -> addon estático.

Uso: python -m my_stremio.pipeline [pasta_saida]   (padrão: build/addon)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, stremio
from .scorers.base import get_scorer
from .tmdb import TMDB

KINDS = {"movie": "movie", "series": "tv"}  # tipo Stremio -> tipo TMDB
IMG = "https://image.tmdb.org/t/p/w342"


def _title(x: dict) -> str:
    return x.get("title") or x.get("name") or "?"


def _year(x: dict) -> str:
    return (x.get("release_date") or x.get("first_air_date") or "")[:4]


def collect_signals(s, tmdb: TMDB) -> dict:
    """Une biblioteca Stremio (implícito) e notas TMDB (explícito) por (kind, tmdb_id)."""
    items: dict[tuple[str, int], dict] = {}

    for raw in stremio.fetch_library(s.stremio_auth_key):
        sig = stremio.to_signal(raw)
        kind = KINDS.get(sig["type"])
        if not kind or not (sig["imdb_id"] or "").startswith("tt"):
            continue
        found = tmdb.find_imdb(sig["imdb_id"]).get(f"{kind}_results", [])
        if found:
            items[(kind, found[0]["id"])] = {"title": sig["name"], **sig}

    if s.tmdb_account_id and s.tmdb_session_id:
        for kind, path in (("movie", "movies"), ("tv", "tv")):
            for r in tmdb.rated(s.tmdb_account_id, s.tmdb_session_id, path):
                key = (kind, r["id"])
                items.setdefault(key, {"title": _title(r)})
                items[key]["rating"] = r.get("rating")
                items[key]["year"] = _year(r)
    return items


def build_profile(items: dict) -> tuple[str, list[tuple[str, int]]]:
    """Perfil em texto para o scorer + sementes para gerar candidatos."""
    loved, hated, watched, abandoned = [], [], [], []
    for key, it in items.items():
        r, p = it.get("rating"), it.get("progress")
        label = f"{it['title']} ({it.get('year', '')})".replace(" ()", "")
        if r is not None and r >= 8:
            loved.append((r, label, key))
        elif r is not None and r <= 5:
            hated.append((r, label))
        elif it.get("flagged_watched") or it.get("times_watched", 0) > 0 or (p or 0) >= 0.8:
            watched.append((it.get("last_watched") or "", label, key))
        elif p is not None and 0 < p < 0.3:
            abandoned.append(label)

    loved.sort(reverse=True)
    watched.sort(reverse=True)
    profile = "\n".join([
        "AMA (nota >= 8): " + "; ".join(f"{l} [{r}]" for r, l, _ in loved[:40]),
        "ODEIA (nota <= 5): " + "; ".join(f"{l} [{r}]" for r, l in hated[:20]),
        "ASSISTIU RECENTEMENTE (sem nota): " + "; ".join(l for _, l, _ in watched[:20]),
        "ABANDONOU NO INÍCIO: " + "; ".join(abandoned[:15]),
    ])
    seeds = [k for _, _, k in loved[:15]] + [k for _, _, k in watched[:10]]
    return profile, seeds


def gather_candidates(tmdb: TMDB, seeds, seen: set, limit: int) -> list[dict]:
    pool: dict[tuple[str, int], dict] = {}
    for kind, tid in seeds:
        for fn in (tmdb.recommendations, tmdb.similar):
            for c in fn(kind, tid):
                key = (kind, c["id"])
                if key in seen or c.get("vote_count", 0) < 50:
                    continue
                entry = pool.setdefault(key, {**c, "kind": kind, "hits": 0})
                entry["hits"] += 1  # quantas sementes apontam pra ele
    ranked = sorted(pool.values(), key=lambda c: (c["hits"], c.get("vote_average", 0)), reverse=True)
    return ranked[:limit]


def write_addon(out: Path, ranked: dict[str, list[dict]]) -> None:
    manifest = {
        "id": "com.victorbernardi.mystremio",
        "version": "1.0.0",
        "name": "Para Você",
        "description": "Recomendações pessoais geradas diariamente a partir do meu histórico e notas.",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "idPrefixes": ["tt"],
        "catalogs": [
            {"type": "movie", "id": "para-voce-filmes", "name": "Para Você — Filmes"},
            {"type": "series", "id": "para-voce-series", "name": "Para Você — Séries"},
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    for stype, cid in (("movie", "para-voce-filmes"), ("series", "para-voce-series")):
        d = out / "catalog" / stype
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{cid}.json").write_text(json.dumps({"metas": ranked[stype]}, ensure_ascii=False))
    (out / ".nojekyll").write_text("")


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/addon")
    s = config.load()
    tmdb = TMDB(s.tmdb_read_token, s.language)
    scorer = get_scorer(s)

    items = collect_signals(s, tmdb)
    profile, seeds = build_profile(items)
    print(f"Sinais: {len(items)} títulos | sementes: {len(seeds)}")
    if not seeds:
        raise SystemExit("Sem sementes: avalie títulos no TMDB ou assista algo no Stremio.")

    candidates = gather_candidates(tmdb, seeds, set(items), s.candidates_per_run)
    genres = {k: tmdb.genres(k) for k in ("movie", "tv")}
    payload = [
        {
            "tmdb_id": c["id"],
            "title": _title(c),
            "year": _year(c),
            "genres": [genres[c["kind"]].get(g, "") for g in c.get("genre_ids", [])],
            "overview": c.get("overview", ""),
        }
        for c in candidates
    ]
    scores = {sc.tmdb_id: sc for sc in scorer.score(profile, payload)}
    print(f"Candidatos: {len(candidates)} | pontuados: {len(scores)}")

    ranked: dict[str, list[dict]] = {"movie": [], "series": []}
    for c in sorted(candidates, key=lambda c: scores[c["id"]].p_like if c["id"] in scores else 0, reverse=True):
        stype = "movie" if c["kind"] == "movie" else "series"
        if len(ranked[stype]) >= s.catalog_size or c["id"] not in scores:
            continue
        imdb = tmdb.external_ids(c["kind"], c["id"]).get("imdb_id")
        if not imdb:
            continue
        sc = scores[c["id"]]
        ranked[stype].append({
            "id": imdb,
            "type": stype,
            "name": _title(c),
            "poster": f"{IMG}{c['poster_path']}" if c.get("poster_path") else None,
            "releaseInfo": _year(c),
            "description": f"[{sc.p_like:.0%} · {sc.reason}] {c.get('overview', '')}",
        })

    write_addon(out, ranked)
    print(f"Addon gerado em {out} — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | "
          f"filmes: {len(ranked['movie'])} | séries: {len(ranked['series'])}")


if __name__ == "__main__":
    main()
