# Zenn記事 骨子 — TiDBテーマ応募

**タイトル候補(再現性・課題を前面に / ハンズオン示唆の動詞)**
1. 「5社のAIエージェントの"共有記憶"を、専用ベクトルDBを捨ててTiDB Cloud 1台に畳んだ」
2. 「AIエージェントのメモリを TiDB に統合した — 構造化フィルタ×ベクトル×全文検索を1 SQLで」
3. 「RAGの3層構成(ベクトルDB＋全文＋RDB)を、TiDBの1クエリに置き換えた実装と実測」

→ 1 を主、副題に 2 の技術要素。idea/ポエム語(「考える」等)は避け「畳んだ/統合した/置き換えた」。

**想定文字数**: 6,000–9,000字 + コードブロック多数 + 構成図2点 + bench表2点 + デモGIF1点。

---

## 構成 (各節を審査軸にマッピング)

### 0. TL;DR (冒頭3行 + 構成図 before/after)
- 3層→1台。recall@10 は X→Y、レイテンシ p95 は A→B(repo実測)。clone&run可能なrepo: <URL>。
- [独自性][有益性] 最初の5秒で「これは本番級の畳み込み事例」と伝える。

### 1. 課題: マルチエージェントの“記憶”が散らばる [有益性/課題解決]
- 5社のAI(Claude/Gemini/Codex/Grok+orchestrator)が観測・決定・学びを書き、後で想起する必要。
- 想起の要求が複合的: 「**orchestratorが書いた / posplus文脈の / 重要度3以上で / 意味的に"返金フロー"に近く / "TiDB"を含む** 記憶」。
- これを満たすには 構造化フィルタ＋ベクトル類似＋全文 の3種を同時に効かせたい。
- 従来=ベクトルDB+全文エンジン+RDBの3層 → 同期・マージ・運用が重い。

### 2. 設計: TiDB 1台に畳む [独自性/有益性]
- memories テーブル(VECTOR(384) + FULLTEXT MULTILINGUAL)の DDL を提示(schema/01)。
- なぜTiDBか: 1つのSQLで構造化×ベクトル×全文。MySQL互換で既存ORM流用。
- kb-signal-classifier(自社の signal_type: hypothesis/learning/decision/contact)に接地。

### 3. 実装ハンズオン (ここが本体) [再現性]
- 3-1 クラスタ作成: **ap-southeast-1(Singapore)必須**の罠を最初に(全文検索のリージョン制約)。
- 3-2 スキーマ適用 / TiFlashレプリカが自動で乗る話。
- 3-3 埋め込み(ローカルe5-small, APIキー不要)→ ingest。
- 3-4 想起クエリ(schema/02)を一行ずつ解説:
    - ANNは `ORDER BY VEC_COSINE_DISTANCE ASC` 限定、**WHEREプレフィルタで索引が死ぬ**→KNN先取り回避策。
    - `fts_match_word("語", body)` を WHERE/ORDER BY DESC で。
    - **公式に生SQLのRRF例が無い**ので `ROW_NUMBER()+1/(k+rank)` で自前融合 ← 独自貢献。

### 4. 実測: before(3層) vs after(TiDB 1台) [有益性/再現性]
- bench表: recall@5/@10, MRR, p50/p95 を 4モード(vector/fts/hybrid/baseline)で。
- 構成の畳み込み表: ストア数3→1, 接続3→1, アプリ側マージ→1 SQL, 二重書き込み→不要。
- **数値はrepoのbench由来**＝読者が同じ数字を再現可能、と明記。

### 5. 詰まりどころ集 [再現性/有益性] ← 審査員(中の人)が一番うなる節
- リージョン制約 / プレフィルタ索引無効 / RRF自前 / TiFlash依存 / beta仕様変動。
- 各々「症状→原因→回避」の3行で。

### 6. まとめ + 限界 [独自性/正直性]
- 向く用途/向かない用途。beta機能の本番採用判断。
- 合成データで検証した旨を明記(正直性)。次の一手(本番KB全面移行は別記事)。

### 付録
- 全コードのrepoリンク、`make all`一発再現、ライセンス。

---

## 投稿前チェック
- [ ] repo が fresh env で `make all` 通過(別マシン/CIで検証)。
- [ ] 技術主張を `/debate verify` に通す(構文・リージョン・beta表記の事実確認)。
- [ ] TiDB Cloud を実使用(加点)。
- [ ] 数値はbench由来のみ。誇張・未公開本番数値なし。
- [ ] タイトルに具体技術名(TiDB)＋動詞。サムネ/OGP整備。
