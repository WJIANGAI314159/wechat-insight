#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信公众号深度研究工具 - 数据库模块
使用 SQLite 存储历史报告，同时作为搜索缓存
支持按方向（direction）区分缓存
"""

import os
import sqlite3
import json
import time
from datetime import datetime

# 数据库文件路径
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "insight.db"))

# 缓存有效期（秒）：相同关键词+时间范围+方向在此时长内直接返回缓存
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
            direction TEXT DEFAULT 'general',
            total_results INTEGER DEFAULT 0,
            sentiment_hint TEXT,
            summary TEXT,
            created_at TEXT NOT NULL,
            created_ts REAL NOT NULL,
            data_json TEXT NOT NULL
        )
    """)
    # 如果旧表没有 direction 列，自动添加
    try:
        conn.execute("SELECT direction FROM reports LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE reports ADD COLUMN direction TEXT DEFAULT 'general'")
        conn.commit()

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_query
        ON reports(query, days, direction, created_ts)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_reports_created
        ON reports(created_ts DESC)
    """)
    conn.commit()
    conn.close()


def save_report(query: str, days: int, total_results: int,
                articles: list, analysis: dict,
                direction: str = "general") -> int:
    """保存一份搜索报告，返回报告 ID"""
    now = datetime.now()
    data = {
        "query": query,
        "days": days,
        "direction": direction,
        "total_results": total_results,
        "articles": articles,
        "analysis": analysis,
        "error": None,
    }
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO reports
           (query, days, direction, total_results, sentiment_hint, summary, created_at, created_ts, data_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            query,
            days,
            direction,
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


def get_cached_report(query: str, days: int, direction: str = "general") -> dict | None:
    """
    查找缓存：相同关键词 + 相同时间范围 + 相同方向 + 在 CACHE_TTL 内
    """
    cutoff = time.time() - CACHE_TTL
    conn = get_conn()
    row = conn.execute(
        """SELECT data_json, id FROM reports
           WHERE query = ? AND days = ? AND direction = ? AND created_ts > ?
           ORDER BY created_ts DESC LIMIT 1""",
        (query, days, direction, cutoff),
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
        """SELECT id, query, days, direction, total_results, sentiment_hint,
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
