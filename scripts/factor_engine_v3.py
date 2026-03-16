#!/usr/bin/env python3
"""
因子计算引擎 v3 - 长桥 API 数据源
基于长桥 OpenAPI 获取港股基本面数据 (不再依赖 Yahoo Finance)
"""

import sys
import os
from pathlib import Path

# 使用相对路径（适配 GitHub Actions）
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from longport_simple_client import load_config, get_kline
from longport.openapi import Config, QuoteContext
from manual_data_loader import ManualDataLoader
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('FactorEngineV3')

# 全局 QuoteContext 缓存
_quote_ctx = None

def get_quote_context():
    """获取 QuoteContext 单例"""
    global _quote_ctx
    if _quote_ctx is None:
        config = load_config()
        cfg = Config(
            app_key=config.get('APP_KEY', ''),
            app_secret=config.get('APP_SECRET', ''),
            access_token=config.get('ACCESS_TOKEN', '')
        )
        _quote_ctx = QuoteContext(cfg)
    return _quote_ctx

class FactorEngineV3:
    """因子计算引擎 v3 - 长桥 API 数据源"""
    
    def __init__(self, symbol: str = '9988.HK'):
        self.symbol = symbol
        self.stock_code = symbol.split('.')[0]
        
        # 长桥 QuoteContext
        self.quote_ctx = get_quote_context()
        
        # 手动数据加载器
        self.manual_loader = ManualDataLoader()
        
        self.factors = {}
        self.factor_count = 0
        self.fundamentals = {}
    
    def get_all_fundamentals(self, current_price: float = None) -> dict:
        """获取所有基本面数据 (长桥 API + 手动)"""
        logger.info(f"获取 {self.symbol} 基本面数据 (长桥 API)...")
        
        # 从长桥获取静态信息
        try:
            info_list = self.quote_ctx.static_info([self.symbol])
            if info_list:
                info = info_list[0]
                
                # 计算 PE/PB (如果当前价格已知)
                pe_ttm = None
                pb = None
                if current_price:
                    pe_ttm = float(current_price) / float(info.eps_ttm) if info.eps_ttm else None
                    pb = float(current_price) / float(info.bps) if info.bps else None
                
                self.fundamentals = {
                    # 长桥 API 数据
                    'eps_ttm': info.eps_ttm,
                    'eps': info.eps,
                    'bps': info.bps,
                    'pe_ttm': pe_ttm,
                    'pb': pb,
                    'dividend_yield': info.dividend_yield,
                    'market_cap': info.market_cap if hasattr(info, 'market_cap') else None,
                    'circulating_shares': info.circulating_shares,
                    'total_shares': info.total_shares,
                    
                    # 手动数据 (分析师评级等)
                    'analyst_rating': None,
                    'target_upside': None,
                    'analyst_coverage': None,
                    'growth_expectation': None,
                    'short_ratio_score': None,
                    'insider_trading_score': None,
                }
                
                pe_str = f"{pe_ttm:.2f}" if pe_ttm else "N/A"
                pb_str = f"{pb:.2f}" if pb else "N/A"
                logger.info(f"长桥数据：PE={pe_str} | PB={pb_str} | 股息率={info.dividend_yield:.2f}%")
            else:
                logger.warning(f"无法获取 {self.symbol} 静态信息")
                self.fundamentals = self._empty_fundamentals()
                
        except Exception as e:
            logger.error(f"获取基本面数据失败：{e}")
            self.fundamentals = self._empty_fundamentals()
        
        # 加载手动数据
        self._load_manual_data(current_price)
        
        return self.fundamentals
    
    def _empty_fundamentals(self) -> dict:
        """返回空基本面数据"""
        return {
            'eps_ttm': None, 'eps': None, 'bps': None,
            'pe_ttm': None, 'pb': None, 'dividend_yield': None,
            'market_cap': None, 'circulating_shares': None, 'total_shares': None,
            'analyst_rating': None, 'target_upside': None, 'analyst_coverage': None,
            'growth_expectation': None, 'short_ratio_score': None, 'insider_trading_score': None,
        }
    
    def _load_manual_data(self, current_price: float = None):
        """加载手动数据 (分析师评级等)"""
        try:
            manual_factors = self.manual_loader.get_sentiment_factors()
            
            if current_price:
                self.manual_loader.set_target_upside(current_price)
                self.fundamentals['target_upside'] = self.manual_loader.data.get('target_upside_score', 50)
            
            self.fundamentals.update({
                'analyst_rating': manual_factors.get('manual_analyst_rating'),
                'analyst_coverage': manual_factors.get('manual_analyst_coverage'),
                'growth_expectation': manual_factors.get('manual_growth_expectation'),
                'short_ratio_score': manual_factors.get('manual_short_ratio'),
                'insider_trading_score': manual_factors.get('manual_insider_trading'),
            })
        except Exception as e:
            logger.debug(f"手动数据加载失败：{e}")
    
    def calculate_value_factors(self, fundamentals: dict) -> dict:
        """计算估值因子"""
        factors = {}
        
        # PE 因子 (越低越好，0-100 分)
        pe = fundamentals.get('pe_ttm')
        if pe is not None and pe > 0:
            pe = float(pe)
            # PE<10 得 100 分，PE>50 得 0 分
            factors['value_pe_score'] = max(0, min(100, (50 - pe) * 2))
            logger.debug(f"  PE 因子：{pe:.2f} → {factors['value_pe_score']:.0f}分")
        
        # PB 因子 (越低越好)
        pb = fundamentals.get('pb')
        if pb is not None and pb > 0:
            pb = float(pb)
            # PB<1 得 100 分，PB>5 得 0 分
            factors['value_pb_score'] = max(0, min(100, (5 - pb) * 20))
            logger.debug(f"  PB 因子：{pb:.2f} → {factors['value_pb_score']:.0f}分")
        
        # 股息率因子 (越高越好)
        dy = fundamentals.get('dividend_yield')
        if dy is not None and dy > 0:
            dy = float(dy)
            # 股息率>5% 得 100 分，0% 得 0 分
            factors['value_dividend_score'] = min(100, dy * 20)
            logger.debug(f"  股息率因子：{dy:.2f}% → {factors['value_dividend_score']:.0f}分")
        
        # 综合估值因子
        value_scores = [v for k, v in factors.items() if k.startswith('value_') and v is not None]
        if value_scores:
            factors['value_composite'] = np.mean(value_scores)
            logger.debug(f"  估值综合：{factors['value_composite']:.1f}分")
        
        self.factor_count += len([k for k in factors.keys() if k.startswith('value_')])
        
        return factors
    
    def calculate_growth_factors(self, fundamentals: dict) -> dict:
        """计算成长因子"""
        factors = {}
        
        # EPS 增长 (用 EPS 代替盈利增长，需要历史数据对比)
        # 暂时用手动数据
        ge = fundamentals.get('growth_expectation')
        if ge is not None:
            factors['growth_expectation'] = ge
            logger.debug(f"  增长预期：{ge:.0f}分")
        
        # 综合成长因子
        growth_scores = [v for k, v in factors.items() if k.startswith('growth_') and v is not None]
        if growth_scores:
            factors['growth_composite'] = np.mean(growth_scores)
        
        self.factor_count += len([k for k in factors.keys() if k.startswith('growth_')])
        
        return factors
    
    def calculate_quality_factors(self, fundamentals: dict) -> dict:
        """计算品质因子"""
        factors = {}
        
        # ROE (用 EPS/BPS 近似)
        eps = fundamentals.get('eps_ttm')
        bps = fundamentals.get('bps')
        if eps and bps and bps > 0:
            roe = float(eps) / float(bps)
            # ROE>20% 得 100 分，ROE<5% 得 0 分
            factors['quality_roe'] = max(0, min(100, (roe - 0.05) * 100 / 0.15))
            logger.debug(f"  ROE 因子：{roe*100:.1f}% → {factors['quality_roe']:.0f}分")
        
        # 综合品质因子
        quality_scores = [v for k, v in factors.items() if k.startswith('quality_') and v is not None]
        if quality_scores:
            factors['quality_composite'] = np.mean(quality_scores)
        
        self.factor_count += len([k for k in factors.keys() if k.startswith('quality_')])
        
        return factors
    
    def calculate_sentiment_factors(self, fundamentals: dict) -> dict:
        """计算情绪因子"""
        factors = {}
        
        # 分析师评级 (手动)
        rating = fundamentals.get('analyst_rating')
        if rating is not None:
            factors['sentiment_analyst'] = float(rating)
        
        # 目标价空间 (手动)
        upside = fundamentals.get('target_upside')
        if upside is not None:
            upside = float(upside)
            factors['sentiment_target'] = upside
            logger.debug(f"  目标价空间：{upside:.0f}分")
        
        # 分析师覆盖 (手动)
        coverage = fundamentals.get('analyst_coverage')
        if coverage is not None:
            factors['sentiment_coverage'] = coverage
        
        # 卖空比例 (手动)
        short = fundamentals.get('short_ratio_score')
        if short is not None:
            factors['sentiment_short'] = short
        
        # 内部人交易 (手动)
        insider = fundamentals.get('insider_trading_score')
        if insider is not None:
            factors['sentiment_insider'] = insider
        
        # 综合情绪因子
        sentiment_scores = [v for k, v in factors.items() if k.startswith('sentiment_') and v is not None]
        if sentiment_scores:
            factors['sentiment_composite'] = np.mean(sentiment_scores)
            logger.debug(f"  情绪综合：{factors['sentiment_composite']:.1f}分")
        
        self.factor_count += len([k for k in factors.keys() if k.startswith('sentiment_')])
        
        return factors
    
    def calculate_technical_factors(self, kline_data: dict) -> dict:
        """计算技术面因子"""
        factors = {}
        
        if 'close' in kline_data:
            closes = kline_data['close']
            if len(closes) > 20:
                # RSI
                factors['rsi_14'] = self._calc_rsi(closes, 14)
                # 动量
                factors['momentum_20'] = (closes[-1] - closes[-20]) / closes[-20] * 100
        
        return factors
    
    def _calc_rsi(self, prices: list, period: int = 14) -> float:
        """计算 RSI"""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices[-period-1:])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains) if len(gains) > 0 else 0
        avg_loss = np.mean(losses) if len(losses) > 0 else 1
        
        rs = avg_gain / avg_loss if avg_loss > 0 else 0
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def calculate_all_factors(self, kline_data: dict = None, current_price: float = None, suppress_log: bool = False) -> dict:
        """计算所有因子"""
        if not suppress_log:
            logger.info(f"开始计算 {self.symbol} 因子 (长桥 API 数据源)...")
        
        self.factors = {}
        self.factor_count = 0
        
        # 1. 获取基本面数据 (长桥 API)
        fundamentals = self.get_all_fundamentals(current_price)
        
        # 2. 计算各类因子
        self.factors.update(self.calculate_value_factors(fundamentals))
        self.factors.update(self.calculate_growth_factors(fundamentals))
        self.factors.update(self.calculate_quality_factors(fundamentals))
        self.factors.update(self.calculate_sentiment_factors(fundamentals))
        
        # 3. 添加技术面因子
        if kline_data:
            self.factors.update(self.calculate_technical_factors(kline_data))
        
        if not suppress_log:
            logger.info(f"因子计算完成：{self.factor_count} 个因子")
        
        return self.factors


# ============ 测试 ============
if __name__ == '__main__':
    print("=" * 70)
    print("因子引擎 v3 测试 (长桥 API 数据源)")
    print("=" * 70)
    
    test_symbols = ['9988.HK', '00700.HK', '03690.HK']
    
    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 50)
        
        engine = FactorEngineV3(symbol)
        
        # 获取当前价格
        kline = get_kline(symbol, 5)
        current_price = kline[-1].close if kline else 0
        
        # 准备 K 线数据
        if kline:
            closes = [c.close for c in kline]
            kline_data = {'close': closes}
        else:
            kline_data = None
        
        # 计算因子
        factors = engine.calculate_all_factors(kline_data, current_price)
        
        # 输出关键因子
        print(f"  股价：HK$ {current_price:.2f}")
        print(f"\n估值因子:")
        print(f"  PE 得分：{factors.get('value_pe_score', 'N/A'):>6}")
        print(f"  PB 得分：{factors.get('value_pb_score', 'N/A'):>6}")
        print(f"  股息得分：{factors.get('value_dividend_score', 'N/A'):>6}")
        print(f"  估值综合：{factors.get('value_composite', 'N/A'):>6}")
        
        print(f"\n品质因子:")
        print(f"  ROE 得分：{factors.get('quality_roe', 'N/A'):>6}")
        
        print(f"\n技术因子:")
        print(f"  RSI: {factors.get('rsi_14', 'N/A'):>6}")
        
        print(f"\n总计：{engine.factor_count} 个因子")
    
    print("\n" + "=" * 70)
