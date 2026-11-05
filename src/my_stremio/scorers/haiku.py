"""Scorer via Claude Haiku, com saída estruturada por tool use."""
import anthropic

from .base import Score

REASONS = ["genero", "diretor", "tom", "elenco", "tema", "outro"]

TOOL = {
    "name": "submit_scores",
    "description": "Registra a probabilidade de o usuário gostar de cada candidato.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tmdb_id": {"type": "integer"},
                        "p_like": {"type": "number", "minimum": 0, "maximum": 1},
                        "reason": {"type": "string", "enum": REASONS},
                    },
                    "required": ["tmdb_id", "p_like", "reason"],
                },
            }
        },
        "required": ["scores"],
    },
}


class HaikuScorer:
    def __init__(self, api_key: str | None, model: str, batch_size: int = 25):
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY ausente.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.batch_size = batch_size

    def _batch(self, profile: str, batch: list[dict]) -> list[Score]:
        lines = "\n".join(
            f"- id={c['tmdb_id']} | {c['title']} ({c.get('year','?')}) | "
            f"gêneros: {', '.join(c.get('genres', []))} | {c.get('overview','')[:300]}"
            for c in batch
        )
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=(
                "Você é um sistema de recomendação. Dado o perfil de gosto do usuário, "
                "estime de forma calibrada a probabilidade de ele gostar de cada título. "
                "Seja conservador: 0.5 = incerto."
            ),
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "submit_scores"},
            messages=[{"role": "user", "content": f"PERFIL:\n{profile}\n\nCANDIDATOS:\n{lines}"}],
        )
        block = next(b for b in msg.content if b.type == "tool_use")
        valid = {c["tmdb_id"] for c in batch}
        return [Score(**s) for s in block.input["scores"] if s["tmdb_id"] in valid]

    def score(self, profile: str, candidates: list[dict]) -> list[Score]:
        out: list[Score] = []
        for i in range(0, len(candidates), self.batch_size):
            out += self._batch(profile, candidates[i : i + self.batch_size])
        return out
