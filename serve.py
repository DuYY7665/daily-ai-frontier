# -*- coding: utf-8 -*-
"""每日AI前沿 - 微型 HTTP 服务（零外部依赖，仅 Python 标准库）"""

import json
import sqlite3
import os
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_news.db")
PORT = 8899


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

        # POST /api/news/<id>/like
        if (
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

        for key in ("category", "platform", "date"):
            if key in params and params[key][0]:
                conds.append(f"{key} = ?")
                vals.append(params[key][0])

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

        # Filter options (based on current filters)
        platforms = [
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT platform FROM news WHERE {where} ORDER BY platform",
                vals,
            ).fetchall()
        ]
        categories = [
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT category FROM news WHERE {where} ORDER BY category",
                vals,
            ).fetchall()
        ]
        dates = [
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT date FROM news WHERE {where} ORDER BY date DESC",
                vals,
            ).fetchall()
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

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
    if not os.path.exists(DB_PATH):
        print("Database not found. Please run init_db.py first:")
        print("  python init_db.py")
        exit(1)

    server = HTTPServer(("0.0.0.0", PORT), NewsHandler)
    print()
    print(f"  ╔══════════════════════════════════════╗")
    print(f"  ║   每日AI前沿 服务已启动               ║")
    print(f"  ║   http://localhost:{PORT}              ║")
    print(f"  ║   按 Ctrl+C 停止服务                 ║")
    print(f"  ╚══════════════════════════════════════╝")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  服务已停止")
        server.server_close()
