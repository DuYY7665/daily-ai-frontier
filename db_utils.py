# -*- coding: utf-8 -*-
"""SQLite 数据库读写工具 - 供抓取脚本和自动化任务使用（自动去重）"""

import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_news.db")

PRIORITY_MAP = {
    "应用落地与工具": 0,
    "Agent智能体": 0,
    "模型技术": 1,
    "方法论与研究": 1,
    "行业生态与政策": 2,
}


def _ensure_table():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            platform TEXT NOT NULL,
            category TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 2,
            summary TEXT,
            cn_text TEXT,
            url TEXT UNIQUE NOT NULL,
            en_text TEXT,
            likes INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pd ON news(priority ASC, date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON news(date DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cat ON news(category)")
    conn.commit()
    conn.close()


def save_news_items(items):
    """保存新闻列表到数据库（URL去重：已存在则自动跳过）

    Args:
        items: list of dict，每条需包含:
            date, platform, category, summary, cn_text, url, en_text

    Returns:
        int: 实际新增条数（去重跳过的不计数）
    """
    _ensure_table()
    conn = sqlite3.connect(DB_PATH)
    inserted = 0

    for item in items:
        priority = PRIORITY_MAP.get(item.get("category", ""), 2)
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO news "
                "(date, platform, category, priority, summary, cn_text, url, en_text) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["date"],
                    item["platform"],
                    item["category"],
                    priority,
                    item.get("summary", ""),
                    item.get("cn_text", ""),
                    item["url"],
                    item.get("en_text", ""),
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            print(f"  [WARN] {e}")

    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    print(f"DB: {DB_PATH}")
    if os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        print(f"Records: {count}")
        conn.close()
