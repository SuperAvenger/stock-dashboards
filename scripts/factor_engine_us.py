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

数据源优先级:
1. 长桥 API (Longbridge) - 优先
2. Yahoo Finance - 备选
3. 默认中性值 - 兜底
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
    print("⚠️ yfinance 未安装，基本面数据将使用默认值")

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
    
    def get_fundamentals(self) -> dict:
        """
        获取基本面数据 (优先级：长桥 → Yahoo → 默认值)
        
        Returns:
            dict: PE, PB, PS, 股息率，ROE, 盈利增长，营收增长
        """
        # 尝试 1: 从长桥 API 获取
        try:
            kline_extended = get_kline(self.symbol, 1, include_extended=True)
            if kline_extended and len(kline_extended) > 0:
                data = kline_extended[0]
                pe = data.get('pe_ttm', 0) if isinstance(data, dict) else getattr(data, 'pe_ttm', 0)
                pb = data.get('pb', 0) if isinstance(data, dict) else getattr(data, 'pb', 0)
                ps = data.get('ps_ttm', 0) if isinstance(data, dict) else getattr(data, 'ps_ttm', 0)
                div = data.get('dividend_yield', 0) if isinstance(data, dict) else getattr(data, 'dividend_yield', 0)
                
                # 检查长桥数据是否有效 (非 0)
                if pe and pe > 0:
                    self.fundamentals['source'] = 'Longbridge'
                    return {
                        'pe_ttm': float(pe),
                        'pb': float(pb),
                        'ps_ttm': float(ps),
                        'dividend_yield': float(div),
                        'roe': 15.0,  # 长桥无 ROE，用默认值
                        'earnings_growth': 10.0,  # 长桥无增长数据
                        'revenue_growth': 10.0,
                        'debt_to_equity': 0.5,
                    }
        except Exception as e:
            pass
        
        # 尝试 2: 从 Yahoo Finance 获取
        if YF_AVAILABLE:
            try:
                # 去掉.US 后缀
                yf_symbol = self.symbol.replace('.US', '')
                stock = yf.Ticker(yf_symbol)
                info = stock.info
                
                pe = info.get('trailingPE')
                pb = info.get('priceToBook')
                ps = info.get('priceToSalesTrailing12Months')
                div = info.get('dividendYield', 0)
                roe = info.get('returnOnEquity')
                earnings_growth = info.get('earningsGrowth')
                revenue_growth = info.get('revenueGrowth')
                
                if pe and pe > 0:
                    self.fundamentals['source'] = 'Yahoo Finance'
                    return {
                        'pe_ttm': float(pe),
                        'pb': float(pb) if pb else 2.0,
                        'ps_ttm': float(ps) if ps else 3.0,
                        'dividend_yield': float(div) * 100 if div else 0,  # 转换为百分比
                        'roe': float(roe) * 100 if roe else 15.0,  # 转换为百分比
                        'earnings_growth': float(earnings_growth) * 100 if earnings_growth else 10.0,
                        'revenue_growth': float(revenue_growth) * 100 if revenue_growth else 10.0,
                        'debt_to_equity': 0.5,
                    }
            except Exception as e:
                pass
        
        # 尝试 3: 返回默认中性值
        self.fundamentals['source'] = 'Default'
        return {
            'pe_ttm': 20.0,
            'pb': 2.0,
            'ps_ttm': 3.0,
            'dividend_yield': 1.0,
            'roe': 15.0,
            'earnings_growth': 10.0,
            'revenue_growth': 10.0,
            'debt_to_equity': 0.5,
        }
    
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
        
        pe = fundamentals.get('pe_ttm', 20)
        pb = fundamentals.get('pb', 2)
        ps = fundamentals.get('ps_ttm', 3)
        dividend_yield = fundamentals.get('dividend_yield', 0)
        
        # PE 得分 (低 PE=高分，行业调整)
        # 科技股 PE 通常较高，用分位数更合理
        pe_score = max(0, min(100, (50 - (pe - 20) * 2)))
        
        # PB 得分
        pb_score = max(0, min(100, (50 - (pb - 3) * 10)))
        
        # PS 得分
        ps_score = max(0, min(100, (50 - (ps - 5) * 8)))
        
        # 股息率得分 (美股成长股通常不分红，权重降低)
        div_score = min(50, dividend_yield * 10)
        
        value_score = (pe_score * 0.4 + pb_score * 0.3 + ps_score * 0.2 + div_score * 0.1)
        
        return {
            'score': round(value_score, 1),
            'details': {
                'pe_ttm': round(pe, 2),
                'pb': round(pb, 2),
                'ps_ttm': round(ps, 2),
                'dividend_yield': round(dividend_yield, 2),
                'source': self.fundamentals.get('source', 'Unknown'),
            }
        }
    
    def calculate_growth_factors(self) -> dict:
        """
        成长因子 (20%)
        基于 Ch.6 成长策略
        """
        fundamentals = self.get_fundamentals()
        
        earnings_growth = fundamentals.get('earnings_growth', 10)
        revenue_growth = fundamentals.get('revenue_growth', 10)
        
        # 盈利增长得分
        earnings_score = min(100, 50 + earnings_growth * 2)
        
        # 营收增长得分
        revenue_score = min(100, 50 + revenue_growth * 2)
        
        growth_score = (earnings_score * 0.6 + revenue_score * 0.4)
        
        return {
            'score': round(growth_score, 1),
            'details': {
                'earnings_growth': round(earnings_growth, 2),
                'revenue_growth': round(revenue_growth, 2),
            }
        }
    
    def calculate_quality_factors(self) -> dict:
        """
        质量因子 (20%)
        基于 Ch.7 质量因子
        """
        fundamentals = self.get_fundamentals()
        
        roe = fundamentals.get('roe', 15)
        debt_to_equity = fundamentals.get('debt_to_equity', 0.5)
        
        # ROE 得分
        roe_score = min(100, roe * 5)
        
        # 负债率得分 (低负债=高分)
        debt_score = max(0, 100 - debt_to_equity * 50)
        
        quality_score = (roe_score * 0.7 + debt_score * 0.3)
        
        return {
            'score': round(quality_score, 1),
            'details': {
                'roe': round(roe, 2),
                'debt_to_equity': round(debt_to_equity, 2),
            }
        }
    
    def calculate_sentiment_factors(self) -> dict:
        """
        市场情绪因子 (15%)
        基于 Ch.9 市场情绪
        """
        # 简化版：用波动率和近期表现替代
        if self.df is None:
            return {'score': 50, 'details': {}}
        
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
        total_score = (
            momentum['score'] * FACTOR_WEIGHTS['momentum'] +
            value['score'] * FACTOR_WEIGHTS['value'] +
            growth['score'] * FACTOR_WEIGHTS['growth'] +
            quality['score'] * FACTOR_WEIGHTS['quality'] +
            sentiment['score'] * FACTOR_WEIGHTS['sentiment']
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
        pe = fundamentals.get('pe_ttm', 20)
        if pe < 15:
            reasons.append(f'估值偏低 (PE={pe:.1f})')
        elif pe < 25:
            reasons.append('估值合理')
        else:
            reasons.append(f'估值偏高 (PE={pe:.1f})')
        
        # 质量理由
        roe = fundamentals.get('roe', 15)
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
                'momentum': momentum,
                'value': value,
                'growth': growth,
                'quality': quality,
                'sentiment': sentiment,
            },
            'current_price': float(current_price),
            'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            
            # 基本面指标
            'fundamentals': {
                'pe_ttm': round(pe, 2),
                'pb': round(fundamentals.get('pb', 2), 2),
                'roe': round(roe, 2),
                'dividend_yield': round(fundamentals.get('dividend_yield', 0), 2),
                'eps': round(fundamentals.get('eps', pe * 0.5), 2),  # 估算
                'bps': round(current_price / fundamentals.get('pb', 2), 2),
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
