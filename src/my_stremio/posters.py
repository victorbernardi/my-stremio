"""Pôsteres do "Para Você" com notas da crítica (MDBList) + chance de você gostar (Jev).

A chave do MDBList vai na query string — por isso nenhum erro aqui imprime URL.
"""
import io
import os
import time
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont

MDBLIST = "https://api.mdblist.com/tmdb"
TMDB_IMG = "https://image.tmdb.org/t/p/w342"
W, H = 342, 513

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size=size)


def fetch_ratings(api_key: str, kind: str, tmdb_id: int) -> dict[str, float]:
    """{'imdb': 7.8, 'tomatoes': 93, 'metacritic': 77, ...} — vazio se falhar."""
    mtype = "movie" if kind == "movie" else "show"
    try:
        r = httpx.get(f"{MDBLIST}/{mtype}/{tmdb_id}", params={"apikey": api_key}, timeout=20)
    except httpx.HTTPError as e:
        print(f"Aviso: MDBList sem resposta ({type(e).__name__})")
        return {}
    if r.status_code != 200:
        if r.status_code == 429:
            print("Aviso: limite diário do MDBList atingido")
        return {}
    out = {}
    for it in r.json().get("ratings", []) or []:
        src, val = it.get("source"), it.get("value")
        if src and isinstance(val, (int, float)) and val > 0:
            out[src] = val
    return out


def _color(score100: float) -> tuple[int, int, int]:
    if score100 >= 75:
        return (46, 160, 67)
    if score100 >= 60:
        return (210, 153, 34)
    return (200, 60, 60)


def render(poster_path: str | None, p_like: float, ratings: dict[str, float], dest: Path) -> bool:
    if not poster_path:
        return False
    try:
        img = Image.open(io.BytesIO(httpx.get(f"{TMDB_IMG}{poster_path}", timeout=20).content))
        img = img.convert("RGB").resize((W, H))
    except Exception:  # noqa: BLE001
        return False

    d = ImageDraw.Draw(img, "RGBA")

    # Selo superior: chance de você gostar
    pct = round(p_like * 100)
    label = f"{pct}% p/ você"
    f_top = _font(22)
    tw = d.textlength(label, font=f_top)
    d.rounded_rectangle((8, 8, 8 + tw + 20, 44), radius=10, fill=(*_color(pct), 235))
    d.text((18, 13), label, font=f_top, fill="white")

    # Faixa inferior: notas da crítica
    parts = []
    if "tomatoes" in ratings:
        parts.append(("RT", f"{ratings['tomatoes']:.0f}", ratings["tomatoes"]))
    if "imdb" in ratings:
        parts.append(("IMDb", f"{ratings['imdb']:.1f}", ratings["imdb"] * 10))
    if "metacritic" in ratings:
        parts.append(("MC", f"{ratings['metacritic']:.0f}", ratings["metacritic"]))
    if not parts:
        img.save(dest, "JPEG", quality=85)
        return True

    d.rectangle((0, H - 58, W, H), fill=(0, 0, 0, 200))
    f_lab, f_val = _font(15), _font(24)
    col_w = W / len(parts)
    for i, (lab, val, s100) in enumerate(parts):
        cx = col_w * i + col_w / 2
        d.text((cx, H - 46), lab, font=f_lab, fill=(210, 210, 210), anchor="mm")
        d.text((cx, H - 21), val, font=f_val, fill=_color(s100), anchor="mm")
    img.save(dest, "JPEG", quality=85)
    return True


def build(out: Path, items: list[dict], api_key: str | None, base_url: str, version: str) -> dict[str, str]:
    """items: [{imdb, kind, tmdb_id, poster_path, p_like}] -> {imdb: url_do_poster}"""
    folder = out / "posters"
    folder.mkdir(parents=True, exist_ok=True)
    urls, with_ratings = {}, 0
    for it in items:
        ratings = fetch_ratings(api_key, it["kind"], it["tmdb_id"]) if api_key else {}
        with_ratings += bool(ratings)
        if render(it["poster_path"], it["p_like"], ratings, folder / f"{it['imdb']}.jpg"):
            urls[it["imdb"]] = f"{base_url}/posters/{it['imdb']}.jpg?v={version}"
        time.sleep(0.05)
    print(f"Pôsteres: {len(urls)} gerados | {with_ratings} com notas da crítica")
    return urls


def mask_key() -> None:
    key = os.getenv("MDBLIST_API_KEY")
    if key and os.getenv("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{key}", flush=True)
