"""TiDB 上の3検索モード。hybrid は schema/02_hybrid_recall.sql の実行版
(コメント除去・%(name)s 化)。構造化WHERE×ベクトルANN×全文を 1 SQL の RRF で融合。
"""
from __future__ import annotations

from typing import Optional

# --- ベクトルのみ (ANN は ORDER BY VEC_COSINE_DISTANCE ASC のみ索引利用) ---
SQL_VECTOR = """
SELECT id FROM (
  SELECT id, VEC_COSINE_DISTANCE(embedding, %(qvec)s) AS dist
  FROM memories
  ORDER BY VEC_COSINE_DISTANCE(embedding, %(qvec)s) ASC
  LIMIT 100
) t
WHERE (%(agent)s IS NULL OR id IN (SELECT id FROM memories WHERE agent = %(agent)s))
  AND id IN (SELECT id FROM memories WHERE product_id = %(product)s AND importance >= %(min_imp)s)
ORDER BY dist ASC
LIMIT %(topk)s
"""

# --- 全文のみ ---
SQL_FTS = """
SELECT id FROM memories
WHERE fts_match_word(%(q)s, body)
  AND (%(agent)s IS NULL OR agent = %(agent)s)
  AND product_id = %(product)s
  AND importance >= %(min_imp)s
ORDER BY fts_match_word(%(q)s, body) DESC
LIMIT %(topk)s
"""

# --- ハイブリッド: 構造化 × ANN × 全文 を RRF で1 SQL に (自前実装) ---
SQL_HYBRID = """
WITH
vec_knn AS (
  SELECT id, VEC_COSINE_DISTANCE(embedding, %(qvec)s) AS dist
  FROM memories
  ORDER BY VEC_COSINE_DISTANCE(embedding, %(qvec)s) ASC
  LIMIT 100
),
vec_ranked AS (
  SELECT k.id, ROW_NUMBER() OVER (ORDER BY k.dist ASC) AS rnk
  FROM vec_knn k JOIN memories m ON m.id = k.id
  WHERE (%(agent)s IS NULL OR m.agent = %(agent)s)
    AND m.product_id = %(product)s AND m.importance >= %(min_imp)s
),
fts_ranked AS (
  SELECT id, ROW_NUMBER() OVER (ORDER BY fts_match_word(%(q)s, body) DESC) AS rnk
  FROM memories
  WHERE fts_match_word(%(q)s, body)
    AND (%(agent)s IS NULL OR agent = %(agent)s)
    AND product_id = %(product)s AND importance >= %(min_imp)s
  ORDER BY fts_match_word(%(q)s, body) DESC
  LIMIT 100
),
fused AS (
  SELECT id, SUM(rrf) AS rrf_score FROM (
    SELECT id, 1.0/(%(rrf_k)s + rnk) AS rrf FROM vec_ranked
    UNION ALL
    SELECT id, 1.0/(%(rrf_k)s + rnk) AS rrf FROM fts_ranked
  ) u GROUP BY id
)
SELECT id FROM fused ORDER BY rrf_score DESC LIMIT %(topk)s
"""


def _params(qvec: str, q: str, agent: Optional[str], product: str,
            min_imp: int, topk: int, rrf_k: int = 60) -> dict:
    return {"qvec": qvec, "q": q, "agent": agent, "product": product,
            "min_imp": min_imp, "topk": topk, "rrf_k": rrf_k}


def _run(conn, sql: str, params: dict) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [r[0] for r in cur.fetchall()]


def vector_only(conn, qvec, *, product, min_imp, topk, agent=None):
    return _run(conn, SQL_VECTOR, _params(qvec, "", agent, product, min_imp, topk))


def fts_only(conn, term, *, product, min_imp, topk, agent=None):
    return _run(conn, SQL_FTS, _params("", term, agent, product, min_imp, topk))


def hybrid_rrf(conn, qvec, term, *, product, min_imp, topk, agent=None, rrf_k=60):
    return _run(conn, SQL_HYBRID, _params(qvec, term, agent, product, min_imp, topk, rrf_k))
