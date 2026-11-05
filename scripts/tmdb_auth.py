"""Autorização única do TMDB para ler suas notas — em UM run.

python scripts/tmdb_auth.py           -> gera o link, espera você aprovar (até 10 min) e cria a sessão
python scripts/tmdb_auth.py <token>   -> só cria a sessão a partir de um token já aprovado

Precisa de TMDB_READ_TOKEN no ambiente. Escreve no $GITHUB_STEP_SUMMARY quando roda no Actions.
"""
import os
import sys
import time

import httpx

API = "https://api.themoviedb.org/3"
WAIT_SECONDS = 600


def out(text: str, summary: bool = True) -> None:
    print(text, flush=True)
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary and path:
        with open(path, "a") as f:
            f.write(text + "\n")


def create_session(c: httpx.Client, token: str) -> httpx.Response:
    return c.post("/authentication/session/new", json={"request_token": token})


def main() -> None:
    c = httpx.Client(
        base_url=API,
        headers={"Authorization": f"Bearer {os.environ['TMDB_READ_TOKEN']}"},
        timeout=30,
    )
    token = sys.argv[1].strip() if len(sys.argv) > 1 else ""

    if token:
        r = create_session(c, token)
    else:
        token = c.get("/authentication/token/new").raise_for_status().json()["request_token"]
        out("=" * 70, summary=False)
        out("ABRA ESTE LINK, FAÇA LOGIN NO TMDB SE PEDIR, E CLIQUE EM 'APPROVE':", summary=False)
        out(f"https://www.themoviedb.org/authenticate/{token}", summary=False)
        out(f"Aguardando aprovação por até {WAIT_SECONDS // 60} min...", summary=False)
        out("=" * 70, summary=False)
        deadline = time.time() + WAIT_SECONDS
        while True:
            r = create_session(c, token)
            if r.status_code == 200 or time.time() > deadline:
                break
            time.sleep(10)

    if r.status_code != 200:
        out(f"Falhou ({r.status_code}): {r.text}")
        out("Rode o workflow de novo com o campo vazio e aprove o link nos 10 minutos seguintes.")
        sys.exit(1)

    session_id = r.json()["session_id"]
    account = c.get("/account", params={"session_id": session_id}).raise_for_status().json()
    out("## Aprovado — cadastre estes 2 secrets\n")
    out("Settings → Secrets and variables → Actions → New repository secret:\n")
    out(f"- `TMDB_ACCOUNT_ID` = `{account['id']}`")
    out(f"- `TMDB_SESSION_ID` = `{session_id}`")
    out("\nDepois de salvar, rode este workflow com `limpar` no campo — ele apaga este run do histórico.")


if __name__ == "__main__":
    main()
