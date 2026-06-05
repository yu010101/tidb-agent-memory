"""Before(旧3層構成)のローカル再現。

「業界標準のRAG構成」= ベクトルストア(別) + 全文エンジン(別) + RDB(別) を別々に持ち、
構造化フィルタ・ベクトル類似・全文を **アプリ側でマージ** する典型を最小実装。
TiDB(1台/1 SQL)との apples-to-apples 比較のため、検索アルゴリズム(RRF)は同一。

- ベクトルストア: numpy(正規化済み埋め込みの内積=cosine) … 別システムの代役
- 全文エンジン  : sqlite FTS5 trigram(日本語の部分一致に対応) … 別システムの代役
- メタ(構造化)  : sqlite 通常テーブル … 別システムの代役
これらを跨いでアプリ側で RRF 融合する = 二重書き込み・3クライアント・マージ実装が必要。
"""
from __future__ import annotations

import sqlite3
from typing import Optional

import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.fusion import rrf_fuse  # noqa: E402


class BaselineStore:
    """3つのストアを別々に持つ“前”の構成。"""

    def __init__(self) -> None:
        self.meta = sqlite3.connect(":memory:")
        self.meta.execute(
            "CREATE TABLE memories(id INTEGER PRIMARY KEY, agent TEXT, signal_type TEXT, "
            "body TEXT, importance INT, product_id TEXT)"
        )
        self.meta.execute(
            "CREATE VIRTUAL TABLE fts USING fts5(body, content='', tokenize='trigram')"
        )
        self.ids: list[int] = []
        self.vectors: Optional[np.ndarray] = None  # (N, dim) 正規化済み

    def build(self, rows: list[dict], embeddings: np.ndarray) -> None:
        self.ids = [r["id"] for r in rows]
        # 別システム①: メタ(構造化) / 別システム②: 全文 へ「二重書き込み」
        for r in rows:
            self.meta.execute(
                "INSERT INTO memories VALUES (?,?,?,?,?,?)",
                (r["id"], r["agent"], r["signal_type"], r["body"], r["importance"], r["product_id"]),
            )
        for r in rows:
            self.meta.execute("INSERT INTO fts(rowid, body) VALUES (?,?)", (r["id"], r["body"]))
        self.meta.commit()
        # 別システム③: ベクトルストア
        self.vectors = embeddings.astype(np.float32)
        self._id_to_row = {i: n for n, i in enumerate(self.ids)}

    # --- 構造化フィルタ(メタストアに問い合わせ) ---
    def _allowed(self, product: str, min_imp: int, agent: Optional[str]) -> set[int]:
        q = "SELECT id FROM memories WHERE product_id=? AND importance>=?"
        args: list = [product, min_imp]
        if agent is not None:
            q += " AND agent=?"
            args.append(agent)
        return {r[0] for r in self.meta.execute(q, args).fetchall()}

    def vector_ids(self, qvec: np.ndarray, k: int = 100) -> list[int]:
        sims = self.vectors @ qvec.astype(np.float32)
        order = np.argsort(-sims)[:k]
        return [self.ids[i] for i in order]

    def fts_ids(self, term: str, k: int = 100) -> list[int]:
        rows = self.meta.execute(
            "SELECT rowid FROM fts WHERE fts MATCH ? LIMIT ?", (term, k)
        ).fetchall()
        return [r[0] for r in rows]

    def vector_only(self, qvec, *, product, min_imp, topk, agent=None):
        allowed = self._allowed(product, min_imp, agent)
        return [i for i in self.vector_ids(qvec, 100) if i in allowed][:topk]

    def fts_only(self, term, *, product, min_imp, topk, agent=None):
        allowed = self._allowed(product, min_imp, agent)
        return [i for i in self.fts_ids(term, 100) if i in allowed][:topk]

    def hybrid_rrf(self, qvec, term, *, product, min_imp, topk, agent=None, rrf_k=60):
        allowed = self._allowed(product, min_imp, agent)
        vec = [i for i in self.vector_ids(qvec, 100) if i in allowed]
        fts = [i for i in self.fts_ids(term, 100) if i in allowed]
        # アプリ側で2システムの結果を RRF 融合(=TiDBなら1 SQLで済む部分)
        return rrf_fuse([vec, fts], k=rrf_k)[:topk]
