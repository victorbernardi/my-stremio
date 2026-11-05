"""Pipeline diário: sinais -> perfil -> candidatos -> scoring -> addon estático.

Uso: python -m my_stremio.pipeline [pasta_saida]   (padrão: build/addon)
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import config, posters, stremio
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

    # Reações no Stremio: ❤️ = nota 10, 👍 = nota 8 (nota do TMDB, se houver, sobrescreve depois)
    by_imdb = {it["imdb_id"]: key for key, it in items.items() if it.get("imdb_id")}
    reactions = stremio.fetch_reactions(s.stremio_auth_key)
    for imdb_id, status in reactions.items():
        key = by_imdb.get(imdb_id)
        if not key:  # reagiu a algo que não está na biblioteca
            for kind in ("movie", "tv"):
                found = tmdb.find_imdb(imdb_id).get(f"{kind}_results", [])
                if found:
                    key = (kind, found[0]["id"])
                    items.setdefault(key, {"title": _title(found[0]), "year": _year(found[0]), "imdb_id": imdb_id})
                    break
        if key:
            items[key]["rating"] = 10 if status == "loved" else 8
            items[key]["reaction"] = status
    print(f"Reações Stremio: {sum(v == 'loved' for v in reactions.values())} amei | "
          f"{sum(v == 'liked' for v in reactions.values())} gostei")

    account_id, session_id = s.tmdb_account_id, s.tmdb_session_id
    if not session_id and s.tmdb_username and s.tmdb_password:
        account_id, session_id = tmdb.login(s.tmdb_username, s.tmdb_password)
    if not session_id:
        print("Aviso: sem acesso às notas do TMDB — usando só o histórico do Stremio.")
    if account_id and session_id:
        for kind, path in (("movie", "movies"), ("tv", "tv")):
            for r in tmdb.rated(account_id, session_id, path):
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
    favorites = [(k, l.split(" (")[0]) for r, l, k in loved[:15] if r >= 9]
    return profile, seeds, favorites


def gather_candidates(tmdb: TMDB, seeds, seen: set, limit: int) -> list[dict]:
    pool: dict[tuple[str, int], dict] = {}
    for kind, tid in seeds:
        for fn in (tmdb.recommendations, tmdb.similar):
            for c in fn(kind, tid):
                key = (kind, c["id"])
                if key in seen or c.get("vote_count", 0) < 50:
                    continue
                entry = pool.setdefault(key, {**c, "kind": kind, "hits": 0, "sources": set()})
                entry["hits"] += 1  # quantas sementes apontam pra ele
                entry["sources"].add((kind, tid))
    ranked = sorted(pool.values(), key=lambda c: (c["hits"], c.get("vote_average", 0)), reverse=True)
    return ranked[:limit]


CATALOGS = [
    ("para-voce", "Para Você"),
    ("porque-amou", "Porque você amou ❤️"),
    ("joias", "Joias escondidas"),
    ("fora-da-bolha", "Fora da bolha"),
]


def write_addon(out: Path, catalogs: dict[tuple[str, str], list[dict]]) -> None:
    """catalogs: {(stype, slug): metas}"""
    manifest = {
        "id": "com.victorbernardi.mystremio",
        "version": "1.1.0",
        "name": "Para Você",
        "description": "Recomendações pessoais geradas diariamente a partir do meu histórico e notas.",
        "resources": ["catalog"],
        "types": ["movie", "series"],
        "idPrefixes": ["tt"],
        "catalogs": [
            {"type": stype, "id": f"{slug}-{suffix}", "name": f"{name} — {label}"}
            for slug, name in CATALOGS
            for stype, suffix, label in (("movie", "filmes", "Filmes"), ("series", "series", "Séries"))
        ],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    for (stype, slug), metas in catalogs.items():
        suffix = "filmes" if stype == "movie" else "series"
        d = out / "catalog" / stype
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{slug}-{suffix}.json").write_text(json.dumps({"metas": metas}, ensure_ascii=False))


def addon_slug() -> str:
    """Caminho secreto do addon no Pages (sem ele, ninguém acha o catálogo). Nunca é impresso."""
    key = os.getenv("IMPORT_KEY")
    if not key:
        return ""
    slug = hashlib.sha256(f"my-stremio-addon:{key}".encode()).hexdigest()[:32]
    if os.getenv("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{slug}", flush=True)
    return slug


def main() -> None:
    site = Path(sys.argv[1] if len(sys.argv) > 1 else "build/addon")
    slug = addon_slug()
    out = site / slug if slug else site
    site.mkdir(parents=True, exist_ok=True)
    (site / ".nojekyll").write_text("")
    (site / "index.html").write_text("")
    s = config.load()
    tmdb = TMDB(s.tmdb_read_token, s.language)
    scorer = get_scorer(s)

    items = collect_signals(s, tmdb)
    profile, seeds, favorites = build_profile(items)
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

    by_id = {c["id"]: c for c in candidates if c["id"] in scores}
    p = lambda c: scores[c["id"]].p_like  # noqa: E731
    stype_of = lambda c: "movie" if c["kind"] == "movie" else "series"  # noqa: E731
    imdb_cache: dict[int, str | None] = {}

    def imdb_of(c) -> str | None:
        if c["id"] not in imdb_cache:
            imdb_cache[c["id"]] = tmdb.external_ids(c["kind"], c["id"]).get("imdb_id")
        return imdb_cache[c["id"]]

    def pick(pool, stype, n, note=lambda c: "") -> list[dict]:
        metas = []
        for c in sorted(pool, key=p, reverse=True):
            if stype_of(c) != stype or len(metas) >= n:
                continue
            imdb = imdb_of(c)
            if not imdb:
                continue
            sc = scores[c["id"]]
            extra = note(c)
            metas.append({
                "id": imdb, "type": stype, "name": _title(c),
                "poster": f"{IMG}{c['poster_path']}" if c.get("poster_path") else None,
                "releaseInfo": _year(c),
                "description": f"[{sc.p_like:.0%} · {sc.reason}]{' ' + extra if extra else ''} {c.get('overview', '')}",
                "_poster": {"imdb": imdb, "kind": c["kind"], "tmdb_id": c["id"],
                            "poster_path": c.get("poster_path"), "p_like": sc.p_like},
            })
        return metas

    pool = list(by_id.values())
    catalogs: dict[tuple[str, str], list[dict]] = {}
    day = datetime.now(timezone.utc).toordinal()

    for stype in ("movie", "series"):
        kind = "movie" if stype == "movie" else "tv"
        # 1) Para Você — o ranking geral
        catalogs[(stype, "para-voce")] = pick(pool, stype, s.catalog_size)

        # 2) Porque você amou X — um favorito diferente por dia
        favs = [(k, t) for k, t in favorites if k[0] == kind]
        favs = [(k, t) for k, t in favs if sum(k in c["sources"] for c in pool) >= 8] or favs
        if favs:
            fav_key, fav_title = favs[day % len(favs)]
            near = [c for c in pool if fav_key in c["sources"]]
            catalogs[(stype, "porque-amou")] = pick(near, stype, 30, lambda c, t=fav_title: f"Porque você amou {t}.")
        else:
            catalogs[(stype, "porque-amou")] = []

        # 3) Joias escondidas — você deve gostar, público aprova, pouca gente viu
        gems = [c for c in pool if c.get("vote_average", 0) >= 7.2 and c.get("vote_count", 0) < 1500 and p(c) >= 0.5]
        catalogs[(stype, "joias")] = pick(gems, stype, 30)

        # 4) Fora da bolha — fora dos 3 gêneros dominantes do seu ranking, mas com boa previsão
        top = catalogs[(stype, "para-voce")]
        counts: dict[int, int] = {}
        for m in top:
            for g in by_id[m["_poster"]["tmdb_id"]].get("genre_ids", []):
                counts[g] = counts.get(g, 0) + 1
        dominant = {g for g, _ in sorted(counts.items(), key=lambda x: -x[1])[:3]}
        outside = [c for c in pool if not dominant & set(c.get("genre_ids", [])) and p(c) >= 0.4]
        catalogs[(stype, "fora-da-bolha")] = pick(outside, stype, 30)

    # Snapshot do que foi recomendado hoje (para a avaliação mensal; vai criptografado)
    snap = os.getenv("SNAPSHOT_PATH")
    if snap:
        rows = [
            {"catalog": slug, "type": st, "rank": i, "tmdb_id": m["_poster"]["tmdb_id"],
             "kind": m["_poster"]["kind"], "imdb": m["id"], "p_like": round(m["_poster"]["p_like"], 4)}
            for (st, slug), metas in catalogs.items() for i, m in enumerate(metas, 1)
        ]
        Path(snap).write_text(json.dumps({"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "items": rows}))

    # Pôsteres com selo "% p/ você" + notas RT/IMDb/Metacritic (um por título, sem repetir)
    posters.mask_key()
    unique = {}
    for metas in catalogs.values():
        for m in metas:
            unique.setdefault(m["id"], m["_poster"])
    base = os.getenv("PAGES_BASE_URL", "https://victorbernardi.github.io/my-stremio") + (f"/{slug}" if slug else "")
    urls = posters.build(out, list(unique.values()), os.getenv("MDBLIST_API_KEY"), base,
                         datetime.now(timezone.utc).strftime("%Y%m%d"))
    for metas in catalogs.values():
        for m in metas:
            m.pop("_poster", None)
            m["poster"] = urls.get(m["id"], m["poster"])

    write_addon(out, catalogs)
    resumo = " | ".join(f"{slug}-{st}: {len(v)}" for (st, slug), v in catalogs.items())
    print(f"Addon gerado — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC | {resumo}")


if __name__ == "__main__":
    main()
