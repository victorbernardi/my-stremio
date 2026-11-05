"""Acrescenta o snapshot do dia ao histórico (JSON Lines). Um registro por data.

Uso: python scripts/history.py <historico.jsonl> <snapshot.json>
"""
import json
import sys
from pathlib import Path

hist, snap = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
rows = [json.loads(line) for line in hist.read_text().splitlines() if line.strip()] if hist.exists() else []
rows = [r for r in rows if r["date"] != snap["date"]] + [snap]
hist.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n")
print(f"Histórico: {len(rows)} dias registrados")
