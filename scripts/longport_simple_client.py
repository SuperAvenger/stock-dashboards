#!/usr/bin/env python3
"""
长桥简易客户端 - 纯 HTTP 版 (绕过 SDK 签名问题)
直接调用长桥 REST API, 不依赖 longport SDK
"""

import os
import json
import time
import hmac
import hashlib
import base64
from pathlib import Path
from datetime import datetime

import requests

SCRIPT_DIR = Path(__file__).parent
LOCAL_CONFIG = SCRIPT_DIR.parent / 'config' / 'longbridge.conf'

API_BASE = "https://openapi.longportapp.com"


def load_config():
    """优先从环境变量读取，其次读取本地配置文件"""
    config = {}

    if os.environ.get('LONGPORT_APP_KEY'):
        config['APP_KEY'] = os.environ.get('LONGPORT_APP_KEY', '')
        config['APP_SECRET'] = os.environ.get('LONGPORT_APP_SECRET', '')
        config['ACCESS_TOKEN'] = os.environ.get('LONGPORT_ACCESS_TOKEN', '')
        return config

    if LOCAL_CONFIG.exists():
        with open(LOCAL_CONFIG, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    config[key.strip()] = val.strip()

    return config


def _sign_request(method, path, body, timestamp, app_secret):
    """生成请求签名"""
    # 长桥签名格式: method + path + body + timestamp
    msg = f"{method}\n{path}\n{body}\n{timestamp}"
    sig = hmac.new(
        app_secret.encode('utf-8'),
        msg.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(sig).decode('utf-8')


def _api_request(method, path, params=None, config=None):
    """发起 API 请求"""
    if config is None:
        config = load_config()

    url = f"{API_BASE}{path}"
    timestamp = str(int(time.time()))

    headers = {
        'Authorization': f'Bearer {config["ACCESS_TOKEN"]}',
        'Content-Type': 'application/json',
        'X-App-Key': config['APP_KEY'],
        'X-Timestamp': timestamp,
    }

    body = json.dumps(params) if params else ""

    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        else:
            resp = requests.post(url, headers=headers, data=body, timeout=15)

        if resp.status_code != 200:
            print(f"API Error {resp.status_code}: {resp.text[:200]}")
            return None

        data = resp.json()
        if data.get('code') != 0:
            print(f"API Error: {data.get('message', 'unknown')} (code={data.get('code')})")
            return None

        return data.get('data')

    except Exception as e:
        print(f"Request failed: {e}")
        return None


_quote_context = None


def get_quote_context():
    """Reuse an authenticated SDK context; current SDK uses a config factory."""
    global _quote_context
    if _quote_context is None:
        from longport.openapi import Config, QuoteContext
        config = load_config()
        factory = getattr(Config, 'from_apikey', Config)
        cfg = factory(
            app_key=config.get('APP_KEY', ''),
            app_secret=config.get('APP_SECRET', ''),
            access_token=config.get('ACCESS_TOKEN', ''),
        )
        _quote_context = QuoteContext(cfg)
    return _quote_context


def normalize_symbol(symbol):
    if symbol.endswith('.HK'):
        return symbol.lstrip('0')
    return symbol if '.' in symbol else symbol + '.US'


def get_kline(symbol='9988.HK', count=200):
    """Fetch typed candles through the SDK, avoiding the retired REST endpoint."""
    from longport.openapi import Period, AdjustType
    candles = get_quote_context().candlesticks(
        normalize_symbol(symbol), Period.Day, count, AdjustType.NoAdjust
    )
    if not candles:
        raise RuntimeError(f'No candlesticks returned for {symbol}')
    return list(candles)


def get_quote(symbol):
    """获取实时行情"""
    code = symbol.lstrip('0')
    data = _api_request('GET', '/quote/v1/quote', {'symbol': code})
    if data and 'quote' in data:
        q = data['quote'][0] if isinstance(data['quote'], list) else data['quote']
        return {
            'symbol': symbol,
            'last_done': float(q.get('last_done', 0)),
            'prev_close': float(q.get('prev_close', 0)),
            'change': float(q.get('change', 0)),
            'change_percent': float(q.get('change_percent', 0)),
            'volume': float(q.get('volume', 0)),
            'turnover': float(q.get('turnover', 0)),
            'pe_ttm': float(q.get('pe_ttm', 0)),
            'pb': float(q.get('pb', 0)),
            'dividend_yield': float(q.get('dividend_yield', 0)),
            'high_52w': float(q.get('high_price_52w', 0)),
            'low_52w': float(q.get('low_price_52w', 0)),
        }
    return None


if __name__ == '__main__':
    print("=" * 60)
    print("长桥 K 线获取测试 (HTTP)")
    print("=" * 60)

    kline = get_kline('9988.HK', 10)
    if kline:
        print(f"获取到 {len(kline)} 条 K 线")
        for k in kline[-3:]:
            print(f"  {k}")
    else:
        print("获取失败")
