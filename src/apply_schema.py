"""schema/*.sql を TiDB に適用する。行コメント(--)を除去してから ; で分割実行。

Makefile の一行版だと「先頭コメント行＋DROP」が同チャンクになり DROP が握り潰される
バグがあったため、コメント除去を先に行う堅牢版に分離した。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import db  # noqa: E402

SCHEMA = Path(__file__).resolve().parent.parent / "schema" / "01_schema.sql"


def strip_sql_comments(sql: str) -> str:
    # 各行の "--" 以降を除去(文字列内に -- は無い前提のスキーマ)
    lines = [re.sub(r"--.*$", "", ln) for ln in sql.splitlines()]
    return "\n".join(lines)


def statements(sql: str) -> list[str]:
    cleaned = strip_sql_comments(sql)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def main() -> None:
    conn = db.connect()
    with conn.cursor() as cur:
        for stmt in statements(SCHEMA.read_text(encoding="utf-8")):
            head = stmt.split("\n", 1)[0][:60]
            cur.execute(stmt)
            print(f"  ok: {head} ...")
    print("schema applied")


if __name__ == "__main__":
    main()
