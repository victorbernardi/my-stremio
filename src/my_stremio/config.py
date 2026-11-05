"""Configuração central: lê variáveis do .env (local) ou dos Secrets (GitHub Actions)."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _req(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Variável {name} não definida (.env ou GitHub Secrets).")
    return val


@dataclass(frozen=True)
class Settings:
    stremio_auth_key: str
    tmdb_read_token: str
    tmdb_account_id: str | None
    tmdb_session_id: str | None
    scorer: str
    anthropic_api_key: str | None
    anthropic_model: str
    jev_api_key: str | None
    jev_provider: str
    language: str
    region: str
    candidates_per_run: int
    catalog_size: int


def _stremio_auth_key() -> str:
    """Usa STREMIO_AUTH_KEY se existir; senão faz login com STREMIO_EMAIL/STREMIO_PASSWORD."""
    key = os.getenv("STREMIO_AUTH_KEY")
    if key:
        return key
    email, password = os.getenv("STREMIO_EMAIL"), os.getenv("STREMIO_PASSWORD")
    if email and password:
        from .stremio import login
        return login(email, password)
    raise RuntimeError("Defina STREMIO_AUTH_KEY ou STREMIO_EMAIL + STREMIO_PASSWORD.")


def load() -> Settings:
    return Settings(
        stremio_auth_key=_stremio_auth_key(),
        tmdb_read_token=_req("TMDB_READ_TOKEN"),
        tmdb_account_id=os.getenv("TMDB_ACCOUNT_ID"),
        tmdb_session_id=os.getenv("TMDB_SESSION_ID"),
        scorer=os.getenv("SCORER", "auto"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        jev_api_key=os.getenv("COMMAND_CODE_API_KEY") or os.getenv("TYPESAFE_API_KEY"),
        jev_provider="commandcode" if os.getenv("COMMAND_CODE_API_KEY") else "typesafe",
        language=os.getenv("LANGUAGE", "pt-BR"),
        region=os.getenv("REGION", "BR"),
        candidates_per_run=int(os.getenv("CANDIDATES_PER_RUN", "300")),
        catalog_size=int(os.getenv("CATALOG_SIZE", "50")),
    )
