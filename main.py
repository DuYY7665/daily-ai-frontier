# -*- coding: utf-8 -*-
"""每日AI前沿 - 云原生爬虫主程序（Supabase 版）

从多个 AI 资讯源抓取最新资讯，清洗后写入 Supabase（PostgreSQL）。
通过 GitHub Actions 每日定时触发。
"""

import os
import re
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from supabase import create_client, Client

# ── Supabase 连接 ──────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "缺少环境变量 SUPABASE_URL 或 SUPABASE_KEY，请在 .env 或 GitHub Secrets 中配置"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── 分类 → 优先级映射 ─────────────────────────────────
PRIORITY_MAP = {
    "应用落地与工具": 0,
    "Agent智能体": 0,
    "模型技术": 1,
    "方法论与研究": 1,
    "行业生态与政策": 2,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def get_now_iso() -> str:
    """获取北京时间当前时刻的 ISO 8601 时间戳（精确到分钟）"""
    bj = timezone(timedelta(hours=8))
    return datetime.now(bj).strftime("%Y-%m-%dT%H:%M:00+08:00")


# ── 爬虫：抓取各资讯源 ────────────────────────────────

def crawl_deeplearning_ai() -> list[dict]:
    """抓取 DeepLearning.AI The Batch 最新文章"""
    items = []
    try:
        print("  [FETCH] DeepLearning.AI - The Batch ...")
        resp = requests.get("https://www.deeplearning.ai/the-batch/", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        articles = soup.select("a[href*='/the-batch/']")
        seen_urls = set()
        for a in articles[:10]:
            href = a.get("href", "")
            if not href or href == "/the-batch/" or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://www.deeplearning.ai" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "DeepLearning.AI",
                "category": "方法论与研究",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] DeepLearning.AI: {e}")
    return items


def crawl_nvidia_blog() -> list[dict]:
    """抓取 NVIDIA Developer Blog AI 相关文章"""
    items = []
    try:
        print("  [FETCH] NVIDIA Developer Blog ...")
        resp = requests.get(
            "https://developer.nvidia.com/blog/category/ai/",
            headers=HEADERS, timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("article h2 a, .post-title a, h3.entry-title a")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://developer.nvidia.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            category = "模型技术"
            if "agent" in title.lower():
                category = "Agent智能体"
            elif "tool" in title.lower() or "deploy" in title.lower():
                category = "应用落地与工具"

            items.append({
                "date": get_now_iso(),
                "platform": "NVIDIA Developer Blog",
                "category": category,
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] NVIDIA: {e}")
    return items


def crawl_huggingface() -> list[dict]:
    """抓取 Hugging Face Blog"""
    items = []
    try:
        print("  [FETCH] Hugging Face Blog ...")
        resp = requests.get("https://huggingface.co/blog", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("article a[href*='/blog/'], a.block[href*='/blog/']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href == "/blog" or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://huggingface.co" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "Hugging Face",
                "category": "模型技术",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] Hugging Face: {e}")
    return items


def crawl_openai() -> list[dict]:
    """抓取 OpenAI Blog"""
    items = []
    try:
        print("  [FETCH] OpenAI Blog ...")
        resp = requests.get("https://openai.com/blog", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='/index/']") or soup.select("a[href*='/blog/']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href == "/blog" or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://openai.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "OpenAI",
                "category": "模型技术",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] OpenAI: {e}")
    return items


def crawl_anthropic() -> list[dict]:
    """抓取 Anthropic News"""
    items = []
    try:
        print("  [FETCH] Anthropic News ...")
        resp = requests.get("https://www.anthropic.com/news", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='/news/']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href == "/news" or href == "/news/" or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://www.anthropic.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "Anthropic",
                "category": "Agent智能体",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] Anthropic: {e}")
    return items


def crawl_openai_academy() -> list[dict]:
    """抓取 OpenAI Academy 活动和课程"""
    items = []
    try:
        print("  [FETCH] OpenAI Academy ...")
        resp = requests.get("https://academy.openai.com", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='/events/'], a[href*='/courses/'], a[href*='/catalog/']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://academy.openai.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "OpenAI Academy",
                "category": "Agent智能体",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] OpenAI Academy: {e}")
    return items


def crawl_google_ai() -> list[dict]:
    """抓取 Google Grow with Google AI 内容"""
    items = []
    try:
        print("  [FETCH] Google Grow with Google AI ...")
        resp = requests.get("https://grow.google/ai/", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='grow.google'], a[href*='/courses/'], a[href*='/ai']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href in seen_urls or len(href) < 10:
                continue
            if not href.startswith("http"):
                href = "https://grow.google" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "Google Grow with Google",
                "category": "模型技术",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] Google AI: {e}")
    return items


def crawl_ibm_skillsbuild() -> list[dict]:
    """抓取 IBM SkillsBuild 活动和课程"""
    items = []
    try:
        print("  [FETCH] IBM SkillsBuild ...")
        resp = requests.get("https://skillsbuild.org/events", headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='/events/'], a[href*='/courses/'], a[href*='skillsbuild']")
        seen_urls = set()
        for a in posts[:8]:
            href = a.get("href", "")
            if not href or href in seen_urls or len(href) < 10:
                continue
            if not href.startswith("http"):
                href = "https://skillsbuild.org" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "IBM SkillsBuild",
                "category": "行业生态与政策",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] IBM SkillsBuild: {e}")
    return items


def crawl_nvidia_cuda() -> list[dict]:
    """抓取 NVIDIA CUDA/开发者工具更新"""
    items = []
    try:
        print("  [FETCH] NVIDIA Developer (CUDA & Tools) ...")
        resp = requests.get(
            "https://developer.nvidia.com/blog/category/developer-tools/",
            headers=HEADERS, timeout=15
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("article h2 a, .post-title a, h3.entry-title a")
        seen_urls = set()
        for a in posts[:5]:
            href = a.get("href", "")
            if not href or href in seen_urls:
                continue
            if not href.startswith("http"):
                href = "https://developer.nvidia.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "NVIDIA Developer",
                "category": "应用落地与工具",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [ERR] NVIDIA CUDA: {e}")
    return items


def crawl_meta_ai() -> list[dict]:
    """抓取 Meta AI Resources（可能报错，容错处理）"""
    items = []
    try:
        print("  [FETCH] Meta AI ...")
        resp = requests.get("https://ai.meta.com/resources/", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        posts = soup.select("a[href*='/resources/'], a[href*='/blog/'], a[href*='/research/']")
        seen_urls = set()
        for a in posts[:5]:
            href = a.get("href", "")
            if not href or href in seen_urls or len(href) < 10:
                continue
            if not href.startswith("http"):
                href = "https://ai.meta.com" + href
            seen_urls.add(href)

            title = a.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            items.append({
                "date": get_now_iso(),
                "platform": "Meta AI",
                "category": "模型技术",
                "summary": title[:200],
                "cn_text": title,
                "url": href,
                "en_text": title,
            })

        print(f"    [OK] 获取 {len(items)} 条")
    except Exception as e:
        print(f"    [SKIP] Meta AI（页面不可用，已跳过）: {e}")
    return items


def fetch_all_news() -> list[dict]:
    """汇总所有 10 个资讯源（含 3 个容错源）"""
    all_items = []
    # 7 个稳定源
    all_items.extend(crawl_deeplearning_ai())
    all_items.extend(crawl_nvidia_blog())
    all_items.extend(crawl_nvidia_cuda())
    all_items.extend(crawl_huggingface())
    all_items.extend(crawl_openai())
    all_items.extend(crawl_openai_academy())
    all_items.extend(crawl_anthropic())
    all_items.extend(crawl_google_ai())
    all_items.extend(crawl_ibm_skillsbuild())
    # 容错源（可能失败，不影响整体）
    all_items.extend(crawl_meta_ai())
    return all_items


NOISE_KEYWORDS = [
    "learn more", "sign up", "register", "subscribe", "cookie",
    "privacy", "terms of", "log in", "menu", "navigation",
    "skip to content", "search", "footer", "header",
]


def is_noise(text: str) -> bool:
    """判断是否为噪音内容（导航、按钮文字等）"""
    t = text.lower().strip()
    if len(t) < 20:
        return True
    for kw in NOISE_KEYWORDS:
        if t == kw or t.startswith(kw):
            return True
    return False


def has_chinese(text: str) -> bool:
    """判断文本是否包含中文"""
    return any('\u4e00' <= c <= '\u9fff' for c in text)


def clean_item(item: dict) -> dict | None:
    """清洗单条资讯数据，不合格返回 None"""
    summary = (item.get("summary") or "").strip()
    cn_text = (item.get("cn_text") or "").strip()
    url = (item.get("url") or "").strip()
    en_text = (item.get("en_text") or "").strip()

    if not url:
        return None

    # 过滤噪音内容
    if is_noise(summary):
        return None

    # summary 必须有实质长度（至少30字符）
    if len(summary) < 30:
        return None

    # cn_text 必须有实质内容且与 summary 不同（证明有翻译/编辑）
    if len(cn_text) < 50:
        return None
    if cn_text == summary and not has_chinese(cn_text):
        return None

    return {
        "date": (item.get("date") or get_now_iso()).strip(),
        "platform": (item.get("platform") or "Unknown").strip(),
        "category": (item.get("category") or "行业生态与政策").strip(),
        "priority": PRIORITY_MAP.get(item.get("category", ""), 2),
        "summary": summary,
        "cn_text": cn_text,
        "url": url,
        "en_text": en_text,
        "likes": 0,
    }


def insert_to_supabase(items: list[dict]) -> tuple[int, int]:
    """将清洗后的数据插入 Supabase ai_news 表（URL 已存在则跳过，绝不覆盖）

    Returns:
        (inserted, skipped): 新增条数和跳过条数
    """
    if not items:
        print("  [WARN] 没有数据需要写入")
        return 0, 0

    existing = supabase.table("ai_news").select("url").execute()
    existing_urls = {r["url"] for r in (existing.data or [])}

    inserted = 0
    skipped = 0

    for item in items:
        if item["url"] in existing_urls:
            skipped += 1
            continue

        try:
            result = (
                supabase.table("ai_news")
                .insert(item)
                .execute()
            )
            if result.data:
                inserted += 1
                existing_urls.add(item["url"])
        except Exception as e:
            print(f"  [ERR] 写入失败 ({item.get('url', 'N/A')[:50]}): {e}")

    return inserted, skipped


def main():
    """主入口"""
    print("=" * 60)
    print("  每日AI前沿 - 云原生爬虫")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Supabase: {SUPABASE_URL}")
    print("=" * 60)
    print()

    # 1. 抓取资讯
    print("[1/3] 正在抓取资讯...")
    raw_items = fetch_all_news()
    print(f"  共获取 {len(raw_items)} 条原始数据\n")

    # 2. 数据清洗（严格质量过滤）
    print("[2/3] 正在清洗数据...")
    cleaned = [r for r in (clean_item(item) for item in raw_items) if r is not None]
    print(f"  清洗后有效数据 {len(cleaned)} 条（过滤了 {len(raw_items) - len(cleaned)} 条低质量内容）\n")

    # 3. 写入 Supabase（仅新增，不覆盖已有数据）
    print("[3/3] 正在写入 Supabase...")
    inserted, skipped = insert_to_supabase(cleaned)
    print(f"  新增 {inserted} 条，跳过 {skipped} 条已存在\n")

    print("=" * 60)
    print(f"  任务完成！新增 {inserted} 条，跳过 {skipped} 条")
    print("=" * 60)


if __name__ == "__main__":
    main()
