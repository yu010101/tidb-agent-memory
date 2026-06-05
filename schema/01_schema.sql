-- =============================================================================
-- AI エージェント共有メモリ (5社マルチエージェント) を TiDB Cloud 1台に統合
--   構造化フィルタ × ベクトルANN × 全文検索 を 1 DB / 1 クエリで
-- 全構文は pingcap/docs (公式) から verbatim 確認済み。出典は各行コメント。
-- =============================================================================
--
-- ★前提 (記事でも明記する落とし穴):
--   1) 全文検索(FULLTEXT/fts_match_word)が使えるのは TiDB Cloud Starter/Essential かつ
--      AWS Frankfurt(eu-central-1) または Singapore(ap-southeast-1) のみ。
--      → クラスタは必ず ap-southeast-1 (Singapore) で作成すること。
--      出典: https://github.com/pingcap/docs/blob/master/ai/guides/vector-search-full-text-search-sql.md
--   2) VECTOR INDEX は TiFlash レプリカに依存。CREATE TABLE 時に索引を定義すれば自動作成される。
--      出典: https://github.com/pingcap/docs/blob/master/ai/reference/vector-search-index.md
--   3) vector search / full-text search はともに beta(early stages)。本番採用時は仕様変動に注意。
--
-- 埋め込み次元: 既定はローカル多言語モデル multilingual-e5-small = 384 次元
--   (APIキー不要で clone&run 可能にするため)。OpenAI text-embedding-3-small を使う場合は 1536 に変更。
-- =============================================================================

DROP TABLE IF EXISTS memories;

CREATE TABLE memories (
    id          BIGINT       PRIMARY KEY,   -- seed側で採番(評価の真値と対応させるため明示id)
    agent       VARCHAR(32)  NOT NULL,   -- claude | gemini | codex | grok | orchestrator
    signal_type VARCHAR(32)  NOT NULL,   -- hypothesis | learning | decision | contact (自社 kb-signal-classifier 準拠)
    body        TEXT         NOT NULL,   -- メモリ本文(自然文)
    embedding   VECTOR(384)  NOT NULL,   -- §VECTOR(D) 確定構文。384=local e5-small / 1536=OpenAI
    importance  TINYINT      NOT NULL DEFAULT 3,   -- 1..5
    product_id  VARCHAR(64),             -- どの事業/プロダクト文脈の記憶か
    source      VARCHAR(64),             -- slack | meeting | git | web ...
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- ▼ ベクトルANNインデックス (HNSW)。二重括弧=式インデックス記法で確定。
    --   作成時と同じ距離関数 VEC_COSINE_DISTANCE を ORDER BY ... ASC で使う時のみ索引が効く。
    --   出典: pingcap/docs vector-search-index.md
    VECTOR INDEX idx_emb ((VEC_COSINE_DISTANCE(embedding))),

    -- ▼ 全文インデックス。日本語を含むので MULTILINGUAL パーサ。BM25 ランキング。
    --   出典: pingcap/docs vector-search-full-text-search-sql.md
    FULLTEXT INDEX fts_body (body) WITH PARSER MULTILINGUAL
);

-- 既存テーブルに後付けする場合 (参考。CREATE時に入れていれば不要):
--   ALTER TABLE memories SET TIFLASH REPLICA 1;                                    -- 先にTiFlashレプリカ
--   CREATE VECTOR INDEX idx_emb ON memories ((VEC_COSINE_DISTANCE(embedding))) USING HNSW;
--   ALTER TABLE memories ADD FULLTEXT INDEX fts_body (body)
--       WITH PARSER MULTILINGUAL ADD_COLUMNAR_REPLICA_ON_DEMAND;
