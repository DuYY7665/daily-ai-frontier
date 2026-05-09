# -*- coding: utf-8 -*-
"""每日AI前沿 - 云原生爬虫主程序（Supabase 版）

从多个 AI 资讯源抓取最新资讯，清洗后写入 Supabase（PostgreSQL）。
通过 GitHub Actions 每日定时触发。
"""

import os
import re
import requests
from datetime import datetime, timezone, timedelta
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

# ── 资讯源配置 ────────────────────────────────────────
SOURCES = [
    {
        "name": "DeepLearning.AI - The Batch",
        "url": "https://www.deeplearning.ai/the-batch/",
        "platform": "DeepLearning.AI",
    },
    {
        "name": "NVIDIA Developer Blog",
        "url": "https://developer.nvidia.com/blog/",
        "platform": "NVIDIA Developer Blog",
    },
    {
        "name": "Hugging Face Blog",
        "url": "https://huggingface.co/blog",
        "platform": "Hugging Face",
    },
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog",
        "platform": "OpenAI",
    },
    {
        "name": "Anthropic News",
        "url": "https://www.anthropic.com/news",
        "platform": "Anthropic",
    },
]


def get_today_str() -> str:
    """获取北京时间今天的日期字符串"""
    bj = timezone(timedelta(hours=8))
    return datetime.now(bj).strftime("%Y-%m-%d")


def fetch_news_from_sources() -> list[dict]:
    """从配置的资讯源抓取新闻（示例实现）

    实际使用时可替换为真正的爬虫逻辑（requests + BeautifulSoup / Selenium / RSS 解析等）。
    此处提供框架和示例数据，展示完整数据流。
    """
    today = get_today_str()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        )
    }

    collected = []

    for source in SOURCES:
        try:
            print(f"  [FETCH] {source['name']} ...")
            resp = requests.get(source["url"], headers=headers, timeout=15)
            resp.raise_for_status()

            # TODO: 根据实际网站结构解析页面内容
            # 下面是数据模板，实际爬虫替换此处逻辑
            # from bs4 import BeautifulSoup
            # soup = BeautifulSoup(resp.text, 'html.parser')
            # ... 解析逻辑 ...

            print(f"    [OK] 成功访问 {source['name']} ({len(resp.text)} bytes)")

        except Exception as e:
            print(f"    [ERR] {source['name']}: {e}")

    # ── 示例数据（展示完整数据结构，实际部署后替换为真实解析结果）──
    sample_news = [
        {
            "date": today,
            "platform": "NVIDIA Developer Blog",
            "category": "Agent智能体",
            "summary": "NVIDIA Dynamo 发布多轮 Agent 推理与工具调用支持",
            "cn_text": "NVIDIA 发布 Dynamo 推理框架的重大更新，新增多轮 Agent 推理与工具调用的完整支持。",
            "url": "https://developer.nvidia.com/blog/streaming-tokens-and-tools-multi-turn-agentic-harness-support-in-nvidia-dynamo/",
            "en_text": "NVIDIA announced multi-turn agentic harness support in Dynamo.",
        },
        {
            "date": today,
            "platform": "DeepLearning.AI",
            "category": "Agent智能体",
            "summary": "DeepLearning.AI 联合 CopilotKit 发布免费课程「构建交互式 Agent 与生成式 UI」",
            "cn_text": "DeepLearning.AI 与 CopilotKit 联合发布全新免费课程「Build Interactive Agents with Generative UI」。",
            "url": "https://www.deeplearning.ai/short-courses/build-interactive-agents-with-generative-ui/",
            "en_text": "DeepLearning.AI and CopilotKit released a free course on building interactive agents with generative UI.",
        },
        {
            "date": today,
            "platform": "Anthropic Academy",
            "category": "Agent智能体",
            "summary": "Anthropic Academy 新增 Agent Skills 和 Subagents 课程",
            "cn_text": "Anthropic Academy 持续扩展其课程体系，新增 Agent Skills 和 Subagents 两大 Claude Code 课程。",
            "url": "https://anthropic.skilljar.com",
            "en_text": "Anthropic Academy expanded to 17 courses covering the full Claude ecosystem.",
        },
    ]

    collected.extend(sample_news)
    return collected


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
    """将清洗后的数据 upsert 到 Supabase ai_news 表

    使用 original_url 字段（即 url）作为唯一键进行去重。
    如果 url 已存在则更新，不存在则插入。

    Returns:
        int: 成功处理的条数
    """
    if not items:
        print("  [WARN] 没有数据需要写入")
        return 0

    success_count = 0

    for item in items:
        if not item.get("url"):
            print("  [SKIP] 缺少 URL，跳过")
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
            print(f"  [ERR] 写入失败 ({item.get('url', 'N/A')}): {e}")

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
    raw_items = fetch_news_from_sources()
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
