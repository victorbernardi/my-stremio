"""Interface comum de scoring. Haiku hoje, Jev quando houver acesso — troca via SCORER."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Score:
    tmdb_id: int
    p_like: float  # probabilidade de o usuário gostar (0–1)
    reason: str    # motivo dominante: genero | diretor | tom | elenco | tema | outro


class Scorer(Protocol):
    def score(self, profile: str, candidates: list[dict]) -> list[Score]: ...


def get_scorer(settings) -> Scorer:
    if settings.scorer == "jev":
        from .jev import JevScorer
        return JevScorer(settings.typesafe_api_key)
    from .haiku import HaikuScorer
    return HaikuScorer(settings.anthropic_api_key, settings.anthropic_model)
