"""Avaliação mensal do recomendador — só com o que você realmente assistiu.

Rótulos (vindos do Stremio):
  positivo = assistiu >= 80% (ou marcou como visto / reassistiu) ou deu 👍/❤️
  negativo = parou nos primeiros 20%, há mais de 7 dias, sem reação

1) Offline (holdout): esconde 30% dos títulos rotulados, monta o perfil sem eles e pede ao
   scorer a P(gostar). Mede AUC, Brier e compara com um baseline (nota média do TMDB).
2) Online: cruza o histórico de recomendações dos últimos 30 dias com o que você assistiu
   DEPOIS de ter sido recomendado. Mede acertos por catálogo.

Imprime só agregados (o repositório é público). Uso:
  python -m my_stremio.evaluate [historico.jsonl]
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .pipeline import _title, _year, build_profile, collect_signals
from .scorers.base import get_scorer
from .tmdb import TMDB


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def label(it: dict, now: datetime) -> int | None:
    if it.get("reaction") or it.get("flagged_watched") or it.get("times_watched", 0) > 0:
        return 1
    p = it.get("progress")
    if p is None:
        return None
    if p >= 0.8:
        return 1
    last = _ts(it.get("last_watched"))
    if 0 < p <= 0.2 and last and now - last > timedelta(days=7):
        return 0
    return None


def auc(y: list[int], s: list[float]) -> float | None:
    pos = [b for a, b in zip(y, s) if a == 1]
    neg = [b for a, b in zip(y, s) if a == 0]
    if not pos or not neg:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def brier(y: list[int], s: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(y, s)) / len(y)


def out(text: str = "") -> None:
    print(text, flush=True)
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(text + "\n")


def offline(s, tmdb: TMDB, items: dict, labels: dict) -> None:
    out("## 1. Offline — holdout")
    keys = list(labels)
    if len(keys) < 20 or len(set(labels.values())) < 2:
        out(f"Poucos rótulos ({len(keys)}; precisa de 20+ com positivos e negativos). Pulando.\n")
        return
    rng = random.Random(datetime.now(timezone.utc).strftime("%Y-%m"))
    pos = [k for k in keys if labels[k] == 1]
    neg = [k for k in keys if labels[k] == 0]
    hold = rng.sample(pos, max(1, int(len(pos) * 0.3))) + rng.sample(neg, max(1, int(len(neg) * 0.3)))

    train = {k: v for k, v in items.items() if k not in set(hold)}
    profile, _, _ = build_profile(train)

    genres = {k: tmdb.genres(k) for k in ("movie", "tv")}
    payload, base = [], {}
    for kind, tid in hold:
        d = tmdb.details(kind, tid)
        payload.append({
            "tmdb_id": tid, "title": _title(d), "year": _year(d),
            "genres": [g["name"] for g in d.get("genres", [])] or
                      [genres[kind].get(g, "") for g in d.get("genre_ids", [])],
            "overview": d.get("overview", ""),
        })
        base[tid] = (d.get("vote_average") or 0) / 10
    scores = {x.tmdb_id: x.p_like for x in get_scorer(s).score(profile, payload)}

    y = [labels[k] for k in hold if k[1] in scores]
    pm = [scores[k[1]] for k in hold if k[1] in scores]
    pb = [base[k[1]] for k in hold if k[1] in scores]
    a_m, a_b = auc(y, pm), auc(y, pb)
    out(f"- Avaliados: **{len(y)}** ({sum(y)} positivos, {len(y) - sum(y)} negativos)")
    out(f"- AUC do modelo: **{a_m:.2f}** | baseline (nota TMDB): {a_b:.2f}  (0,5 = acaso, 1,0 = perfeito)")
    out(f"- Brier do modelo: **{brier(y, pm):.3f}** (quanto menor, melhor calibrado)")
    out(f"- P(gostar) média — positivos: {sum(p for p, t in zip(pm, y) if t) / max(1, sum(y)):.0%} | "
        f"negativos: {sum(p for p, t in zip(pm, y) if not t) / max(1, len(y) - sum(y)):.0%}\n")


def online(items: dict, labels: dict, hist_path: Path | None, now: datetime) -> None:
    out("## 2. Online — recomendações dos últimos 30 dias")
    if not hist_path or not hist_path.exists():
        out("Sem histórico de recomendações ainda.\n")
        return
    since = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    first: dict[tuple[str, int], dict] = {}
    for line in hist_path.read_text().splitlines():
        if not line.strip():
            continue
        day = json.loads(line)
        if day["date"] < since:
            continue
        for r in day["items"]:
            k = (r["kind"], r["tmdb_id"])
            if k not in first or r["rank"] < first[k]["rank"]:
                first[k] = {**r, "date": first.get(k, {}).get("date", day["date"])}
    out(f"- Títulos distintos recomendados: **{len(first)}**")

    per_cat: dict[str, list[int]] = {}
    plikes = {0: [], 1: []}
    for k, r in first.items():
        if k not in labels:
            continue
        last = _ts(items[k].get("last_watched"))
        if last and last.strftime("%Y-%m-%d") < r["date"]:
            continue  # já tinha visto antes da recomendação
        per_cat.setdefault(r["catalog"], []).append(labels[k])
        plikes[labels[k]].append(r["p_like"])

    total = sum(len(v) for v in per_cat.values())
    if not total:
        out("- Nenhum título recomendado foi assistido no período (normal com pouca frequência).\n")
        return
    hits = sum(sum(v) for v in per_cat.values())
    out(f"- Assistidos depois de recomendados: **{total}** | acertos: **{hits}** ({hits / total:.0%})")
    for cat, v in sorted(per_cat.items()):
        out(f"  - {cat}: {sum(v)}/{len(v)} acertos")
    if plikes[1] and plikes[0]:
        out(f"- P(gostar) média — acertos: {sum(plikes[1]) / len(plikes[1]):.0%} | "
            f"erros: {sum(plikes[0]) / len(plikes[0]):.0%}")
    out("")


def main() -> None:
    hist = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    now = datetime.now(timezone.utc)
    s = config.load()
    tmdb = TMDB(s.tmdb_read_token, s.language)
    items = collect_signals(s, tmdb)
    labels = {k: v for k, it in items.items() if (v := label(it, now)) is not None}
    out(f"# Avaliação do recomendador — {now:%Y-%m}\n")
    out(f"Rótulos do Stremio: **{sum(labels.values())}** positivos (≥80% ou 👍/❤️) | "
        f"**{len(labels) - sum(labels.values())}** negativos (parou ≤20%)\n")
    offline(s, tmdb, items, labels)
    online(items, labels, hist, now)


if __name__ == "__main__":
    main()
