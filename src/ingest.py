"""seed/memories.jsonl を読み、本文を埋め込み、TiDB の memories へ投入する。"""
from __future__ import annotations

import json

from . import config, db, embed

INSERT = (
    "INSERT INTO memories "
    "(id, agent, signal_type, body, embedding, importance, product_id, source, created_at) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


def load_rows() -> list[dict]:
    rows = []
    with config.SEED_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main(batch: int = 64) -> None:
    rows = load_rows()
    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM memories")
        for start in range(0, len(rows), batch):
            chunk = rows[start:start + batch]
            vecs = embed.embed_passages([r["body"] for r in chunk])
            params = [
                (r["id"], r["agent"], r["signal_type"], r["body"], embed.to_sql_vector(v),
                 r["importance"], r["product_id"], r["source"], r["created_at"])
                for r, v in zip(chunk, vecs)
            ]
            cur.executemany(INSERT, params)
            print(f"  ingested {min(start + batch, len(rows))}/{len(rows)}")
    print(f"done: {len(rows)} rows")


if __name__ == "__main__":
    main()
