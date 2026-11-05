"""TMDB: notas do usuário (label explícito), candidatos e metadados."""
import httpx

API = "https://api.themoviedb.org/3"


class TMDB:
    def __init__(self, read_token: str, language: str = "pt-BR"):
        self.c = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {read_token}"},
            params={"language": language},
            timeout=30,
        )

    def _get(self, path: str, **params) -> dict:
        r = self.c.get(path, params=params)
        r.raise_for_status()
        return r.json()

    def _paged(self, path: str, max_pages: int = 50, **params) -> list[dict]:
        out, page = [], 1
        while page <= max_pages:
            data = self._get(path, page=page, **params)
            out += data.get("results", [])
            if page >= data.get("total_pages", 1):
                break
            page += 1
        return out

    # --- Labels -----------------------------------------------------------
    def rated(self, account_id: str, session_id: str, kind: str) -> list[dict]:
        """kind: 'movies' | 'tv'. Retorna itens com campo 'rating' (0.5–10)."""
        return self._paged(f"/account/{account_id}/rated/{kind}", session_id=session_id)

    # --- Candidatos -------------------------------------------------------
    def recommendations(self, kind: str, tmdb_id: int) -> list[dict]:
        return self._get(f"/{kind}/{tmdb_id}/recommendations").get("results", [])

    def similar(self, kind: str, tmdb_id: int) -> list[dict]:
        return self._get(f"/{kind}/{tmdb_id}/similar").get("results", [])

    # --- Ponte IMDb <-> TMDB (Stremio usa IMDb ids) -----------------------
    def find_imdb(self, imdb_id: str) -> dict:
        return self._get(f"/find/{imdb_id}", external_source="imdb_id")

    def external_ids(self, kind: str, tmdb_id: int) -> dict:
        return self._get(f"/{kind}/{tmdb_id}/external_ids")

    def genres(self, kind: str) -> dict[int, str]:
        return {g["id"]: g["name"] for g in self._get(f"/genre/{kind}/list")["genres"]}

    # --- Features ---------------------------------------------------------
    def details(self, kind: str, tmdb_id: int) -> dict:
        return self._get(f"/{kind}/{tmdb_id}", append_to_response="keywords,credits")
