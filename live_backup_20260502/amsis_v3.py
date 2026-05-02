import tushare as ts
import pandas as pd
import numpy as np
import datetime
import os
from openai import OpenAI

# ==================== 数据路径配置 ====================
DATA_PATH = "/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata"

# --- 配置 ---
TS_TOKEN = '9946fc50def862e5d4e3b620abcf2f32ab1945d95e6e2d2187fb81a0' 
ts.set_token(TS_TOKEN)
pro = ts.pro_api()
ds_client = OpenAI(api_key="sk-02523eca6446488ba739f9f76ce87615", base_url="https://api.deepseek.com")

class AMSIS_V3:
    def __init__(self, start_date, end_date, 
                filter_band=0.01,
                confirm_days=2,
                vol_filter=1.2,
                all_a_mode='relaxed',
                position_mode='default'):   # 'default', 'bear_fixed', 'hybrid'
        self.start_date = start_date
        self.end_date = end_date
        self.filter_band = filter_band
        self.confirm_days = confirm_days
        self.vol_filter = vol_filter
        self.all_a_mode = all_a_mode
        self.position_mode = position_mode    
        self.start_date = start_date
        self.end_date = end_date
        self.filter_band = filter_band
        self.confirm_days = confirm_days
        self.vol_filter = vol_filter
        self.all_a_mode = all_a_mode
        self.results = []
        self.df_results = None
        self.last_breakout_price = 0
        self.last_breakout_date = None
        # 用于确认天数的计数器
        self.bull_confirm_count = 0
        self.bear_confirm_count = 0

    def prepare_data(self):
        print(f"正在拉取数据: {self.start_date} -> {self.end_date}")
        dt_obj = datetime.datetime.strptime(self.start_date, '%Y%m%d')
        fetch_start = (dt_obj - datetime.timedelta(days=250)).strftime('%Y%m%d')
        
        # 数据中枢根目录
        DATA_PATH = "/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata"
        cache_dir = DATA_PATH
        os.makedirs(cache_dir, exist_ok=True)
        
        indices = {'HS300': '000300.SH', 'ALL_A': '000985.SH'}
        data = {}
        
        for name, code in indices.items():
            cache_file = f"{cache_dir}/index_{code}.csv"
            
            # ---------- 自动增量更新 ----------
            if os.path.exists(cache_file):
                df_existing = pd.read_csv(cache_file, dtype={'trade_date': str})
                df_existing = df_existing.sort_values('trade_date', ascending=True)
                last_date = df_existing['trade_date'].max()
                print(f"  → {name} 缓存最新日期: {last_date}")
                
                if last_date < self.end_date:
                    print(f"     → 数据过期，从 Tushare 获取 {last_date} 之后的数据...")
                    fetch_start_new = (pd.to_datetime(last_date) + pd.Timedelta(days=1)).strftime('%Y%m%d')
                    df_new = pro.index_daily(ts_code=code, start_date=fetch_start_new, end_date=self.end_date)
                    if not df_new.empty:
                        print(f"     → 获取到 {len(df_new)} 条新数据")
                        df = pd.concat([df_existing, df_new], ignore_index=True)
                        df = df.sort_values('trade_date', ascending=True)
                        df.to_csv(cache_file, index=False)
                    else:
                        print(f"     → 无新数据，继续使用现有缓存")
                        df = df_existing
                else:
                    print(f"     → 数据已是最新，直接使用缓存")
                    df = df_existing
            else:
                print(f"  → 缓存文件不存在，从 Tushare 获取 {name} 全量数据...")
                df = pro.index_daily(ts_code=code, start_date=fetch_start, end_date=self.end_date)
                if df.empty:
                    raise ValueError(f"未获取到 {code} 数据，请检查 Tushare Token 或网络")
                df = df.sort_values('trade_date')
                df.to_csv(cache_file, index=False)
            
            # 统一处理索引
            if 'trade_date' in df.columns:
                df['trade_date'] = df['trade_date'].astype(str)
                df.set_index('trade_date', inplace=True)
            df.sort_index(inplace=True)
            df = df[~df.index.duplicated(keep='first')]
            
            # 计算技术指标（使用 .copy() 避免 SettingWithCopyWarning）
            df = df.copy()
            df['MA20'] = df['close'].rolling(20).mean()
            df['MA60'] = df['close'].rolling(60).mean()
            df['MA120'] = df['close'].rolling(120).mean()
            df['MA_Vol5'] = df['amount'].rolling(5).mean()
            df['MA_Vol20'] = df['amount'].rolling(20).mean()
            df['Pct'] = df['close'].pct_change()
            
            data[name] = df
        
        return data 

    def judge_logic(self, date, data, prev_state):
        h = data['HS300']
        a = data['ALL_A']
        idx = h.index.get_loc(date)
        if isinstance(idx, slice):
            idx = idx.start
        today_h = h.iloc[idx]
        today_a = a.iloc[idx]
        
        # 滤波带（使用参数）
        upper_bound = today_h['MA60'] * (1 + self.filter_band)
        lower_bound = today_h['MA60'] * (1 - self.filter_band)
        h_above = today_h['close'] > upper_bound
        h_below = today_h['close'] < lower_bound
        
        # 全A确认条件
        if self.all_a_mode == 'strict':
            a_above = today_a['close'] > today_a['MA60']

        else:  # relaxed
            if idx >= 20:
                a_above = (today_a['close'] > today_a['MA60']) or (today_a['close'] > a.iloc[idx-20]['close'])
            else:
                a_above = (today_a['close'] > today_a['MA60'])            
        
        
        # 量能条件
        vol_condition = True
        if self.vol_filter is not None:
            vol_condition = today_h['amount'] > today_h['MA_Vol20'] * self.vol_filter
        
        # 潜在状态（尚未确认）
        potential_state = prev_state
        if h_above and a_above and vol_condition:
            potential_state = "SYSTEMIC_BULL" if today_h['MA20'] > today_h['MA60'] else "SIDEWAYS_UP"
        elif h_below:
            potential_state = "SYSTEMIC_BEAR"
        elif not h_above and not h_below:
            if prev_state == "SYSTEMIC_BULL":
                potential_state = "SIDEWAYS_DOWN"
            else:
                potential_state = prev_state
        else:
            potential_state = "SIDEWAYS"   # 【关键】补齐此分支，使“突破但未确认”的情况归为震荡
        
        # 确认天数计数
        if potential_state == "SYSTEMIC_BULL":
            self.bull_confirm_count += 1
            self.bear_confirm_count = 0
        elif potential_state == "SYSTEMIC_BEAR":
            self.bear_confirm_count += 1
            self.bull_confirm_count = 0
        else:
            self.bull_confirm_count = 0
            self.bear_confirm_count = 0
        
        # 只有达到确认天数才真正切换状态
        if potential_state == "SYSTEMIC_BULL" and self.bull_confirm_count >= self.confirm_days:
            state = "SYSTEMIC_BULL"
        elif potential_state == "SYSTEMIC_BEAR" and self.bear_confirm_count >= self.confirm_days:
            state = "SYSTEMIC_BEAR"
        else:
            state = potential_state   # 直接输出潜在状态
        
        # 信号部分保持不变（略，可自行保留原逻辑）
        signal = "IGNORE"
        # ... 原有突破/回踩/假突破等信号逻辑，如需参数化也可类似处理
        
        metrics = {
            'close': today_h['close'],
            'ma60': today_h['MA60'],
            'ma20': today_h['MA20'],
            'vol_ratio': today_h['amount'] / today_h['MA_Vol20'],
            'bias_60': (today_h['close'] - today_h['MA60']) / today_h['MA60'],
            'upper_bound': upper_bound,
            'lower_bound': lower_bound,
            'a_above': a_above
        }
        return state, signal, metrics
       

    def run_backtest(self):
        data = self.prepare_data()
        trade_days = data['HS300'][data['HS300'].index >= self.start_date].index.tolist()
        current_state = "SIDEWAYS"
        state_duration = 1
        
        for date in trade_days:
            state, signal, metrics = self.judge_logic(date, data, current_state)
            
            # 计算连续天数
            if state == current_state:
                state_duration += 1
            else:
                state_duration = 1
            
            res = {
                'date': date, 'state': state, 'signal': signal,
                'h_ret': data['HS300'].loc[date]['Pct'],
                'a_ret': data['ALL_A'].loc[date]['Pct'],
                'state_duration': state_duration
            }
            res.update(metrics)
            self.results.append(res)
            current_state = state
        
        self.df_results = pd.DataFrame(self.results)


    def analyze_results_to_str(self):
        df = self.df_results.copy()
        if df.empty:
            return "无有效回测数据"
        
        first_day = df['date'].iloc[0]
        last_day = df['date'].iloc[-1]
        last_row = df.iloc[-1]
        
        report = [
            f"=== AMSIS 3.2 市场形态量化报告 ===",
            f"回测区间: {first_day} → {last_day}",
            f"截止日期: {last_day}\n",
            "【一、当前核心状态】",
            f"● 当前状态: {last_row['state']}",
            f"● 择时信号: {last_row['signal']}",
            f"● 赚钱效应: {'全A同步走强' if last_row['a_above'] else '个股背离/权重护盘'}\n",
            "【二、当日技术仪表盘 (Technical Dashboard)】",
            f"1. 价格位置: {last_row['close']:.2f} (MA60: {last_row['ma60']:.2f})",
            f"2. 滤波带位置: {last_row['lower_bound']:.2f} < 价格 < {last_row['upper_bound']:.2f}",
            f"   (注: 价格需 > {last_row['upper_bound']:.2f} 确认牛市稳定性)",
            f"3. 量能倍率: {last_row['vol_ratio']:.2f}x (对比20日均量)",
            f"4. 均线距离: 距离MA20: {((last_row['close']/last_row['ma20'])-1)*100:.2f}%",
            f"5. 乖离率(Bias60): {last_row['bias_60']*100:.2f}% (过12%警惕风险)\n",
            "【三、近期历史统计】"
        ]
        
        recent_10 = df.tail(10)
        report.append(f"● 过去10日状态分布:\n{recent_10['state'].value_counts().to_string()}")
        sig_history = recent_10[recent_10['signal'] != 'IGNORE']
        if not sig_history.empty:
            report.append(f"● 近期触发信号:\n{sig_history[['date', 'signal']].to_string(index=False)}")
        else:
            report.append("● 近期无触发信号")
            
        return "\n".join(report)

    # ========== 回测验证方法 =========

    def compute_state_consistency(self, forward_days=[5, 10, 20, 60]):
        """计算各状态下未来N日上涨概率和平均收益（支持多窗口）"""
        df = self.df_results.copy()
        for d in forward_days:
            df[f'fwd_ret_{d}d'] = df['h_ret'].rolling(d).apply(lambda x: (1+x).prod()-1).shift(-d)
        
        stats = []
        for state in sorted(df['state'].unique()):
            sub = df[df['state'] == state]
            row = {'state': state, 'count': len(sub)}
            for d in forward_days:
                col = f'fwd_ret_{d}d'
                valid = sub[col].dropna()
                if len(valid) > 0:
                    row[f'{d}d_positive_ratio'] = (valid > 0).mean()
                    row[f'{d}d_avg_ret'] = valid.mean()
                else:
                    row[f'{d}d_positive_ratio'] = None
                    row[f'{d}d_avg_ret'] = None
            stats.append(row)
        return pd.DataFrame(stats)
    
    def simulate_state_portfolio(self):
        if self.position_mode == 'bear_fixed':
            return self._simulate_bear_fixed()
        elif self.position_mode == 'hybrid':
            return self._simulate_hybrid()
        else:
            return self._simulate_default()

    def _simulate_default(self):
        df = self.df_results.copy()
        df['position'] = 0.5
        df.loc[df['state'] == 'SYSTEMIC_BULL', 'position'] = 1.0
        df.loc[df['state'] == 'SYSTEMIC_BEAR', 'position'] = 0.0
        df['strategy_ret'] = df['position'].shift(1) * df['h_ret']
        df['strategy_ret'] = df['strategy_ret'].fillna(0)
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['strategy_nav'] = (1 + df['strategy_ret']).cumprod()
        return df

    def _simulate_bear_fixed(self):
        df = self.df_results.copy()
        df['position'] = 0.5
        df.loc[df['state'] == 'SYSTEMIC_BULL', 'position'] = 1.0
        df.loc[df['state'] == 'SYSTEMIC_BEAR', 'position'] = 0.0
        # 熊市持续>30天恢复半仓
        df.loc[(df['state'] == 'SYSTEMIC_BEAR') & (df['state_duration'] > 30), 'position'] = 0.5
        df['strategy_ret'] = df['position'].shift(1) * df['h_ret']
        df['strategy_ret'] = df['strategy_ret'].fillna(0)
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['strategy_nav'] = (1 + df['strategy_ret']).cumprod()
        return df

    def _simulate_hybrid(self):
        df = self.df_results.copy()
        df['position'] = 0.5
        for i in range(1, len(df)):
            prev_state = df.iloc[i-1]['state']
            prev_duration = df.iloc[i-1]['state_duration']
            prev_close = df.iloc[i-1]['close']
            df.iloc[i, df.columns.get_loc('position')] = df.iloc[i-1]['position']
            
            if prev_state == 'SYSTEMIC_BULL':
                df.iloc[i, df.columns.get_loc('position')] = 1.0
            elif prev_state == 'SYSTEMIC_BEAR':
                if prev_duration > 30:
                    df.iloc[i, df.columns.get_loc('position')] = 0.5
                else:
                    df.iloc[i, df.columns.get_loc('position')] = 0.0
            elif prev_state in ['SIDEWAYS_UP', 'SIDEWAYS_DOWN', 'SIDEWAYS']:
                if i >= 5:
                    prev_5 = df.iloc[i-5:i]['close']
                    low_5 = prev_5.min()
                    high_5 = prev_5.max()
                    current_pos = df.iloc[i-1]['position']
                    if prev_close < low_5:
                        new_pos = min(1.0, current_pos + 0.2)
                    elif prev_close > high_5:
                        new_pos = max(0.0, current_pos - 0.2)
                    else:
                        new_pos = current_pos
                    df.iloc[i, df.columns.get_loc('position')] = new_pos
        
        df['strategy_ret'] = df['position'].shift(1) * df['h_ret']
        df['strategy_ret'] = df['strategy_ret'].fillna(0)
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['strategy_nav'] = (1 + df['strategy_ret']).cumprod()
        return df
        
    def simulate_ds_score(row):
        """
        根据状态持续天数和量能倍率，模拟 DeepSeek 的评分。
        返回 trend_confidence (0-10) 和 fake_breakout_risk (0-10)
        """
        duration = row['state_duration']
        vol_ratio = row['vol_ratio'] if pd.notna(row['vol_ratio']) else 1.0
        
        # 趋势置信度基础分
        trend_conf = 5
        
        # 持续天数加分
        if duration >= 10:
            trend_conf += 3
        elif duration >= 5:
            trend_conf += 2
        elif duration >= 3:
            trend_conf += 1
        
        # 量能加分
        if vol_ratio > 2.0:
            trend_conf += 2
        elif vol_ratio > 1.5:
            trend_conf += 1
        elif vol_ratio < 0.8:
            trend_conf -= 1  # 缩量突破，扣分
        
        trend_conf = max(0, min(10, trend_conf))
        
        # 假突破风险基础分
        fake_risk = 5
        
        # 持续天数减分
        if duration >= 10:
            fake_risk -= 3
        elif duration >= 5:
            fake_risk -= 2
        elif duration >= 3:
            fake_risk -= 1
        
        # 量能减分（量越大，假突破风险越低）
        if vol_ratio > 2.0:
            fake_risk -= 2
        elif vol_ratio > 1.5:
            fake_risk -= 1
        elif vol_ratio < 0.8:
            fake_risk += 1  # 无量突破，假突破风险高
        
        fake_risk = max(0, min(10, fake_risk))
        
        return trend_conf, fake_risk
    
    def simulate_filtered_portfolio(self):
        """模拟加入持续天数过滤后的仓位策略"""
        df = self.df_results.copy()
        
        # 初始仓位设为50%
        df['position'] = 0.5
        
        # 逐日计算仓位（使用shift(1)获取前一天的状态和持续天数）
        for i in range(1, len(df)):
            prev_state = df.iloc[i-1]['state']
            prev_duration = df.iloc[i-1]['state_duration']
            
            # 默认维持前一天仓位
            df.iloc[i, df.columns.get_loc('position')] = df.iloc[i-1]['position']
            
            # 根据前一天的状态和持续天数决定今日仓位
            if prev_state == 'SYSTEMIC_BULL' and prev_duration >= 5:
                df.iloc[i, df.columns.get_loc('position')] = 1.0
            elif prev_state == 'SYSTEMIC_BEAR':
                if 5 <= prev_duration <= 30:
                    df.iloc[i, df.columns.get_loc('position')] = 0.0
                # 超过30天，恢复半仓（避免长期踏空）
                elif prev_duration > 30:
                    df.iloc[i, df.columns.get_loc('position')] = 0.5
            elif prev_state == 'SIDEWAYS_UP' and prev_duration >= 9:
                df.iloc[i, df.columns.get_loc('position')] = 0.7
            elif prev_state == 'SIDEWAYS_DOWN' and prev_duration >= 5:
                df.iloc[i, df.columns.get_loc('position')] = 0.3
        
        # 计算策略日收益
        df['filtered_ret'] = df['position'].shift(1) * df['h_ret']
        df['filtered_ret'] = df['filtered_ret'].fillna(0)   
        
        # 计算累计净值
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['filtered_nav'] = (1 + df['filtered_ret']).cumprod()
        
        return df

    def simulate_hybrid_portfolio(self):
        """趋势策略（牛熊）+ 震荡策略（网格）混合"""
        df = self.df_results.copy()
        df['position'] = 0.5
        
        for i in range(1, len(df)):
            prev_state = df.iloc[i-1]['state']
            prev_duration = df.iloc[i-1]['state_duration']
            prev_close = df.iloc[i-1]['close']
            
            # 默认维持前一天仓位
            df.iloc[i, df.columns.get_loc('position')] = df.iloc[i-1]['position']
            
            # 趋势策略部分（牛熊状态）
            if prev_state == 'SYSTEMIC_BULL':
                df.iloc[i, df.columns.get_loc('position')] = 1.0
            elif prev_state == 'SYSTEMIC_BEAR':
                if prev_duration > 30:
                    df.iloc[i, df.columns.get_loc('position')] = 0.5   # 长期熊市恢复半仓
                else:
                    df.iloc[i, df.columns.get_loc('position')] = 0.0
            
            # 震荡策略部分（仅当状态为SIDEWAYS系列时覆盖）
            if prev_state in ['SIDEWAYS_UP', 'SIDEWAYS_DOWN', 'SIDEWAYS']:
                # 计算前5日最高最低
                if i >= 5:
                    prev_5 = df.iloc[i-5:i]['close']
                    low_5 = prev_5.min()
                    high_5 = prev_5.max()
                    current_pos = df.iloc[i-1]['position']
                    if prev_close < low_5:
                        new_pos = min(1.0, current_pos + 0.2)
                    elif prev_close > high_5:
                        new_pos = max(0.0, current_pos - 0.2)
                    else:
                        new_pos = current_pos
                    df.iloc[i, df.columns.get_loc('position')] = new_pos
        
        df['hybrid_ret'] = df['position'].shift(1) * df['h_ret']
        df['hybrid_ret'] = df['hybrid_ret'].fillna(0)
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['hybrid_nav'] = (1 + df['hybrid_ret']).cumprod()
        return df    


    
    def simulate_progressive_portfolio(self):
        """模拟渐进仓位策略：根据状态持续天数逐步调整仓位"""
        df = self.df_results.copy()
        df['position'] = 0.5  # 初始默认半仓
        
        for i in range(1, len(df)):
            prev_state = df.iloc[i-1]['state']
            prev_duration = df.iloc[i-1]['state_duration']
            
            # 默认维持前一天仓位
            df.iloc[i, df.columns.get_loc('position')] = df.iloc[i-1]['position']
            
            # 牛市渐进加仓
            if prev_state == 'SYSTEMIC_BULL':
                if prev_duration == 1:
                    df.iloc[i, df.columns.get_loc('position')] = 0.2
                elif prev_duration == 2:
                    df.iloc[i, df.columns.get_loc('position')] = 0.4
                elif prev_duration == 3:
                    df.iloc[i, df.columns.get_loc('position')] = 0.6
                elif prev_duration == 4:
                    df.iloc[i, df.columns.get_loc('position')] = 0.8
                else:  # >=5
                    df.iloc[i, df.columns.get_loc('position')] = 1.0
            
            # 熊市渐进减仓
            elif prev_state == 'SYSTEMIC_BEAR':
                if prev_duration == 1:
                    df.iloc[i, df.columns.get_loc('position')] = 0.8
                elif prev_duration == 2:
                    df.iloc[i, df.columns.get_loc('position')] = 0.6
                elif prev_duration == 3:
                    df.iloc[i, df.columns.get_loc('position')] = 0.4
                elif prev_duration == 4:
                    df.iloc[i, df.columns.get_loc('position')] = 0.2
                else:  # >=5
                    df.iloc[i, df.columns.get_loc('position')] = 0.0
            
            # 震荡状态维持原仓位（已在默认中处理）
        
        # 计算策略日收益
        df['progressive_ret'] = df['position'].shift(1) * df['h_ret']
        df['progressive_ret'] = df['progressive_ret'].fillna(0)
        
        # 累计净值
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['progressive_nav'] = (1 + df['progressive_ret']).cumprod()
        
        return df
    
    def analyze_by_duration(self, state_filter=None, forward_days=20):
        """
        按状态持续天数分组，统计未来N日准确率。
        若 state_filter 为 None，则返回所有状态汇总。
        """
        df = self.df_results.copy()
        df['fwd_ret'] = df['h_ret'].rolling(forward_days).apply(
            lambda x: (1+x).prod()-1
        ).shift(-forward_days)
        
        if state_filter is not None:
            df = df[df['state'] == state_filter]
        
        if df.empty:
            return pd.DataFrame()
        
        stats = []
        # 按状态和持续天数分组
        group_cols = ['state', 'state_duration'] if state_filter is None else ['state_duration']
        for keys, group in df.groupby(group_cols):
            if not isinstance(keys, tuple):
                keys = (keys,)
            valid = group['fwd_ret'].dropna()
            if len(valid) > 0:
                row = {
                    '状态': keys[0] if state_filter is None else state_filter,
                    '持续天数': keys[-1],
                    '样本数': len(valid),
                    '上涨概率': (valid > 0).mean() * 100,
                    '平均收益': valid.mean() * 100
                }
                stats.append(row)
        return pd.DataFrame(stats).sort_values(['状态', '持续天数'])

    def annual_performance(self):
        """计算策略和基准的年度收益率及超额收益"""
        df = self.simulate_state_portfolio()
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        
        # 计算每日收益率（已在 simulate_state_portfolio 中有 strategy_ret 和 h_ret）
        annual = df.groupby('year').agg({
            'h_ret': lambda x: (1 + x).prod() - 1,
            'strategy_ret': lambda x: (1 + x).prod() - 1
        }).rename(columns={'h_ret': 'benchmark_return', 'strategy_ret': 'strategy_return'})
        annual['excess_return'] = annual['strategy_return'] - annual['benchmark_return']
        annual = annual.round(4)
        return annual

    def max_drawdown(self):
        """计算策略和基准的最大回撤（百分比）及回撤区间"""
        df = self.simulate_state_portfolio()
        
        # 计算累计净值
        df['benchmark_nav'] = (1 + df['h_ret']).cumprod()
        df['strategy_nav'] = (1 + df['strategy_ret']).cumprod()
        
        def compute_mdd(nav_series, date_series):
            peak = nav_series.expanding().max()
            drawdown = (nav_series - peak) / peak
            mdd = drawdown.min()
            end_idx = drawdown.idxmin()
            peak_idx = peak.loc[:end_idx].idxmax()
            return mdd, date_series.loc[peak_idx], date_series.loc[end_idx]
        
        bench_mdd, bench_peak, bench_trough = compute_mdd(df['benchmark_nav'], df['date'])
        strat_mdd, strat_peak, strat_trough = compute_mdd(df['strategy_nav'], df['date'])
        
        return {
            'benchmark': {'mdd': bench_mdd, 'peak_date': bench_peak, 'trough_date': bench_trough},
            'strategy': {'mdd': strat_mdd, 'peak_date': strat_peak, 'trough_date': strat_trough}
        }


def get_deepseek_interpretation(report_text):
    print("\n🚀 正在请求 DeepSeek 专家级深度解读...\n")
    try:
        prompt = f"""
        你作为资深A股量化专家，请根据下方的【仪表盘数据】和【状态报告】进行解读。
        
        重点分析：
        1. 判断当前市场的主导力量（多头、空头还是存量博弈）。
        2. 观察状态转换的频率，分析市场的稳定性。
        3. 价格是否有效站稳在“滤波带”上方？
        4. “量能倍率”是否支持当前的趋势突破？
        5. 结合“均线距离”判断目前是该【追涨】、【等回踩】还是【止损】。
        6. 如果“当前状态”与“信号”出现矛盾，请指出潜在的假突破风险。
        7. 给出下一阶段的操作建议（轻仓、满仓或分批撤离）。

        数据报告：
        {report_text}
        """
        response = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你是一个严谨的A股实战分析师。"},{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e: 
        return f"AI 解读失败: {str(e)}"

if __name__ == "__main__":
    # 测试一组参数，例如：滤波带1.5%，确认2天，量能过滤1.2倍，宽松全A模式
    tester = AMSIS_V3('20200101', '20260409',
                      filter_band=0.015,
                      confirm_days=2,
                      vol_filter=1.2,
                      all_a_mode='relaxed')
    tester.run_backtest()
    print("回测完成，结果行数:", len(tester.df_results))
    print(tester.df_results[['date', 'state', 'state_duration']].tail(10))




