"""エージェント記憶の想起デモ(CLI)。

既定は baseline(ローカル3層)で動くので **TiDBクラスタが無くても実行できる**。
`--tidb` を付けると TiDB(ingest済み)に対して同じ hybrid 想起を実行する。

例:
  python -m src.recall --query "POSの返金フローはどう実装したか" --term 返金フロー --product posplus --min-imp 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, embed  # noqa: E402


def load_rows() -> list[dict]:
    return [json.loads(l) for l in config.SEED_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def run_baseline(args, rows) -> list[int]:
    from before.baseline import BaselineStore
    vecs = embed.embed_passages([r["body"] for r in rows])
    store = BaselineStore()
    store.build(rows, vecs)
    qv = embed.embed_query(args.query)
    return store.hybrid_rrf(qv, args.term, product=args.product,
                            min_imp=args.min_imp, topk=args.topk, agent=args.agent)


def run_tidb(args) -> list[int]:
    from src import db, search
    conn = db.connect()
    qv = embed.to_sql_vector(embed.embed_query(args.query))
    return search.hybrid_rrf(conn, qv, args.term, product=args.product,
                             min_imp=args.min_imp, topk=args.topk, agent=args.agent)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True, help="意味検索クエリ(自然文)")
    ap.add_argument("--term", required=True, help="全文検索語(3文字以上)")
    ap.add_argument("--product", required=True)
    ap.add_argument("--min-imp", type=int, default=2)
    ap.add_argument("--agent", default=None)
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--tidb", action="store_true", help="TiDB(ingest済)に対して実行")
    args = ap.parse_args()

    rows = load_rows()
    by_id = {r["id"]: r for r in rows}
    ids = run_tidb(args) if args.tidb else run_baseline(args, rows)

    backend = "TiDB(1 SQL)" if args.tidb else "baseline(3層, ローカル)"
    print(f"\n想起: query='{args.query}' / term='{args.term}' / "
          f"filter: product={args.product}, importance>={args.min_imp}"
          f"{', agent=' + args.agent if args.agent else ''}  [{backend}]\n")
    print(f"{'rank':>4}  {'id':>4}  {'agent':<12} {'type':<10} imp  body")
    print("-" * 88)
    for rank, i in enumerate(ids, 1):
        m = by_id.get(i, {})
        body = m.get("body", "")[:46]
        print(f"{rank:>4}  {i:>4}  {m.get('agent',''):<12} {m.get('signal_type',''):<10} "
              f"{m.get('importance',''):>2}   {body}")
    print()


if __name__ == "__main__":
    main()
