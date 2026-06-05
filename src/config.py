"""環境設定の読込。.env があれば読み、なければ os.environ をそのまま使う。"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()

EMBED_BACKEND = os.environ.get("EMBED_BACKEND", "local")
EMBED_DIM = int(os.environ.get("EMBED_DIM", "384"))

TIDB = {
    "host": os.environ.get("TIDB_HOST", ""),
    "port": int(os.environ.get("TIDB_PORT", "4000")),
    "user": os.environ.get("TIDB_USER", ""),
    "password": os.environ.get("TIDB_PASSWORD", ""),
    "database": os.environ.get("TIDB_DB", "test"),
}

SEED_PATH = ROOT / "seed" / "memories.jsonl"
EVAL_PATH = ROOT / "seed" / "eval.yaml"
RESULTS_DIR = ROOT / "bench" / "results"
