# -*- coding: utf-8 -*-
"""每日AI前沿 - 微型 HTTP 服务（零外部依赖，仅 Python 标准库）

用法:
  python serve.py                    # 默认端口 8899
  python serve.py --port 8080        # 指定端口
  python serve.py --dir /app/news    # 指定工作目录
"""

import json
import sqlite3
import os
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ── 命令行参数 ──────────────────────────────────────────
def parse_args():
    args = {"port": 8899, "dir": None}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--port" and i + 1 < len(sys.argv):
            args["port"] = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--dir" and i + 1 < len(sys.argv):
            args["dir"] = sys.argv[i + 1]
            i += 2
        else:
            i += 1
    return args

_args = parse_args()
BASE_DIR = os.path.abspath(_args["dir"]) if _args["dir"] else os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_news.db")
PORT = _args["port"]

PRIORITY_MAP = {
    "应用落地与工具": 0,
    "Agent智能体": 0,
    "模型技术": 1,
    "方法论与研究": 1,
    "行业生态与政策": 2,
}

# ── 数据库自动初始化 ────────────────────────────────────
def _init_db():
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

_init_db()


class NewsHandler(SimpleHTTPRequestHandler):
    """API + 静态文件处理器"""

    # ── GET ──────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            self._serve_html()
        elif path == "/api/news":
            self._serve_news(params)
        else:
            self.send_error(404)

    # ── POST ─────────────────────────────────────────────
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.strip("/").split("/") if p]

        # POST /api/news/ingest — 批量接收资讯（供定时任务推送）
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "news" and parts[2] == "ingest":
            self._ingest_news()

        # POST /api/news/<id>/like — 点赞
        elif (
            len(parts) == 3
            and parts[0] == "api"
            and parts[1] == "news"
            and parts[2] == "like"
        ):
            self._like_news(params=urllib.parse.parse_qs(parsed.query))
        elif len(parts) == 4 and parts[0] == "api" and parts[3] == "like":
            self._like_news(news_id=parts[2])
        else:
            self.send_error(404)

    # ── OPTIONS (CORS preflight) ─────────────────────────
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    # ── Serve index.html ─────────────────────────────────
    def _serve_html(self):
        html_path = os.path.join(BASE_DIR, "index.html")
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                content = f.read()
            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404, "index.html not found")

    # ── GET /api/news ────────────────────────────────────
    def _serve_news(self, params):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        # Build WHERE
        conds, vals = [], []

        if "priority" in params:
            conds.append("priority = ?")
            vals.append(int(params["priority"][0]))

        for key in ("category", "platform"):
            if key in params and params[key][0]:
                conds.append(f"{key} = ?")
                vals.append(params[key][0])

        if "date" in params and params["date"][0]:
            conds.append("date LIKE ?")
            vals.append(params["date"][0] + "%")

        if "search" in params and params["search"][0]:
            conds.append("(summary LIKE ? OR cn_text LIKE ? OR platform LIKE ?)")
            s = f"%{params['search'][0]}%"
            vals.extend([s, s, s])

        where = " AND ".join(conds) if conds else "1=1"

        # Total count
        total = conn.execute(
            f"SELECT COUNT(*) FROM news WHERE {where}", vals
        ).fetchone()[0]

        # Pagination
        try:
            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            page, limit = 1, 100
        offset = (page - 1) * limit

        # Fetch rows
        rows = conn.execute(
            f"SELECT * FROM news WHERE {where} "
            f"ORDER BY priority ASC, date DESC, id DESC "
            f"LIMIT ? OFFSET ?",
            vals + [limit, offset],
        ).fetchall()

        platforms = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT platform FROM news ORDER BY platform",
            ).fetchall()
        ]
        categories = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT category FROM news ORDER BY category",
            ).fetchall()
        ]
        dates = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT SUBSTR(date, 1, 10) AS d FROM news ORDER BY d DESC",
            ).fetchall()
            if r[0]
        ]

        # Priority counts (global, not filtered)
        p0 = conn.execute("SELECT COUNT(*) FROM news WHERE priority=0").fetchone()[0]
        p1 = conn.execute("SELECT COUNT(*) FROM news WHERE priority=1").fetchone()[0]
        p2 = conn.execute("SELECT COUNT(*) FROM news WHERE priority=2").fetchone()[0]
        conn.close()

        result = {
            "data": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "filters": {
                "platforms": platforms,
                "categories": categories,
                "dates": dates,
            },
            "counts": {"p0": p0, "p1": p1, "p2": p2, "total": p0 + p1 + p2},
        }

        self._json_response(result)

    # ── POST /api/news/ingest — 批量接收资讯 ────────────
    def _ingest_news(self):
        """接收 JSON 数组，批量写入（URL去重）

        请求格式: POST /api/news/ingest
        Body: [{"date":"...", "platform":"...", "category":"...", "summary":"...", "cn_text":"...", "url":"...", "en_text":"..."}]

        可选 Header: X-Secret-Key (如果设置了 SECRET_KEY 环境变量)
        """
        # 鉴权检查（可选）
        secret = os.environ.get("SECRET_KEY", "")
        if secret:
            provided = self.headers.get("X-Secret-Key", "")
            if provided != secret:
                self._json_response({"success": False, "error": "Unauthorized"})
                return

        # 读取请求体
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            items = json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._json_response({"success": False, "error": f"Invalid JSON: {e}"})
            return

        if not isinstance(items, list):
            self._json_response({"success": False, "error": "Expected JSON array"})
            return

        # 写入数据库
        conn = sqlite3.connect(DB_PATH)
        inserted = 0
        skipped = 0

        for item in items:
            url = item.get("url", "")
            if not url:
                skipped += 1
                continue

            priority = PRIORITY_MAP.get(item.get("category", ""), 2)
            try:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO news "
                    "(date, platform, category, priority, summary, cn_text, url, en_text) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.get("date", ""),
                        item.get("platform", ""),
                        item.get("category", ""),
                        priority,
                        item.get("summary", ""),
                        item.get("cn_text", ""),
                        url,
                        item.get("en_text", ""),
                    ),
                )
                if cursor.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except Exception as e:
                print(f"  [WARN] {e}")
                skipped += 1

        conn.commit()

        total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        conn.close()

        self._json_response({
            "success": True,
            "inserted": inserted,
            "skipped": skipped,
            "total_records": total,
        })

    # ── POST like ────────────────────────────────────────
    def _like_news(self, params=None, news_id=None):
        if news_id:
            nid = news_id
        elif params and "id" in params:
            nid = params["id"][0]
        else:
            self._json_response({"success": False, "error": "Missing id"})
            return

        try:
            nid = int(nid)
        except (ValueError, TypeError):
            self._json_response({"success": False, "error": "Invalid id"})
            return

        conn = sqlite3.connect(DB_PATH)
        try:
            cursor = conn.execute(
                "UPDATE news SET likes = likes + 1 WHERE id = ?", (nid,)
            )
            conn.commit()
            if cursor.rowcount > 0:
                likes = conn.execute(
                    "SELECT likes FROM news WHERE id = ?", (nid,)
                ).fetchone()[0]
                self._json_response({"success": True, "likes": likes})
            else:
                self._json_response({"success": False, "error": "Not found"})
        except Exception as e:
            self._json_response({"success": False, "error": str(e)})
        finally:
            conn.close()

    # ── Helpers ──────────────────────────────────────────
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Secret-Key")

    def _json_response(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


# ── Main ────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print(f"  每日AI前沿 服务已启动")
    print(f"  地址: http://0.0.0.0:{PORT}")
    print(f"  目录: {BASE_DIR}")
    print(f"  数据库: {DB_PATH}")
    print(f"  按 Ctrl+C 停止服务")
    print()

    server = HTTPServer(("0.0.0.0", PORT), NewsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()
