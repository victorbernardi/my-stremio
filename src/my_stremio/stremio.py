"""Leitura da biblioteca/histórico da conta Stremio (sinal implícito)."""
import os

import httpx

API = "https://api.strem.io/api"
LIKES = "https://likes.stremio.com/addons"


def login(email: str, password: str) -> str:
    """Obtém authKey a partir de e-mail e senha (só contas com senha, não login Google/Apple)."""
    r = httpx.post(
        f"{API}/login",
        json={"type": "Login", "email": email, "password": password, "facebook": False},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Login Stremio falhou: {data['error'].get('message', data['error'])}")
    key = data["result"]["authKey"]
    mask(key)
    return key


def mask(value: str) -> None:
    """Pede ao GitHub Actions para ocultar o valor em todos os logs (repo é público)."""
    if value and os.getenv("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{value}", flush=True)


def fetch_library(auth_key: str) -> list[dict]:
    """Todos os itens da biblioteca, incluindo progresso de visualização."""
    r = httpx.post(
        f"{API}/datastoreGet",
        json={"authKey": auth_key, "collection": "libraryItem", "all": True},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("result", [])


def to_signal(item: dict) -> dict:
    """Normaliza um libraryItem em features de sinal implícito."""
    state = item.get("state") or {}
    duration = state.get("duration") or 0
    offset = state.get("timeOffset") or 0
    progress = (offset / duration) if duration else None
    return {
        "imdb_id": item.get("_id"),
        "type": item.get("type"),  # movie | series
        "name": item.get("name"),
        "in_library": not item.get("removed", False),
        "times_watched": state.get("timesWatched", 0),
        "last_watched": state.get("lastWatched"),
        "progress": progress,  # abandono com ~20% ≈ sinal negativo fraco
        "flagged_watched": bool(state.get("flaggedWatched")),
    }


def fetch_reactions(auth_key: str) -> dict[str, str]:
    """Botões 👍 (liked) e ❤️ (loved) do Stremio -> {imdb_id: 'liked'|'loved'}.

    A authKey vai no caminho da URL (desenho do serviço oficial likes.stremio.com),
    por isso erros NUNCA incluem a URL — só o status HTTP.
    """
    out: dict[str, str] = {}
    for status in ("liked", "loved"):
        for stype in ("movie", "series"):
            url = f"{LIKES}/{status}/movies-shows/{auth_key}/catalog/{stype}/stremio-{status}-{stype}.json"
            try:
                r = httpx.get(url, timeout=30)
            except httpx.HTTPError as e:
                print(f"Aviso: falha de rede ao ler reações {status}/{stype} ({type(e).__name__})")
                continue
            if r.status_code != 200:
                print(f"Aviso: reações {status}/{stype} retornaram HTTP {r.status_code}")
                continue
            for meta in r.json().get("metas", []):
                if meta.get("id"):
                    out[meta["id"]] = status
    return out
