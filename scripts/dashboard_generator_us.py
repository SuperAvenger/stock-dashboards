#!/usr/bin/env python3
"""
美股监控看板生成器
基于《打开量化投资的黑箱》框架
数据源优先级：长桥 API → Yahoo Finance → 默认值
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

# 使用相对路径（适配 GitHub Actions）
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from factor_engine_us import USStockFactorEngine, US_STOCKS

def generate_html(stocks_data, update_time):
    """生成 HTML 看板"""
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🇺🇸 美股监控看板 - 专业机构版</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #0a0a2e 0%, #1a1a4e 100%);
            min-height: 100vh;
            color: #e4e4e4;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; padding: 20px; }}
        
        header {{
            text-align: center;
            padding: 40px 0;
            border-bottom: 2px solid rgba(59, 130, 246, 0.3);
            margin-bottom: 40px;
            background: rgba(59, 130, 246, 0.05);
            border-radius: 16px;
        }}
        header h1 {{
            font-size: 2.8em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #60a5fa, #3b82f6, #60a5fa);
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
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            border-radius: 20px;
            margin-top: 15px;
            color: #60a5fa;
            font-size: 0.9em;
        }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(480px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .card {{
            background: linear-gradient(145deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%);
            border-radius: 20px;
            padding: 25px;
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
            background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.5), transparent);
            opacity: 0;
            transition: opacity 0.3s;
        }}
        .card:hover {{
            transform: translateY(-8px);
            box-shadow: 0 25px 50px rgba(0,0,0,0.4);
            border-color: rgba(59, 130, 246, 0.3);
        }}
        .card:hover::before {{
            opacity: 1;
        }}
        
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .stock-info h2 {{
            font-size: 1.4em;
            margin-bottom: 5px;
        }}
        .stock-info .symbol {{
            color: #9ca3af;
            font-size: 0.9em;
        }}
        .signal-badge {{
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .signal-strong-buy {{ background: linear-gradient(135deg, #10b981, #059669); color: white; }}
        .signal-buy {{ background: linear-gradient(135deg, #34d399, #10b981); color: white; }}
        .signal-hold {{ background: linear-gradient(135deg, #fbbf24, #f59e0b); color: white; }}
        .signal-reduce {{ background: linear-gradient(135deg, #fb923c, #f97316); color: white; }}
        .signal-sell {{ background: linear-gradient(135deg, #ef4444, #dc2626); color: white; }}
        
        .score-display {{
            text-align: center;
            margin: 20px 0;
        }}
        .score-number {{
            font-size: 3em;
            font-weight: 700;
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .score-label {{
            color: #9ca3af;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        
        .dimensions {{
            margin-top: 20px;
        }}
        .dimension-item {{
            display: flex;
            align-items: center;
            margin-bottom: 12px;
        }}
        .dimension-name {{
            width: 80px;
            font-size: 0.9em;
            color: #d1d5db;
        }}
        .dimension-bar {{
            flex: 1;
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 0 12px;
        }}
        .dimension-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }}
        .dimension-value {{
            width: 40px;
            text-align: right;
            font-size: 0.85em;
            color: #9ca3af;
        }}
        
        .price-info {{
            display: flex;
            justify-content: space-between;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }}
        .price-item {{
            text-align: center;
        }}
        .price-value {{
            font-size: 1.3em;
            font-weight: 600;
            color: #60a5fa;
        }}
        .price-label {{
            font-size: 0.75em;
            color: #6b7280;
            margin-top: 3px;
        }}
        
        .action-recommendation {{
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.2);
            border-radius: 12px;
            padding: 15px;
            margin-top: 15px;
            text-align: center;
        }}
        .action-text {{
            font-size: 1.1em;
            font-weight: 600;
            color: #60a5fa;
        }}
        .reasons-list {{
            font-size: 0.85em;
            color: #9ca3af;
            margin-top: 8px;
            line-height: 1.5;
        }}
        
        .details-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 15px;
        }}
        
        .detail-section {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 12px;
        }}
        .detail-section h3 {{
            font-size: 0.9em;
            color: #60a5fa;
            margin-bottom: 10px;
        }}
        
        .detail-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
        }}
        .detail-item {{
            display: flex;
            flex-direction: column;
            padding: 6px;
            background: rgba(255,255,255,0.02);
            border-radius: 6px;
        }}
        .detail-label {{
            font-size: 0.75em;
            color: #6b7280;
            margin-bottom: 3px;
        }}
        .detail-value {{
            font-size: 0.9em;
            color: #e4e4e4;
            font-weight: 600;
        }}
        
        .week52-container {{
            padding: 10px;
        }}
        .week52-bar {{
            position: relative;
            height: 6px;
            background: linear-gradient(90deg, #ef4444 0%, #fbbf24 50%, #10b981 100%);
            border-radius: 3px;
            margin-bottom: 8px;
        }}
        .week52-marker {{
            position: absolute;
            width: 3px;
            height: 14px;
            background: #fff;
            border: 2px solid #3b82f6;
            border-radius: 2px;
            top: -4px;
            transform: translateX(-50%);
        }}
        .week52-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 0.75em;
            color: #9ca3af;
        }}
        .week52-low, .week52-high {{
            text-align: center;
        }}
        .week52-current {{
            text-align: center;
            font-weight: 600;
            color: #60a5fa;
        }}
        .week52-position {{
            text-align: center;
            font-size: 0.8em;
            color: #6b7280;
            margin-top: 5px;
        }}
        
        .chart-container {{
            height: 200px;
            margin-top: 20px;
        }}
        
        footer {{
            text-align: center;
            padding: 30px;
            color: #6b7280;
            font-size: 0.85em;
            border-top: 1px solid rgba(255,255,255,0.1);
            margin-top: 40px;
        }}
        
        .data-source {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 10px;
            font-size: 0.75em;
            margin-left: 8px;
        }}
        .source-longbridge {{ background: rgba(16, 185, 129, 0.2); color: #10b981; }}
        .source-yahoo {{ background: rgba(99, 102, 241, 0.2); color: #818cf7; }}
        .source-default {{ background: rgba(107, 114, 128, 0.2); color: #9ca3af; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🇺🇸 美股监控看板</h1>
            <p class="subtitle">基于《打开量化投资的黑箱》因子框架</p>
            <div class="update-badge">📅 更新时间：{update_time}</div>
        </header>
        
        <div class="grid">
'''
    
    for stock in stocks_data:
        symbol = stock['symbol']
        name = stock['name']
        score = stock['total_score']
        signal = stock['signal']
        action = stock['action']
        price = stock['current_price']
        dimensions = stock['dimensions']
        data_source = dimensions.get('value', {}).get('source', 'Unknown')
        
        # 信号样式
        signal_class = {
            '强烈买入': 'signal-strong-buy',
            '买入': 'signal-buy',
            '持有': 'signal-hold',
            '减持': 'signal-reduce',
            '卖出': 'signal-sell',
        }.get(signal, 'signal-hold')
        
        # 分数颜色
        if score >= 70:
            score_color = '#10b981'
        elif score >= 55:
            score_color = '#34d399'
        elif score >= 40:
            score_color = '#fbbf24'
        elif score >= 25:
            score_color = '#fb923c'
        else:
            score_color = '#ef4444'
        
        # 维度颜色
        def get_dim_color(val):
            if val >= 70: return '#10b981'
            elif val >= 50: return '#3b82f6'
            elif val >= 30: return '#fbbf24'
            else: return '#ef4444'
        
        # 数据源样式
        source_class = {
            'Longbridge': 'source-longbridge',
            'Yahoo Finance': 'source-yahoo',
            'Default': 'source-default',
        }.get(data_source, 'source-default')
        
        html += f'''
            <div class="card">
                <div class="card-header">
                    <div class="stock-info">
                        <h2>{name}</h2>
                        <span class="symbol">{symbol}</span>
                        <span class="data-source {source_class}">{data_source}</span>
                    </div>
                    <span class="signal-badge {signal_class}">{signal}</span>
                </div>
                
                <div class="score-display">
                    <div class="score-number" style="color: {score_color}">{score}</div>
                    <div class="score-label">综合评分</div>
                </div>
                
                <div class="dimensions">
                    <div class="dimension-item">
                        <span class="dimension-name">📈 动量</span>
                        <div class="dimension-bar">
                            <div class="dimension-fill" style="width: {dimensions['momentum']['score']}%; background: {get_dim_color(dimensions['momentum']['score'])}"></div>
                        </div>
                        <span class="dimension-value">{dimensions['momentum']['score']}</span>
                    </div>
                    <div class="dimension-item">
                        <span class="dimension-name">💰 价值</span>
                        <div class="dimension-bar">
                            <div class="dimension-fill" style="width: {dimensions['value']['score']}%; background: {get_dim_color(dimensions['value']['score'])}"></div>
                        </div>
                        <span class="dimension-value">{dimensions['value']['score']}</span>
                    </div>
                    <div class="dimension-item">
                        <span class="dimension-name">🚀 成长</span>
                        <div class="dimension-bar">
                            <div class="dimension-fill" style="width: {dimensions['growth']['score']}%; background: {get_dim_color(dimensions['growth']['score'])}"></div>
                        </div>
                        <span class="dimension-value">{dimensions['growth']['score']}</span>
                    </div>
                    <div class="dimension-item">
                        <span class="dimension-name">💎 质量</span>
                        <div class="dimension-bar">
                            <div class="dimension-fill" style="width: {dimensions['quality']['score']}%; background: {get_dim_color(dimensions['quality']['score'])}"></div>
                        </div>
                        <span class="dimension-value">{dimensions['quality']['score']}</span>
                    </div>
                    <div class="dimension-item">
                        <span class="dimension-name">😊 情绪</span>
                        <div class="dimension-bar">
                            <div class="dimension-fill" style="width: {dimensions['sentiment']['score']}%; background: {get_dim_color(dimensions['sentiment']['score'])}"></div>
                        </div>
                        <span class="dimension-value">{dimensions['sentiment']['score']}</span>
                    </div>
                </div>
                
                <div class="details-grid">
                    <div class="detail-section">
                        <h3>📊 基本面指标</h3>
                        <div class="detail-grid">
                            <div class="detail-item">
                                <span class="detail-label">PE(TTM)</span>
                                <span class="detail-value">{stock['fundamentals']['pe_ttm']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">PB</span>
                                <span class="detail-value">{stock['fundamentals']['pb']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">ROE</span>
                                <span class="detail-value">{stock['fundamentals']['roe']}%</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">股息率</span>
                                <span class="detail-value">{stock['fundamentals']['dividend_yield']}%</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">EPS</span>
                                <span class="detail-value">${stock['fundamentals']['eps']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">BPS</span>
                                <span class="detail-value">${stock['fundamentals']['bps']}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="detail-section">
                        <h3>📈 技术指标</h3>
                        <div class="detail-grid">
                            <div class="detail-item">
                                <span class="detail-label">RSI(14)</span>
                                <span class="detail-value" style="color: {'#10b981' if stock['technical']['rsi_14'] < 30 else '#ef4444' if stock['technical']['rsi_14'] > 70 else '#9ca3af'}">{stock['technical']['rsi_14']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">MA(10)</span>
                                <span class="detail-value">${stock['technical']['ma_10']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">MA(30)</span>
                                <span class="detail-value">${stock['technical']['ma_30']}</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">MACD</span>
                                <span class="detail-value" style="color: {'#10b981' if stock['technical']['macd_histogram'] > 0 else '#ef4444'}">{stock['technical']['macd_histogram']:.4f} ({stock['technical']['macd_status']})</span>
                            </div>
                            <div class="detail-item">
                                <span class="detail-label">ATR(波动)</span>
                                <span class="detail-value">{stock['technical']['atr']}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="detail-section">
                        <h3>📉 52 周位置</h3>
                        <div class="week52-container">
                            <div class="week52-bar">
                                <div class="week52-marker" style="left: {stock['week52']['position']}%"></div>
                            </div>
                            <div class="week52-labels">
                                <span class="week52-low">${stock['week52']['low']}<br/>({stock['week52']['pct_from_low']:+.1f}%)</span>
                                <span class="week52-current">${stock['week52']['current_price']}</span>
                                <span class="week52-high">${stock['week52']['high']}<br/>({stock['week52']['pct_from_high']:+.1f}%)</span>
                            </div>
                            <div class="week52-position">位置 {stock['week52']['position']:.1f}%</div>
                        </div>
                    </div>
                </div>
                
                <div class="action-recommendation">
                    <div class="action-text">💡 {action}</div>
                    <div class="reasons-list">
                        {' | '.join(stock['reasons'])}
                    </div>
                </div>
                
                <div class="chart-container">
                    <canvas id="chart-{symbol.replace('.', '_')}"></canvas>
                </div>
            </div>
'''
    
    # 添加 JavaScript 图表
    html += '''
        </div>
        
        <footer>
            <p>🥔 美股监控看板 v1.0 | 基于《打开量化投资的黑箱》因子框架</p>
            <p>数据源优先级：长桥 API → Yahoo Finance → 默认值</p>
            <p>因子权重：动量 25% | 价值 20% | 成长 20% | 质量 20% | 情绪 15%</p>
        </footer>
    </div>
    
    <script>
        const stocksData = ''' + json.dumps(stocks_data) + ''';
        
        function renderCharts() {
            stocksData.forEach(stock => {
                const ctx = document.getElementById(`chart-${stock.symbol.replace('.', '_')}`);
                if (!ctx) return;
                
                // 获取价格历史 (如果有)
                const labels = stock.price_history ? stock.price_history.map(d => d.date.slice(5)) : [];
                const prices = stock.price_history ? stock.price_history.map(d => d.close) : [];
                
                if (prices.length === 0) {
                    ctx.parentElement.style.display = 'none';
                    return;
                }
                
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: '收盘价',
                            data: prices,
                            borderColor: stock.total_score >= 55 ? '#3b82f6' : '#ef4444',
                            backgroundColor: stock.total_score >= 55 ? 'rgba(59, 130, 246, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 2,
                            pointHoverRadius: 5
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            x: {
                                display: true,
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: '#9ca3af', maxTicksLimit: 6 }
                            },
                            y: {
                                display: true,
                                grid: { color: 'rgba(255,255,255,0.05)' },
                                ticks: { color: '#9ca3af' }
                            }
                        }
                    }
                });
            });
        }
        
        renderCharts();
    </script>
</body>
</html>'''
    
    return html


def main():
    print("=" * 70)
    print("🇺🇸 生成美股监控看板")
    print("=" * 70)
    
    stocks_data = []
    
    for symbol, name in US_STOCKS.items():
        print(f"\n分析 {symbol} ({name})...")
        
        engine = USStockFactorEngine(symbol)
        result = engine.calculate_all_factors()
        
        if result:
            # 添加股票基本信息
            result['symbol'] = symbol
            result['name'] = name
            
            # 获取价格历史 (用于图表)
            if engine.df is not None:
                recent_df = engine.df.tail(30)
                result['price_history'] = [
                    {'date': str(idx)[:10], 'close': round(row['close'], 2)}
                    for idx, row in recent_df.iterrows()
                ]
            
            stocks_data.append(result)
            
            d = result['dimensions']
            print(f"  综合：{result['total_score']} | {result['signal']} | {result['action']}")
            print(f"  维度：动={d['momentum']['score']:>3} 价={d['value']['score']:>3} 成={d['growth']['score']:>3} 质={d['quality']['score']:>3} 情={d['sentiment']['score']:>3}")
            print(f"  数据源：{d['value']['details'].get('source', 'Unknown')}")
    
    update_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    html_content = generate_html(stocks_data, update_time)
    
    # 动态输出路径：GitHub Actions 输出到 ./output/，本地保持原路径
    if os.environ.get('GITHUB_ACTIONS'):
        output_dir = Path(__file__).parent.parent / 'output'
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / 'us-dashboard.html'
        json_path = output_dir / 'us-data.json'
    else:
        output_path = '/home/venger/projects/us_stocks_monitor/美股监控看板.html'
        json_path = '/home/venger/projects/us_stocks_monitor/dashboard_data.json'
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"\n✅ 看板已生成：{output_path}")
    print(f"   共 {len(stocks_data)} 只股票")
    print(f"   更新时间：{update_time}")
    
    # 保存 JSON 数据
    stocks_serializable = convert_to_serializable({'update_time': update_time, 'stocks': stocks_data})
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(stocks_serializable, f, indent=2, ensure_ascii=False)
    print(f"   数据已保存：{json_path}")
    
    # 归档到 data_archive (按日期，仅本地环境)
    if not os.environ.get('GITHUB_ACTIONS'):
        archive_dir = Path('/home/venger/projects/us_stocks_monitor/data_archive')
    archive_dir.mkdir(exist_ok=True)
    month_dir = archive_dir / datetime.now().strftime('%Y-%m')
    month_dir.mkdir(exist_ok=True)
    
    archive_path = month_dir / f"{datetime.now().strftime('%Y-%m-%d')}_us.json"
    with open(archive_path, 'w', encoding='utf-8') as f:
        json.dump(stocks_serializable, f, indent=2, ensure_ascii=False)
    print(f"   已归档：{archive_path}")


if __name__ == '__main__':
    main()
