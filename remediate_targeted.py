# -*- coding: utf-8 -*-
"""定点治理：扫描译文异常记录，按优先级用阿里翻译重译（额度不足则 Google）。

用法（在项目根目录、与 ai_news.db 同级）:
  ALIYUN_AK_ID=... ALIYUN_AK_SECRET=... python3 remediate_targeted.py
  python3 remediate_targeted.py --dry-run   # 只扫描不报写
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_news.db")
USAGE_FILE = os.path.join(BASE_DIR, ".ali_usage.txt")
ALI_MONTHLY_LIMIT = 900_000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


def _load_env_from_systemd() -> None:
    path = "/etc/systemd/system/ai-news.service.d/env.conf"
    if os.environ.get("ALIYUN_AK_ID"):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r'^Environment="([^=]+)=(.*)"\s*$', line.strip())
                if not m:
                    continue
                key, val = m.group(1), m.group(2)
                if key in ("ALIYUN_AK_ID", "ALIYUN_AK_SECRET"):
                    os.environ[key] = val
    except OSError:
        pass


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def _letter_counts(text: str) -> tuple[int, int]:
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return latin, chinese


def _load_month_usage() -> int:
    try:
        with open(USAGE_FILE, encoding="utf-8") as f:
            month, count = f.read().strip().split(",", 1)
            if month == datetime.now().strftime("%Y-%m"):
                return int(count)
    except Exception:
        pass
    return 0


def _save_month_usage(total: int) -> None:
    month = datetime.now().strftime("%Y-%m")
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        f.write(f"{month},{total}")


_GLUED_RE = re.compile(
    r"(?i)(company|research|safety|announcements)"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
)


def needs_remediation(row: sqlite3.Row) -> tuple[bool, list[str]]:
    cn = row["cn_text"] or ""
    summary = row["summary"] or ""
    reasons: list[str] = []

    if not _has_chinese(cn):
        reasons.append("cn_no_zh")
    if summary and not _has_chinese(summary):
        reasons.append("summary_no_zh")

    if _GLUED_RE.search(cn) or _GLUED_RE.search(summary):
        reasons.append("glued_metadata")

    # 拉丁字母占比过高（夹杂大块英文）——专有名词多时易误判，仅在中文字偏少时触发
    lat, zh = _letter_counts(cn)
    if 5 <= zh < 28 and lat > 0 and lat / (lat + zh) > 0.42:
        reasons.append("high_latin_ratio")

    # 摘要与正文前几字完全相同且疑似英文标题重复一遍
    if len(cn) > 30 and len(summary) > 30:
        head = cn[: min(40, len(cn))]
        if head and cn.count(head) >= 2:
            reasons.append("duplicate_prefix")

    # 过长连续拉丁片段（未拆开的英文句）
    if re.search(r"[A-Za-z][A-Za-z\s,\-\.:;'\"/]{100,}[A-Za-z]", cn) and zh < lat:
        reasons.append("long_latin_run")

    return bool(reasons), reasons


def pick_source_text(row: sqlite3.Row) -> str | None:
    en = (row["en_text"] or "").strip()
    cn = (row["cn_text"] or "").strip()
    if len(en) >= 35:
        return en
    lat, _ = _letter_counts(cn)
    if len(cn) >= 40 and lat > len(cn) * 0.45:
        return cn[:2000]
    if len(en) >= 15:
        return en
    return cn[:2000] if cn else None


def make_summary(text: str, max_len: int = 120) -> str:
    sentences = re.split(r"[。！？\n]", text)
    summary = ""
    for s in sentences:
        s = s.strip()
        if len(s) < 5:
            continue
        if len(summary) + len(s) + 1 > max_len:
            break
        summary += s + "。"
    return summary if summary else text[:max_len]


def _ali_translate(text: str, ak: str, secret: str) -> tuple[str | None, int]:
    if not ak or not secret or len(text) < 5:
        return None, 0
    try:
        from alibabacloud_alimt20181012.client import Client
        from alibabacloud_alimt20181012.models import TranslateGeneralRequest
        from alibabacloud_tea_openapi.models import Config
    except ImportError:
        return None, 0

    config = Config(
        access_key_id=ak,
        access_key_secret=secret,
        endpoint="mt.aliyuncs.com",
    )
    client = Client(config)
    req = TranslateGeneralRequest(
        format_type="text",
        source_language="en",
        target_language="zh",
        source_text=text[:4800],
        scene="general",
    )
    try:
        resp = client.translate_general(req)
        if resp.body and str(resp.body.code) == "200" and resp.body.data:
            return resp.body.data.translated, len(text[:4800])
    except Exception as e:
        print(f"      [WARN] 阿里翻译异常: {e}")
    return None, 0


def _google_translate(text: str) -> str | None:
    if len(text) < 5:
        return None
    apis = [
        (
            "https://translate.googleapis.com/translate_a/single",
            {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:4500]},
        ),
        (
            "https://translate.google.com/translate_a/single",
            {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text[:4500]},
        ),
    ]
    for url, params in apis:
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=HEADERS, timeout=15)
                r.raise_for_status()
                data = r.json()
                if data and data[0]:
                    out = "".join(p[0] for p in data[0] if p[0])
                    if out and _has_chinese(out):
                        return out
            except Exception:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只列出待治理条目")
    args = parser.parse_args()

    _load_env_from_systemd()
    ak = os.environ.get("ALIYUN_AK_ID", "")
    secret = os.environ.get("ALIYUN_AK_SECRET", "")

    if not os.path.isfile(DB_PATH):
        print(f"[ERR] 找不到数据库: {DB_PATH}")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, platform, url, summary, cn_text, en_text FROM news ORDER BY id"
    ).fetchall()

    candidates: list[tuple[sqlite3.Row, list[str]]] = []
    for r in rows:
        bad, reasons = needs_remediation(r)
        if bad:
            candidates.append((r, reasons))

    print("=== 定点治理扫描 ===")
    print(f"总记录: {len(rows)}")
    print(f"待治理: {len(candidates)}")
    reason_counts: dict[str, int] = {}
    for _, rs in candidates:
        for x in rs:
            reason_counts[x] = reason_counts.get(x, 0) + 1
    print("原因分布:", dict(sorted(reason_counts.items(), key=lambda x: -x[1])))

    if args.dry_run:
        for r, rs in candidates[:30]:
            print(f"  id={r['id']} {r['platform']} | {','.join(rs)}")
        if len(candidates) > 30:
            print(f"  ... 另有 {len(candidates)-30} 条")
        conn.close()
        return 0

    usage_base = _load_month_usage()
    ali_used_run = 0
    fixed = 0
    failed = 0
    skipped_quota = 0

    for r, reasons in candidates:
        sid = r["id"]
        src = pick_source_text(r)
        if not src:
            print(f"  [{sid}] 无可用英文素材，跳过")
            failed += 1
            continue

        print(f"  [{sid}] {r['platform']} | {reasons} | 源长度={len(src)}")

        result = None
        chars_billed = 0
        if ak and secret and usage_base + ali_used_run < ALI_MONTHLY_LIMIT:
            result, chars_billed = _ali_translate(src, ak, secret)
            if result and _has_chinese(result):
                ali_used_run += chars_billed
                print(f"       -> 阿里翻译 OK ({chars_billed} 字符)")
            else:
                result = None

        if not result:
            print("       -> 尝试 Google …")
            result = _google_translate(src)
            if result:
                print("       -> Google OK")

        if result and _has_chinese(result):
            cn_detail = result.strip()
            cn_summary = make_summary(cn_detail)
            if cn_summary == cn_detail:
                cn_detail = cn_summary + "（详见原文）"
            conn.execute(
                "UPDATE news SET summary = ?, cn_text = ? WHERE id = ?",
                (cn_summary, cn_detail, sid),
            )
            conn.commit()
            fixed += 1
        else:
            failed += 1
            print("       -> [FAIL]")

        if ak and usage_base + ali_used_run >= ALI_MONTHLY_LIMIT:
            skipped_quota += 1

        time.sleep(0.35)

    if ali_used_run > 0:
        _save_month_usage(usage_base + ali_used_run)

    conn.close()

    print()
    print("=== 治理结果 ===")
    print(f"  修复成功: {fixed}")
    print(f"  失败: {failed}")
    print(f"  阿里翻译本次计费字符(约): {ali_used_run}")
    print(f"  本月累计(写入后): {usage_base + ali_used_run}")
    if skipped_quota:
        print(f"  注意: 治理过程中曾触及额度上限，后续条目可能只用了 Google")
    return 0


if __name__ == "__main__":
    sys.exit(main())
