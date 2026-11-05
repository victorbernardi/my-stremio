"""Scorer via Jev (TypeSafe AI). Stub até liberarem o early access.

Docs: https://docs.typesafe.ai/  — mapear para: state = perfil + metadados do título,
questions = {"gostaria": bool, "motivo": enum(REASONS)}; usar a probabilidade de "gostaria=True".
"""
from .base import Score


class JevScorer:
    def __init__(self, api_key: str | None):
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY ausente — use SCORER=haiku por enquanto.")
        self.api_key = api_key

    def score(self, profile: str, candidates: list[dict]) -> list[Score]:
        raise NotImplementedError("Implementar quando houver acesso à API do Jev.")
