"""埋め込み生成。既定はローカル多言語モデル(APIキー不要)。

local: intfloat/multilingual-e5-small (384次元)。e5系は "query:" / "passage:" プレフィクス規約。
openai: text-embedding-3-small (1536次元)。
"""
from __future__ import annotations

import functools

import numpy as np

from . import config


@functools.lru_cache(maxsize=1)
def _local_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("intfloat/multilingual-e5-small")


def _embed_local(texts: list[str], prefix: str) -> np.ndarray:
    model = _local_model()
    inputs = [f"{prefix}: {t}" for t in texts]
    vecs = model.encode(inputs, normalize_embeddings=True, convert_to_numpy=True)
    return np.asarray(vecs, dtype=np.float32)


def _embed_openai(texts: list[str]) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI()
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return np.asarray([d.embedding for d in resp.data], dtype=np.float32)


def embed_passages(texts: list[str]) -> np.ndarray:
    """格納する記憶本文の埋め込み。"""
    if config.EMBED_BACKEND == "openai":
        return _embed_openai(texts)
    return _embed_local(texts, "passage")


def embed_query(text: str) -> np.ndarray:
    """検索クエリの埋め込み(1件)。"""
    if config.EMBED_BACKEND == "openai":
        return _embed_openai([text])[0]
    return _embed_local([text], "query")[0]


def to_sql_vector(vec: np.ndarray) -> str:
    """TiDB の VECTOR 列に渡す '[v1, v2, ...]' 文字列。"""
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"
