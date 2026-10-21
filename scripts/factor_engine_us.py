#!/usr/bin/env python3
"""
美股监控因子引擎 v1.0
基于《打开量化投资的黑箱》(里什·纳兰 第二版) 设计

因子框架:
- 趋势动量 (25%): 价格动量、均线排列、相对强度
- 价值因子 (20%): PE/PB/PS、EV/EBITDA、自由现金流收益率
- 成长因子 (20%): 营收增长、盈利增长、预期修正
- 质量因子 (20%): ROE/ROIC、毛利率、负债率
- 市场情绪 (15%): 分析师评级、财报季效应、波动率

基本面数据仅使用实际来源。没有取到的数据保持为空，不以默认值参与评分。
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# 使用相对路径（适配 GitHub Actions）
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from longport_simple_client import get_kline

# 尝试导入 yfinance (备选数据源)
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("⚠️ yfinance 未安装，美股基本面数据将显示为暂无数据")

# ============ 配置 ============
US_STOCKS = {
    'NVDA.US': '英伟达 (AI 芯片)',
    'TSM.US': '台积电 (半导体)',
    'CRCL.US': 'Circle (稳定币)',
    'TSLA.US': '特斯拉 (电动车)',
    'GOOGL.US': '谷歌 (互联网)',
    'BABA.US': '阿里巴巴 (电商)',
}

# 因子权重 (基于书中框架 + 美股特点)
FACTOR_WEIGHTS = {
    'momentum': 0.25,      # 趋势动量
    'value': 0.20,         # 价值
    'growth': 0.20,        # 成长
    'quality': 0.20,       # 质量
    'sentiment': 0.15,     # 市场情绪
}

# 信号阈值
SIGNAL_THRESHOLDS = {
    'strong_buy': 70,
    'buy': 55,
    'hold': 40,
    'reduce': 25,
    'sell': 0,
}


class USStockFactorEngine:
    """美股因子引擎"""
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.df = None
        self.fundamentals = {}
        self._fundamentals_loaded = False
    
    def get_fundamentals(self) -> dict:
        """
        获取实际基本面数据。缺失指标保持 None，不使用估算值。
        
        Returns:
            dict: PE, PB, PS, 股息率，ROE, 盈利增长，营收增长
        """
        if self._fundamentals_loaded:
            return self.fundamentals.copy()

        data = {
            'pe_ttm': None, 'pb': None, 'ps_ttm': None,
            'dividend_yield': None, 'roe': None, 'earnings_growth': None,
            'revenue_growth': None, 'debt_to_equity': None,
            'eps': None, 'bps': None, 'source': 'Unavailable',
        }

        # Yahoo Finance supplies the actual reported/market-derived values.
        if YF_AVAILABLE:
            try:
                yf_symbol = self.symbol.replace('.US', '')
                stock = yf.Ticker(yf_symbol)
                info = stock.info
                def number(key, multiplier=1.0):
                    value = info.get(key)
                    try:
                        value = float(value)
                        return value * multiplier if np.isfinite(value) else None
                    except (TypeError, ValueError):
                        return None

                data.update({
                    'pe_ttm': number('trailingPE'),
                    'pb': number('priceToBook'),
                    'ps_ttm': number('priceToSalesTrailing12Months'),
                    # Yahoo's dividendYield field is already expressed in percent units.
                    'dividend_yield': number('dividendYield'),
                    'roe': number('returnOnEquity', 100),
                    'earnings_growth': number('earningsGrowth', 100),
                    'revenue_growth': number('revenueGrowth', 100),
                    # Yahoo reports debtToEquity as a percentage, e.g. 75 means 0.75.
                    'debt_to_equity': number('debtToEquity', 0.01),
                    'eps': number('trailingEps'),
                    'bps': number('bookValue'),
                })
                if any(value is not None for key, value in data.items() if key != 'source'):
                    data['source'] = 'Yahoo Finance'
            except Exception as e:
                print(f"⚠️ {self.symbol} Yahoo Finance 基本面读取失败：{e}")

        self.fundamentals = data
        self._fundamentals_loaded = True
        if data['source'] == 'Unavailable':
            print(f"⚠️ {self.symbol} 无可用基本面数据；本次不以估算值评分")
        return data.copy()
    
    def get_kline_data(self, bars: int = 200) -> pd.DataFrame:
        """获取 K 线数据"""
        try:
            kline = get_kline(self.symbol, bars)
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
            self.df = df
            return df
        except Exception as e:
            print(f"❌ {self.symbol} 数据获取失败：{e}")
            return None
    
    def calculate_momentum_factors(self) -> dict:
        """
        趋势动量因子 (25%)
        基于 Ch.4 趋势跟踪
        """
        if self.df is None:
            return {'score': 50, 'details': {}}
        
        close = self.df['close']
        
        # 1. 价格动量 (20 日/60 日)
        mom_20 = (close.iloc[-1] / close.iloc[-20] - 1) * 100 if len(close) >= 20 else 0
        mom_60 = (close.iloc[-1] / close.iloc[-60] - 1) * 100 if len(close) >= 60 else 0
        
        # 2. 均线排列
        ma_10 = close.rolling(10).mean().iloc[-1]
        ma_50 = close.rolling(50).mean().iloc[-1]
        ma_200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else close.rolling(100).mean().iloc[-1]
        
        current_price = close.iloc[-1]
        ma_score = 0
        if current_price > ma_10 > ma_50 > ma_200:
            ma_score = 100  # 完美多头排列
        elif current_price > ma_200:
            ma_score = 60
        elif current_price > ma_50:
            ma_score = 40
        else:
            ma_score = 20
        
        # 3. 相对强度 (vs 大盘，简化版用自身历史)
        high_52w = close.rolling(252).max().iloc[-1] if len(close) >= 252 else close.max()
        low_52w = close.rolling(252).min().iloc[-1] if len(close) >= 252 else close.min()
        rs_score = (current_price - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50
        
        # 综合动量得分
        momentum_score = (
            mom_20 * 0.3 +      # 短期动量
            mom_60 * 0.3 +      # 中期动量
            ma_score * 0.2 +    # 均线排列
            rs_score * 0.2      # 相对强度
        )
        
        # 标准化到 0-100
        momentum_score = max(0, min(100, 50 + momentum_score * 0.5))
        
        return {
            'score': round(momentum_score, 1),
            'details': {
                'mom_20d': round(mom_20, 2),
                'mom_60d': round(mom_60, 2),
                'ma_arrangement': round(ma_score, 1),
                'relative_strength': round(rs_score, 1),
            }
        }
    
    def calculate_value_factors(self) -> dict:
        """
        价值因子 (20%)
        基于 Ch.5 价值投资
        """
        fundamentals = self.get_fundamentals()
        
        pe = fundamentals.get('pe_ttm')
        pb = fundamentals.get('pb')
        ps = fundamentals.get('ps_ttm')
        dividend_yield = fundamentals.get('dividend_yield')

        components = []
        if pe is not None and pe > 0:
            components.append((max(0, min(100, 50 - (pe - 20) * 2)), 0.4))
        if pb is not None and pb > 0:
            components.append((max(0, min(100, 50 - (pb - 3) * 10)), 0.3))
        if ps is not None and ps > 0:
            components.append((max(0, min(100, 50 - (ps - 5) * 8)), 0.2))
        if dividend_yield is not None:
            components.append((max(0, min(50, dividend_yield * 10)), 0.1))

        value_score = (
            sum(score * weight for score, weight in components) / sum(weight for _, weight in components)
            if components else None
        )
        
        return {
            'score': round(value_score, 1) if value_score is not None else None,
            'details': {
                'pe_ttm': round(pe, 2) if pe is not None else None,
                'pb': round(pb, 2) if pb is not None else None,
                'ps_ttm': round(ps, 2) if ps is not None else None,
                'dividend_yield': round(dividend_yield, 2) if dividend_yield is not None else None,
                'source': self.fundamentals.get('source', 'Unknown'),
            }
        }
    
    def calculate_growth_factors(self) -> dict:
        """
        成长因子 (20%)
        基于 Ch.6 成长策略
        """
        fundamentals = self.get_fundamentals()
        
        earnings_growth = fundamentals.get('earnings_growth')
        revenue_growth = fundamentals.get('revenue_growth')
        components = []
        if earnings_growth is not None:
            components.append((max(0, min(100, 50 + earnings_growth * 2)), 0.6))
        if revenue_growth is not None:
            components.append((max(0, min(100, 50 + revenue_growth * 2)), 0.4))
        growth_score = (
            sum(score * weight for score, weight in components) / sum(weight for _, weight in components)
            if components else None
        )
        
        return {
            'score': round(growth_score, 1) if growth_score is not None else None,
            'details': {
                'earnings_growth': round(earnings_growth, 2) if earnings_growth is not None else None,
                'revenue_growth': round(revenue_growth, 2) if revenue_growth is not None else None,
            }
        }
    
    def calculate_quality_factors(self) -> dict:
        """
        质量因子 (20%)
        基于 Ch.7 质量因子
        """
        fundamentals = self.get_fundamentals()
        
        roe = fundamentals.get('roe')
        debt_to_equity = fundamentals.get('debt_to_equity')
        components = []
        if roe is not None:
            components.append((max(0, min(100, roe * 5)), 0.7))
        if debt_to_equity is not None:
            components.append((max(0, min(100, 100 - debt_to_equity * 50)), 0.3))
        quality_score = (
            sum(score * weight for score, weight in components) / sum(weight for _, weight in components)
            if components else None
        )
        
        return {
            'score': round(quality_score, 1) if quality_score is not None else None,
            'details': {
                'roe': round(roe, 2) if roe is not None else None,
                'debt_to_equity': round(debt_to_equity, 2) if debt_to_equity is not None else None,
            }
        }
    
    def calculate_sentiment_factors(self) -> dict:
        """
        市场情绪因子 (15%)
        基于 Ch.9 市场情绪
        """
        # 简化版：用波动率和近期表现替代
        if self.df is None:
            return {'score': None, 'details': {}}
        
        close = self.df['close']
        
        # 1. 波动率 (低波动=好情绪)
        returns = close.pct_change()
        volatility = returns.rolling(20).std().iloc[-1] * 100
        vol_score = max(0, 100 - volatility * 3)
        
        # 2. 近期表现
        recent_return = (close.iloc[-1] / close.iloc[-10] - 1) * 100 if len(close) >= 10 else 0
        sentiment_score = 50 + recent_return * 2
        
        # 综合
        final_score = (vol_score * 0.5 + sentiment_score * 0.5)
        final_score = max(0, min(100, final_score))
        
        return {
            'score': round(final_score, 1),
            'details': {
                'volatility_20d': round(volatility, 2),
                'recent_10d_return': round(recent_return, 2),
            }
        }
    
    def calculate_all_factors(self) -> dict:
        """计算所有因子并返回综合评分"""
        if self.get_kline_data() is None:
            return None
        
        # 计算各维度因子
        momentum = self.calculate_momentum_factors()
        value = self.calculate_value_factors()
        growth = self.calculate_growth_factors()
        quality = self.calculate_quality_factors()
        sentiment = self.calculate_sentiment_factors()
        
        # 综合评分
        dimensions = {
            'momentum': momentum,
            'value': value,
            'growth': growth,
            'quality': quality,
            'sentiment': sentiment,
        }
        scored_dimensions = [
            (dimension['score'], FACTOR_WEIGHTS[name])
            for name, dimension in dimensions.items()
            if dimension.get('score') is not None
        ]
        total_score = (
            sum(score * weight for score, weight in scored_dimensions) /
            sum(weight for _, weight in scored_dimensions)
        )
        
        # 确定信号
        if total_score >= SIGNAL_THRESHOLDS['strong_buy']:
            signal = '强烈买入'
            action = '建仓 60-70%'
        elif total_score >= SIGNAL_THRESHOLDS['buy']:
            signal = '买入'
            action = '建仓 50-60%'
        elif total_score >= SIGNAL_THRESHOLDS['hold']:
            signal = '持有'
            action = '持有 30-40%'
        elif total_score >= SIGNAL_THRESHOLDS['reduce']:
            signal = '减持'
            action = '减仓至 10-20%'
        else:
            signal = '卖出'
            action = '清仓'
        
        # 获取基本面数据
        fundamentals = self.get_fundamentals()
        
        # 计算技术指标
        close = self.df['close']
        rsi_14 = self._calculate_rsi(close, 14).iloc[-1]
        ma_10 = close.rolling(10).mean().iloc[-1]
        ma_30 = close.rolling(30).mean().iloc[-1]
        
        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - macd_signal
        macd_value = macd.iloc[-1]
        macd_sig_value = macd_signal.iloc[-1]
        macd_histogram = macd_hist.iloc[-1]
        
        # ATR
        high_low = self.df['high'] - self.df['low']
        high_close = np.abs(self.df['high'] - close.shift())
        low_close = np.abs(self.df['low'] - close.shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]
        
        # 52 周位置
        high_52w = close.rolling(252).max().iloc[-1] if len(close) >= 252 else close.max()
        low_52w = close.rolling(252).min().iloc[-1] if len(close) >= 252 else close.min()
        current_price = close.iloc[-1]
        pct_from_high = (current_price - high_52w) / high_52w * 100
        pct_from_low = (current_price - low_52w) / low_52w * 100
        position_52w = (current_price - low_52w) / (high_52w - low_52w) * 100 if high_52w > low_52w else 50
        
        # 投资理由
        reasons = []
        # 估值理由
        pe = fundamentals.get('pe_ttm')
        if pe is not None and pe > 0:
            if pe < 15:
                reasons.append(f'估值偏低 (PE={pe:.1f})')
            elif pe < 25:
                reasons.append('估值合理')
            else:
                reasons.append(f'估值偏高 (PE={pe:.1f})')
        
        # 质量理由
        roe = fundamentals.get('roe')
        if roe is not None:
            if roe > 20:
                reasons.append(f'盈利能力强 (ROE={roe:.1f}%)')
            elif roe > 10:
                reasons.append('盈利能力尚可')
            else:
                reasons.append(f'盈利能力偏弱 (ROE={roe:.1f}%)')
        
        # 技术面理由
        if rsi_14 < 30:
            reasons.append('技术面超卖')
        elif rsi_14 > 70:
            reasons.append('技术面超买')
        elif current_price > ma_10 > ma_30:
            reasons.append('均线多头排列')
        else:
            reasons.append('技术面偏弱')
        
        return {
            'symbol': self.symbol,
            'total_score': round(total_score, 1),
            'signal': signal,
            'action': action,
            'dimensions': {
                **dimensions,
            },
            'current_price': float(current_price),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            
            # 基本面指标
            'fundamentals': {
                'pe_ttm': round(pe, 2) if pe is not None else None,
                'pb': round(fundamentals['pb'], 2) if fundamentals.get('pb') is not None else None,
                'roe': round(roe, 2) if roe is not None else None,
                'dividend_yield': round(fundamentals['dividend_yield'], 2) if fundamentals.get('dividend_yield') is not None else None,
                'eps': round(fundamentals['eps'], 2) if fundamentals.get('eps') is not None else None,
                'bps': round(fundamentals['bps'], 2) if fundamentals.get('bps') is not None else None,
                'source': fundamentals.get('source', 'Unavailable'),
            },
            
            # 技术指标
            'technical': {
                'rsi_14': round(rsi_14, 1),
                'ma_10': round(ma_10, 2),
                'ma_30': round(ma_30, 2),
                'macd': round(macd_value, 4),
                'macd_signal': round(macd_sig_value, 4),
                'macd_histogram': round(macd_histogram, 4),
                'macd_status': '金叉' if macd_histogram > 0 else '死叉',
                'atr': round(atr, 2),
            },
            
            # 52 周位置
            'week52': {
                'current_price': round(current_price, 2),
                'high': round(high_52w, 2),
                'low': round(low_52w, 2),
                'pct_from_high': round(pct_from_high, 1),
                'pct_from_low': round(pct_from_low, 1),
                'position': round(position_52w, 1),
            },
            
            # 投资理由
            'reasons': reasons,
        }
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算 RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


def main():
    """主函数"""
    print("=" * 70)
    print("🇺🇸 美股监控因子引擎 v1.0")
    print("基于《打开量化投资的黑箱》框架")
    print("=" * 70)
    
    results = []
    
    for symbol, name in US_STOCKS.items():
        print(f"\n分析 {symbol} ({name})...")
        engine = USStockFactorEngine(symbol)
        result = engine.calculate_all_factors()
        
        if result:
            results.append(result)
            d = result['dimensions']
            print(f"  综合：{result['total_score']} | {result['signal']} | {result['action']}")
            print(f"  维度：动={d['momentum']['score']:>3} 价={d['value']['score']:>3} 成={d['growth']['score']:>3} 质={d['quality']['score']:>3} 情={d['sentiment']['score']:>3}")
        else:
            print(f"  ❌ 分析失败")
    
    print("\n" + "=" * 70)
    print(f"✅ 完成 {len(results)} 只股票分析")
    print("=" * 70)
    
    return results


if __name__ == '__main__':
    main()
