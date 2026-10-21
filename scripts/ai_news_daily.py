#!/usr/bin/env python3
"""
AI 资讯日报 - 轻量版
从多个 AI 资讯源抓取最新标题+链接，推送到飞书
v2: 增加英文→中文翻译（非中文标题自动翻译）
"""
import os
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from deep_translator import GoogleTranslator
    TRANSLATOR = GoogleTranslator(source='auto', target='zh-CN')
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False
    print("⚠️ deep-translator 未安装，跳过翻译")

FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TRANSLATION_CACHE_FILE = Path(__file__).parent.parent / "output" / "translation-cache.json"
TRANSLATION_INTERVAL_SECONDS = 0.8


def is_chinese(text):
    """判断文本是否主要是中文"""
    if not text:
        return False
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return chinese_chars / max(len(text), 1) > 0.3


def translate_title(title):
    """翻译英文标题为中文"""
    if not title or not HAS_TRANSLATOR:
        return title
    if is_chinese(title):
        return title  # 已经是中文，不翻译
    last_error = None
    for attempt, wait_seconds in enumerate((0, 1, 2), start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            translated = TRANSLATOR.translate(title[:200])
            if translated and is_chinese(translated):
                return translated
            last_error = ValueError("翻译结果没有中文字符")
        except Exception as e:
            last_error = e
        print(f"  翻译尝试 {attempt}/3 失败: {last_error}")
    return None


def translate_titles_deepseek(indexed_titles):
    """Batch-translate titles with DeepSeek to avoid per-title throttling."""
    if not DEEPSEEK_API_KEY or not indexed_titles:
        return {}

    translated = {}
    batch_size = 8
    for offset in range(0, len(indexed_titles), batch_size):
        batch = indexed_titles[offset:offset + batch_size]
        numbered_titles = [f"{index}: {title}" for index, title in batch]
        prompt = (
            "把下面的英文科技/AI资讯标题逐条翻译成准确、自然、简洁的简体中文。"
            "保留产品名、人名、公司名、型号和数字；不要总结、解释或增加事实。"
            "只返回 JSON 对象，格式为 {\"translations\":[{\"index\":原编号,\"text\":\"中文译文\"}]}。\n\n"
            + "\n".join(numbered_titles)
        )
        payload = {
            "model": "deepseek-flash",
            "messages": [
                {"role": "system", "content": "你是严谨的科技新闻翻译。必须输出有效 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "stream": False,
        }
        for attempt, wait_seconds in enumerate((0, 2, 5), start=1):
            if wait_seconds:
                time.sleep(wait_seconds)
            try:
                response = requests.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    json=payload,
                    timeout=45,
                )
                response.raise_for_status()
                result = response.json()
                choice = result["choices"][0]
                if choice.get("finish_reason") == "length":
                    raise ValueError("DeepSeek response was truncated")
                content = choice["message"]["content"]
                decoded = json.loads(content)
                entries = decoded.get("translations", [])
                for entry in entries:
                    index = int(entry["index"])
                    value = str(entry.get("text", "")).strip()
                    if value and is_chinese(value):
                        translated[index] = value
                missing = [index for index, _ in batch if index not in translated]
                if missing:
                    print(f"  DeepSeek 本批有 {len(missing)} 条未返回有效中文译文")
                break
            except Exception as e:
                print(f"  DeepSeek 批量翻译尝试 {attempt}/3 失败: {type(e).__name__}: {e}")
        if offset + batch_size < len(indexed_titles):
            time.sleep(0.5)
    return translated


def load_translation_cache():
    try:
        data = json.loads(TRANSLATION_CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_translation_cache(cache):
    TRANSLATION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_CACHE_FILE.write_text(
        json.dumps(dict(list(cache.items())[-1000:]), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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
        raise RuntimeError("FEISHU_WEBHOOK not set")
    if not items:
        raise RuntimeError("没有通过中文校验的资讯，已停止推送")

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
        resp.raise_for_status()
        result = resp.json()
        code = result.get("code", result.get("StatusCode"))
        if code not in (0, "0"):
            raise RuntimeError(f"飞书拒绝资讯推送，业务码：{code}")
        print("✅ 飞书确认资讯推送成功")
    except Exception as e:
        raise RuntimeError(f"资讯推送失败: {e}") from e


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

    # 优先用 DeepSeek 批量翻译；缺少密钥或批次失败时，使用带缓存和退避的 Google 备用翻译。
    cache = load_translation_cache()
    if HAS_TRANSLATOR or DEEPSEEK_API_KEY:
        print("\n>>> 翻译英文标题...")
        en_titles = [(i, item['title']) for i, item in enumerate(all_items) if not is_chinese(item['title'])]
        if en_titles:
            pending = []
            for idx, title in en_titles:
                cached = cache.get(title)
                if cached and is_chinese(cached):
                    all_items[idx]['title_original'] = title
                    all_items[idx]['title'] = cached
                else:
                    pending.append((idx, title))

            deepseek_translations = {}
            if DEEPSEEK_API_KEY and pending:
                print(f"  DeepSeek 批量翻译 {len(pending)} 条标题...")
                deepseek_translations = translate_titles_deepseek(pending)

            failed_titles = []
            last_request_at = 0.0
            for idx, title in pending:
                translated = deepseek_translations.get(idx)
                if translated:
                    print(f"  DeepSeek 已翻译: {title[:70]}")
                elif HAS_TRANSLATOR:
                    delay = TRANSLATION_INTERVAL_SECONDS - (time.monotonic() - last_request_at)
                    if delay > 0:
                        time.sleep(delay)
                    translated = translate_title(title)
                    last_request_at = time.monotonic()
                else:
                    translated = None
                if translated and is_chinese(translated):
                    all_items[idx]['title_original'] = title
                    all_items[idx]['title'] = translated
                    cache[title] = translated
                else:
                    failed_titles.append(title)
                    print(f"  丢弃未能翻译的标题: {title[:100]}")
            if failed_titles:
                failed_set = set(failed_titles)
                all_items = [item for item in all_items if item.get('title') not in failed_set]
            save_translation_cache(cache)
            print(f"  中文标题可用 {len(all_items)} 条；本次翻译失败 {len(failed_titles)} 条")
    else:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY，且 Google 备用翻译组件不可用；已停止发送英文资讯")

    if not all(is_chinese(item['title']) for item in all_items):
        raise RuntimeError("日报含未翻译标题，已停止推送")

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
