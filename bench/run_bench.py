"""before(3層) vs after(TiDB 1台) を同一seed・同一クエリで実測。

出力: bench/results/results.md (recall@5/@10, MRR, レイテンシ p50/p95 を4モード比較)。
TiDB未設定でも baseline は走るので、まずローカルで数値を確認できる。
記事の数値はこの results.md をそのまま引用する(=読者が再現可能)。
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import config, db, embed, search  # noqa: E402
from src.fusion import mrr, recall_at_k  # noqa: E402
from before.baseline import BaselineStore  # noqa: E402


def load_rows() -> list[dict]:
    return [json.loads(l) for l in config.SEED_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_queries() -> list[dict]:
    return yaml.safe_load(config.EVAL_PATH.read_text(encoding="utf-8"))["queries"]


def summarize(recalls5, recalls10, mrrs, lats) -> dict:
    return {
        "recall@5": round(statistics.mean(recalls5), 4),
        "recall@10": round(statistics.mean(recalls10), 4),
        "MRR": round(statistics.mean(mrrs), 4),
        "p50_ms": round(statistics.median(lats) * 1000, 1),
        "p95_ms": round(sorted(lats)[max(0, int(len(lats) * 0.95) - 1)] * 1000, 1),
    }


def eval_mode(name, runner, queries) -> dict:
    r5, r10, mr, lat = [], [], [], []
    for q in queries:
        t0 = time.perf_counter()
        got = runner(q)
        lat.append(time.perf_counter() - t0)
        rel = q["relevant_ids"]
        r5.append(recall_at_k(got, rel, 5))
        r10.append(recall_at_k(got, rel, 10))
        mr.append(mrr(got, rel))
    print(f"  [{name}] done ({len(queries)} q)")
    return summarize(r5, r10, mr, lat)


def main() -> None:
    rows = load_rows()
    queries = load_queries()
    print(f"embedding {len(rows)} passages ...")
    body_vecs = embed.embed_passages([r["body"] for r in rows])
    qvecs = {q["query_id"]: embed.embed_query(q["query_text"]) for q in queries}

    # ---- baseline(3層): 3モードを実数で比較(TiDBクラスタ無しでも出る) ----
    base = BaselineStore()
    base.build(rows, body_vecs)
    results: dict[str, dict] = {}
    results["D1. baseline vector のみ"] = eval_mode(
        "baseline-vector",
        lambda q: base.vector_only(qvecs[q["query_id"]],
                                   product=q["product"], min_imp=q["min_imp"], topk=10),
        queries)
    results["D2. baseline 全文のみ"] = eval_mode(
        "baseline-fts",
        lambda q: base.fts_only(q["fts_term"],
                                product=q["product"], min_imp=q["min_imp"], topk=10),
        queries)
    results["D3. baseline 3層 hybrid"] = eval_mode(
        "baseline-hybrid",
        lambda q: base.hybrid_rrf(qvecs[q["query_id"]], q["fts_term"],
                                  product=q["product"], min_imp=q["min_imp"], topk=10),
        queries)

    # ---- TiDB(設定済みなら) ----
    if db.configured():
        try:
            conn = db.connect()
            sv = embed.to_sql_vector
            results["A. TiDB vector"] = eval_mode(
                "tidb-vector",
                lambda q: search.vector_only(conn, sv(qvecs[q["query_id"]]),
                                              product=q["product"], min_imp=q["min_imp"], topk=10),
                queries)
            results["B. TiDB fts"] = eval_mode(
                "tidb-fts",
                lambda q: search.fts_only(conn, q["fts_term"],
                                          product=q["product"], min_imp=q["min_imp"], topk=10),
                queries)
            results["C. TiDB hybrid (本命)"] = eval_mode(
                "tidb-hybrid",
                lambda q: search.hybrid_rrf(conn, sv(qvecs[q["query_id"]]), q["fts_term"],
                                            product=q["product"], min_imp=q["min_imp"], topk=10),
                queries)
        except Exception as e:  # noqa: BLE001
            print(f"  TiDB スキップ(未ingest/接続不可?): {e}")
    else:
        print("  TIDB_HOST 未設定 → baseline のみ。クラスタ作成後 make ingest && make bench で全モード。")

    write_report(results, len(rows), len(queries))


def write_report(results: dict[str, dict], n_rows: int, n_q: int) -> None:
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cols = ["recall@5", "recall@10", "MRR", "p50_ms", "p95_ms"]
    lines = [
        "# Bench Results", "",
        f"- メモリ件数: {n_rows} / 評価クエリ: {n_q} / topk=10 / RRF k=60 / 埋め込み: {config.EMBED_BACKEND}({config.EMBED_DIM}d)",
        "- 数値は本repoの `make bench` 由来(合成seed・固定random.seed=42で再現可能)。", "",
        "| モード | " + " | ".join(cols) + " |",
        "|---|" + "|".join(["---"] * len(cols)) + "|",
    ]
    for name, m in results.items():
        lines.append(f"| {name} | " + " | ".join(str(m[c]) for c in cols) + " |")
    lines += [
        "", "## 構成の畳み込み (定性)", "",
        "| 観点 | Before(3層) | After(TiDB 1台) |", "|---|---|---|",
        "| データストア数 | 3 (RDB/ベクトル/全文) | **1** |",
        "| 接続・クライアント | 3 | **1** |",
        "| 構造化×意味×全文 の合成 | アプリ側で RRF マージ実装 | **1 SQL** |",
        "| 二重書き込み/同期 | 必要 | **不要** |",
        "", "> 注: recall は同一アルゴリズム(RRF)のため baseline と TiDB は概ね同等になる想定。",
        "> 本事例の主眼は『品質を保ったままインフラ3→1・マージをSQL化』した点(=有益性/独自性)。",
    ]
    out = config.RESULTS_DIR / "results.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {out}")
    print("\n".join(lines[:8 + len(results)]))


if __name__ == "__main__":
    main()
