"""Interface comum de scoring. Jev quando houver chave; Haiku como reserva."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Score:
    tmdb_id: int
    p_like: float  # probabilidade de o usuário gostar (0–1)
    reason: str    # motivo dominante: genero | diretor | tom | elenco | tema | outro


class Scorer(Protocol):
    def score(self, profile: str, candidates: list[dict]) -> list[Score]: ...


class FallbackScorer:
    """Tenta o principal; se falhar inteiro ou devolver vazio, usa o reserva."""

    def __init__(self, primary: Scorer, backup: Scorer | None):
        self.primary, self.backup = primary, backup

    def score(self, profile, candidates):
        try:
            out = self.primary.score(profile, candidates)
            if out:
                return out
            print("Scorer principal não devolveu resultados.")
        except Exception as e:  # noqa: BLE001
            print(f"Scorer principal falhou: {e}")
        if not self.backup:
            raise RuntimeError("Sem scorer reserva configurado.")
        print("Usando scorer reserva (Haiku).")
        return self.backup.score(profile, candidates)


def get_scorer(settings) -> Scorer:
    from .haiku import HaikuScorer

    haiku = (
        HaikuScorer(settings.anthropic_api_key, settings.anthropic_model)
        if settings.anthropic_api_key else None
    )
    choice = settings.scorer
    if choice == "auto":
        choice = "jev" if settings.jev_api_key else "haiku"
    if choice == "jev":
        from .jev import JevScorer
        print(f"Scorer: Jev via {settings.jev_provider}" + (" (reserva: Haiku)" if haiku else ""))
        return FallbackScorer(JevScorer(settings.jev_api_key, settings.jev_provider), haiku)
    if not haiku:
        raise RuntimeError("Nenhum scorer disponível: defina COMMAND_CODE_API_KEY, TYPESAFE_API_KEY ou ANTHROPIC_API_KEY.")
    print("Scorer: Haiku")
    return haiku
