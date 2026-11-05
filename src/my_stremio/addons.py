"""Gestão dos addons instalados na conta Stremio (vale para todos os dispositivos).

Pedido (JSON, sempre criptografado no repo público):
  {"actions": [
     {"op": "list"},
     {"op": "install", "url": "https://.../manifest.json", "position": 2},   # position opcional (1 = topo)
     {"op": "remove",  "match": "Torrentio"},                               # nome, id ou trecho da URL
     {"op": "move",    "match": "Para Você", "position": 1},
     {"op": "restore"},                                                     # volta ao último backup
     {"op": "inspect", "match": "Comet"}                                    # versão/recursos (sem URL)
  ]}

Regras de segurança (repo público):
  - o log mostra só NOME, id e posição dos addons — nunca transportUrl (pode conter chaves);
  - antes de qualquer escrita, salva backup criptografado da coleção;
  - addons protegidos do Stremio nunca são removidos.
"""
import json
import sys
from pathlib import Path

import httpx

from . import config
from .stremio import API


def get_collection(auth_key: str) -> list[dict]:
    r = httpx.post(
        f"{API}/addonCollectionGet",
        json={"type": "AddonCollectionGet", "authKey": auth_key, "update": True},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Stremio recusou a leitura: {data['error']}")
    return data["result"]["addons"]


def set_collection(auth_key: str, addons: list[dict]) -> None:
    r = httpx.post(
        f"{API}/addonCollectionSet",
        json={"type": "AddonCollectionSet", "authKey": auth_key, "addons": addons},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("error") or not data.get("result", {}).get("success"):
        raise RuntimeError(f"Stremio recusou a gravação: {data.get('error')}")


def _name(a: dict) -> str:
    m = a.get("manifest", {})
    return f"{m.get('name', '?')} ({m.get('id', '?')})"


def _find(addons: list[dict], match: str) -> int:
    m = match.lower()
    hits = [
        i for i, a in enumerate(addons)
        if m in a.get("manifest", {}).get("name", "").lower()
        or m == a.get("manifest", {}).get("id", "").lower()
        or m in a.get("transportUrl", "").lower()
    ]
    if len(hits) != 1:
        names = [_name(addons[i]) for i in hits]
        raise RuntimeError(f"'{match}' casou com {len(hits)} addons: {names}. Seja mais específico.")
    return hits[0]


def _fetch_manifest(url: str) -> dict:
    if not url.endswith("/manifest.json"):
        raise RuntimeError("A URL do addon precisa terminar em /manifest.json")
    url = url.replace("stremio://", "https://", 1)
    r = httpx.get(url, timeout=30, follow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError(f"Manifest inacessível (HTTP {r.status_code})")
    return r.json()


def print_list(addons: list[dict], title: str) -> None:
    print(f"\n{title}")
    for i, a in enumerate(addons, 1):
        flags = a.get("flags", {})
        tag = " [protegido]" if flags.get("protected") else (" [oficial]" if flags.get("official") else "")
        print(f"  {i:>2}. {_name(a)}{tag}")


def run(request: dict, backup_path: Path, restore_path: Path | None) -> None:
    s = config.load_stremio_only()
    addons = get_collection(s)
    print_list(addons, "Coleção atual:")

    ops = request.get("actions", [])
    for o in ops:
        if o["op"] == "inspect":
            m = o["match"].lower()
            for i, a in enumerate(addons, 1):
                man = a.get("manifest", {})
                if m in man.get("name", "").lower() or m in man.get("id", "").lower():
                    print(f"\n#{i} {_name(a)} v{man.get('version')}")
                    print(f"   recursos: {[r if isinstance(r, str) else r.get('name') for r in man.get('resources', [])]}")
                    print(f"   tipos: {man.get('types')} | catálogos: {len(man.get('catalogs', []))}")
                    print(f"   descrição: {(man.get('description') or '')[:300]}")
    if all(o["op"] in ("list", "inspect") for o in ops):
        return

    backup_path.write_text(json.dumps(addons))
    print(f"\nBackup salvo ({len(addons)} addons).")

    for o in ops:
        op = o["op"]
        if op in ("list", "inspect"):
            continue
        if op == "restore":
            if not restore_path or not restore_path.exists():
                raise RuntimeError("Nenhum backup anterior disponível para restaurar.")
            addons = json.loads(restore_path.read_text())
            print("→ restaurado o backup anterior")
        elif op == "install":
            manifest = _fetch_manifest(o["url"])
            url = o["url"].replace("stremio://", "https://", 1)
            addons = [a for a in addons if a.get("manifest", {}).get("id") != manifest.get("id")]
            desc = {"transportUrl": url, "transportName": "http", "manifest": manifest,
                    "flags": {"official": False, "protected": False}}
            pos = max(1, min(int(o.get("position", len(addons) + 1)), len(addons) + 1))
            addons.insert(pos - 1, desc)
            print(f"→ instalado {_name(desc)} na posição {pos}")
        elif op == "remove":
            i = _find(addons, o["match"])
            if addons[i].get("flags", {}).get("protected"):
                raise RuntimeError(f"{_name(addons[i])} é protegido pelo Stremio e não pode ser removido.")
            print(f"→ removido {_name(addons.pop(i))}")
        elif op == "move":
            i = _find(addons, o["match"])
            a = addons.pop(i)
            pos = max(1, min(int(o["position"]), len(addons) + 1))
            addons.insert(pos - 1, a)
            print(f"→ movido {_name(a)} para a posição {pos}")
        else:
            raise RuntimeError(f"Operação desconhecida: {op}")

    set_collection(s, addons)
    print_list(get_collection(s), "Coleção depois da mudança:")


if __name__ == "__main__":
    req = json.loads(Path(sys.argv[1]).read_text())
    restore = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    run(req, Path(sys.argv[2]), restore)
