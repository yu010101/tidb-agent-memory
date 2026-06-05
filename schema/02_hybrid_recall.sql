-- =============================================================================
-- エージェント記憶の想起クエリ: 構造化WHERE × ベクトルANN × 全文 を 1 SQL で
--   公式のhybrid searchガイドは pytidbの .fusion() のみ案内で、生SQLのRRF融合の完全例が見当たらない。
--   → ここでは RRF (Reciprocal Rank Fusion, score = Σ 1/(k+rank)) を
--     ROW_NUMBER() で生SQL自前実装する。これが本記事の独自貢献。
--   出典(融合は未提供の確認): https://github.com/pingcap/docs/blob/master/ai/guides/vector-search-hybrid-search.md
-- =============================================================================
--
-- パラメータ:
--   :qvec        検索クエリの埋め込み (例 '[0.01, -0.02, ...384個...]')
--   :q           検索語 (例 "POSの返金フロー")
--   :agent       想起したいエージェント文脈 (例 'orchestrator'。全エージェント横断なら条件を外す)
--   :product     プロダクト文脈 (例 'posplus')
--   :min_imp     重要度しきい値 (例 3)
--   :rrf_k       RRF定数 (公式pytidb既定=60)
--   :topk        最終返却件数 (例 10)
--
-- 設計上の罠と対処 (記事の山場):
--   ・ベクトルANNは WHERE プレフィルタを付けると索引が無効化される。
--     → vec_ann で先に KNN を多めに取り(LIMIT 100)、構造化フィルタは「後段」で適用する。
--   ・ANN は ORDER BY VEC_COSINE_DISTANCE(...) ASC のみ索引利用(DESC不可)。

WITH
-- (A) ベクトル枝: 索引を効かせるため純粋KNNを先に取得 (プレフィルタ無し)
vec_knn AS (
    SELECT id, body, agent, signal_type, importance, product_id, created_at,
           VEC_COSINE_DISTANCE(embedding, :qvec) AS dist
    FROM memories
    ORDER BY VEC_COSINE_DISTANCE(embedding, :qvec) ASC   -- 索引利用条件: 作成時と同関数 + ASC
    LIMIT 100
),
-- 構造化フィルタは KNN の「後」で適用 + ベクトル順位 rank を採番
vec_ranked AS (
    SELECT id, body, agent, signal_type, importance, product_id, created_at, dist,
           ROW_NUMBER() OVER (ORDER BY dist ASC) AS rnk
    FROM vec_knn
    WHERE (:agent   IS NULL OR agent = :agent)
      AND (:product IS NULL OR product_id = :product)
      AND importance >= :min_imp
),
-- (B) 全文枝: fts_match_word を WHERE/ORDER BY で使用。構造化フィルタは同一クエリ内で併用可。
fts_ranked AS (
    SELECT id, body, agent, signal_type, importance, product_id, created_at,
           fts_match_word(:q, body) AS score,
           ROW_NUMBER() OVER (ORDER BY fts_match_word(:q, body) DESC) AS rnk
    FROM memories
    WHERE fts_match_word(:q, body)
      AND (:agent   IS NULL OR agent = :agent)
      AND (:product IS NULL OR product_id = :product)
      AND importance >= :min_imp
    ORDER BY fts_match_word(:q, body) DESC
    LIMIT 100
),
-- (C) RRF 融合: id ごとに Σ 1/(k+rank) を合算 (生SQL自前実装)
fused AS (
    SELECT id,
           SUM(rrf) AS rrf_score,
           MAX(vdist) AS vector_distance,
           MAX(fscore) AS fts_score
    FROM (
        SELECT id, 1.0/(:rrf_k + rnk) AS rrf, dist  AS vdist, NULL AS fscore FROM vec_ranked
        UNION ALL
        SELECT id, 1.0/(:rrf_k + rnk) AS rrf, NULL  AS vdist, score AS fscore FROM fts_ranked
    ) u
    GROUP BY id
)
SELECT m.id, m.agent, m.signal_type, m.importance, m.product_id, m.created_at,
       f.rrf_score, f.vector_distance, f.fts_score,
       LEFT(m.body, 80) AS body_preview
FROM fused f
JOIN memories m ON m.id = f.id
ORDER BY f.rrf_score DESC
LIMIT :topk;
