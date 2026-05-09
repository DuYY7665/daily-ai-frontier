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


def get_today_str() -> str:
    """获取北京时间今天的日期字符串"""
    bj = timezone(timedelta(hours=8))
    return datetime.now(bj).strftime("%Y-%m-%d")


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
                "date": get_today_str(),
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
                "date": get_today_str(),
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
                "date": get_today_str(),
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
                "date": get_today_str(),
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
                "date": get_today_str(),
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


def fetch_all_news() -> list[dict]:
    """汇总所有资讯源"""
    all_items = []
    all_items.extend(crawl_deeplearning_ai())
    all_items.extend(crawl_nvidia_blog())
    all_items.extend(crawl_huggingface())
    all_items.extend(crawl_openai())
    all_items.extend(crawl_anthropic())
    return all_items


def clean_item(item: dict) -> dict:
    """清洗单条资讯数据"""
    return {
        "date": (item.get("date") or get_today_str()).strip(),
        "platform": (item.get("platform") or "Unknown").strip(),
        "category": (item.get("category") or "行业生态与政策").strip(),
        "priority": PRIORITY_MAP.get(item.get("category", ""), 2),
        "summary": (item.get("summary") or "").strip(),
        "cn_text": (item.get("cn_text") or "").strip(),
        "url": (item.get("url") or "").strip(),
        "en_text": (item.get("en_text") or "").strip(),
        "likes": 0,
    }


def upsert_to_supabase(items: list[dict]) -> int:
    """将清洗后的数据 upsert 到 Supabase ai_news 表"""
    if not items:
        print("  [WARN] 没有数据需要写入")
        return 0

    success_count = 0

    for item in items:
        if not item.get("url"):
            continue

        try:
            result = (
                supabase.table("ai_news")
                .upsert(item, on_conflict="url")
                .execute()
            )
            if result.data:
                success_count += 1
        except Exception as e:
            print(f"  [ERR] 写入失败 ({item.get('url', 'N/A')[:50]}): {e}")

    return success_count


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

    # 2. 数据清洗
    print("[2/3] 正在清洗数据...")
    cleaned = [clean_item(item) for item in raw_items if item.get("url")]
    print(f"  清洗后有效数据 {len(cleaned)} 条\n")

    # 3. 写入 Supabase
    print("[3/3] 正在写入 Supabase...")
    count = upsert_to_supabase(cleaned)
    print(f"  成功写入/更新 {count} 条\n")

    print("=" * 60)
    print(f"  任务完成！共处理 {count}/{len(cleaned)} 条资讯")
    print("=" * 60)


if __name__ == "__main__":
    main()
