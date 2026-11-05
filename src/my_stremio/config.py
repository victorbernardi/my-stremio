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
    typesafe_api_key: str | None
    language: str
    region: str
    candidates_per_run: int
    catalog_size: int


def load() -> Settings:
    return Settings(
        stremio_auth_key=_req("STREMIO_AUTH_KEY"),
        tmdb_read_token=_req("TMDB_READ_TOKEN"),
        tmdb_account_id=os.getenv("TMDB_ACCOUNT_ID"),
        tmdb_session_id=os.getenv("TMDB_SESSION_ID"),
        scorer=os.getenv("SCORER", "haiku"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        typesafe_api_key=os.getenv("TYPESAFE_API_KEY"),
        language=os.getenv("LANGUAGE", "pt-BR"),
        region=os.getenv("REGION", "BR"),
        candidates_per_run=int(os.getenv("CANDIDATES_PER_RUN", "300")),
        catalog_size=int(os.getenv("CATALOG_SIZE", "50")),
    )
