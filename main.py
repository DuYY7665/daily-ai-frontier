# -*- coding: utf-8 -*-
"""每日AI前沿 - 爬虫主程序（SQLite 版）

从多个 AI 资讯源抓取最新资讯，抓取正文并翻译为中文，
清洗后写入本地 SQLite 数据库。通过 cron 定时触发。
全程免费，无需付费 API。
"""

import os
import re
import sys
import time
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

# ── 数据库配置 ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_news.db")


def _ensure_db():
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


_ensure_db()

# ── 常量 ──────────────────────────────────────────────
PRIORITY_MAP = {
    "应用落地与工具": 0,
    "Agent智能体": 0,
    "模型技术": 1,
    "方法论与研究": 1,
    "行业生态与政策": 2,
}

CATEGORY_KEYWORDS = {
    "Agent智能体": [
        "agent", "agentic", "copilot", "autonomous", "multi-agent",
        "tool use", "function call", "orchestrat", "workflow automat",
    ],
    "应用落地与工具": [
        "deploy", "production", "sdk", "api", "plugin", "integration",
        "tool", "platform", "release", "launch", "available", "ship",
        "developer", "build", "framework", "library", "open source",
        "cuda", "tensorrt", "triton", "vllm", "nim", "container",
    ],
    "模型技术": [
        "model", "gpt", "claude", "llama", "gemini", "mistral",
        "transformer", "attention", "training", "fine-tun", "pretrain",
        "benchmark", "parameter", "token", "inference", "quantiz",
        "vision", "multimodal", "speech", "audio", "video generat",
    ],
    "方法论与研究": [
        "research", "paper", "study", "finding", "method", "approach",
        "algorithm", "dataset", "evaluat", "survey", "analysis",
        "scaling law", "rlhf", "reinforcement", "alignment",
    ],
    "行业生态与政策": [
        "policy", "regulat", "govern", "partner", "acqui", "invest",
        "funding", "market", "industry", "enterprise", "business",
        "safety", "ethics", "bias", "copyright", "climate", "energy",
        "hiring", "layoff", "workforce", "ads", "revenue",
    ],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

NOISE_KEYWORDS = [
    "learn more", "sign up", "register", "subscribe", "cookie",
    "privacy", "terms of", "log in", "menu", "navigation",
    "skip to content", "search", "footer", "header", "contact us",
]


def get_now_iso() -> str:
    bj = timezone(timedelta(hours=8))
    return datetime.now(bj).strftime("%Y-%m-%dT%H:%M:00+08:00")


# ── 通用工具 ──────────────────────────────────────────

def fetch_page(url: str, timeout: int = 15) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        print(f"    [ERR] 无法访问 {url[:60]}: {e}")
        return None


def extract_article_text(url: str, max_chars: int = 3000) -> str:
    """进入文章详情页，提取正文文本"""
    soup = fetch_page(url)
    if not soup:
        return ""

    for tag in soup.select(
        "nav, header, footer, script, style, aside, "
        ".sidebar, .nav, .menu, .cookie, .ad, .share, .related"
    ):
        tag.decompose()

    content_selectors = [
        "article", "main", "[role='main']",
        ".post-content", ".entry-content", ".article-content",
        ".blog-content", ".prose", ".content-body",
    ]
    content_el = None
    for sel in content_selectors:
        content_el = soup.select_one(sel)
        if content_el:
            break
    if not content_el:
        content_el = soup.body or soup

    paragraphs = content_el.find_all(["p", "h1", "h2", "h3", "li"])
    text_parts = []
    total = 0
    for p in paragraphs:
        t = p.get_text(strip=True)
        if len(t) < 10:
            continue
        text_parts.append(t)
        total += len(t)
        if total >= max_chars:
            break

    return "\n".join(text_parts)


def is_noise(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 15:
        return True
    for kw in NOISE_KEYWORDS:
        if t == kw or t.startswith(kw):
            return True
    return False


# ── 翻译（阿里翻译优先，Google 备选）─────────────────────

ALIYUN_AK_ID = os.environ.get("ALIYUN_AK_ID", "")
ALIYUN_AK_SECRET = os.environ.get("ALIYUN_AK_SECRET", "")

_ali_client = None


def _get_ali_client():
    """懒加载阿里翻译客户端"""
    global _ali_client
    if _ali_client is None and ALIYUN_AK_ID and ALIYUN_AK_SECRET:
        try:
            from alibabacloud_alimt20181012.client import Client
            from alibabacloud_tea_openapi.models import Config
            config = Config(
                access_key_id=ALIYUN_AK_ID,
                access_key_secret=ALIYUN_AK_SECRET,
                endpoint="mt.aliyuncs.com",
            )
            _ali_client = Client(config)
        except ImportError:
            print("  [WARN] 阿里翻译 SDK 未安装，回退到 Google")
        except Exception as e:
            print(f"  [WARN] 阿里翻译初始化失败: {e}")
    return _ali_client


def translate_to_chinese(text: str) -> str:
    """翻译英文为中文：优先阿里翻译，失败时回退到 Google"""
    if not text or len(text.strip()) < 5:
        return text

    chunks = _split_text(text, max_len=4500)
    translated_parts = []

    for chunk in chunks:
        result = None
        if ALIYUN_AK_ID:
            result = _ali_translate_chunk(chunk)
        if not result:
            result = _google_translate_chunk(chunk)
        translated_parts.append(result if result else chunk)
        if len(chunks) > 1:
            time.sleep(0.3)

    return "".join(translated_parts)


def _split_text(text: str, max_len: int = 4500) -> list[str]:
    """按句子边界拆分长文本"""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for sentence in re.split(r'(?<=[.!?。！？\n])\s*', text):
        if len(current) + len(sentence) > max_len and current:
            chunks.append(current)
            current = sentence
        else:
            current += (" " if current else "") + sentence
    if current:
        chunks.append(current)
    return chunks


def _ali_translate_chunk(text: str, retries: int = 2) -> str | None:
    """调用阿里云机器翻译 API"""
    client = _get_ali_client()
    if not client:
        return None

    from alibabacloud_alimt20181012.models import TranslateGeneralRequest

    req = TranslateGeneralRequest(
        format_type="text",
        source_language="en",
        target_language="zh",
        source_text=text,
        scene="general",
    )

    for attempt in range(retries):
        try:
            resp = client.translate_general(req)
            if resp.body and resp.body.code == 200:
                return resp.body.data.translated
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
            else:
                print(f"      [WARN] 阿里翻译失败: {e}")
    return None


def _google_translate_chunk(text: str, retries: int = 3) -> str | None:
    """调用 Google Translate 免费接口（备选）"""
    apis = [
        {
            "url": "https://translate.googleapis.com/translate_a/single",
            "params": {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text},
        },
        {
            "url": "https://translate.google.com/translate_a/single",
            "params": {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text},
        },
    ]
    for api in apis:
        for attempt in range(retries):
            try:
                resp = requests.get(
                    api["url"], params=api["params"], headers=HEADERS, timeout=10,
                )
                resp.raise_for_status()
                result = resp.json()
                if result and result[0]:
                    translated = "".join(
                        part[0] for part in result[0] if part[0]
                    )
                    if translated:
                        return translated
            except Exception:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        print(f"    [WARN] Google 翻译接口 {api['url'][:40]} 失败")
    print(f"    [ERR] 所有翻译接口均失败")
    return None


# ── 智能分类 ──────────────────────────────────────────

def classify_article(title: str, body: str) -> str:
    """基于关键词匹配判断文章分类"""
    combined = (title + " " + body[:1000]).lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined)
        scores[cat] = score

    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return "行业生态与政策"


def make_summary(text: str, max_len: int = 120) -> str:
    """从翻译后的中文文本中提取前几句作为摘要"""
    sentences = re.split(r'[。！？\n]', text)
    summary = ""
    for s in sentences:
        s = s.strip()
        if len(s) < 5:
            continue
        if len(summary) + len(s) + 1 > max_len:
            break
        summary += s + "。"
    return summary if summary else text[:max_len]


# ── 各资讯源爬虫（列表页 → 标题+URL） ────────────────

def crawl_list_page(
    name: str,
    url: str,
    link_selector: str,
    base_url: str,
    exclude_hrefs: set | None = None,
    max_items: int = 8,
) -> list[dict]:
    """通用列表页爬虫"""
    items = []
    exclude_hrefs = exclude_hrefs or set()

    print(f"  [FETCH] {name} ...")
    soup = fetch_page(url)
    if not soup:
        return items

    links = soup.select(link_selector)
    seen = set()
    for a in links:
        if len(items) >= max_items:
            break
        href = a.get("href", "")
        if not href or href in seen or href in exclude_hrefs:
            continue
        if not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")
        if href in seen:
            continue
        seen.add(href)

        title = a.get_text(strip=True)
        if not title or len(title) < 10 or is_noise(title):
            continue

        items.append({"title": title, "url": href, "platform": name})

    print(f"    [OK] 列表页获取 {len(items)} 条链接")
    return items


def fetch_all_links() -> list[dict]:
    """从11个资讯源获取文章链接列表"""
    all_links = []

    all_links.extend(crawl_list_page(
        "DeepLearning.AI", "https://www.deeplearning.ai/the-batch/",
        "a[href*='/the-batch/']", "https://www.deeplearning.ai",
        exclude_hrefs={"/the-batch/", "/the-batch"},
    ))
    all_links.extend(crawl_list_page(
        "NVIDIA Developer Blog",
        "https://developer.nvidia.com/blog/",
        "article h2 a, .post-title a, h3.entry-title a, a.post-card__link",
        "https://developer.nvidia.com",
    ))
    all_links.extend(crawl_list_page(
        "Hugging Face Blog", "https://huggingface.co/blog",
        "article a[href*='/blog/'], a.block[href*='/blog/']",
        "https://huggingface.co",
        exclude_hrefs={"/blog", "/blog/"},
    ))
    # OpenAI 有反爬保护(403)，暂时跳过，保留入口以便后续恢复
    try:
        all_links.extend(crawl_list_page(
            "OpenAI Blog", "https://openai.com/news/",
            "a[href*='/index/']", "https://openai.com",
            exclude_hrefs={"/news", "/news/"},
        ))
    except Exception as e:
        print(f"  [SKIP] OpenAI Blog: {e}")
    all_links.extend(crawl_list_page(
        "Anthropic News", "https://www.anthropic.com/news",
        "a[href*='/news/']", "https://www.anthropic.com",
        exclude_hrefs={"/news", "/news/"},
    ))
    all_links.extend(crawl_list_page(
        "OpenAI Academy", "https://academy.openai.com",
        "a[href*='/events/'], a[href*='/courses/'], a[href*='/catalog/']",
        "https://academy.openai.com",
    ))
    all_links.extend(crawl_list_page(
        "Google Grow with Google", "https://grow.google/ai/",
        "a[href*='grow.google'], a[href*='/courses/'], a[href*='/ai']",
        "https://grow.google",
    ))
    all_links.extend(crawl_list_page(
        "IBM SkillsBuild", "https://skillsbuild.org/events",
        "a[href*='/events/'], a[href*='/courses/'], a[href*='skillsbuild']",
        "https://skillsbuild.org",
    ))
    all_links.extend(crawl_list_page(
        "SemiAnalysis", "https://newsletter.semianalysis.com/archive",
        "a[href*='/p/']",
        "https://newsletter.semianalysis.com",
        max_items=5,
    ))
    try:
        all_links.extend(crawl_list_page(
            "Meta AI", "https://ai.meta.com/blog/",
            "a[href*='/blog/'], a[href*='/research/']",
            "https://ai.meta.com",
            max_items=5,
        ))
    except Exception as e:
        print(f"  [SKIP] Meta AI: {e}")

    return all_links


# ── 核心流程：抓正文 + 翻译 ──────────────────────────

def process_article(link: dict) -> dict | None:
    """对单篇文章：抓正文 → 翻译 → 分类 → 组装"""
    title = link["title"]
    url = link["url"]
    platform = link["platform"]

    try:
        print(f"    [DETAIL] {platform}: {title[:50]}...")

        body = extract_article_text(url)
        if len(body) < 30:
            print(f"      [WARN] 正文太短({len(body)}字符)")
            body = title

        en_full = _make_en_summary(title, body, max_len=1500)
        en_short = _make_en_summary(title, body, max_len=300)
        category = classify_article(title, body)

        cn_detail = translate_to_chinese(en_full)
        if not cn_detail or len(cn_detail) < 30:
            print(f"      [SKIP] 翻译结果为空或太短")
            return None

        cn_summary = make_summary(cn_detail, max_len=120)

        if cn_summary == cn_detail:
            cn_detail = cn_summary + "（详见原文）"

        if len(cn_detail) < 50:
            print(f"      [SKIP] 中文内容太短({len(cn_detail)}字)")
            return None

        print(f"      [OK] 分类={category}, 摘要={len(cn_summary)}字, 详情={len(cn_detail)}字")

        return {
            "date": get_now_iso(),
            "platform": platform,
            "category": category,
            "priority": PRIORITY_MAP.get(category, 2),
            "summary": cn_summary,
            "cn_text": cn_detail,
            "url": url,
            "en_text": en_short[:300],
            "likes": 0,
        }
    except Exception as e:
        print(f"      [ERR] 处理异常: {e}")
        return None


def _make_en_summary(title: str, body: str, max_len: int = 1500) -> str:
    """从英文正文提取关键内容（标题 + 前N段正文）"""
    parts = [title + "."]
    remaining = max_len - len(title)

    for paragraph in body.split("\n"):
        paragraph = paragraph.strip()
        if len(paragraph) < 15:
            continue
        if remaining <= 0:
            break
        parts.append(paragraph)
        remaining -= len(paragraph)

    return " ".join(parts)


def get_existing_urls() -> set:
    """从 SQLite 获取所有已存在的 URL"""
    conn = sqlite3.connect(DB_PATH)
    urls = {r[0] for r in conn.execute("SELECT url FROM news").fetchall()}
    conn.close()
    return urls


def insert_to_db(items: list[dict]) -> tuple[int, int]:
    """插入 SQLite（URL 已存在则跳过）"""
    if not items:
        print("  [WARN] 没有数据需要写入")
        return 0, 0

    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0

    for item in items:
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO news "
                "(date, platform, category, priority, summary, cn_text, url, en_text, likes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item["date"], item["platform"], item["category"],
                    item["priority"], item["summary"], item["cn_text"],
                    item["url"], item["en_text"], item.get("likes", 0),
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  [ERR] 写入失败 ({item.get('url', 'N/A')[:50]}): {e}")
            skipped += 1

    conn.commit()
    conn.close()
    return inserted, skipped


# ── 主入口 ────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  每日AI前沿 - 爬虫（SQLite 版）")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  数据库: {DB_PATH}")
    print(f"  翻译引擎: {'阿里翻译 API' if ALIYUN_AK_ID else 'Google Translate (备选)'}")
    print("=" * 60)
    print()

    # 1. 抓取列表页链接
    print("[1/4] 正在抓取各站点文章链接...")
    all_links = fetch_all_links()
    print(f"  共获取 {len(all_links)} 条文章链接\n")

    # 2. 去重：跳过已在数据库中的 URL
    print("[2/4] 正在去重...")
    existing_urls = get_existing_urls()
    new_links = [l for l in all_links if l["url"] not in existing_urls]
    print(f"  {len(new_links)} 条新链接（跳过 {len(all_links) - len(new_links)} 条已存在）\n")

    if not new_links:
        print("没有新文章，本次任务结束。")
        return

    # 3. 逐篇：抓正文 + 翻译
    print(f"[3/4] 正在处理 {len(new_links)} 篇新文章（抓正文+翻译）...")
    processed = []
    for i, link in enumerate(new_links, 1):
        print(f"  [{i}/{len(new_links)}]")
        result = process_article(link)
        if result:
            processed.append(result)
        time.sleep(1)
    print(f"  成功处理 {len(processed)} 篇\n")

    # 4. 写入 SQLite
    print("[4/4] 正在写入数据库...")
    inserted, skipped = insert_to_db(processed)
    print(f"  新增 {inserted} 条，跳过 {skipped} 条\n")

    print("=" * 60)
    print(f"  任务完成！新增 {inserted} 条")
    print("=" * 60)

    if inserted == 0 and len(new_links) > 0 and len(processed) == 0:
        print("\n[!] 有新文章但处理全部失败（翻译可能被限流），触发重试")
        raise SystemExit(1)


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        print("[!] --refresh 模式：清空数据库后重新爬取")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM news")
        conn.commit()
        conn.close()
        print("  数据库已清空\n")
    main()
