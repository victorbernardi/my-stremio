"""Autorização única do TMDB para ler suas notas.

Passo 1:  python scripts/tmdb_auth.py            -> gera link de aprovação
Passo 2:  python scripts/tmdb_auth.py <token>    -> cria session_id e descobre account_id

Precisa de TMDB_READ_TOKEN no ambiente. Escreve no $GITHUB_STEP_SUMMARY quando roda no Actions.
"""
import os
import sys

import httpx

API = "https://api.themoviedb.org/3"


def out(text: str) -> None:
    print(text)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(text + "\n")


def main() -> None:
    c = httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {os.environ['TMDB_READ_TOKEN']}"},
        timeout=30,
    )
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        token = c.get("/authentication/token/new").raise_for_status().json()["request_token"]
        out("## Passo 1 — aprove o acesso no TMDB\n")
        out(f"1. Abra e clique em **Approve**: https://www.themoviedb.org/authenticate/{token}")
        out(f"2. Rode o workflow de novo com o campo `request_token` = `{token}`")
        out("\nO token expira em 60 minutos.")
        return

    token = sys.argv[1].strip()
    r = c.post("/authentication/session/new", json={"request_token": token})
    if r.status_code != 200:
        out(f"Falhou ({r.status_code}): {r.text}. Aprovou o link? Gere um novo token se passou de 60 min.")
        sys.exit(1)
    session_id = r.json()["session_id"]
    account = c.get("/account", params={"session_id": session_id}).raise_for_status().json()
    out("## Passo 2 — cadastre estes 2 secrets\n")
    out("Em Settings → Secrets and variables → Actions → New repository secret:\n")
    out(f"- `TMDB_ACCOUNT_ID` = `{account['id']}`")
    out(f"- `TMDB_SESSION_ID` = `{session_id}`")
    out("\nDepois apague este run (⋯ → Delete workflow run) para o session_id não ficar no histórico.")


if __name__ == "__main__":
    main()
