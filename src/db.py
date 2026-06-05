"""TiDB Cloud 接続。TiDB Cloud は TLS 必須。"""
from __future__ import annotations

import pymysql

from . import config


def connect() -> pymysql.connections.Connection:
    t = config.TIDB
    if not t["host"] or not t["user"]:
        raise RuntimeError("TIDB_HOST / TIDB_USER 未設定 (.env を確認)")
    return pymysql.connect(
        host=t["host"], port=t["port"], user=t["user"],
        password=t["password"], database=t["database"],
        ssl={"ssl": {}},  # TiDB Cloud は TLS 必須。OSのCAバンドルで検証。
        charset="utf8mb4", autocommit=True,
    )


def configured() -> bool:
    return bool(config.TIDB["host"] and config.TIDB["user"])
