"""
AMSIS_V3 实盘版本（最优参数固化）
每日运行，输出市场状态、策略路由建议，可选 DeepSeek 辅助解读。
"""

import os
import pandas as pd
import tushare as ts
import numpy as np
import datetime
import json
import re
from openai import OpenAI

# ==================== 配置 ====================
TS_TOKEN = '9946fc50def862e5d4e3b620abcf2f32ab1945d95e6e2d2187fb81a0'
ts.set_token(TS_TOKEN)
pro = ts.pro_api()

DS_API_KEY = "sk-02523eca6446488ba739f9f76ce87615"
DS_BASE_URL = "https://api.deepseek.com"
ds_client = OpenAI(api_key=DS_API_KEY, base_url=DS_BASE_URL) if DS_API_KEY else None

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backtestdata")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_state.json")

# ==================== 最优参数（固化） ====================
FILTER_BAND = 0.01          # 滤波带 ±1%
CONFIRM_DAYS = 2            # 连续2日确认
VOL_FILTER = 1.2            # 量能 > 20日均量 1.2倍
ALL_A_MODE = 'relaxed'      # 全A宽松条件

# ==================== 中文映射与解读函数 ====================

STATE_CN_MAP = {
    'SYSTEMIC_BULL': '🟢 系统性牛市',
    'SYSTEMIC_BEAR': '🔴 系统性熊市',
    'SIDEWAYS_UP': '🟡 震荡偏强',
    'SIDEWAYS_DOWN': '🟠 震荡偏弱',
    'SIDEWAYS': '⚪ 中性震荡'
}

def interpret_ds_score(trend_conf, fake_risk):
    """将DS评分转化为直观解读"""
    if trend_conf is None or fake_risk is None:
        return "暂无AI评分"
    
    if trend_conf >= 7 and fake_risk <= 3:
        return "✅ AI高度认可当前信号，可积极执行"
    elif trend_conf >= 5 and fake_risk <= 5:
        return "⚠️ AI持谨慎态度，建议控制仓位"
    else:
        return "❌ AI提示假突破风险较高，建议观望或轻仓"

def get_signal_analysis(data):
    """根据量价数据生成关键信号解读"""
    signals = []
    close = data['close']
    ma60 = data['ma60']
    ma20 = data['ma20']
    vol_ratio = data['vol_ratio']
    bias = data['bias_60']
    a_above = data['a_above']
    
    # 价格与均线关系
    if close > ma60:
        signals.append(f"价格站上MA60(高出{(close/ma60-1)*100:.2f}%)")
    else:
        signals.append(f"价格低于MA60(低{(ma60/close-1)*100:.2f}%)")
    
    # 量能解读
    if vol_ratio > 1.5:
        signals.append(f"放量({vol_ratio:.2f}x)，交投活跃")
    elif vol_ratio < 0.8:
        signals.append(f"缩量({vol_ratio:.2f}x)，交投清淡")
    else:
        signals.append(f"量能平稳({vol_ratio:.2f}x)")
    
    # 乖离率解读
    if bias > 0.08:
        signals.append(f"乖离率偏高({bias*100:.1f}%)，追高风险大")
    elif bias < -0.08:
        signals.append(f"乖离率偏低({bias*100:.1f}%)，超跌反弹可期")
    
    # 赚钱效应（使用真实涨跌家数比进行校验）
    up_ratio = data.get('up_ratio', 0.5)
    if data['a_above'] and up_ratio > 0.55:
        signals.append(f"全A同步走强且真实上涨家数占比{up_ratio*100:.0f}%，赚钱效应良好")
    elif data['a_above'] and up_ratio <= 0.55:
        signals.append(f"指数走强但上涨家数仅{up_ratio*100:.0f}%，权重护盘特征明显，警惕假突破")
    else:
        signals.append(f"个股普遍走弱，上涨家数占比仅{up_ratio*100:.0f}%")
    
    return "；".join(signals)

# ==================== 状态记忆函数 ====================
def load_last_state():
    """加载昨日状态与持续天数"""
    default = {"state": "SIDEWAYS", "duration": 1, "date": None}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_last_state(state, duration, date):
    """保存今日状态供明日使用"""
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump({"state": state, "duration": duration, "date": date}, f)

# ==================== 数据更新 ====================
def update_data(code, end_date):
    """增量更新指数数据"""
    cache_file = f"{CACHE_DIR}/index_{code}.csv"
    os.makedirs(CACHE_DIR, exist_ok=True)

    if os.path.exists(cache_file):
        df_existing = pd.read_csv(cache_file, dtype={'trade_date': str})
        df_existing = df_existing.sort_values('trade_date', ascending=True)
        last_date = df_existing['trade_date'].max()
        print(f"  → {code} 缓存最新日期: {last_date}")

        if last_date < end_date:
            fetch_start = (pd.to_datetime(last_date) + pd.Timedelta(days=1)).strftime('%Y%m%d')
            print(f"     → 从 Tushare 获取 {fetch_start} 之后的数据...")
            df_new = pro.index_daily(ts_code=code, start_date=fetch_start, end_date=end_date)
            if not df_new.empty:
                df = pd.concat([df_existing, df_new], ignore_index=True)
                df = df.sort_values('trade_date', ascending=True)
                df.to_csv(cache_file, index=False)
                print(f"     → 获取到 {len(df_new)} 条新数据")
            else:
                df = df_existing
        else:
            print(f"     → 数据已是最新")
            df = df_existing
    else:
        print(f"  → 缓存不存在，从 Tushare 全量获取...")
        df = pro.index_daily(ts_code=code, start_date='20050101', end_date=end_date)
        df = df.sort_values('trade_date')
        df.to_csv(cache_file, index=False)

    if 'trade_date' in df.columns:
        df['trade_date'] = df['trade_date'].astype(str)
        df.set_index('trade_date', inplace=True)
    df.sort_index(inplace=True)
    df = df[~df.index.duplicated(keep='first')]

    df = df.copy()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['MA_Vol20'] = df['amount'].rolling(20).mean()
    return df

# ==================== DeepSeek 解读 ====================

def get_deepseek_interpretation(report_text, duration, recent_state_dist=None, recent_signals=None):
    """调用 DeepSeek 获取解读与评分（可选）"""
    if ds_client is None:
        return None, None
    print("\n🚀 正在请求 DeepSeek 解读...")
    
    # ========== 历史统计数据（基于2005-2026完整回测，可定期更新） ==========
    bull_stats = {
        'short_duration': {'prob': 53, 'avg_ret': 1.06},   # 持续1-2天时（与之前一致）
        'long_duration': {'prob': 69, 'avg_ret': 4.39}     # 持续≥3天时（更新为最新回测数据）
    }
    bear_stats = {
        'mid_duration': {'prob': 45, 'avg_ret': -0.10},    # 持续5-30天时
        'long_duration': {'prob': 52, 'avg_ret': 0.30}     # 持续>30天时
    }
    
    # 安全处理：构建历史信息字符串
    history_info = ""
    if recent_state_dist is not None:
        history_info += f"\n【近10日状态分布】\n{recent_state_dist}\n"
    if recent_signals is not None and not recent_signals.empty:
        history_info += f"\n【近期触发信号】\n{recent_signals.to_string(index=False)}\n"

     
    prompt = f"""
你是一位极度审慎的A股量化策略师。请基于当前数据与历史统计规律，推演明日的两种可能情景，并给出具体的操作预案。

**核心要求**：
- 整体字数控制在300字左右。
- 不要预测涨跌，只做情景应对。

【当前市场数据】
{report_text}
{history_info}

f"**当前状态**：{report_text.split('状态:')[1].split(chr(10))[0].strip()}，已持续 **{duration}** 个交易日。\n"

【历史统计规律（2005-2026年回测，仅供参考）】
- 当SYSTEMIC_BULL持续1-2天时：后续20日上涨概率约{bull_stats['short_duration']['prob']}%，平均收益约{bull_stats['short_duration']['avg_ret']}%。
- 当SYSTEMIC_BULL持续≥3天时：后续20日上涨概率约{bull_stats['long_duration']['prob']}%，平均收益约{bull_stats['long_duration']['avg_ret']}%。
- 当SYSTEMIC_BEAR持续5-30天时：后续20日上涨概率约{bear_stats['mid_duration']['prob']}%，空仓有效。
- 当SYSTEMIC_BEAR持续>30天时：后续20日上涨概率约{bear_stats['long_duration']['prob']}%，踏空风险上升。
- 震荡状态（SIDEWAYS系列）：后续20日上涨概率接近50%，无明显方向性。

【规律适用性自评】
在引用上述规律前，请评估当前环境与历史典型环境的相似度（高/中/低），并简要说明理由。

【输出格式】
【今日小结】（一句话概括状态 + 历史相似度评级：高/中/低）
【情景A：延续趋势】（走势推演 + 操作预案：触发条件→仓位调整，目标点位）
【情景B：反向风险】（走势推演 + 操作预案：触发条件→仓位调整，止损点位）
【核心关注点】（一句话）明日最关键的单一观察点。

【JSON】
{{"trend_confidence":0-10,"fake_breakout_risk":0-10,"recommended_strategy":"trend/range/defensive"}}
"""
    try:
        response = ds_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个既严谨又接地气的A股量化实战专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=500,
        )
        content = response.choices[0].message.content
        
        # 兼容新旧两种输出格式
        # 提取 JSON
        json_match = re.search(r'\{.*"trend_confidence".*\}', content, re.DOTALL)
        score = json.loads(json_match.group()) if json_match else None
        
        # 提取解读文本（优先新格式，回退旧格式）
        new_format_match = re.search(r'【今日小结】(.*?)【JSON】', content, re.DOTALL)
        if new_format_match:
            interpretation = new_format_match.group(1).strip()
        else:
            interp_match = re.search(r'【解读】\s*(.*?)\s*【JSON】', content, re.DOTALL)
            interpretation = interp_match.group(1).strip() if interp_match else None
        
        return interpretation, score
    except Exception as e:
        print(f"DeepSeek 调用失败: {e}")
        return None, None
    
# ==================== 核心状态机 ====================
class LiveAMSI:
    def __init__(self):
        self.today_date = datetime.datetime.now().strftime('%Y%m%d')

    def run(self):
        print(f"更新数据至 {self.today_date}...")
        df_hs300 = update_data('000300.SH', self.today_date)
        df_all_a = update_data('000985.SH', self.today_date)
        df_sz = update_data('000001.SH', self.today_date)

        # 确定实际有效日期（处理非交易日）
        if self.today_date not in df_hs300.index:
            available = df_hs300.index[df_hs300.index <= self.today_date]
            if len(available) == 0:
                raise ValueError("无有效交易日数据")
            self.today_date = available[-1]
            print(f"注意：使用最近交易日 {self.today_date}")

        today_h = df_hs300.loc[self.today_date]
        today_a = df_all_a.loc[self.today_date]
        today_sz = df_sz.loc[self.today_date]
        sz_close = today_sz['close']
        idx = df_hs300.index.get_loc(self.today_date)

        # 滤波带
        upper = today_h['MA60'] * (1 + FILTER_BAND)
        lower = today_h['MA60'] * (1 - FILTER_BAND)
        h_above = today_h['close'] > upper
        h_below = today_h['close'] < lower

        # 全A条件
        if ALL_A_MODE == 'strict':
            a_above = today_a['close'] > today_a['MA60']
        else:
            if idx >= 20:
                a_above = (today_a['close'] > today_a['MA60']) or (today_a['close'] > df_all_a.iloc[idx-20]['close'])
            else:
                a_above = (today_a['close'] > today_a['MA60'])

        # 量能条件
        vol_ok = True
        if VOL_FILTER is not None:
            vol_ok = today_h['amount'] > today_h['MA_Vol20'] * VOL_FILTER
        bias_60 = (today_h['close'] - today_h['MA60']) / today_h['MA60']

        # 潜在状态
        if h_above and a_above and vol_ok:
            potential = "SYSTEMIC_BULL" if today_h['MA20'] > today_h['MA60'] else "SIDEWAYS_UP"
        elif h_below:
            potential = "SYSTEMIC_BEAR"
        elif not h_above and not h_below:
            last = load_last_state()
            if last['state'] == "SYSTEMIC_BULL":
                potential = "SIDEWAYS_DOWN"
            else:
                potential = last['state']
        else:
            potential = "SIDEWAYS"

        # 读取昨日状态，计算持续天数
        last = load_last_state()

        if last['date'] == self.today_date:
            print(f"注意：今日 {self.today_date} 已运行过，直接使用上次状态，不重复更新。")
            final_state = last['state']
            duration = last['duration']
        else:
            if potential == last['state']:
                duration = last['duration'] + 1
            else:
                duration = 1

            if potential == "SYSTEMIC_BULL" and duration < CONFIRM_DAYS:
                final_state = last['state']
            elif potential == "SYSTEMIC_BEAR" and duration < CONFIRM_DAYS:
                final_state = last['state']
            else:
                final_state = potential

            save_last_state(final_state, duration, self.today_date)


        # 计算短线信号
        short_signals = self.compute_short_signals(df_hs300, df_all_a, idx, today_h, today_a, final_state)

        # 计算真实涨跌家数比（基于全A市场）
        try:
            today_all = pro.daily(trade_date=self.today_date)
            if not today_all.empty:
                up_count = (today_all['pct_chg'] > 0).sum()
                down_count = (today_all['pct_chg'] < 0).sum()
                total = len(today_all)
                up_ratio = up_count / total if total > 0 else 0.5
            else:
                up_ratio = 0.5
        except:
            up_ratio = 0.5  # 获取失败时默认为中性

        # ========== 写入历史日志（确保所有字段完整） ==========
        log_file = "state_history.csv"
        max_rows = 500
        
        # 确保所有字段都有默认值
        log_state = final_state if 'final_state' in locals() else last['state']
        log_duration = duration if 'duration' in locals() else last['duration']
        log_close = today_h['close']
        log_ma60 = today_h['MA60']
        log_bias = (today_h['close'] - today_h['MA60']) / today_h['MA60']
        log_vol = today_h['amount'] / today_h['MA_Vol20']
        log_signals = ','.join(short_signals) if short_signals else ''
        
        log_entry = {
            'date': self.today_date,
            'state': log_state,
            'duration': log_duration,
            'close': log_close,
            'ma60': log_ma60,
            'bias_60': log_bias,
            'vol_ratio': log_vol,
            'short_signals': log_signals
        }
        
        df_log = pd.DataFrame([log_entry])
        if os.path.exists(log_file):
            df_existing = pd.read_csv(log_file)
            # 确保现有文件的列完整
            if 'state' not in df_existing.columns:
                df_existing = pd.DataFrame(columns=log_entry.keys())
            df_combined = pd.concat([df_existing, df_log], ignore_index=True)
            if len(df_combined) > max_rows:
                df_combined = df_combined.tail(max_rows)
            df_combined.to_csv(log_file, index=False)
        else:
            df_log.to_csv(log_file, index=False)

        return {
            'date': self.today_date,
            'state': final_state,
            'duration': duration,
            'close': today_h['close'],
            'ma60': today_h['MA60'],
            'ma20': today_h['MA20'],
            'upper': upper,
            'lower': lower,
            'vol_ratio': today_h['amount'] / today_h['MA_Vol20'],
            'bias_60': bias_60,
            'a_above': a_above,
            'short_signals': short_signals,
            'sz_close': sz_close,
            'up_ratio': up_ratio      # 新增
        }

    def compute_short_signals(self, df_hs300, df_all_a, idx, today_h, today_a, final_state):
        signals = []
        
        if idx >= 20:
            h_20_high = df_hs300.iloc[idx-20:idx]['close'].max()
            if today_h['close'] > h_20_high * 1.005 and today_h['amount'] > today_h['MA_Vol20'] * 1.5:
                signals.append("BREAKOUT_BUY")
        
        if idx >= 7:
            recent_high = df_hs300.iloc[idx-7:idx]['close'].max()
            if today_h['close'] < recent_high * 0.98:
                signals.append("FALSE_BREAKOUT_WARNING")
        
        if final_state in ["SYSTEMIC_BULL", "SIDEWAYS_UP"]:
            dist_ma20 = (today_h['close'] - today_h['MA20']) / today_h['MA20']
            if -0.005 <= dist_ma20 <= 0.015 and today_h['amount'] < today_h['MA_Vol20'] * 0.8:
                signals.append("PULLBACK_BUY")
        
        bias_60 = (today_h['close'] - today_h['MA60']) / today_h['MA60']
        if bias_60 > 0.12:
            signals.append("RISK_DIVERGENCE")
        
        return signals

# ==================== 报告生成 ====================
def get_recent_history(log_file='state_history.csv', n=10):
    """读取最近 n 条历史记录，返回状态分布和信号历史"""
    if not os.path.exists(log_file):
        return None, None
    try:
        df = pd.read_csv(log_file)
        if df.empty:
            return None, None
        # 检查必需列
        if 'state' not in df.columns or 'short_signals' not in df.columns:
            print("警告：日志文件列名不匹配，跳过历史分析。")
            return None, None
        df['date'] = df['date'].astype(str).str.replace(r'\.0$', '', regex=True)
        recent = df.tail(n)
        state_dist = recent['state'].value_counts().to_dict()
        signals_history = recent[recent['short_signals'].notna() & (recent['short_signals'] != '')][['date', 'short_signals']]
        return state_dist, signals_history
    except Exception as e:
        print(f"读取历史日志失败: {e}")
        return None, None

def auto_verify_state(log_file='state_history.csv', lookback_days=5):
    """检查实盘日志的连续性与合理性（兼容同日多次运行）"""
    if not os.path.exists(log_file):
        return False, "日志文件不存在，跳过验证。"
    try:
        df = pd.read_csv(log_file)
        if df.empty:
            return False, "日志为空，跳过验证。"
        if 'state' not in df.columns or 'duration' not in df.columns:
            return False, "日志文件缺少必要列，跳过验证。"

        df['date'] = df['date'].astype(str).str.replace(r'\.0$', '', regex=True)
        df = df.sort_values('date')
        # 去重：同一天多次运行只保留最后一条
        df = df.drop_duplicates(subset=['date'], keep='last')
        df = df.tail(lookback_days)

        if len(df) < 2:
            return True, f"✅ 日志记录不足2天，跳过自检。"

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        last_duration = last_row['duration']
        prev_duration = prev_row['duration']

        if pd.isna(last_duration):
            return False, f"⚠️ 最新记录持续天数为空，请检查日志。"
        if pd.isna(prev_duration):
            prev_duration = 0

        last_duration = int(last_duration)
        prev_duration = int(prev_duration)

        # 仅在不同日期时检查天数连续性
        if last_row['date'] != prev_row['date']:
            if last_row['state'] == prev_row['state']:
                if last_duration != prev_duration + 1:
                    return False, f"⚠️ 状态持续天数异常：{prev_row['date']}→{last_row['date']} 状态相同，天数应从 {prev_duration} 变为 {prev_duration+1}，实际为 {last_duration}。"
            else:
                if last_duration != 1:
                    return False, f"⚠️ 状态切换后持续天数应为1，实际为 {last_duration}。"

        latest_date = df['date'].max()
        return True, f"✅ 日志连续且自洽，最新记录 {latest_date}。"
    except Exception as e:
        return False, f"验证过程出错: {e}"

def generate_report(data, ds_interp=None, ds_score=None):
    state = data['state']
    duration = data['duration']
    up_ratio = data.get('up_ratio', 0.5)   # ← 新增这一行
    state_cn = STATE_CN_MAP.get(state, state)
    
    # 策略路由
    if state == 'SYSTEMIC_BULL' and duration >= 2:
        advice = "【趋势跟踪策略】建议满仓或重仓"
        action_detail = "可追涨强势宽基，止损设于MA20下方2%"
    elif state == 'SYSTEMIC_BEAR' and duration >= 2:
        advice = "【防御策略】建议空仓或极轻仓避险"
        action_detail = "权益空仓，可配置货币基金或债券ETF"
    else:
        advice = "【震荡策略】建议半仓或使用网格/波段策略"
        action_detail = "高抛低吸，区间操作，严格止盈止损"
    
    # 信号解读
    signal_analysis = get_signal_analysis(data)

    # 赚钱效应双因子校验（全A指数 + 真实上涨家数）
    up_ratio = data.get('up_ratio', 0.5)
    if data['a_above'] and up_ratio > 0.55:
        money_effect = f'全A同步走强，真实上涨家数占比{up_ratio*100:.0f}%，赚钱效应良好'
    elif data['a_above'] and up_ratio <= 0.55:
        money_effect = f'⚠️ 指数走强但真实上涨家数仅{up_ratio*100:.0f}%，权重护盘特征明显'
    elif not data['a_above'] and up_ratio > 0.55:
        money_effect = f'全A走弱但上涨家数占比{up_ratio*100:.0f}%，个股活跃度尚可'
    else:
        money_effect = f'全A走弱，上涨家数占比仅{up_ratio*100:.0f}%，个股普遍下跌'
    
    # 基础报告（不含自检）
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    report = f"""
========================================
   AMSIS_V3 实盘市场状态报告
========================================
报告日期: {today_str}
数据日期: {data['date']}（最近交易日）
状态: {state_cn} (已持续 {duration} 天)
"""    
    # 状态自检
    is_consistent, verify_msg = auto_verify_state()
    if is_consistent:
        report += f"\n{verify_msg}\n"
    else:
        report += f"\n【⚠️ 日志自检异常】{verify_msg}\n"
        
    # ========================================================

    report += f"""
【核心指标】
  沪深300: {data['close']:.2f}  |  MA20: {data['ma20']:.2f}  |  MA60: {data['ma60']:.2f}
  上证指数: {data['sz_close']:.2f}
  滤波带: {data['lower']:.2f} ～ {data['upper']:.2f}
  量能倍率: {data['vol_ratio']:.2f}x  |  乖离率(60日): {data['bias_60']*100:.2f}%
  赚钱效应: {money_effect}

【关键信号解读】
  {signal_analysis}
"""

    
    # 短线信号区块
    short_signals = data.get('short_signals', [])
    if short_signals:
        signal_map = {
            'BREAKOUT_BUY': '🚀 放量突破20日高点',
            'FALSE_BREAKOUT_WARNING': '⚠️ 假突破预警',
            'PULLBACK_BUY': '📉 缩量回踩MA20',
            'RISK_DIVERGENCE': '🔥 乖离率过高风险'
        }
        readable = [signal_map.get(s, s) for s in short_signals]
        report += f"""
【短线交易信号】
  {', '.join(readable)}
"""
    
    report += f"""
【策略路由建议】
  {advice}
  → {action_detail}
"""
    
    if ds_score:
        trend_conf = ds_score.get('trend_confidence', 'N/A')
        fake_risk = ds_score.get('fake_breakout_risk', 'N/A')
        rec_strategy = ds_score.get('recommended_strategy', 'N/A')
        strategy_cn = {'trend': '趋势跟踪', 'range': '震荡策略', 'defensive': '防御避险'}.get(rec_strategy, rec_strategy)
        ds_interpret = interpret_ds_score(trend_conf, fake_risk)
        
        report += f"""
----------------------------------------
【DeepSeek 辅助评分】（仅供参考）
  趋势置信度: {trend_conf}/10（越高趋势越可靠）
  假突破风险: {fake_risk}/10（越高假突破概率越大）
  AI推荐策略: {strategy_cn}
  → {ds_interpret}
"""
    
    if ds_interp:
        report += f"""
【DeepSeek 解读】
  {ds_interp}
"""
    
    return report

# ==================== 主程序 ====================
if __name__ == "__main__":
    print("=" * 50)
    print("AMSIS_V3 实盘运行 (最优参数)")
    print("=" * 50)

    engine = LiveAMSI()
    data = engine.run()

    base_report = generate_report(data)
    state_dist, recent_signals = get_recent_history()

    interp, score = None, None
    if ds_client:
        interp, score = get_deepseek_interpretation(base_report, data['duration'], state_dist, recent_signals)

    final_report = generate_report(data, ds_interp=interp, ds_score=score)
    
    print(final_report)

    if not ds_client:
        print("\n(DeepSeek 未配置，跳过 AI 解读)")
