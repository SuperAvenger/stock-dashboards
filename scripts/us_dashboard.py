#!/usr/bin/env python3
"""
美股监控看板生成器 - GitHub Actions 版
数据源：长桥 API
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from decimal import Decimal
import requests

# ============== 配置 ==============
LONGPORT_APP_KEY = os.environ.get('LONGPORT_APP_KEY', '')
LONGPORT_ACCESS_TOKEN = os.environ.get('LONGPORT_ACCESS_TOKEN', '')
LONGPORT_API_BASE = 'https://openapi.longportapp.com'

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR.parent / 'config' / 'stocks.json'
OUTPUT_DIR = SCRIPT_DIR.parent / 'output'

OUTPUT_DIR.mkdir(exist_ok=True)


# ============== 长桥 API 客户端 ==============
def get_kline(symbol: str, days: int = 200):
    """获取 K 线数据"""
    if not LONGPORT_ACCESS_TOKEN:
        print(f"⚠️ 未配置长桥 Token，使用模拟数据")
        return generate_mock_kline(symbol, days)
    
    try:
        url = f"{LONGPORT_API_BASE}/quote/kline"
        headers = {
            'Authorization': f'Bearer {LONGPORT_ACCESS_TOKEN}',
            'Content-Type': 'application/json'
        }
        payload = {
            'symbol': symbol,
            'period': 'D',
            'rehab_type': 'FRH',
            'count': days
        }
        
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('code') == 0 and data.get('data'):
                return [KlineData(c) for c in data['data']['candles']]
        print(f"⚠️ API 返回异常：{resp.text[:200]}")
    except Exception as e:
        print(f"⚠️ 获取 K 线失败 {symbol}: {e}")
    
    return generate_mock_kline(symbol, days)


class KlineData:
    def __init__(self, candle):
        self.timestamp = candle.get('time', '')
        self.open = float(candle.get('open', 0))
        self.high = float(candle.get('high', 0))
        self.low = float(candle.get('low', 0))
        self.close = float(candle.get('close', 0))
        self.volume = float(candle.get('volume', 0))


def generate_mock_kline(symbol: str, days: int):
    """生成模拟 K 线（用于测试）"""
    import random
    base_price = 100 + random.random() * 400
    candles = []
    for i in range(days):
        date = datetime.now().replace(hour=0, minute=0, second=0)
        date = date.replace(day=max(1, date.day - (days - i)))
        change = random.uniform(-0.05, 0.05)
        close = base_price * (1 + change)
        candles.append({
            'time': date.strftime('%Y-%m-%d'),
            'open': base_price,
            'high': base_price * 1.03,
            'low': base_price * 0.97,
            'close': close,
            'volume': random.randint(1000000, 50000000)
        })
        base_price = close
    return [KlineData(c) for c in candles]


# ============== 技术指标 ==============
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices):
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def calculate_score(df, current_price):
    """计算综合得分（0-100）"""
    score = 50
    
    ma10 = df['close'].rolling(10).mean().iloc[-1]
    ma30 = df['close'].rolling(30).mean().iloc[-1]
    if current_price > ma10 > ma30:
        score += 20
    elif current_price < ma10 < ma30:
        score -= 20
    
    rsi = calculate_rsi(df['close']).iloc[-1]
    if rsi < 30:
        score += 15
    elif rsi > 70:
        score -= 15
    
    macd, signal = calculate_macd(df['close'])
    if macd.iloc[-1] > signal.iloc[-1]:
        score += 10
    
    return max(0, min(100, score))


def get_signal(score):
    if score >= 70:
        return '✅ 买入'
    elif score >= 50:
        return '⚠️ 观望'
    else:
        return '❌ 谨慎'


# ============== 主逻辑 ==============
def fetch_stock_data(symbol):
    df = pd.DataFrame([{
        'date': c.timestamp,
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume
    } for c in get_kline(symbol, 200)])
    
    if len(df) < 30:
        return None
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    return df


def analyze_stock(symbol, name, settings):
    df = fetch_stock_data(symbol)
    if df is None:
        return None
    
    current_price = df['close'].iloc[-1]
    prev_price = df['close'].iloc[-2]
    pct_change = ((current_price - prev_price) / prev_price) * 100
    
    high_52w = df['high'].max()
    low_52w = df['low'].min()
    score = calculate_score(df, current_price)
    
    price_history = []
    for idx, row in df.tail(60).iterrows():
        price_history.append({
            'date': idx.strftime('%Y-%m-%d'),
            'close': round(row['close'], 2)
        })
    
    return {
        'symbol': symbol,
        'name': name,
        'current': round(current_price, 2),
        'change': round(pct_change, 2),
        'score': score,
        'signal': get_signal(score),
        'high_52w': round(high_52w, 2),
        'low_52w': round(low_52w, 2),
        'price_history': price_history
    }


# ============== HTML 生成 ==============
def generate_html(stocks_data, title, update_time):
    cards_html = ''
    for stock in stocks_data:
        color = '#22c55e' if stock['score'] >= 70 else '#f59e0b' if stock['score'] >= 50 else '#ef4444'
        cards_html += f'''
        <div class="stock-card" style="border-left: 4px solid {color}">
            <div class="stock-header">
                <span class="stock-name">{stock['name']}</span>
                <span class="stock-symbol">{stock['symbol']}</span>
            </div>
            <div class="stock-price">
                <span class="price">${stock['current']}</span>
                <span class="change {'positive' if stock['change'] >= 0 else 'negative'}">
                    {stock['change']:+.2f}%
                </span>
            </div>
            <div class="stock-score">
                <span class="score-label">得分</span>
                <span class="score-value" style="color: {color}">{stock['score']}分</span>
                <span class="signal">{stock['signal']}</span>
            </div>
            <div class="stock-metrics">
                <div>52 周高：{stock['high_52w']}</div>
                <div>52 周低：{stock['low_52w']}</div>
            </div>
        </div>
        '''
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            min-height: 100vh;
            color: #e4e4e4;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            text-align: center;
            padding: 30px 0;
            margin-bottom: 30px;
        }}
        header h1 {{
            font-size: 2em;
            background: linear-gradient(90deg, #3b82f6, #2563eb);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .update-time {{ color: #9ca3af; margin-top: 10px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        .stock-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            transition: transform 0.2s;
        }}
        .stock-card:hover {{ transform: translateY(-4px); }}
        .stock-header {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 15px;
        }}
        .stock-name {{ font-weight: bold; font-size: 1.1em; }}
        .stock-symbol {{ color: #9ca3af; }}
        .stock-price {{
            display: flex;
            align-items: baseline;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .price {{ font-size: 1.8em; font-weight: bold; }}
        .change {{ font-size: 1.1em; }}
        .change.positive {{ color: #22c55e; }}
        .change.negative {{ color: #ef4444; }}
        .stock-score {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }}
        .score-label {{ color: #9ca3af; }}
        .score-value {{ font-weight: bold; font-size: 1.3em; }}
        .signal {{ margin-left: auto; }}
        .stock-metrics {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            color: #9ca3af;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <div class="update-time">更新时间：{update_time}</div>
        </header>
        <div class="grid">
            {cards_html}
        </div>
    </div>
</body>
</html>'''
    return html


def main():
    print("=" * 70)
    print("🇺🇸 美股监控看板生成器")
    print("=" * 70)
    
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    us_stocks = config.get('us_stocks', {})
    settings = config.get('settings', {})
    
    print(f"📋 股票池：{len(us_stocks)} 只")
    print(f"🔑 长桥 API: {'✅' if LONGPORT_ACCESS_TOKEN else '❌'}")
    
    stocks_data = []
    for symbol, name in us_stocks.items():
        print(f"\n📈 分析：{symbol} - {name}")
        result = analyze_stock(symbol, name, settings)
        if result:
            stocks_data.append(result)
            print(f"   得分：{result['score']} | 信号：{result['signal']}")
        else:
            print(f"   ⚠️ 数据不足")
    
    stocks_data.sort(key=lambda x: x['score'], reverse=True)
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    html = generate_html(stocks_data, '🇺🇸 美股监控看板', update_time)
    
    output_file = OUTPUT_DIR / 'us-dashboard.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ 看板已保存：{output_file}")
    
    json_file = OUTPUT_DIR / 'us-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'update_time': update_time,
            'stocks': stocks_data
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ 数据已保存：{json_file}")
    
    print("\n" + "=" * 70)
    print("📱 飞书推送摘要:")
    for stock in stocks_data[:5]:
        print(f"  {stock['name']}: {stock['score']}分 {stock['signal']}")
    
    return stocks_data


if __name__ == '__main__':
    main()
