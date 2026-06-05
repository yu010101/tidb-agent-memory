"""RRF 融合と評価メトリクス(検索手段に依存しない純ロジック)。

TiDBパスは RRF を生SQLで行うが、同じ式をここにも置き baseline と単体テストで共有する。
RRF: score(id) = Σ_over_lists 1 / (k + rank_in_list)   (rank は1始まり, k 既定60=pytidb準拠)
"""
from __future__ import annotations

from typing import Iterable, Sequence


def rrf_fuse(rankings: Sequence[Sequence[int]], k: int = 60) -> list[int]:
    """複数の順位付きid列(各々ベスト順)を RRF で融合し、id を高スコア順に返す。"""
    scores: dict[int, float] = {}
    for ranked in rankings:
        for rank, _id in enumerate(ranked, start=1):
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: scores[i], reverse=True)


def recall_at_k(retrieved: Sequence[int], relevant: Iterable[int], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    hit = sum(1 for i in retrieved[:k] if i in rel)
    return hit / min(len(rel), k)


def mrr(retrieved: Sequence[int], relevant: Iterable[int]) -> float:
    rel = set(relevant)
    for rank, i in enumerate(retrieved, start=1):
        if i in rel:
            return 1.0 / rank
    return 0.0
