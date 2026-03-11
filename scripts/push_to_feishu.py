#!/usr/bin/env python3
"""
推送股票看板到飞书
"""

import os
import json
from datetime import datetime
from pathlib import Path
import requests

SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / 'output'

FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK', '')


def load_data():
    """加载 HK 和 US 数据"""
    hk_data = {}
    us_data = {}
    
    hk_file = OUTPUT_DIR / 'hk-data.json'
    us_file = OUTPUT_DIR / 'us-data.json'
    
    if hk_file.exists():
        with open(hk_file, 'r', encoding='utf-8') as f:
            hk_data = json.load(f)
    
    if us_file.exists():
        with open(us_file, 'r', encoding='utf-8') as f:
            us_data = json.load(f)
    
    return hk_data, us_data


def format_stock_line(stock, currency=''):
    """格式化单只股票信息"""
    f = stock.get('fundamentals', {})
    lines = []
    lines.append(f"**{stock['name']}** `{stock['symbol']}`")
    lines.append(f"   得分：{stock['score']} | {stock['signal']}")
    lines.append(f"   现价：{currency}{stock['current']} ({stock['change']:+.2f}%)")
    lines.append(f"   行业：{f.get('sector', 'N/A')} | PE: {f.get('pe', 'N/A')} | PB: {f.get('pb', 'N/A')}")
    lines.append(f"   市值：{f.get('market_cap', 'N/A')} | 股息：{f.get('dividend', 'N/A')}")
    lines.append(f"   52 周：{stock['low_52w']} ~ {stock['high_52w']} (距高点{stock['pct_from_high']:+.1f}%)")
    return '\n'.join(lines)


def push_to_feishu(hk_data, us_data):
    """推送 Markdown 消息到飞书"""
    if not FEISHU_WEBHOOK:
        print("⚠️ 未配置飞书 Webhook")
        return
    
    # 推送全部股票，不按 TOP5 限制
    hk_stocks = hk_data.get('stocks', [])
    us_stocks = us_data.get('stocks', [])
    hk_time = hk_data.get('update_time', 'N/A')
    us_time = us_data.get('update_time', 'N/A')
    
    # 构建 Markdown 消息
    lines = [
        f"📊 **每日股票监控看板** ({datetime.now().strftime('%Y-%m-%d')})",
        f"共 {len(hk_stocks)} 只港股 | {len(us_stocks)} 只美股",
        "",
        "═" * 40,
        "",
        f"🇭🇰 **港股监控** ({len(hk_stocks)}只)",
        ""
    ]
    
    for i, stock in enumerate(hk_stocks, 1):
        lines.append(f"{i}. {format_stock_line(stock, 'HK$ ')}")
        lines.append("")
    
    lines.extend([
        "═" * 40,
        "",
        f"🇺🇸 **美股监控** ({len(us_stocks)}只)",
        ""
    ])
    
    for i, stock in enumerate(us_stocks, 1):
        lines.append(f"{i}. {format_stock_line(stock, '$')}")
        lines.append("")
    
    lines.extend([
        "═" * 40,
        "",
        "🔗 **查看详细看板:**",
        f"🇭🇰 港股：https://SuperAvenger.github.io/stock-dashboards/hk-dashboard.html",
        f"🇺🇸 美股：https://SuperAvenger.github.io/stock-dashboards/us-dashboard.html",
        "",
        f"_数据更新：{hk_time}_"
    ])
    
    message = '\n'.join(lines)
    
    # 飞书卡片消息
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 每日股票监控看板"},
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
    print("📱 推送股票看板到飞书")
    print("=" * 70)
    
    hk_data, us_data = load_data()
    
    print(f"🇭🇰 港股数据：{len(hk_data.get('stocks', []))} 只")
    print(f"🇺🇸 美股数据：{len(us_data.get('stocks', []))} 只")
    
    push_to_feishu(hk_data, us_data)


if __name__ == '__main__':
    main()
