#!/usr/bin/env python3
# daily_signal.py - 支持多账户和动态策略的信号生成

import pandas as pd
import numpy as np
import os
import json
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, INIT_CASH, load_strategy, get_holdings_file

# 动态加载策略类以及 Holding 类
AlphaEnginePro, Holding = load_strategy()

class LiveStrategy(AlphaEnginePro):
    def __init__(self, account="main"):
        super().__init__(DATA_DIR, etf_path=DATA_DIR)
        self.account = account
        self.holdings_file = get_holdings_file(account)

        # 动态覆盖 ETF 池（从 etf_pool.csv）
        pool_file = os.path.join(os.path.dirname(__file__), "etf_pool.csv")
        if os.path.exists(pool_file):
            pool_df = pd.read_csv(pool_file, encoding='utf-8')
            self.ETF_POOL = pool_df.to_dict('records')

        self._setup_market_temp_params()
        self.load_state()

    def _setup_market_temp_params(self):
        self.market_temp_params = {
            'w_trend': 0.5, 'smooth': 1, 'delay': 1,
            'w_emotion': 0.2, 'w_volume': 0.2,
            'N_emotion': 20, 'N_volume': 20, 'N_trend': 60,
            'base_coeff': 0.5, 'slope_coeff': 0.25,
            'all_a_filter': False
        }

    # ==================== 持仓缓存 ====================
    def load_state(self):
        if os.path.exists(self.holdings_file):
            with open(self.holdings_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            self.cash = state.get('cash', INIT_CASH)
            self.holdings = {}
            for code, h in state.get('holdings', {}).items():
                self.holdings[code] = Holding(
                    code=code, name=h['name'], qty=h['qty'],
                    cost=h['cost'], highest=h.get('highest', h['cost']),
                    buy_date=h['buy_date'],
                    signal_history=h.get('signal_history', [])
                )
            self.peak_nav = state.get('peak_nav', INIT_CASH)
            self.cooling = state.get('cooling', {})
            self.cooling_type = state.get('cooling_type', {})
            self.frozen_until = state.get('frozen_until', None)
        else:
            self.cash = INIT_CASH
            self.holdings = {}
            self.peak_nav = INIT_CASH
            self.cooling = {}
            self.cooling_type = {}
            self.frozen_until = None
            self.save_state()

    def save_state(self):
        holdings_serial = {}
        for code, h in self.holdings.items():
            holdings_serial[code] = {
                'name': h.name, 'qty': h.qty, 'cost': h.cost,
                'highest': h.highest, 'buy_date': h.buy_date,
                'signal_history': h.signal_history
            }
        state = {
            'cash': self.cash, 'holdings': holdings_serial,
            'peak_nav': self.peak_nav, 'cooling': self.cooling,
            'cooling_type': self.cooling_type, 'frozen_until': self.frozen_until
        }
        with open(self.holdings_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    # ==================== 主流程 ====================
    def daily_run(self):
        self.load_data()
        last_date = sorted(self.all_trade_dates)[-1]
        # 数据保鲜度检查（不再退出，仅警告）
        if '000300.SH' in self.index_data:
            idx_last = sorted(self.index_data['000300.SH'].index)[-1]
            if idx_last != last_date:
                print(f"⚠️ 数据延迟：沪深300最新为 {idx_last}，策略使用 {idx_last} 计算")

        self.update_holdings_highest(last_date)
        nav, drawdown = self.calculate_nav(last_date)

        if self.check_circuit_breaker(last_date, nav, drawdown):
            self.save_state()
            return self.generate_report(last_date, nav, "熔断")
        if self.frozen_until and last_date < self.frozen_until:
            return self.generate_report(last_date, nav, "冰封期")
        if self.frozen_until and last_date >= self.frozen_until:
            self.frozen_until = None

        params = getattr(self, 'market_temp_params', None)
        self.current_nav = nav
        coeff, is_bull, total_score, is_red = self.get_market_temperature(last_date, params)

        v3_state, v3_dur = self.get_v3_state(last_date)
        if v3_state == 'SYSTEMIC_BEAR' and 5 <= v3_dur <= 30:
            coeff = min(coeff, 0.10)
            is_red = True

        self.cooling = {k: v for k, v in self.cooling.items() if v > last_date}
        self.cooling_type = {k: v for k, v in self.cooling_type.items() if k in self.cooling}

        rankings = self.get_rankings(last_date, is_bull)
        self.rankings = rankings
        self.generate_sell_signals(last_date, rankings, len(self.holdings))

        max_buy = 3
        buy_cnt = 0
        buy_cnt += self.check_rebalance(last_date, rankings, coeff, is_red, nav, buy_cnt, max_buy)
        buy_cnt += self.generate_buy_signals(last_date, rankings, nav, coeff, is_red, is_bull, buy_cnt, max_buy)

        nav, _ = self.calculate_nav(last_date)
        return self.generate_report(last_date, nav, "信号正常")

    def generate_report(self, date, nav, status):
        report = f"=== {date} 交易信号报告 (账户: {self.account}) ===\n"
        report += f"状态: {status}  净值估算: {nav:,.2f} 元\n\n"
        if self.pending_orders:
            report += "【今日拟交易指令】\n"
            for o in self.pending_orders:
                act = "买入" if o.type == "BUY" else "卖出"
                report += f"  {act} {o.name} ({o.code}) {o.qty}股\n"
                report += f"     原因：{o.reason}\n"
                if o.type == "BUY":
                    try:
                        buy_sig = self.analyze_buy_signal(o.code, date, 0.5, False, False)
                        if buy_sig:
                            low, high = buy_sig.price_lower, buy_sig.price_upper
                            close_price = None
                            if o.code in self.etf_data and date in self.etf_data[o.code].index:
                                row = self.etf_data[o.code].loc[date]
                                if isinstance(row, pd.DataFrame): row = row.iloc[-1]
                                close_price = row['close']
                                if isinstance(close_price, pd.Series): close_price = close_price.iloc[-1]
                                close_price = float(close_price)
                                report += f"     建议买入区间：{low:.3f} ~ {high:.3f} 元\n"
                                if close_price:
                                    report += f"     最佳建议价：{close_price:.3f} 元\n"
                                    report += f"     🔖 挂单策略：在{low:.3f}–{high:.3f}元内成交即可，最优价{close_price:.3f}元。\n"
                    except:
                        pass
        else:
            report += "【今日拟交易指令】\n今日无交易动作。\n"
        if hasattr(self, 'rankings') and self.rankings:
            report += "\n🏆 【今日ETF排行榜 (Top 5)】\n"
            top5 = sorted(self.rankings, key=lambda x: x.S, reverse=True)[:5]
            for i, item in enumerate(top5, 1):
                report += f"  {i}. {item.name} ({item.code}) S={item.S:.1f}\n"
        report += "\n【当前持仓】\n"
        if not self.holdings:
            report += "  空仓\n"
        else:
            for code, h in self.holdings.items():
                report += f"  {h.name} ({code})：{h.qty}股  成本 {h.cost:.3f}  最高价 {h.highest:.3f}\n"
        report += f"\n可用现金: {self.cash:,.2f} 元\n"
        return report