#!/usr/bin/env python3
"""
港股监控看板 - 专业机构版
数据源：长桥 API | 参考华尔街/彭博终端设计
"""

import sys
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from decimal import Decimal

def convert_to_serializable(obj):
    """递归转换对象为 JSON 可序列化格式"""
    if isinstance(obj, dict):
        return {k: convert_to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_serializable(v) for v in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj

sys.path.insert(0, '/home/venger/projects/alibaba_monitor')
sys.path.insert(0, '/home/venger/projects/ricequant')

from longport_simple_client import get_kline
from factor_engine_v3 import FactorEngineV3

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

def get_stock_data(symbol):
    try:
        kline = get_kline(symbol, 200)
        if not kline or len(kline) == 0:
            return None
        df = pd.DataFrame([{
            'date': str(c.timestamp)[:10],
            'open': float(c.open),
            'high': float(c.high),
            'low': float(c.low),
            'close': float(c.close),
            'volume': float(c.volume)
        } for c in kline])
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').sort_index()
        return df
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

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

def calculate_technical_indicators(df):
    """计算技术指标"""
    ma_fast = df['close'].rolling(FAST_MA).mean()
    ma_slow = df['close'].rolling(SLOW_MA).mean()
    rsi = calculate_rsi(df['close'], 14)
    macd, macd_signal = calculate_macd(df['close'])
    
    # 布林带
    ma20 = df['close'].rolling(20).mean()
    std20 = df['close'].rolling(20).std()
    bb_upper = ma20 + 2 * std20
    bb_lower = ma20 - 2 * std20
    
    # ATR (波动率)
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(14).mean()
    
    return {
        'ma_fast': ma_fast.iloc[-1],
        'ma_slow': ma_slow.iloc[-1],
        'rsi': rsi.iloc[-1],
        'macd': macd.iloc[-1],
        'macd_signal': macd_signal.iloc[-1],
        'bb_upper': bb_upper.iloc[-1],
        'bb_lower': bb_lower.iloc[-1],
        'atr': atr.iloc[-1],
    }

def generate_comprehensive_analysis(symbol, name, df, current_price):
    """生成综合分析 (参考华尔街评级体系)"""
    try:
        engine = FactorEngineV3(symbol)
        closes = df['close'].tolist()
        kline_data = {'close': closes}
        factors = engine.calculate_all_factors(kline_data, current_price, suppress_log=True)
        tech = calculate_technical_indicators(df)
        
        # ============ 五大维度评分 ============
        
        # 1. 估值维度 (30% 权重)
        valuation_score = factors.get('value_composite', 50)
        valuation_grade = get_grade(valuation_score)
        
        # 2. 成长维度 (25% 权重) - 用手动数据
        growth_score = factors.get('growth_composite', 50)
        growth_grade = get_grade(growth_score)
        
        # 3. 盈利质量 (20% 权重)
        quality_score = factors.get('quality_composite', 50)
        quality_grade = get_grade(quality_score)
        
        # 4. 市场情绪 (15% 权重)
        sentiment_score = factors.get('sentiment_composite', 50)
        sentiment_grade = get_grade(sentiment_score)
        
        # 5. 技术面 (10% 权重)
        tech_score = calculate_technical_score(tech, current_price, df)
        tech_grade = get_grade(tech_score)
        
        # ============ 综合评分 ============
        total_score = (
            valuation_score * 0.30 +
            growth_score * 0.25 +
            quality_score * 0.20 +
            sentiment_score * 0.15 +
            tech_score * 0.10
        )
        
        # 综合评级
        if total_score >= 80:
            rating = '强烈推荐'
            rating_color = '#22c55e'
            action = '建仓 70-80%'
        elif total_score >= 60:
            rating = '推荐'
            rating_color = '#84cc16'
            action = '建仓 50-60%'
        elif total_score >= 40:
            rating = '中性'
            rating_color = '#eab308'
            action = '持有 30-40%'
        elif total_score >= 20:
            rating = '谨慎'
            rating_color = '#f97316'
            action = '减持至 10-20%'
        else:
            rating = '卖出'
            rating_color = '#ef4444'
            action = '清仓'
        
        # ============ 关键数据 ============
        pe = factors.get('pe_score')
        pb = factors.get('pb_score')
        roe = factors.get('roe_score')
        dividend = factors.get('dividend_score')
        
        # 计算实际 PE/PB 值
        fundamentals = engine.fundamentals
        pe_ttm = fundamentals.get('pe_ttm')
        pb_ratio = fundamentals.get('pb')
        dividend_yield = fundamentals.get('dividend_yield', 0)
        
        # 52 周数据
        high_52w = df['high'].rolling(250).max().iloc[-1] if len(df) >= 250 else df['high'].max()
        low_52w = df['low'].rolling(250).min().iloc[-1] if len(df) >= 250 else df['low'].min()
        pct_from_high = (current_price - high_52w) / high_52w * 100
        pct_from_low = (current_price - low_52w) / low_52w * 100
        
        # ============ 投资建议 ============
        reasons = generate_investment_reasons({
            'valuation': valuation_score,
            'growth': growth_score,
            'quality': quality_score,
            'sentiment': sentiment_score,
            'technical': tech_score,
        }, fundamentals, tech, current_price)
        
        return {
            'total_score': round(total_score),
            'rating': rating,
            'rating_color': rating_color,
            'action': action,
            'dimensions': {
                'valuation': {'score': round(valuation_score), 'grade': valuation_grade, 'weight': 30},
                'growth': {'score': round(growth_score), 'grade': growth_grade, 'weight': 25},
                'quality': {'score': round(quality_score), 'grade': quality_grade, 'weight': 20},
                'sentiment': {'score': round(sentiment_score), 'grade': sentiment_grade, 'weight': 15},
                'technical': {'score': round(tech_score), 'grade': tech_grade, 'weight': 10},
            },
            'fundamentals': {
                'pe_ttm': round(pe_ttm, 2) if pe_ttm else None,
                'pb': round(pb_ratio, 2) if pb_ratio else None,
                'roe': round(roe) if roe else None,
                'dividend_yield': round(dividend_yield, 2) if dividend_yield else None,
                'eps_ttm': round(fundamentals.get('eps_ttm', 0), 2) if fundamentals.get('eps_ttm') else None,
                'bps': round(fundamentals.get('bps', 0), 2) if fundamentals.get('bps') else None,
            },
            'technical': {
                'rsi': round(tech['rsi'], 1),
                'macd': round(tech['macd'], 4),
                'ma_fast': round(tech['ma_fast'], 2),
                'ma_slow': round(tech['ma_slow'], 2),
                'atr': round(tech['atr'], 2),
                'signal': '金叉' if tech['ma_fast'] > tech['ma_slow'] else '死叉',
            },
            'price_data': {
                'current': round(current_price, 2),
                'high_52w': round(high_52w, 2),
                'low_52w': round(low_52w, 2),
                'pct_from_high': round(pct_from_high, 1),
                'pct_from_low': round(pct_from_low, 1),
            },
            'reasons': reasons,
        }
    except Exception as e:
        print(f"  ⚠ 综合分析失败：{str(e)[:50]}")
        return get_default_analysis(current_price)

def get_grade(score):
    if score >= 80: return 'A'
    if score >= 60: return 'B'
    if score >= 40: return 'C'
    if score >= 20: return 'D'
    return 'F'

def calculate_technical_score(tech, current_price, df):
    """计算技术面评分"""
    score = 50
    
    # 均线 (20 分)
    if tech['ma_fast'] > tech['ma_slow']:
        score += 20
    else:
        score -= 20
    
    # RSI (20 分)
    if tech['rsi'] < 30:
        score += 20
    elif tech['rsi'] > 70:
        score -= 20
    
    # MACD (20 分)
    if tech['macd'] > tech['macd_signal']:
        score += 20
    else:
        score -= 20
    
    # 布林带位置 (20 分)
    bb_position = (current_price - tech['bb_lower']) / (tech['bb_upper'] - tech['bb_lower']) * 100
    if bb_position < 20:
        score += 20
    elif bb_position > 80:
        score -= 20
    
    # 趋势 (20 分)
    if len(df) > 20:
        ma20 = df['close'].rolling(20).mean().iloc[-1]
        if current_price > ma20:
            score += 20
        else:
            score -= 20
    
    return max(0, min(100, score))

def generate_investment_reasons(scores, fundamentals, tech, current_price):
    """生成投资理由"""
    reasons = []
    
    # 估值
    v = scores['valuation']
    if v >= 70:
        reasons.append("估值极具吸引力，安全边际高")
    elif v >= 50:
        reasons.append("估值合理，具备配置价值")
    elif v >= 30:
        reasons.append("估值偏高，需等待更好买点")
    else:
        reasons.append("估值泡沫，警惕回调风险")
    
    # 盈利质量
    q = scores['quality']
    if q >= 70:
        reasons.append("ROE 优异，盈利能力强")
    elif q >= 50:
        reasons.append("盈利质量良好")
    else:
        reasons.append("盈利能力偏弱，需观察改善")
    
    # 技术面
    t = scores['technical']
    if t >= 70:
        reasons.append("技术面强势，趋势向上")
    elif t >= 50:
        reasons.append("技术面中性，震荡整理")
    else:
        reasons.append("技术面偏弱，趋势向下")
    
    # 股息
    dy = fundamentals.get('dividend_yield', 0)
    if dy and dy > 3:
        reasons.append(f"高股息 ({dy:.1f}%)，防御性强")
    
    return reasons

def get_default_analysis(current_price):
    """默认分析 (数据不足时)"""
    return {
        'total_score': 50,
        'rating': '数据不足',
        'rating_color': '#6b7280',
        'action': '观望',
        'dimensions': {
            'valuation': {'score': 50, 'grade': 'C', 'weight': 30},
            'growth': {'score': 50, 'grade': 'C', 'weight': 25},
            'quality': {'score': 50, 'grade': 'C', 'weight': 20},
            'sentiment': {'score': 50, 'grade': 'C', 'weight': 15},
            'technical': {'score': 50, 'grade': 'C', 'weight': 10},
        },
        'fundamentals': {},
        'technical': {},
        'price_data': {'current': current_price},
        'reasons': ['数据不足，无法进行完整分析'],
    }

def convert_decimals(obj):
    """递归转换 Decimal 为 float"""
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(v) for v in obj]
    elif hasattr(obj, '__float__'):
        return float(obj)
    return obj

def generate_html(stocks_data, update_time):
    """生成专业机构版 HTML"""
    stocks_data = convert_decimals(stocks_data)
    stocks_json = json.dumps(stocks_data, ensure_ascii=False)
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🥔 港股监控看板 - 专业机构版</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
            min-height: 100vh;
            color: #e4e4e4;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; padding: 20px; }}
        
        header {{
            text-align: center;
            padding: 40px 0;
            border-bottom: 2px solid rgba(251, 191, 36, 0.3);
            margin-bottom: 40px;
            background: rgba(251, 191, 36, 0.05);
            border-radius: 16px;
        }}
        header h1 {{
            font-size: 2.8em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #fbbf24, #f59e0b, #fbbf24);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: shine 3s linear infinite;
        }}
        @keyframes shine {{
            to {{ background-position: 200% center; }}
        }}
        .subtitle {{
            color: #9ca3af;
            font-size: 1.1em;
            margin-top: 10px;
        }}
        .update-badge {{
            display: inline-block;
            padding: 8px 20px;
            background: rgba(251, 191, 36, 0.15);
            border: 1px solid rgba(251, 191, 36, 0.3);
            border-radius: 20px;
            margin-top: 15px;
            color: #fbbf24;
            font-size: 0.9em;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 30px;
            margin-bottom: 40px;
        }}
        
        .card {{
            background: linear-gradient(145deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
            border-radius: 20px;
            padding: 30px;
            border: 1px solid rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }}
        .card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, transparent, rgba(251, 191, 36, 0.5), transparent);
            opacity: 0;
            transition: opacity 0.3s;
        }}
        .card:hover {{
            transform: translateY(-8px);
            box-shadow: 0 25px 50px rgba(0,0,0,0.4);
            border-color: rgba(251, 191, 36, 0.3);
        }}
        .card:hover::before {{
            opacity: 1;
        }}
        
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .stock-info h2 {{
            font-size: 1.5em;
            margin-bottom: 5px;
        }}
        .stock-symbol {{
            color: #6b7280;
            font-size: 0.9em;
        }}
        
        .rating-badge {{
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: bold;
            font-size: 1em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .score-display {{
            text-align: center;
            padding: 25px;
            background: rgba(255,255,255,0.03);
            border-radius: 16px;
            margin-bottom: 25px;
        }}
        .score-number {{
            font-size: 4em;
            font-weight: bold;
            background: linear-gradient(180deg, #fbbf24, #f59e0b);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            line-height: 1;
        }}
        .score-label {{
            color: #9ca3af;
            margin-top: 10px;
            font-size: 1.1em;
        }}
        
        .dimensions-grid {{
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }}
        .dimension-item {{
            text-align: center;
            padding: 15px 10px;
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            position: relative;
        }}
        .dimension-label {{
            font-size: 0.75em;
            color: #9ca3af;
            margin-bottom: 8px;
        }}
        .dimension-score {{
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .dimension-grade {{
            font-size: 1.5em;
            font-weight: bold;
            padding: 5px 10px;
            border-radius: 8px;
            display: inline-block;
            min-width: 40px;
        }}
        .grade-A {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
        .grade-B {{ background: rgba(132, 204, 22, 0.2); color: #84cc16; }}
        .grade-C {{ background: rgba(234, 179, 8, 0.2); color: #eab308; }}
        .grade-D {{ background: rgba(249, 115, 22, 0.2); color: #f97316; }}
        .grade-F {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
        
        .data-section {{
            margin-bottom: 25px;
        }}
        .section-title {{
            font-size: 0.95em;
            color: #fbbf24;
            margin-bottom: 15px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(251, 191, 36, 0.3);
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }}
        .metric-item {{
            padding: 12px;
            background: rgba(255,255,255,0.02);
            border-radius: 10px;
            text-align: center;
        }}
        .metric-label {{
            font-size: 0.75em;
            color: #9ca3af;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 1.2em;
            font-weight: bold;
            color: #e4e4e4;
        }}
        .metric-value.positive {{ color: #22c55e; }}
        .metric-value.negative {{ color: #ef4444; }}
        
        .reasons-container {{
            padding: 15px;
            background: rgba(251, 191, 36, 0.08);
            border-left: 4px solid #fbbf24;
            border-radius: 0 12px 12px 0;
            margin-bottom: 20px;
        }}
        .reason-tag {{
            display: inline-block;
            padding: 8px 14px;
            margin: 4px;
            background: rgba(251, 191, 36, 0.15);
            border: 1px solid rgba(251, 191, 36, 0.3);
            border-radius: 8px;
            font-size: 0.85em;
            color: #fbbf24;
        }}
        
        .action-box {{
            padding: 20px;
            background: linear-gradient(135deg, rgba(251, 191, 36, 0.1) 0%, rgba(245, 158, 11, 0.05) 100%);
            border: 1px solid rgba(251, 191, 36, 0.3);
            border-radius: 12px;
            text-align: center;
        }}
        .action-label {{
            color: #9ca3af;
            font-size: 0.9em;
            margin-bottom: 8px;
        }}
        .action-value {{
            font-size: 1.4em;
            font-weight: bold;
            color: #fbbf24;
        }}
        
        .chart-container {{ height: 180px; margin-top: 20px; }}
        
        footer {{
            text-align: center;
            padding: 40px;
            color: #6b7280;
            border-top: 1px solid rgba(255,255,255,0.1);
            margin-top: 40px;
        }}
        
        .legend {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 15px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85em;
            color: #9ca3af;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🥔 港股监控看板 · 专业机构版</h1>
            <p class="subtitle">五大维度综合分析 | 长桥 API 实时数据 | 华尔街评级体系</p>
            <div class="update-badge">📅 更新时间：{update_time}</div>
            <div class="legend">
                <div class="legend-item"><span class="legend-dot" style="background:#22c55e"></span>估值 30%</div>
                <div class="legend-item"><span class="legend-dot" style="background:#84cc16"></span>成长 25%</div>
                <div class="legend-item"><span class="legend-dot" style="background:#eab308"></span>质量 20%</div>
                <div class="legend-item"><span class="legend-dot" style="background:#f97316"></span>情绪 15%</div>
                <div class="legend-item"><span class="legend-dot" style="background:#ef4444"></span>技术 10%</div>
            </div>
        </header>
        
        <div class="grid" id="stockGrid"></div>
        
        <footer>
            <p>薯片 (Chip) 出品 | 数据来自长桥 OpenAPI | 因子引擎 v3</p>
            <p style="margin-top:10px;font-size:0.85em">⚠️ 仅供参考，不构成投资建议</p>
        </footer>
    </div>
    
    <script>
        const stocks = {stocks_json};
        
        function renderDashboard() {{
            const grid = document.getElementById('stockGrid');
            grid.innerHTML = stocks.map(stock => renderCard(stock)).join('');
            setTimeout(() => {{
                stocks.forEach(stock => createChart(stock));
            }}, 100);
        }}
        
        function getScoreColor(score) {{
            if (score >= 80) return '#22c55e';
            if (score >= 60) return '#84cc16';
            if (score >= 40) return '#eab308';
            if (score >= 20) return '#f97316';
            return '#ef4444';
        }}
        
        function renderCard(stock) {{
            const d = stock.dimensions;
            const f = stock.fundamentals || {{}};
            const t = stock.technical || {{}};
            const p = stock.price_data || {{}};
            
            return `
                <div class="card">
                    <div class="card-header">
                        <div class="stock-info">
                            <h2>${{stock.name}}</h2>
                            <div class="stock-symbol">${{stock.symbol}}</div>
                        </div>
                        <span class="rating-badge" style="background: ${{stock.rating_color}}; color: #000;">
                            ${{stock.rating}}
                        </span>
                    </div>
                    
                    <div class="score-display">
                        <div class="score-number" style="color: ${{getScoreColor(stock.total_score)}}">${{stock.total_score}}</div>
                        <div class="score-label">综合评分 / 100</div>
                        <div style="margin-top:15px;font-size:1.1em;color:#fbbf24">💡 ${{stock.action}}</div>
                    </div>
                    
                    <div class="dimensions-grid">
                        <div class="dimension-item">
                            <div class="dimension-label">💰 估值</div>
                            <div class="dimension-score" style="color:${{getScoreColor(d.valuation.score)}}">${{d.valuation.score}}</div>
                            <div class="dimension-grade grade-${{d.valuation.grade}}">${{d.valuation.grade}}</div>
                        </div>
                        <div class="dimension-item">
                            <div class="dimension-label">📈 成长</div>
                            <div class="dimension-score" style="color:${{getScoreColor(d.growth.score)}}">${{d.growth.score}}</div>
                            <div class="dimension-grade grade-${{d.growth.grade}}">${{d.growth.grade}}</div>
                        </div>
                        <div class="dimension-item">
                            <div class="dimension-label">💎 质量</div>
                            <div class="dimension-score" style="color:${{getScoreColor(d.quality.score)}}">${{d.quality.score}}</div>
                            <div class="dimension-grade grade-${{d.quality.grade}}">${{d.quality.grade}}</div>
                        </div>
                        <div class="dimension-item">
                            <div class="dimension-label">🎯 情绪</div>
                            <div class="dimension-score" style="color:${{getScoreColor(d.sentiment.score)}}">${{d.sentiment.score}}</div>
                            <div class="dimension-grade grade-${{d.sentiment.grade}}">${{d.sentiment.grade}}</div>
                        </div>
                        <div class="dimension-item">
                            <div class="dimension-label">📊 技术</div>
                            <div class="dimension-score" style="color:${{getScoreColor(d.technical.score)}}">${{d.technical.score}}</div>
                            <div class="dimension-grade grade-${{d.technical.grade}}">${{d.technical.grade}}</div>
                        </div>
                    </div>
                    
                    <div class="data-section">
                        <div class="section-title">📈 基本面指标</div>
                        <div class="metrics-grid">
                            <div class="metric-item">
                                <div class="metric-label">PE (TTM)</div>
                                <div class="metric-value">${{f.pe_ttm !== null ? f.pe_ttm : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">PB</div>
                                <div class="metric-value">${{f.pb !== null ? f.pb : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">ROE</div>
                                <div class="metric-value">${{f.roe !== null ? f.roe+'%' : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">股息率</div>
                                <div class="metric-value">${{f.dividend_yield !== null ? f.dividend_yield+'%' : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">EPS</div>
                                <div class="metric-value">${{f.eps_ttm !== null ? f.eps_ttm : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">BPS</div>
                                <div class="metric-value">${{f.bps !== null ? f.bps : 'N/A'}}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="data-section">
                        <div class="section-title">📊 技术指标</div>
                        <div class="metrics-grid">
                            <div class="metric-item">
                                <div class="metric-label">RSI (14)</div>
                                <div class="metric-value ${{t.rsi < 30 ? 'positive' : t.rsi > 70 ? 'negative' : ''}}">${{t.rsi !== undefined ? t.rsi : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">MA(10)</div>
                                <div class="metric-value">${{t.ma_fast !== undefined ? t.ma_fast : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">MA(30)</div>
                                <div class="metric-value">${{t.ma_slow !== undefined ? t.ma_slow : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">MACD</div>
                                <div class="metric-value ${{t.macd > t.macd_signal ? 'positive' : 'negative'}}">${{t.macd !== undefined ? t.macd.toFixed(4) : 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">信号</div>
                                <div class="metric-value ${{t.signal === '金叉' ? 'positive' : 'negative'}}">${{t.signal || 'N/A'}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">ATR (波动)</div>
                                <div class="metric-value">${{t.atr !== undefined ? t.atr : 'N/A'}}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="data-section">
                        <div class="section-title">📉 52 周位置</div>
                        <div class="metrics-grid">
                            <div class="metric-item">
                                <div class="metric-label">现价</div>
                                <div class="metric-value">HK$ ${{p.current}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">52 周高</div>
                                <div class="metric-value negative">${{p.high_52w}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">52 周低</div>
                                <div class="metric-value positive">${{p.low_52w}}</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">距高点</div>
                                <div class="metric-value negative">${{p.pct_from_high}}%</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">距低点</div>
                                <div class="metric-value positive">${{p.pct_from_low}}%</div>
                            </div>
                            <div class="metric-item">
                                <div class="metric-label">位置</div>
                                <div class="metric-value">${{((p.current - p.low_52w) / (p.high_52w - p.low_52w) * 100).toFixed(0)}}%</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="reasons-container">
                        <div style="margin-bottom:10px;color:#fbbf24;font-weight:bold">💡 投资理由</div>
                        ${{stock.reasons.map(r => `<span class="reason-tag">${{r}}</span>`).join('')}}
                    </div>
                    
                    <div class="chart-container">
                        <canvas id="chart-${{stock.symbol}}"></canvas>
                    </div>
                </div>
            `;
        }}
        
        function createChart(stock) {{
            const ctx = document.getElementById(`chart-${{stock.symbol}}`);
            if (!ctx) return;
            
            const labels = stock.price_history.map(d => d.date.slice(5));
            const prices = stock.price_history.map(d => d.close);
            
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: '收盘价',
                        data: prices,
                        borderColor: stock.price_data.pct_from_high >= -20 ? '#22c55e' : '#ef4444',
                        backgroundColor: stock.price_data.pct_from_high >= -20 ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 2,
                        pointHoverRadius: 5
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{
                            display: true,
                            grid: {{ color: 'rgba(255,255,255,0.05)' }},
                            ticks: {{ color: '#9ca3af', maxTicksLimit: 6 }}
                        }},
                        y: {{
                            display: true,
                            grid: {{ color: 'rgba(255,255,255,0.05)' }},
                            ticks: {{ color: '#9ca3af' }}
                        }}
                    }}
                }}
            }});
        }}
        
        renderDashboard();
    </script>
</body>
</html>'''
    
    return html

def main():
    print("=" * 70)
    print("生成港股监控看板 (专业机构版)")
    print("=" * 70)
    
    stocks_data = []
    
    for symbol, name in MONITOR_STOCKS.items():
        print(f"\n处理 {symbol} ({name})...")
        
        df = get_stock_data(symbol)
        if df is None:
            continue
        
        current_price = df['close'].iloc[-1]
        analysis = generate_comprehensive_analysis(symbol, name, df, current_price)
        
        # 添加股票基本信息
        analysis['symbol'] = symbol
        analysis['name'] = name
        
        # 添加价格历史
        recent_df = df.tail(30)
        analysis['price_history'] = [
            {'date': str(idx)[:10], 'close': round(d['close'], 2)}
            for idx, d in recent_df.iterrows()
        ]
        
        stocks_data.append(analysis)
        
        d = analysis['dimensions']
        print(f"  综合：{analysis['total_score']} | {analysis['rating']} | {analysis['action']}")
        print(f"  维度：估={d['valuation']['score']:>3} 成={d['growth']['score']:>3} 质={d['quality']['score']:>3} 情={d['sentiment']['score']:>3} 技={d['technical']['score']:>3}")
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = generate_html(stocks_data, update_time)
    
    output_path = '/home/venger/projects/ricequant/港股监控看板.html'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ 看板已生成：{output_path}")
    print(f"   共 {len(stocks_data)} 只股票")
    print(f"   更新时间：{update_time}")
    
    # 保存 JSON 数据
    json_path = '/home/venger/projects/ricequant/dashboard_data.json'
    stocks_serializable = convert_to_serializable({'update_time': update_time, 'stocks': stocks_data})
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(stocks_serializable, f, indent=2, ensure_ascii=False)
    print(f"   数据已保存：{json_path}")
    
    # 归档到 data_archive (按日期)
    archive_dir = Path('/home/venger/projects/ricequant/data_archive')
    archive_dir.mkdir(exist_ok=True)
    month_dir = archive_dir / datetime.now().strftime('%Y-%m')
    month_dir.mkdir(exist_ok=True)
    
    archive_path = month_dir / f"{datetime.now().strftime('%Y-%m-%d')}_hk.json"
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(stocks_serializable, f, indent=2, ensure_ascii=False)
    print(f"   已归档：{archive_path}")

if __name__ == '__main__':
    main()
