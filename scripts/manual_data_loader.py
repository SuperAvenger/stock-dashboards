#!/usr/bin/env python3
"""
手动数据加载器
读取 manual_data.csv 并整合到因子计算
"""

import pandas as pd
import os
from datetime import datetime
from typing import Dict

class ManualDataLoader:
    """手动数据加载器"""
    
    def __init__(self, filepath: str = None):
        if filepath is None:
            filepath = os.path.join(
                os.path.dirname(__file__), 
                'manual_data.csv'
            )
        self.filepath = filepath
        self.data = {}
        self.last_update = None
    
    def load(self) -> Dict:
        """加载手动数据"""
        if not os.path.exists(self.filepath):
            print(f"⚠️ 手动数据文件不存在：{self.filepath}")
            return self._get_default_data()
        
        try:
            # 读取 CSV (跳过注释行)
            with open(self.filepath, 'r', encoding='utf-8') as f:
                lines = [l for l in f.readlines() if not l.startswith('#')]
            
            # 解析数据
            for line in lines:
                line = line.strip()
                if ',' in line:
                    key, value = line.split(',', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # 转换类型
                    try:
                        if key == 'last_update':
                            self.data[key] = value
                            self.last_update = value
                        elif key in ['analyst_rating', 'target_price', 
                                    'next_year_eps', 'earnings_growth_forecast',
                                    'short_ratio']:
                            self.data[key] = float(value)
                        elif key in ['num_analysts', 'insider_net_shares']:
                            self.data[key] = int(value)
                    except:
                        pass
            
            print(f"✅ 加载手动数据成功 (更新：{self.last_update})")
            return self.data
            
        except Exception as e:
            print(f"❌ 加载手动数据失败：{e}")
            return self._get_default_data()
    
    def _get_default_data(self) -> Dict:
        """返回默认数据"""
        return {
            'analyst_rating': 3.0,  # 中性
            'target_price': 140.0,
            'num_analysts': 0,
            'next_year_eps': 8.0,
            'earnings_growth_forecast': 0.0,
            'short_ratio': 0.05,
            'insider_net_shares': 0,
            'last_update': None
        }
    
    def get_sentiment_factors(self) -> Dict:
        """转换为情绪因子"""
        data = self.load()
        
        factors = {}
        
        # 分析师评级因子 (0-100)
        rating = data.get('analyst_rating', 3.0)
        factors['manual_analyst_rating'] = rating / 5 * 100
        
        # 目标价空间 (0-100)
        # (需要当前价格，由外部传入)
        factors['manual_target_upside'] = 50  # 默认中性
        
        # 分析师覆盖度 (0-100)
        num = data.get('num_analysts', 0)
        factors['manual_analyst_coverage'] = min(100, num * 5)
        
        # 盈利增长预期 (0-100)
        growth = data.get('earnings_growth_forecast', 0)
        factors['manual_growth_expectation'] = min(100, max(0, 50 + growth * 2))
        
        # 卖空比例 (越低越好，0-100)
        short = data.get('short_ratio', 0.05)
        factors['manual_short_ratio'] = max(0, min(100, 100 - short * 100))
        
        # 内部人交易 (正=好，0-100)
        insider = data.get('insider_net_shares', 0)
        factors['manual_insider_trading'] = min(100, max(0, 50 + insider / 10000))
        
        return factors
    
    def set_target_upside(self, current_price: float):
        """设置目标价空间"""
        target = self.data.get('target_price', current_price)
        upside = (target - current_price) / current_price * 100
        # 转换为 0-100 分数
        self.data['target_upside_score'] = min(100, max(0, 50 + upside * 2))


# ============ 测试 ============
if __name__ == '__main__':
    print("=" * 60)
    print("手动数据加载器测试")
    print("=" * 60)
    
    loader = ManualDataLoader()
    data = loader.load()
    
    print("\n加载的数据:")
    for key, value in data.items():
        print(f"  {key}: {value}")
    
    print("\n情绪因子:")
    factors = loader.get_sentiment_factors()
    for key, value in factors.items():
        print(f"  {key}: {value:.1f}")
    
    print("\n" + "=" * 60)
