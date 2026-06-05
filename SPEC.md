# Build SPEC — tidb-agent-memory (Zenn Fes Spring 2026 / TiDBテーマ)

**狙い**: 「5社のAIエージェントが共有する記憶を、専用ベクトルDB＋別の全文検索＋RDB の3層から
TiDB Cloud 1台に畳んだ」を、**誰でも fresh 環境で 10分 clone&run できる最小repo**で証明する。
本番システムは権威の背景。**証拠は repo の bench が自分で出す数値**（出せない本番数値は載せない=正直性ガード）。

審査軸への対応:
- **再現性(筆頭)** → APIキー不要(ローカル埋め込み既定)・seed同梱・`make all`で全再現・bench数値もrepo産。
- **有益性/課題解決** → 「RAGの3層構成を1 SQLに畳む」実装パターン＋詰まりどころ(プレフィルタ罠/リージョン制約/RRF自前実装)を手順化。
- **独自性** → ①5社マルチエージェント共有記憶という題材 ②公式に無い"生SQL RRF"を ROW_NUMBER() で実装。

---

## 1. ディレクトリ構成
```
tidb-agent-memory/
├── README.md              # clone&run 手順。冒頭にリージョン警告(Singapore必須)
├── .env.example           # TIDB_DSN, EMBED_BACKEND=local|openai, OPENAI_API_KEY(任意)
├── Makefile               # make setup / seed / ingest / search / bench / all
├── requirements.txt       # pymysql, sqlalchemy, sentence-transformers, numpy, pyyaml, (openai任意)
├── schema/
│   ├── 01_schema.sql      # ✅作成済: memories(VECTOR(384)+FULLTEXT MULTILINGUAL)
│   └── 02_hybrid_recall.sql # ✅作成済: 構造化×ANN×全文 を RRF自前実装で1 SQL
├── seed/
│   ├── make_seed.py       # 決定論的(seed固定)に合成メモリ生成＋評価用 ground-truth も同時出力
│   ├── memories.jsonl     # 生成物: ~400行 (5 agent × 4 signal_type × 複数 product / topicクラスタ)
│   └── eval.yaml          # 生成物: 40クエリ × 各クエリの relevant_ids(クラスタ由来=真値)
├── src/
│   ├── config.py          # env読込, DSN, 埋め込み次元
│   ├── embed.py           # local: multilingual-e5-small(384) / openai: 3-small(1536)
│   ├── ingest.py          # jsonl→embed→INSERT (バッチ, 進捗, リトライ)
│   ├── search.py          # vector_only / fts_only / hybrid_rrf の3関数(02のSQLを実行)
│   └── recall.py          # エージェント想起API: recall(query, agent=, product=, min_imp=)
├── before/
│   ├── README.md          # 旧3層構成(pgvector相当 + 全文 + RDB)の説明と構成図
│   └── baseline.py        # ローカルで“前の構成”を実装(chroma or numpy + sqlite FTS)し同条件bench
├── bench/
│   ├── run_bench.py       # recall@5/@10, MRR, latency p50/p95 を 4モード比較
│   └── results/           # 生成物: results.md + scores.csv + (任意)matplotlib図
└── article/
    └── outline.md         # ✅作成済: Zenn記事の骨子(審査軸マッピング)
```

## 2. seed/make_seed.py 設計 (再現性と真値の肝)
- `random.seed(42)` 固定。生成物はコミットするので clone 時に再生成不要でも一致。
- **topicクラスタ法で ground-truth を作る**: 例 20 トピック(例「POS返金フロー」「TiDB移行」「Slack通知の文字化け」…)。
  各トピックに 15-25 本のメモリ本文をテンプレ＋語彙ゆらぎで生成し `topic_id` を付与。
- 各メモリに agent(5種), signal_type(4種), product_id, importance(1-5), source, created_at を分布付与。
- `eval.yaml`: 各トピックから「検索クエリ文＋構造化フィルタ条件」を作り、
  `relevant_ids = そのtopic_id かつ フィルタを満たすメモリ群` を真値として書き出す。
  → これで recall@k が**機械的に厳密計算**できる(主観評価なし=再現性)。
- 正直性: 合成データである旨を README と記事に明記。「本番KBの構造(kb-signal-classifier準拠)を模した合成」と書く。

## 3. embed.py
- 既定 `EMBED_BACKEND=local`: `intfloat/multilingual-e5-small` (384次元, 日本語対応, CPUで可)。**APIキー不要**。
- 任意 `EMBED_BACKEND=openai`: `text-embedding-3-small`(1536)。その場合 schema の VECTOR(384)→VECTOR(1536) に置換する旨を README に明記。
- e5系は `query:` / `passage:` プレフィクス規約に従う(検索側=query, 格納側=passage)。

## 4. bench/run_bench.py — before/after を“実測”で出す
比較する4モード:
| モード | retrieval |
|---|---|
| A. vector_only (TiDB) | ANN のみ |
| B. fts_only (TiDB) | 全文のみ |
| C. **hybrid_rrf (TiDB, 本命)** | 02のSQL=構造化×ANN×全文 を RRF融合 |
| D. **baseline (before, 旧3層)** | before/baseline.py: numpy/chroma でベクトル + sqlite FTS + 手書きマージ |

メトリクス: `recall@5`, `recall@10`, `MRR`, レイテンシ `p50/p95`(同一マシン/同一クエリ集合)。
出力 `results/results.md` に表＋(任意)図。**記事の数値はこの表をそのまま引用**(=読者が再現可能)。

定性比較(構成の畳み込み)も表で:
| 観点 | Before(3層) | After(TiDB 1台) |
|---|---|---|
| データストア数 | 3 (RDB/ベクトル/全文) | **1** |
| 接続文字列/クライアント | 3 | **1** |
| 「構造化フィルタ＋意味検索＋キーワード」の合成 | アプリ側でマージ実装 | **1 SQL** |
| データ同期(二重書き込み) | 必要 | **不要** |
| 構成図の箱 | ~4 | **1** |

## 5. before/baseline.py (正直で再現可能な“前”)
- 本番で特定の専用VDBを使っていた、とは**書かない**(誇張禁止)。
- 代わりに「**業界標準のRAG構成**(ベクトルストア＋全文エンジン＋RDBを別々に持つ典型)」を
  ローカル最小実装し、**同じseed・同じクエリで実測**。→ 比較が主張でなく実験になる。

## 6. Makefile ターゲット
```
make setup   # venv + pip install + (local model 初回DL)
make seed    # make_seed.py → memories.jsonl + eval.yaml
make schema  # 01_schema.sql を TIDB_DSN に適用
make ingest  # embed + INSERT
make bench   # 4モード比較 → results/results.md
make all     # 上を一括
```

## 7. 記事に必ず入れる“ハンズオン深度の証拠”(差別化)
1. **リージョン罠**: 全文検索は ap-southeast-1/eu-central-1 のみ。US で作ると `fts_match_word` が無く詰む実体験。
2. **プレフィルタ罠**: `WHERE`付きANNは索引無効化 → KNN先取り→後段フィルタの回避策(02のCTE設計)。
3. **公式に無いRRFを生SQLで**: pytidbの`.fusion()`に頼らず ROW_NUMBER()+1/(k+rank) を実装。
4. **TiFlashレプリカ依存**: VECTOR INDEXがTiFlashに乗る挙動と、後付け時の `SET TIFLASH REPLICA 1`。
5. beta明記と本番採用判断の所感(有益性)。

## 8. 正直性チェックリスト (feedback_no_oversell / no_fabrication)
- [ ] 数値はすべて repo の bench 由来。本番の未公開数値は載せない。
- [ ] seed は合成である旨を明記。
- [ ] 「稼働中」等の誇張なし。beta機能はbetaと書く。
- [ ] 技術主張は公開後に `/debate verify` を通してから投稿。
