#!/usr/bin/env python3
# app.py - AlphaEngine 2026 现代金融级专业版（云端适配）
import streamlit as st
import json, os, datetime
import pandas as pd
import auth

# ==================== 1. 全局配置与现代专业 UI 注入 ====================
st.set_page_config(page_title="AlphaEngine Pro", layout="wide", initial_sidebar_state="expanded")

# 引入 Google Material Symbols 矢量图标库 & 现代金融响应式样式
st.markdown("""
<style>
    @import url('https://gs.jurieo.com/gemini/fonts-googleapis/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');
    
    :root {
        --bull-red: #EF4444;
        --bear-green: #10B981;
        --ai-purple: #818CF8;
        --focus-amber: #F59E0B;
        --accent-blue: #3B82F6;
    }
    
    .ms-icon {
        font-family: 'Material Symbols Rounded';
        font-weight: normal; font-style: normal; font-size: 1.2rem;
        line-height: 1; vertical-align: middle; margin-right: 6px;
        -webkit-font-smoothing: antialiased;
    }
    
    .stApp { font-family: 'Inter', "PingFang SC", -apple-system, sans-serif; }
    
    .za-card {
        background-color: var(--secondary-background-color);
        border-radius: 14px; padding: 24px; margin-bottom: 20px;
        border: 1px solid rgba(128, 128, 128, 0.15);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
    }
    
    .metric-label { font-size: 0.85rem; opacity: 0.6; font-weight: 600; margin-bottom: 4px;}
    .metric-value { font-size: 2.2rem; font-weight: 800; }
    
    .order-item {
        background-color: var(--background-color);
        border-left: 4px solid var(--bull-red);
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
    }
    .order-sell { border-left-color: var(--bear-green); }
    
    .ai-insight-box {
        background-color: var(--background-color);
        border-left: 4px solid var(--ai-purple);
        border-radius: 12px; padding: 20px;
    }
    
    .focus-box {
        padding: 16px; background-color: rgba(245, 158, 11, 0.06);
        border-left: 4px solid var(--focus-amber); border-radius: 8px;
    }
    
    .rank-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px dashed rgba(128,128,128,0.15); }
    
    .table-container { overflow-x: auto; border-radius: 8px; border: 1px solid rgba(128,128,128,0.15); }
    .pro-table { width: 100%; border-collapse: collapse; }
    .pro-table th { opacity: 0.6; font-size: 0.8rem; padding: 6px 12px; }
    .pro-table td { font-size: 0.9rem; padding: 6px 12px; }
    
    .stButton>button { border-radius: 8px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. 动态路径（云端自动适配） ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "backtestdata")
POOL_FILE = os.path.join(BASE_DIR, "etf_pool.csv")
REPORT_DIR = os.path.join(BASE_DIR, "logs")
V3_STATE_FILE = os.path.join(BASE_DIR, "last_state.json")

def load_pool():
    if os.path.exists(POOL_FILE):
        df = pd.read_csv(POOL_FILE, encoding='utf-8')
        return dict(zip(df['code'].str.strip(), df['name'].str.strip()))
    return {}

def load_v3_state():
    if os.path.exists(V3_STATE_FILE):
        with open(V3_STATE_FILE, encoding='utf-8') as f:
            return json.load(f)
    return None

def load_holdings(username):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    if os.path.exists(file):
        with open(file, encoding='utf-8') as f: return json.load(f)
    return {"cash": 100000.0, "holdings": {}, "peak_nav": 100000.0}

def save_holdings(username, data):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    with open(file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

def get_latest_price(code):
    file_path = os.path.join(DATA_DIR, f"etf_{code}.csv")
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            return float(df['close'].iloc[-1])
        except: pass
    return 0.0

def extract_section(text, start_marker, end_marker=None):
    start = text.find(start_marker)
    if start == -1: return ""
    start += len(start_marker)
    if end_marker:
        end = text.find(end_marker, start)
        return text[start:end].strip() if end != -1 else text[start:].strip()
    return text[start:].strip()

# ==================== 3. 侧边栏与导航 ====================
if "logged_in" not in st.session_state: st.session_state.logged_in = False

with st.sidebar:
    st.markdown("<h2 style='font-weight:800;'><span class='ms-icon' style='color:#3B82F6;'>monitoring</span>AlphaEngine</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:0.85rem; opacity:0.5; margin-left:32px;'>量化决策中枢 Pro</p>", unsafe_allow_html=True)
    
    if st.session_state.logged_in:
        username = st.session_state.username
        st.success(f"操作员：{username}")
        page = st.radio("系统导航", ["决策大屏 (Dashboard)", "资产账本 (Portfolio)"], label_visibility="collapsed")
        if st.button("安全退出"): auth.logout()
    else:
        st.info("请完成身份验证")

if not st.session_state.logged_in:
    col_a, col_b, col_c = st.columns([1, 1.5, 1])
    with col_b:
        tab1, tab2 = st.tabs(["系统登录", "注册账户"])
        with tab1: auth.login()
        with tab2: auth.register()
    st.stop()

# ==================== 4. 核心业务逻辑 ====================
username = st.session_state.username
portfolio = load_holdings(username)
pool = load_pool()

# 核算真实资产
actual_mkt_val = 0.0
total_cost = 0.0
for c, h in portfolio['holdings'].items():
    curr_p = get_latest_price(c) or h['cost']
    actual_mkt_val += curr_p * h['qty']
    total_cost += h['cost'] * h['qty']

total_assets = portfolio['cash'] + actual_mkt_val
total_profit = actual_mkt_val - total_cost
profit_pct = (total_profit / (portfolio['cash'] + total_cost) * 100) if (portfolio['cash'] + total_cost) > 0 else 0.0

# V3 状态
v3_state = load_v3_state()
light_text = "未知"
if v3_state:
    s = v3_state.get("state", "")
    light_map = {"SYSTEMIC_BULL": "🟢 牛市", "SYSTEMIC_BEAR": "🔴 熊市", "SIDEWAYS_UP": "🟡 震荡偏强", "SIDEWAYS_DOWN": "🟠 震荡偏弱", "SIDEWAYS": "⚪ 中性震荡"}
    light_text = light_map.get(s, s)

# 今日日报
today_str = datetime.datetime.now().strftime('%Y-%m-%d')
report_dir = os.path.join(REPORT_DIR, username)
report_file = os.path.join(report_dir, f"report_{today_str}.txt")

# ----------------- 页面 A: 决策大屏 -----------------
if "决策大屏" in page:
    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:16px; margin-bottom:10px;">
        <h3 style="margin:0;"><span class='ms-icon'>dashboard</span>Decision Dashboard</h3>
        <span style="background:rgba(128,128,128,0.08); padding:6px 12px; border-radius:8px; font-size:0.85rem;">基于 {v3_state.get('date', today_str) if v3_state else today_str} 盘后数据</span>
    </div>
    """, unsafe_allow_html=True)

    # 顶部卡片
    st.markdown(f"""
    <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:20px; margin-bottom:24px;">
        <div class="za-card"><div class="metric-label">账户估值</div><div class="metric-value">{total_assets:,.2f} CNY</div><div>{total_profit:+,.2f} ({profit_pct:+.2f}%)</div></div>
        <div class="za-card"><div class="metric-label">持仓品种</div><div class="metric-value">{len(portfolio['holdings'])}</div></div>
        <div class="za-card"><div class="metric-label">V3 气温</div><div style="font-size:1.5rem;">{light_text}</div></div>
        <div class="za-card"><div class="metric-label">持续天数</div><div class="metric-value">{v3_state.get('duration', 0) if v3_state else 0} Days</div></div>
    </div>
    """, unsafe_allow_html=True)

    # 日报内容
    if not os.path.exists(report_file):
        st.warning("今日日报尚未生成，等待 GitHub Actions 自动运行（每个交易日 8:30 后生成）。")
    else:
        full_report = open(report_file, encoding='utf-8').read()

        # 指令
        orders = extract_section(full_report, "📋 【今日绝对执行指令】", "🏆 【今日ETF排行榜")
        if orders:
            orders_clean = orders.replace('\n【今日ETF排行榜', '').strip()
            st.markdown("### 📋 今日交易指令")
            st.markdown(f'<div class="za-card">{orders_clean.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)

        # AI 解读
        st.markdown("### 🤖 AI 综合解读")
        v3_ai = extract_section(full_report, "━━━ V3 市场深度报告 ━━━", "💼 【账户快照】")
        strategy_ai = extract_section(full_report, "🤖 【DeepSeek风控参谋】", "━━━ V3 市场深度报告 ━━━")
        if v3_ai or strategy_ai:
            combined = ""
            if v3_ai: combined += f"**📡 V3 市场解读**<br>{v3_ai.replace(chr(10), '<br>')}<br><br>"
            if strategy_ai: combined += f"**⚡ 策略风控**<br>{strategy_ai.replace(chr(10), '<br>')}"
            st.markdown(f'<div class="za-card">{combined}</div>', unsafe_allow_html=True)

        # TOP5
        st.markdown("### 🏆 TOP5 信号")
        rankings = []
        with open(report_file, encoding='utf-8') as f:
            for line in f:
                if line.startswith("🏆"):
                    continue
                parts = line.strip().split()
                if len(parts) >= 4 and parts[0].isdigit():
                    try:
                        code = parts[-2] if '(' in parts[-2] else parts[-3]
                        score = float(parts[-1].replace('S=',''))
                        name = ' '.join(parts[1:-2]).split('(')[0].strip()
                        rankings.append({"排名": parts[0], "名称": name, "代码": code, "S分": score})
                    except: pass
                    if len(rankings) == 5: break
        if rankings:
            st.dataframe(pd.DataFrame(rankings), use_container_width=True, hide_index=True)

# ----------------- 页面 B: 资产账本 -----------------
elif "资产账本" in page:
    st.markdown("<h3><span class='ms-icon'>account_balance_wallet</span>Portfolio Ledger</h3>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="za-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:20px;">
        <div>
            <div class="metric-label">总资产净值</div>
            <div class="metric-value">{total_assets:,.2f} CNY</div>
            <div>持仓盈亏：{total_profit:+,.2f} ({profit_pct:+.2f}%)</div>
        </div>
        <div style="text-align:right;">
            <div class="metric-label">可用现金</div>
            <div style="font-size:1.6rem; font-weight:800; color:#3B82F6;">{portfolio['cash']:,.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if portfolio['holdings']:
        html_table = '''<div class="table-container"><table class="pro-table"><thead><tr>
        <th>标的资产</th><th>持有数量</th><th>持仓均价</th><th>最新现价</th><th>止盈</th><th>止损</th><th>浮动盈亏</th></tr></thead><tbody>'''
        for c, h in portfolio['holdings'].items():
            curr_p = get_latest_price(c) or h['cost']
            cost, qty = h['cost'], h['qty']
            pct = (curr_p - cost) / cost * 100
            amt = (curr_p - cost) * qty
            color = "#EF4444" if pct > 0 else ("#10B981" if pct < 0 else "gray")
            stop_loss = cost * 0.92
            take_profit = max(h.get('highest', cost) * (0.88 if pct >= 20 else 0.92 if pct >= 8 else 1), stop_loss)
            html_table += f'''<tr>
                <td><b>{h['name']}</b> {c}</td>
                <td>{qty:,}</td><td>{cost:.3f}</td><td style="color:{color}">{curr_p:.3f}</td>
                <td>{take_profit:.3f}</td><td>{stop_loss:.3f}</td>
                <td style="color:{color}">{'+' if pct>0 else ''}{amt:,.2f} ({'+' if pct>0 else ''}{pct:.2f}%)</td></tr>'''
        html_table += '</tbody></table></div>'
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.info("空仓")

    # 下单与资金划转
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<h5>交易流水补录</h5>", unsafe_allow_html=True)
        act = st.radio("交易方向", ["买入", "卖出"], horizontal=True)
        manual = st.checkbox("自定义池外资产")
        code_in = st.text_input("证券代码 (如 510300)")
        matched_name, final_code = "", None
        if code_in:
            raw = code_in.strip()
            final_code = raw if '.' in raw else None
            for sfx in ['.SZ','.SH']:
                if (raw+sfx) in pool or (raw+sfx) in portfolio.get('holdings',{}): final_code = raw+sfx; break
            if final_code in pool: matched_name = pool[final_code]
            elif manual: matched_name = st.text_input("资产名称")
        qty = st.number_input("数量", min_value=100, step=100)
        prc = st.number_input("价格", min_value=0.001, format="%.3f")
        if st.button("提交记录"):
            if act == "买入" and (cost_amt := qty * prc) > portfolio['cash']: st.error("资金不足")
            else:
                name = matched_name or pool.get(final_code, final_code)
                if act == "买入":
                    portfolio['cash'] -= cost_amt
                    if final_code in portfolio['holdings']:
                        h = portfolio['holdings'][final_code]
                        h['cost'] = round((h['qty']*h['cost']+cost_amt)/(h['qty']+qty), 4)
                        h['qty'] += qty; h['highest'] = max(h['highest'], prc)
                    else: portfolio['holdings'][final_code] = {"name":name,"qty":qty,"cost":prc,"highest":prc,"buy_date":datetime.now().strftime('%Y%m%d')}
                else:
                    if final_code in portfolio['holdings'] and qty <= portfolio['holdings'][final_code]['qty']:
                        portfolio['cash'] += qty * prc
                        portfolio['holdings'][final_code]['qty'] -= qty
                        if portfolio['holdings'][final_code]['qty'] == 0: del portfolio['holdings'][final_code]
                save_holdings(username, portfolio); st.rerun()
    with c2:
        st.markdown("<h5>资金划转</h5>", unsafe_allow_html=True)
        f_act = st.selectbox("业务类型", ["入金", "出金"])
        f_amt = st.number_input("金额", min_value=0.0, step=1000.0)
        if st.button("确认划转"):
            if f_act == "入金": portfolio['cash'] += f_amt
            elif f_amt <= portfolio['cash']: portfolio['cash'] -= f_amt
            else: st.error("可用现金不足")
            save_holdings(username, portfolio); st.rerun()
