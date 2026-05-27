#!/usr/bin/env python3
"""
推送股票看板到飞书 (v3 - 智能推送 + 截止过滤)

改进：
1. 状态持久化：从 gh-pages 分支读取/保存状态
2. 截止过滤：死叉+中性/谨慎/减持的股票不推送
3. 只推送有变化的股票
"""

import os
import json
from datetime import datetime
from pathlib import Path
import requests

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / 'output'
STATE_FILE = OUTPUT_DIR / 'push-state.json'

FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK', '')

# 评分变化阈值
SCORE_CHANGE_THRESHOLD = 5

# 截止信号组合：这些组合不推送（除非信号刚变化）
EXCLUDED_COMBOS = {
    ('死叉', '谨慎'),
    ('死叉', '卖出'),
    ('死叉', '中性'),
}

# 评分过低阈值
MIN_SCORE_THRESHOLD = 25


def load_data():
    """加载 HK 和 US 数据"""
    hk_data, us_data = {}, {}
    hk_file = OUTPUT_DIR / 'hk-data.json'
    us_file = OUTPUT_DIR / 'us-data.json'
    if hk_file.exists():
        with open(hk_file, 'r', encoding='utf-8') as f:
            hk_data = json.load(f)
    if us_file.exists():
        with open(us_file, 'r', encoding='utf-8') as f:
            us_data = json.load(f)
    return hk_data, us_data


def load_state():
    """加载上次推送状态（从 output 目录）"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    """保存推送状态到 output 目录"""
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_expired(stock, prev_stock=None):
    """
    判断股票信号是否已截止（不应推送）

    截止条件：
    1. 死叉 + 评级为中性/谨慎/卖出（但信号刚变化的除外）
    2. 评分低于阈值
    """
    signal = stock.get('technical', {}).get('signal', '')
    rating = stock.get('rating', '')
    score = stock.get('total_score', 0)

    # 如果信号刚从金叉变死叉，不算截止（这是重要变化，需要推送）
    if prev_stock:
        old_signal = prev_stock.get('signal', '')
        if old_signal != signal and signal:
            return False  # 信号变化了，不截止

    if (signal, rating) in EXCLUDED_COMBOS:
        return True

    if score < MIN_SCORE_THRESHOLD:
        return True

    return False


def detect_changes(current_stocks, prev_state, market='hk'):
    """
    检测股票变化，返回需要推送的股票列表

    变化条件（满足任一即推送）：
    1. 信号变化（金叉↔死叉）
    2. 评级变化
    3. 评分大幅波动
    4. 投资建议变化
    5. 新股票
    """
    changed = []
    skipped_expired = []
    prev_stocks = prev_state.get(market, {})

    for stock in current_stocks:
        symbol = stock['symbol']
        prev = prev_stocks.get(symbol)

        # 先检查是否截止（传入上次状态以判断信号是否刚变化）
        if is_expired(stock, prev):
            skipped_expired.append(stock)
            continue
        if prev is None:
            # 新股票，首次推送
            changed.append(stock)
            continue

        # 检查信号变化
        old_signal = prev.get('signal', '')
        new_signal = stock.get('technical', {}).get('signal', '')
        if old_signal != new_signal and new_signal:
            changed.append(stock)
            continue

        # 检查评级变化
        old_rating = prev.get('rating', '')
        new_rating = stock.get('rating', '')
        if old_rating != new_rating:
            changed.append(stock)
            continue

        # 检查评分大幅波动
        old_score = prev.get('total_score', 0)
        new_score = stock.get('total_score', 0)
        if abs(new_score - old_score) >= SCORE_CHANGE_THRESHOLD:
            changed.append(stock)
            continue

        # 检查投资建议变化
        old_action = prev.get('action', '')
        new_action = stock.get('action', '')
        if old_action != new_action:
            changed.append(stock)
            continue

    return changed, skipped_expired


def build_current_state(stocks, market='hk'):
    """构建当前状态快照"""
    state = {}
    for stock in stocks:
        state[stock['symbol']] = {
            'signal': stock.get('technical', {}).get('signal', ''),
            'rating': stock.get('rating', ''),
            'total_score': stock.get('total_score', 0),
            'action': stock.get('action', ''),
            'last_seen': datetime.now().isoformat(),
        }
    return state


def format_stock_line(stock, currency=''):
    """格式化单只股票信息"""
    f = stock.get('fundamentals', {})
    t = stock.get('technical', {})
    p = stock.get('price_data', {})

    lines = []
    lines.append(f"**{stock['name']}** `{stock['symbol']}`")
    lines.append(f"   得分：{stock.get('total_score', '?')} | {stock.get('rating', '?')} | {t.get('signal', '')}")

    current = p.get('current', '?')
    pct_from_high = p.get('pct_from_high', 0) or 0
    lines.append(f"   现价：{currency}{current} (距高点{pct_from_high:+.1f}%)")

    pe = f.get('pe_ttm', 'N/A')
    pb = f.get('pb', 'N/A')
    div = f.get('dividend_yield', 'N/A')
    lines.append(f"   PE: {pe} | PB: {pb} | 股息: {div}%")

    low = p.get('low_52w', '?')
    high = p.get('high_52w', '?')
    lines.append(f"   52 周：{low} ~ {high}")

    action = stock.get('action', '')
    if action:
        lines.append(f"   建议：{action}")

    return '\n'.join(lines)


def format_change_summary(stock, prev_state, market='hk'):
    """格式化变化摘要"""
    symbol = stock['symbol']
    prev = prev_state.get(market, {}).get(symbol, {})
    changes = []

    old_signal = prev.get('signal', '')
    new_signal = stock.get('technical', {}).get('signal', '')
    if old_signal != new_signal and new_signal:
        changes.append(f"信号：{old_signal or 'N/A'} → {new_signal}")

    old_rating = prev.get('rating', '')
    new_rating = stock.get('rating', '')
    if old_rating != new_rating:
        changes.append(f"评级：{old_rating or 'N/A'} → {new_rating}")

    old_score = prev.get('total_score', 0)
    new_score = stock.get('total_score', 0)
    if abs(new_score - old_score) >= SCORE_CHANGE_THRESHOLD:
        direction = '↑' if new_score > old_score else '↓'
        changes.append(f"评分：{old_score} {direction} {new_score}")

    old_action = prev.get('action', '')
    new_action = stock.get('action', '')
    if old_action != new_action:
        changes.append(f"建议：{old_action or 'N/A'} → {new_action}")

    return ' | '.join(changes) if changes else ''


def push_to_feishu(hk_data, us_data, prev_state):
    """智能推送：只推送有变化的、未截止的股票"""
    if not FEISHU_WEBHOOK:
        print("⚠️ 未配置飞书 Webhook")
        return

    hk_stocks = hk_data.get('stocks', [])
    us_stocks = us_data.get('stocks', [])
    hk_time = hk_data.get('update_time', 'N/A')

    # 检测变化
    hk_changed, hk_expired = detect_changes(hk_stocks, prev_state, 'hk')
    us_changed, us_expired = detect_changes(us_stocks, prev_state, 'us')

    # 更新状态（无论是否有变化都更新，包括截止的股票）
    new_state = dict(prev_state)
    new_state['hk'] = build_current_state(hk_stocks, 'hk')
    new_state['us'] = build_current_state(us_stocks, 'us')
    new_state['last_push'] = datetime.now().isoformat()
    save_state(new_state)

    total_changed = len(hk_changed) + len(us_changed)
    total_expired = len(hk_expired) + len(us_expired)

    if total_expired > 0:
        print(f"⏭️ 已过滤截止信号：{total_expired} 只")
        for s in hk_expired + us_expired:
            print(f"   - {s['symbol']} {s['name']} ({s.get('technical',{}).get('signal','')}/{s.get('rating','')})")

    if total_changed == 0:
        print(f"📊 无变化（港股 {len(hk_stocks)} 只、美股 {len(us_stocks)} 只均无信号变化），跳过推送")
        return

    print(f"📊 检测到变化：港股 {len(hk_changed)} 只 | 美股 {len(us_changed)} 只")

    # 构建消息
    lines = [
        f"📊 **股票信号变化** ({datetime.now().strftime('%m-%d %H:%M')})",
        f"共 {total_changed} 只股票有新变化",
    ]
    if total_expired > 0:
        lines.append(f"⏭️ 已过滤截止信号：{total_expired} 只")
    lines.append("")

    if hk_changed:
        lines.append("═" * 35)
        lines.append("")
        lines.append(f"🇭🇰 **港股变化** ({len(hk_changed)}只)")
        lines.append("")
        for i, stock in enumerate(hk_changed, 1):
            change_desc = format_change_summary(stock, prev_state, 'hk')
            lines.append(f"{i}. {format_stock_line(stock, 'HK$ ')}")
            if change_desc:
                lines.append(f"   🔄 {change_desc}")
            lines.append("")

    if us_changed:
        lines.append("═" * 35)
        lines.append("")
        lines.append(f"🇺🇸 **美股变化** ({len(us_changed)}只)")
        lines.append("")
        for i, stock in enumerate(us_changed, 1):
            change_desc = format_change_summary(stock, prev_state, 'us')
            lines.append(f"{i}. {format_stock_line(stock, '$')}")
            if change_desc:
                lines.append(f"   🔄 {change_desc}")
            lines.append("")

    lines.extend([
        "═" * 35,
        "",
        "🔗 **查看详细看板:**",
        f"🇭🇰 港股：https://SuperAvenger.github.io/stock-dashboards/hk-dashboard.html",
        f"🇺🇸 美股：https://SuperAvenger.github.io/stock-dashboards/us-dashboard.html",
        "",
        f"_数据更新：{hk_time}_"
    ])

    message = '\n'.join(lines)

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"📊 股票信号变化 ({total_changed}只)"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": message
                }
            ]
        }
    }

    try:
        resp = requests.post(FEISHU_WEBHOOK, json=payload, timeout=30)
        print(f"\n飞书推送：{resp.status_code}")
        if resp.status_code == 200:
            print("✅ 推送成功！")
        else:
            print(f"❌ 推送失败：{resp.text[:200]}")
    except Exception as e:
        print(f"推送失败：{e}")


def main():
    print("=" * 70)
    print("📱 智能推送股票看板到飞书 (v3)")
    print("=" * 70)

    hk_data, us_data = load_data()
    prev_state = load_state()

    print(f"🇭🇰 港股数据：{len(hk_data.get('stocks', []))} 只")
    print(f"🇺🇸 美股数据：{len(us_data.get('stocks', []))} 只")
    print(f"📋 历史状态：{'有' if prev_state else '无（首次推送）'}")

    push_to_feishu(hk_data, us_data, prev_state)


if __name__ == '__main__':
    main()
