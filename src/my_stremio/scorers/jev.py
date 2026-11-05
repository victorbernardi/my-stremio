"""Scorer via Jev (TypeSafe AI) — https://docs.typesafe.ai

Uma chamada por candidato (padrão do cookbook de re-ranking), em paralelo:
  state     = perfil de gosto + ficha do título
  questions = gostaria (noul 0–1, usado como P(gostar)) + motivo (choice)
"""
from concurrent.futures import ThreadPoolExecutor
import time

import httpx

from .base import Score

API = "https://api.typesafe.ai/v1/systemone"

REASONS = {
    "genero": "O gênero é o que mais combina (ou destoa) do gosto",
    "diretor": "Diretor/criador ou estilo de direção",
    "tom": "Tom, clima e ritmo da obra",
    "elenco": "Atores e atrizes",
    "tema": "Tema, assunto ou premissa",
    "outro": "Nenhum dos anteriores",
}

QUESTIONS = {
    "gostaria": {
        "type": "noul",
        "instructions": (
            "Verdadeiro se, pelo perfil de gosto, esta pessoa provavelmente gostaria do título candidato. "
            "Títulos parecidos com os que ela AMA contam a favor; parecidos com os que ODEIA ou ABANDONOU contam contra."
        ),
    },
    "motivo": {
        "type": "choice",
        "instructions": "Qual fator do título mais pesa nessa avaliação para esta pessoa",
        "criteria": REASONS,
    },
}


class JevScorer:
    def __init__(self, api_key: str | None, model: str = "jev-latest", workers: int = 12):
        if not api_key:
            raise RuntimeError("TYPESAFE_API_KEY ausente.")
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30
        )
        self.model = model
        self.workers = workers

    def _one(self, profile: str, c: dict) -> Score | None:
        state = {
            "perfil_de_gosto": profile,
            "candidato": {
                "titulo": c["title"],
                "ano": c.get("year", ""),
                "generos": c.get("genres", []),
                "sinopse": c.get("overview", "")[:600],
            },
        }
        body = {"model": self.model, "state": state, "questions": QUESTIONS}
        for attempt in range(4):
            r = self.client.post(API, json=body)
            if r.status_code in (429, 529, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            a = r.json()["answers"]
            return Score(tmdb_id=c["tmdb_id"], p_like=a["gostaria"]["noul"], reason=a["motivo"]["choice"])
        return None

    def score(self, profile: str, candidates: list[dict]) -> list[Score]:
        with ThreadPoolExecutor(self.workers) as ex:
            results = list(ex.map(lambda c: self._one(profile, c), candidates))
        return [s for s in results if s]
