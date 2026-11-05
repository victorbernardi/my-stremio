"""TMDB: notas do usuário (label explícito), candidatos e metadados."""
import os

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

    # --- Login sem navegador -----------------------------------------------
    def login(self, username: str, password: str) -> tuple[str, str]:
        """Valida um request token com usuário/senha e devolve (account_id, session_id)."""
        token = self._get("/authentication/token/new")["request_token"]
        r = self.c.post(
            "/authentication/token/validate_with_login",
            json={"username": username, "password": password, "request_token": token},
        )
        if r.status_code != 200:
            raise RuntimeError(f"Login TMDB falhou ({r.status_code}): {r.json().get('status_message')}")
        r = self.c.post("/authentication/session/new", json={"request_token": token})
        r.raise_for_status()
        session_id = r.json()["session_id"]
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{session_id}", flush=True)
        account_id = str(self._get("/account", session_id=session_id)["id"])
        return account_id, session_id

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
