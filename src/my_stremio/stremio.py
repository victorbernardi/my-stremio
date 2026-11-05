"""Leitura da biblioteca/histórico da conta Stremio (sinal implícito)."""
import httpx

API = "https://api.strem.io/api"


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
    return data["result"]["authKey"]


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
