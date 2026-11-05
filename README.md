# my-stremio

Recomendador pessoal de filmes e séries que aprende com o que eu assisto e com as minhas notas, entregue como catálogo dentro do Stremio.

## Arquitetura

```
Stremio (o que assisti, progresso) ─┐
                                    ├─► perfil de gosto ─► candidatos (TMDB) ─► scorer ─► ranking ─► addon (catálogo Stremio)
TMDB (minhas notas 0,5–10) ─────────┘                                         Haiku | Jev
```

| Camada | Fonte | Papel |
|---|---|---|
| Sinal implícito | Biblioteca Stremio (`authKey`) | assistiu, reassistiu, abandonou |
| Label explícito | Notas na conta TMDB | gostei / não gostei |
| Candidatos e features | API TMDB | recomendações, similares, gêneros, keywords, elenco |
| Scoring | Claude Haiku (padrão) ou Jev | P(gostar) calibrada + motivo |
| Entrega | GitHub Pages (JSON estático) | addon instalável no Stremio |

Roda diariamente via GitHub Actions — sem servidor.

## Estrutura

```
src/my_stremio/
  config.py        # lê .env / GitHub Secrets
  stremio.py       # biblioteca e progresso da conta
  tmdb.py          # notas, candidatos, metadados
  scorers/         # base.py (interface), haiku.py, jev.py
addon/             # manifest.json + catálogos gerados (publicados no Pages)
data/              # cache local — ignorado pelo git
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencher
```

Segredos ficam **só** no `.env` (local) e em GitHub Secrets (Actions). Nunca no código.

## Roadmap

- [x] Esqueleto, clientes Stremio/TMDB, scorer Haiku
- [ ] Login TMDB (session_id) para ler notas
- [ ] Perfil de gosto (notas + sinal implícito)
- [ ] Geração de candidatos e deduplicação do que já foi visto
- [ ] Geração do addon estático + GitHub Pages
- [ ] Workflow diário no Actions
- [x] Scorer Jev (principal) com Haiku de reserva
- [ ] Avaliação offline (holdout das notas → AUC / NDCG)
