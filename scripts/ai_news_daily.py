#!/usr/bin/env python3
"""
AI 资讯日报 - 轻量版
从多个 AI 资讯源抓取最新标题+链接，推送到飞书
"""
import os
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_rss(url, source_name, max_items=10):
    """通用 RSS 解析"""
    items = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.find_all("item")[:max_items]:
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubdate") or item.find("published")
            if title and link:
                items.append({
                    "title": title.get_text(strip=True),
                    "link": link.get_text(strip=True) or (link.next_sibling.strip() if link.next_sibling else ""),
                    "source": source_name,
                    "date": pub_date.get_text(strip=True)[:16] if pub_date else "",
                })
    except Exception as e:
        print(f"RSS fetch failed ({source_name}): {e}")
    return items


def fetch_hacker_news_ai():
    """Hacker News AI 相关"""
    items = []
    try:
        # HN Algolia API - 搜索 AI 相关
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": "AI LLM GPT Claude", "tags": "story", "hitsPerPage": 15},
            timeout=15,
        )
        data = resp.json()
        for hit in data.get("hits", []):
            if hit.get("title") and hit.get("url"):
                items.append({
                    "title": hit["title"],
                    "link": hit["url"],
                    "source": "Hacker News",
                    "date": hit.get("created_at", "")[:16],
                })
    except Exception as e:
        print(f"HN fetch failed: {e}")
    return items


def fetch_reddit_ai():
    """Reddit r/artificial + r/MachineLearning"""
    items = []
    subreddits = ["artificial", "MachineLearning", "LocalLLaMA"]
    for sub in subreddits:
        try:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=8",
                headers={**HEADERS, "User-Agent": "Mozilla/5.0 (compatible; bot/1.0)"},
                timeout=15,
            )
            data = resp.json()
            for post in data.get("data", {}).get("children", []):
                d = post.get("data", {})
                if d.get("title") and not d.get("stickied"):
                    url = d.get("url", "")
                    if url.startswith("/r/"):
                        url = f"https://www.reddit.com{url}"
                    items.append({
                        "title": d["title"][:100],
                        "link": url,
                        "source": f"r/{sub}",
                        "date": datetime.fromtimestamp(d.get("created_utc", 0)).strftime("%m-%d %H:%M"),
                    })
        except Exception as e:
            print(f"Reddit fetch failed ({sub}): {e}")
    return items


def fetch_the_verge_ai():
    """The Verge AI 版块"""
    items = []
    try:
        resp = requests.get("https://www.theverge.com/ai-artificial-intelligence", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='/ai-artificial-intelligence']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if title and len(title) > 10 and href.startswith("http"):
                items.append({"title": title, "link": href, "source": "The Verge", "date": ""})
    except Exception as e:
        print(f"Verge fetch failed: {e}")
    return items[:8]


def fetch_techcrunch_ai():
    """TechCrunch AI 版块"""
    items = []
    try:
        resp = requests.get("https://techcrunch.com/category/artificial-intelligence/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='techcrunch.com']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if title and len(title) > 15 and "/202" in href:
                items.append({"title": title, "link": href, "source": "TechCrunch", "date": ""})
    except Exception as e:
        print(f"TechCrunch fetch failed: {e}")
    return items[:8]


def fetch_36kr_ai():
    """36氪 AI 频道"""
    items = []
    try:
        resp = requests.get("https://36kr.com/information/AI/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='/p/']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if title and len(title) > 8:
                if not href.startswith("http"):
                    href = f"https://36kr.com{href}"
                items.append({"title": title, "link": href, "source": "36氪", "date": ""})
    except Exception as e:
        print(f"36kr fetch failed: {e}")
    return items[:8]


def dedup(items):
    """去重"""
    seen = set()
    result = []
    for item in items:
        key = item["title"][:30]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def push_to_feishu(items):
    """推送飞书"""
    if not FEISHU_WEBHOOK:
        print("FEISHU_WEBHOOK not set")
        return

    # 按来源分组
    by_source = {}
    for item in items:
        src = item["source"]
        by_source.setdefault(src, []).append(item)

    lines = [
        f"🤖 **AI 资讯日报** ({datetime.now().strftime('%Y-%m-%d')})",
        f"共 {len(items)} 条",
        "",
    ]

    for src, src_items in by_source.items():
        lines.append(f"**{src}**")
        for i, item in enumerate(src_items[:8], 1):
            lines.append(f"{i}. [{item['title']}]({item['link']})")
        lines.append("")

    message = "\n".join(lines)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🤖 AI 资讯日报 ({datetime.now().strftime('%m/%d')})"},
                "template": "purple",
            },
            "elements": [{"tag": "markdown", "content": message}],
        },
    }

    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=30)
        print(f"飞书推送: {resp.status_code}")
        if resp.status_code == 200:
            print("✅ 推送成功")
        else:
            print(f"❌ {resp.text[:200]}")
    except Exception as e:
        print(f"推送失败: {e}")


def main():
    print("=" * 60)
    print("🤖 AI 资讯日报")
    print("=" * 60)

    all_items = []

    # 1. Hacker News (最稳定)
    print(">>> Hacker News...")
    all_items.extend(fetch_hacker_news_ai())

    # 2. Reddit
    print(">>> Reddit...")
    all_items.extend(fetch_reddit_ai())

    # 3. RSS 源
    rss_sources = [
        ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch"),
        ("https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "The Verge"),
    ]
    for url, name in rss_sources:
        print(f">>> {name} RSS...")
        all_items.extend(fetch_rss(url, name))

    # 4. 36氪
    print(">>> 36氪...")
    all_items.extend(fetch_36kr_ai())

    # 去重
    all_items = dedup(all_items)
    print(f"\n共采集 {len(all_items)} 条 AI 资讯")

    # 保存
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    with open(output_dir / "ai-news.json", "w", encoding="utf-8") as f:
        json.dump({"update_time": datetime.now().isoformat(), "items": all_items}, f, ensure_ascii=False, indent=2)

    # 推送
    push_to_feishu(all_items)

    # 打印
    for item in all_items:
        print(f"  [{item['source']}] {item['title'][:60]}")


if __name__ == "__main__":
    main()
