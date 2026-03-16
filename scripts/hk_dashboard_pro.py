#!/usr/bin/env python3
"""
港股监控看板 - 专业机构版 (GitHub Actions 适配)
数据源：长桥 Python SDK
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from longport.openapi import Config, QuoteContext, Period, AdjustType

SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR.parent / 'config' / 'longbridge.conf'
OUTPUT_DIR = SCRIPT_DIR.parent / 'output'

OUTPUT_DIR.mkdir(exist_ok=True)

# 股票池
MONITOR_STOCKS = {
    '09988.HK': '阿里巴巴',
    '00700.HK': '腾讯控股',
    '03690.HK': '美团',
    '01810.HK': '小米集团',
    '09961.HK': '携程',
    '01024.HK': '快手',
    '09618.HK': '京东',
    '09999.HK': '网易',
    '00981.HK': '中芯国际',
    '01211.HK': '比亚迪股份',
    '01060.HK': '大麦娱乐',
}

FAST_MA = 10
SLOW_MA = 30


def load_config():
    """加载配置文件"""
    config = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    # 也支持从环境变量读取
    if not config.get('ACCESS_TOKEN'):
        config['APP_KEY'] = os.environ.get('LONGPORT_APP_KEY', '')
        config['APP_SECRET'] = os.environ.get('LONGPORT_APP_SECRET', '')
        config['ACCESS_TOKEN'] = os.environ.get('LONGPORT_ACCESS_TOKEN', '')
    return config


def get_quote_context():
    """获取 QuoteContext"""
    config = load_config()
    cfg = Config(
        app_key=config.get('APP_KEY', ''),
        app_secret=config.get('APP_SECRET', ''),
        access_token=config.get('ACCESS_TOKEN', '')
    )
    return QuoteContext(cfg)


def get_kline(symbol: str, count: int = 200):
    """获取 K 线数据 - 使用长桥 SDK"""
    try:
        quote_ctx = get_quote_context()
        kline = quote_ctx.candlesticks(symbol, Period.Day, count, AdjustType.NoAdjust)
        if kline:
            return list(kline)
    except Exception as e:
        print(f"⚠️ 获取 K 线失败 {symbol}: {e}")
    return []


def get_realtime_quote(symbol: str):
    """获取实时行情 - 使用长桥 SDK"""
    try:
        quote_ctx = get_quote_context()
        quotes = quote_ctx.quote([symbol])
        if quotes:
            q = quotes[0]
            return {
                'last_done': float(q.last_done) if hasattr(q, 'last_done') else 0,
                'change_percent': float(q.change_percent) if hasattr(q, 'change_percent') else 0,
                'high': float(q.high) if hasattr(q, 'high') else 0,
                'low': float(q.low) if hasattr(q, 'low') else 0,
                'open': float(q.open) if hasattr(q, 'open') else 0,
                'prev_close': float(q.prev_close) if hasattr(q, 'prev_close') else 0,
            }
    except Exception as e:
        print(f"⚠️ 获取实时行情失败 {symbol}: {e}")
    return None


def get_stock_data(symbol: str):
    """获取股票数据"""
    kline = get_kline(symbol, count=200)
    if not kline:
        print(f"⚠️ 无法获取 {symbol} K 线数据")
        return None
    
    df = pd.DataFrame([{
        'date': c.timestamp,
        'open': float(c.open),
        'high': float(c.high),
        'low': float(c.low),
        'close': float(c.close),
        'volume': float(c.volume)
    } for c in kline])
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date').sort_index()
    return df


def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd, macd_signal


def calculate_score(df, current_price):
    """计算综合评分 (0-100)"""
    score = 50
    
    ma10 = df['close'].rolling(10).mean().iloc[-1]
    ma30 = df['close'].rolling(30).mean().iloc[-1]
    if current_price > ma10 > ma30:
        score += 20
    elif current_price > ma10:
        score += 10
    elif current_price < ma10 < ma30:
        score -= 20
    elif current_price < ma10:
        score -= 10
    
    rsi = calculate_rsi(df['close']).iloc[-1]
    if 40 <= rsi <= 60:
        score += 5
    elif rsi < 30:
        score += 20
    elif rsi > 70:
        score -= 15
    
    macd, macd_signal_line = calculate_macd(df['close'])
    if macd.iloc[-1] > macd_signal_line.iloc[-1]:
        score += 15
    else:
        score -= 10
    
    high_52w = df['high'].max()
    low_52w = df['low'].min()
    pct_position = (current_price - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50
    if pct_position < 30:
        score += 25
    elif pct_position < 50:
        score += 10
    elif pct_position > 80:
        score -= 20
    
    return max(0, min(100, score))


def get_signal(score):
    if score >= 70:
        return "✅ 强烈买入", "green"
    elif score >= 60:
        return "✅ 买入", "lightgreen"
    elif score >= 45:
        return "🟡 持有", "orange"
    elif score >= 30:
        return "🟠 减持", "darkorange"
    else:
        return "🔴 卖出", "red"


def analyze_stock(symbol, name):
    """分析单只股票"""
    df = get_stock_data(symbol)
    if df is None or len(df) < 30:
        return None
    
    realtime = get_realtime_quote(symbol)
    if realtime and realtime['last_done'] > 0:
        current_price = realtime['last_done']
        pct_change = realtime['change_percent']
        prev_close = realtime['prev_close']
    else:
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2] if len(df) > 1 else current_price
        pct_change = ((current_price - prev_price) / prev_price) * 100
        prev_close = prev_price
    
    high_52w = df['high'].max()
    low_52w = df['low'].min()
    pct_from_high = ((current_price - high_52w) / high_52w) * 100
    pct_from_low = ((current_price - low_52w) / low_52w) * 100
    
    score = calculate_score(df, current_price)
    signal, color = get_signal(score)
    
    ma_fast = df['close'].rolling(FAST_MA).mean().iloc[-1]
    ma_slow = df['close'].rolling(SLOW_MA).mean().iloc[-1]
    
    rsi = calculate_rsi(df['close']).iloc[-1]
    macd, macd_signal_line = calculate_macd(df['close'])
    
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
        'signal': signal,
        'color': color,
        'high_52w': round(high_52w, 2),
        'low_52w': round(low_52w, 2),
        'pct_from_high': round(pct_from_high, 1),
        'pct_from_low': round(pct_from_low, 1),
        'ma_fast': round(ma_fast, 2),
        'ma_slow': round(ma_slow, 2),
        'rsi': round(rsi, 1),
        'macd': round(macd.iloc[-1], 2),
        'macd_signal': round(macd_signal_line.iloc[-1], 2),
        'price_history': price_history,
        'prev_close': round(prev_close, 2) if prev_close else None
    }


def generate_html(stocks_data, update_time):
    stocks_json = json.dumps(stocks_data, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>港股监控看板</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
.container {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ color: #333; text-align: center; }}
.update-time {{ text-align: center; color: #666; margin-bottom: 20px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }}
.card {{ background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
.card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
.stock-name {{ font-size: 18px; font-weight: bold; }}
.stock-symbol {{ color: #666; font-size: 14px; }}
.price {{ font-size: 28px; font-weight: bold; margin: 10px 0; }}
.price-up {{ color: #d0021b; }}
.price-down {{ color: #007aff; }}
.change {{ font-size: 16px; margin-left: 10px; }}
.score {{ display: inline-block; padding: 4px 12px; border-radius: 20px; color: white; font-weight: bold; }}
.metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 15px; font-size: 14px; }}
.metric {{ padding: 8px; background: #f8f8f8; border-radius: 6px; }}
.metric-label {{ color: #666; font-size: 12px; }}
.metric-value {{ font-weight: 600; }}
.chart {{ height: 150px; margin-top: 15px; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
<div class="container">
<h1>🇭🇰 港股监控看板 (专业版)</h1>
<div class="update-time">更新时间：{update_time}</div>
<div class="grid" id="cards"></div>
</div>
<script>
const stocks = {stocks_json};
const container = document.getElementById('cards');

stocks.forEach(stock => {{
    const changeClass = stock.change >= 0 ? 'price-up' : 'price-down';
    const changeSign = stock.change >= 0 ? '+' : '';
    
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
        <div class="card-header">
            <div>
                <div class="stock-name">${{stock.name}}</div>
                <div class="stock-symbol">${{stock.symbol}}</div>
            </div>
            <span class="score" style="background: ${{stock.color}}">${{stock.score}}分</span>
        </div>
        <div class="price {{changeClass}}">
            HK$ ${{stock.current}} <span class="change">{{changeSign}}${{stock.change}}%</span>
        </div>
        <div style="text-align: center; margin: 10px 0;">${{stock.signal}}</div>
        <div class="metrics">
            <div class="metric">
                <div class="metric-label">52 周高</div>
                <div class="metric-value">${{stock.high_52w}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">52 周低</div>
                <div class="metric-value">${{stock.low_52w}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">距高点</div>
                <div class="metric-value">${{stock.pct_from_high}}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">距低点</div>
                <div class="metric-value">${{stock.pct_from_low}}%</div>
            </div>
            <div class="metric">
                <div class="metric-label">MA10</div>
                <div class="metric-value">${{stock.ma_fast}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">MA30</div>
                <div class="metric-value">${{stock.ma_slow}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">RSI</div>
                <div class="metric-value">${{stock.rsi}}</div>
            </div>
            <div class="metric">
                <div class="metric-label">MACD</div>
                <div class="metric-value">${{stock.macd}}</div>
            </div>
        </div>
        <canvas class="chart" id="chart-${{stock.symbol}}"></canvas>
    `;
    container.appendChild(card);
    
    const ctx = document.getElementById(`chart-${{stock.symbol}}`).getContext('2d');
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: stock.price_history.map(d => d.date.slice(5)),
            datasets: [{{
                label: '收盘价',
                data: stock.price_history.map(d => d.close),
                borderColor: '#007aff',
                tension: 0.3,
                pointRadius: 0
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: false }} }},
            scales: {{ x: {{ display: false }}, y: {{ beginAtZero: false }} }}
        }}
    }});
}});
</script>
</body></html>'''
    return html


def main():
    print("=" * 70)
    print("🇭🇰 港股监控看板 - 专业机构版")
    print("=" * 70)
    
    stocks_data = []
    
    for symbol, name in MONITOR_STOCKS.items():
        print(f"\n分析 {name} ({symbol})...")
        result = analyze_stock(symbol, name)
        if result:
            stocks_data.append(result)
            print(f"  现价：HK$ {result['current']} ({result['change']:+.2f}%)")
            print(f"  评分：{result['score']} | {result['signal']}")
        else:
            print(f"  ⚠️ 无法获取数据")
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html = generate_html(stocks_data, update_time)
    output_file = OUTPUT_DIR / 'hk-dashboard.html'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\n✅ HTML 已保存：{output_file}")
    
    json_file = OUTPUT_DIR / 'hk-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump({
            'stocks': stocks_data,
            'update_time': update_time
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ 数据已保存：{json_file}")
    
    print(f"\n共 {len(stocks_data)} 只股票")


if __name__ == '__main__':
    main()
