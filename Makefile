.PHONY: setup seed schema ingest bench demo test all clean

PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -r requirements.txt

seed:
	$(PY) seed/make_seed.py

# TiDB(Singaporeリージョン)へスキーマ適用。コメント除去→;分割で堅牢に実行。
schema:
	$(BIN)/python -m src.apply_schema

ingest:
	$(BIN)/python -m src.ingest

bench:
	$(BIN)/python bench/run_bench.py

# 想起デモ(クラスタ無しでも動く=baseline)。--tidb で TiDB 実行に切替。
demo:
	$(BIN)/python -m src.recall --query "POSの返金フローはどう実装したか" \
		--term 返金フロー --product posplus --min-imp 2 --topk 8

test:
	$(PY) tests/test_fusion.py

all: seed test bench

clean:
	rm -rf $(VENV) bench/results/*.md seed/memories.jsonl seed/eval.yaml
