"""決定論的に合成エージェント記憶を生成し、評価用の真値(eval.yaml)も同時出力する。

- random.seed(42) 固定 → 何度実行しても同一。生成物はコミットしてよい。
- topicクラスタ法: 各トピックに複数メモリを紐づけ、検索クエリの relevant_ids を機械的に確定。
  これで recall@k を主観なしで厳密計算できる(=再現性)。

本データは合成です(本番KBの構造= signal_type 分類を模したもの)。
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_JSONL = ROOT / "seed" / "memories.jsonl"
OUT_EVAL = ROOT / "seed" / "eval.yaml"

AGENTS = ["claude", "gemini", "codex", "grok", "orchestrator"]
SIGNALS = ["hypothesis", "learning", "decision", "contact"]
SOURCES = ["slack", "meeting", "git", "web"]

# 各トピック: (topic_id, product, kw(=fts_term, 3文字以上必須), query_text, 本文の核フレーズ群)
#   ※ FTS5 trigram は3文字未満をマッチできない。kw は必ず3文字以上にし、本文へ確実に含める。
TOPICS = [
    ("pos_refund", "posplus", "返金フロー", "POSの返金フローはどう実装したか",
     ["POSの返金処理で在庫を戻す", "返金時に売上を打ち消す仕訳", "部分返金のときの端数処理", "返金フローのテストケース"]),
    ("tidb_migrate", "openclaw", "TiDB", "専用ベクトルDBをTiDBに統合した経緯",
     ["ベクトルと全文を寄せる", "専用ベクトルDBを廃止する判断", "HNSW索引の構成", "MySQL互換で移行コスト低い"]),
    ("slack_mojibake", "openclaw", "文字化け", "Slack通知の文字化けの原因と対策",
     ["head -cでUTF-8が壊れる", "通知をchar単位truncateで修正", "制御文字の除去helper", "多バイト境界の切断"]),
    ("sns_ban", "sns", "シャドウバン", "SNS連投でシャドウバンされた件",
     ["15分15件の連投でbanされた", "投稿間隔を15分強制", "Metaで再発", "バーストを抑えるガード"]),
    ("cron_auth", "openclaw", "認証エラー", "無人cronのclaude認証が落ちる問題",
     ["agent同時にログイン要求", "refresh_tokenのクロバー", "flockで直列化", "429 backoffを入れる"]),
    ("cf_pages", "shozai", "デプロイ", "CF Pagesの無人デプロイが突然死する",
     ["wranglerをローカルにピン留め", "esbuild欠落で失敗", "権限エラーと取得エラーの切り分け", "cronで安定化"]),
    ("embed_cost", "openclaw", "埋め込み", "埋め込み再生成のコストとチャンク設計",
     ["23000件の再生成", "チャンク重複排除", "失敗リトライ", "メタデータ整形に時間を食う"]),
    ("voice_kb", "openclaw", "音声認識", "音声を経営KBに取り込むシグナル層",
     ["会議をKBに反映", "発話区切りで要約", "L5シグナルとして格納", "構造化メモリへ変換"]),
    ("debate_os", "openclaw", "debate", "5社AIを対立させるdebate OSを作った",
     ["学習源の違う4社で対立", "Proposer/Critic/Defender構成", "反論を一次情報で裏取り", "precisionを上げる"]),
    ("llm_router", "openclaw", "ルーター", "脳コストをllm-routerで最適化した",
     ["OpusからcodexへフェイルオープンでBulk", "usage-meterで計測", "月コストを削減", "fail-openの切替"]),
    ("freee_recv", "finance", "未決済", "freeeの未決済が実態と乖離する",
     ["回収済なのに残る", "消込漏れの検出", "督促前に実入金確認", "貸倒判定の前段"]),
    ("kagoya_waf", "media", "SiteGuard", "Kagoyaのwafがdeleteをブロックする",
     ["LiteがPOST設定を弾く", "X-HTTP-Method-Overrideで迂回", "DELETEがブロックされる", "WAF回避の実装"]),
    ("yt_caption", "youtube", "字幕取得", "YouTube字幕取得がIP banされる",
     ["429で停止", "yt-dlp更新で迂回", "whisperで代替", "プロキシ経由の検討"]),
    ("pm2_env", "openclaw", "PM2", "PM2のenv欠落で大量restartした",
     ["env読込ラッパー必須", "52000 restart事故", "launchdではなく常駐", "再起動を安定化"]),
    ("vector_prefilter", "openclaw", "プレフィルタ", "ベクトル検索のプレフィルタ罠",
     ["WHERE付きANNで索引が無効", "KNN先取りで回避", "後段で構造化フィルタ", "ORDER BY ASCのみ索引利用"]),
    ("region_fts", "openclaw", "リージョン", "全文検索のリージョン制約に詰まった",
     ["全文検索はSingaporeのみ", "USで作ると関数が無い", "ap-southeast-1で作り直し", "fts_match_wordが無い"]),
    ("rrf_fusion", "openclaw", "RRF", "公式に無い生SQLのRRFを自前実装した",
     ["pytidbのfusionに頼らない", "ROW_NUMBERで順位採番", "1/(k+rank)で合算", "vectorとftsを融合"]),
    ("tiflash", "openclaw", "TiFlash", "VECTOR索引がTiFlashに依存する",
     ["索引定義でレプリカ自動作成", "後付けはSET REPLICA", "列ストアに乗る", "ベクトル索引の前提"]),
]

# ノイズ(無関係)トピック: 検索を難しくする
NOISE = [
    ("noise_a", "misc", ["天気が良いので散歩した", "コーヒーを淹れた", "猫が膝に乗ってきた"]),
    ("noise_b", "misc", ["プリンタのインクを買った", "電車が遅延した", "ランチはカレーだった"]),
]


def vary(phrase: str, rng: random.Random) -> str:
    tails = ["。", "とメモ。", "（要確認）。", "→対応済み。", "。あとで再検討。"]
    heads = ["", "メモ: ", "気づき: ", "決定: ", "TODO: "]
    return rng.choice(heads) + phrase + rng.choice(tails)


def main() -> None:
    rng = random.Random(42)
    rows = []
    topic_members: dict[str, list[int]] = {}
    next_id = 1

    # シグナルトピック: 各 18〜22 件
    for topic_id, product, kw, _q, cores in TOPICS:
        members = []
        n = rng.randint(18, 22)
        for _ in range(n):
            core = rng.choice(cores)
            body = vary(core, rng)
            # 約70%は kw を本文に含める(全文検索で拾える)。
            # 残り約30%は kw を含めない言い換えのまま = ベクトルでしか拾えない関連文書。
            # → これで FTS単独 recall<1.0 となり、hybrid の優位を非自明に示せる。
            if rng.random() < 0.70 and kw not in body:
                body = f"{body[:-1]}（{kw}）"
            row = {
                "id": next_id,
                "agent": rng.choice(AGENTS),
                "signal_type": rng.choice(SIGNALS),
                "body": body,
                "importance": rng.randint(1, 5),
                "product_id": product,
                "source": rng.choice(SOURCES),
                "created_at": f"2026-{rng.randint(1,6):02d}-{rng.randint(1,28):02d} {rng.randint(0,23):02d}:00:00",
                "topic_id": topic_id,  # 評価用。TiDBには入れない。
            }
            rows.append(row)
            members.append(next_id)
            next_id += 1
        topic_members[topic_id] = members

    # ノイズ
    for topic_id, product, cores in NOISE:
        for _ in range(rng.randint(12, 16)):
            rows.append({
                "id": next_id, "agent": rng.choice(AGENTS), "signal_type": rng.choice(SIGNALS),
                "body": vary(rng.choice(cores), rng), "importance": rng.randint(1, 5),
                "product_id": product, "source": rng.choice(SOURCES),
                "created_at": f"2026-{rng.randint(1,6):02d}-{rng.randint(1,28):02d} 12:00:00",
                "topic_id": topic_id,
            })
            next_id += 1

    rng.shuffle(rows)
    OUT_JSONL.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

    # eval.yaml: 各シグナルトピックを1クエリに。フィルタは min_imp>=2 を課して真値を絞る。
    by_id = {r["id"]: r for r in rows}
    eval_lines = ["# 自動生成。各クエリの relevant_ids はトピック所属 かつ フィルタ充足のメモリ。", "queries:"]
    for topic_id, product, fts_term, q, _cores in TOPICS:
        min_imp = 2
        relevant = sorted(i for i in topic_members[topic_id] if by_id[i]["importance"] >= min_imp)
        eval_lines += [
            f"  - query_id: {topic_id}",
            f"    query_text: \"{q}\"",
            f"    fts_term: \"{fts_term}\"",
            f"    product: {product}",
            f"    min_imp: {min_imp}",
            f"    relevant_ids: [{', '.join(map(str, relevant))}]",
        ]
    OUT_EVAL.write_text("\n".join(eval_lines) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} memories -> {OUT_JSONL.name}")
    print(f"wrote {len(TOPICS)} eval queries -> {OUT_EVAL.name}")


if __name__ == "__main__":
    main()
