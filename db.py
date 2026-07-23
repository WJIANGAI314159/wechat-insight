#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 数据库模块
使用 SQLite 存储历史报告，同时作为搜索缓存
"""

import os
import sqlite3
import json
import time
from datetime import datetime

# 数据库文件路径：本地用 insight.db，Render 上用 /var/data/insight.db 或环境变量指定
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "insight.db"))

# 缓存有效期（秒）：相同关键词+时间范围在此时长内直接返回缓存
CACHE_TTL = 6 * 3600  # 6小时


def get_conn():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            days INTEGER NOT NULL,
            total_results INTEGER DEFAULT 0,
            sentiment_hint TEXT,
            summary TEXT,
            created_at TEXT NOT NULL,
            created_ts REAL NOT NULL,
            data_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_query
        ON reports(query, days, created_ts)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_created
        ON reports(created_ts DESC)
    """)
    conn.commit()
    conn.close()


def save_report(query: str, days: int, total_results: int,
                articles: list, analysis: dict) -> int:
    """保存一份搜索报告，返回报告 ID"""
    now = datetime.now()
    data = {
        "query": query,
        "days": days,
        "total_results": total_results,
        "articles": articles,
        "analysis": analysis,
        "error": None,
    }
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO reports
           (query, days, total_results, sentiment_hint, summary, created_at, created_ts, data_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            query,
            days,
            total_results,
            analysis.get("sentiment_hint", ""),
            analysis.get("summary", ""),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            now.timestamp(),
            json.dumps(data, ensure_ascii=False),
        ),
    )
    report_id = cur.lastrowid
    conn.commit()
    conn.close()
    return report_id


def get_cached_report(query: str, days: int) -> dict | None:
    """
    查找缓存：相同关键词 + 相同时间范围 + 在 CACHE_TTL 内
    如果找到返回完整数据 dict，否则返回 None
    """
    cutoff = time.time() - CACHE_TTL
    conn = get_conn()
    row = conn.execute(
        """SELECT data_json, id FROM reports
           WHERE query = ? AND days = ? AND created_ts > ?
           ORDER BY created_ts DESC LIMIT 1""",
        (query, days, cutoff),
    ).fetchone()
    conn.close()
    if row:
        data = json.loads(row["data_json"])
        data["cached"] = True
        data["report_id"] = row["id"]
        return data
    return None


def get_all_reports(limit: int = 50) -> list:
    """获取所有历史报告列表（摘要信息）"""
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, query, days, total_results, sentiment_hint,
                  summary, created_at, created_ts
           FROM reports
           ORDER BY created_ts DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_report_by_id(report_id: int) -> dict | None:
    """根据 ID 获取完整报告数据"""
    conn = get_conn()
    row = conn.execute(
        "SELECT data_json, created_at FROM reports WHERE id = ?",
        (report_id,),
    ).fetchone()
    conn.close()
    if row:
        data = json.loads(row["data_json"])
        data["report_id"] = report_id
        data["created_at"] = row["created_at"]
        return data
    return None


def delete_report(report_id: int) -> bool:
    """删除指定报告"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
