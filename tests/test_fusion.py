"""RRF融合と評価メトリクスの正しさをオフライン検証(モデル/TiDB不要)。

`python3 tests/test_fusion.py` で実行。bench harness の算術が正しいことを保証する。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.fusion import mrr, recall_at_k, rrf_fuse


def approx(a, b, eps=1e-9):
    return abs(a - b) < eps


def test_rrf_basic():
    # list1: [A,B,C], list2: [B,A,D]  (k=60)
    fused = rrf_fuse([[1, 2, 3], [2, 1, 4]], k=60)
    # scores: id1 = 1/61 + 1/62 ; id2 = 1/62 + 1/61 (同点) ; id3=1/63 ; id4=1/63
    s1 = 1/61 + 1/62
    s2 = 1/62 + 1/61
    assert approx(s1, s2)
    assert set(fused[:2]) == {1, 2}, fused
    assert set(fused[2:]) == {3, 4}, fused
    print("ok test_rrf_basic")


def test_rrf_rank_matters():
    # 同じidでも上位ほど高スコア
    fused = rrf_fuse([[5, 6], [5, 6]], k=1)
    assert fused == [5, 6]
    print("ok test_rrf_rank_matters")


def test_recall():
    retrieved = [10, 11, 12, 13, 14]
    relevant = [12, 14, 99]
    # @5: hit {12,14}=2, min(len(rel),k)=min(3,5)=3 -> 2/3
    assert approx(recall_at_k(retrieved, relevant, 5), 2/3)
    # @1: hit 0 -> 0
    assert approx(recall_at_k(retrieved, relevant, 1), 0.0)
    # 全件関連かつkで頭打ち
    assert approx(recall_at_k([1, 2, 3], [1, 2, 3], 2), 1.0)
    print("ok test_recall")


def test_mrr():
    assert approx(mrr([9, 8, 7], [7]), 1/3)
    assert approx(mrr([7, 8, 9], [7]), 1.0)
    assert approx(mrr([1, 2], [99]), 0.0)
    print("ok test_mrr")


if __name__ == "__main__":
    test_rrf_basic()
    test_rrf_rank_matters()
    test_recall()
    test_mrr()
    print("\nALL PASS")
