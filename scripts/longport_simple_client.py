#!/usr/bin/env python3
"""
长桥简易客户端 - 修复 K 线获取问题
支持环境变量（GitHub Secrets）和本地配置文件
"""

import os
from pathlib import Path
from longport.openapi import Config, QuoteContext, Period

# 配置文件路径（本地开发用）
SCRIPT_DIR = Path(__file__).parent
LOCAL_CONFIG = SCRIPT_DIR.parent / 'config' / 'longbridge.conf'

def load_config():
    """优先从环境变量读取，其次读取本地配置文件"""
    config = {}
    
    # 1. 优先使用环境变量（GitHub Secrets）
    if os.environ.get('LONGPORT_APP_KEY'):
        config['APP_KEY'] = os.environ.get('LONGPORT_APP_KEY', '')
        config['APP_SECRET'] = os.environ.get('LONGPORT_APP_SECRET', '')
        config['ACCESS_TOKEN'] = os.environ.get('LONGPORT_ACCESS_TOKEN', '')
        return config
    
    # 2. 读取本地配置文件
    if LOCAL_CONFIG.exists():
        with open(LOCAL_CONFIG, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    config[line.split('=')[0].strip()] = line.split('=')[1].strip()
    
    return config

def get_kline(symbol='9988.HK', count=400, include_extended=False):
    """
    获取 K 线数据
    
    Args:
        symbol: 股票代码
        count: K 线数量
        include_extended: 是否包含扩展字段 (PE/PB/换手率等)
    """
    config = load_config()
    
    cfg = Config(
        app_key=config.get('APP_KEY', ''),
        app_secret=config.get('APP_SECRET', ''),
        access_token=config.get('ACCESS_TOKEN', '')
    )
    
    try:
        quote_ctx = QuoteContext(cfg)
        
        # 方式 2: 指定调整类型 (最稳定)
        from longport.openapi import AdjustType
        kline = quote_ctx.candlesticks(symbol, Period.Day, count, AdjustType.NoAdjust)
        
        if not kline:
            return None
        
        if include_extended:
            # 获取扩展数据
            try:
                quote = quote_ctx.quote([symbol])
                if quote:
                    q = quote[0]
                    # 为每根 K 线添加扩展字段
                    result = []
                    for c in kline:
                        result.append({
                            'timestamp': c.timestamp,
                            'open': float(c.open),
                            'high': float(c.high),
                            'low': float(c.low),
                            'close': float(c.close),
                            'volume': float(c.volume),
                            'turnover': float(getattr(q, 'turnover', 0)),  # 成交额
                            'pe_ttm': float(getattr(q, 'pe_ttm', 0)),      # 市盈率
                            'pb': float(getattr(q, 'pb', 0)),              # 市净率
                            'ps_ttm': float(getattr(q, 'ps_ttm', 0)),      # 市销率
                            'dividend_yield': float(getattr(q, 'dividend_yield', 0)),  # 股息率
                            'change_percent': float(getattr(q, 'change_percent', 0)),  # 涨跌幅
                            'turnover_rate': float(getattr(q, 'turnover_rate', 0)),    # 换手率
                        })
                    return result
            except Exception as e:
                print(f"⚠️ 获取扩展字段失败：{e}, 使用基础字段")
        
        return list(kline)
        
    except Exception as e:
        print(f"❌ 连接失败：{e}")
        return None

if __name__ == '__main__':
    print("=" * 60)
    print("长桥 K 线获取测试")
    print("=" * 60)
    
    kline = get_kline('9988.HK', 400)
    
    if kline:
        print(f"\n获取到 {len(kline)} 条 K 线")
        print(f"第一条：{kline[0]}")
        print(f"最后一条：{kline[-1]}")
    else:
        print("\n❌ 获取失败")
    
    print("=" * 60)
