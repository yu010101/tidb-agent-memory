.PHONY: setup seed schema ingest bench test all clean

PY ?= python3
VENV = .venv
BIN = $(VENV)/bin

setup:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -U pip
	$(BIN)/pip install -r requirements.txt

seed:
	$(PY) seed/make_seed.py

# TiDB(Singaporeリージョン)へスキーマ適用。要 mysql クライアント or 下の python 適用を使う。
schema:
	$(BIN)/python -c "import pymysql,sys; sys.path.insert(0,'.'); from src import db; \
c=db.connect(); \
[c.cursor().execute(s) for s in open('schema/01_schema.sql',encoding='utf-8').read().split(';') if s.strip() and not s.strip().startswith('--')]; \
print('schema applied')"

ingest:
	$(BIN)/python -m src.ingest

bench:
	$(BIN)/python bench/run_bench.py

test:
	$(PY) tests/test_fusion.py

all: seed test bench

clean:
	rm -rf $(VENV) bench/results/*.md seed/memories.jsonl seed/eval.yaml
