#!/usr/bin/env python3
# app.py - AlphaEngine 2026 现代金融级专业版 (云端适配版)
import streamlit as st
import json, os, datetime
import pandas as pd
import auth

# ==================== 全局配置与 UI ====================
st.set_page_config(page_title="AlphaEngine Pro", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
    @import url('https://gs.jurieo.com/gemini/fonts-googleapis/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');
    :root { --bull-red: #EF4444; --bear-green: #10B981; --ai-purple: #818CF8; --focus-amber: #F59E0B; --accent-blue: #3B82F6; }
    .ms-icon { font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal; font-size: 1.2rem; line-height: 1; vertical-align: middle; margin-right: 6px; }
    .stApp { font-family: 'Inter', "PingFang SC", -apple-system, sans-serif; }
    .za-card { background-color: var(--secondary-background-color); border-radius: 14px; padding: 24px; margin-bottom: 20px; border: 1px solid rgba(128,128,128,0.15); box-shadow: 0 4px 20px rgba(0,0,0,0.03); }
    .metric-label { font-size: 0.85rem; opacity: 0.6; font-weight: 600; margin-bottom: 4px; }
    .metric-value { font-size: 2.2rem; font-weight: 800; }
    .order-item { background: var(--background-color); border-left: 4px solid var(--bull-red); border-radius: 10px; padding: 16px; margin-bottom: 12px; }
    .order-sell { border-left-color: var(--bear-green); }
    .ai-insight-box { background: var(--background-color); border-left: 4px solid var(--ai-purple); border-radius: 12px; padding: 20px; }
    .focus-box { padding: 16px; background: rgba(245,158,11,0.06); border-left: 4px solid var(--focus-amber); border-radius: 8px; }
    .rank-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px dashed rgba(128,128,128,0.15); }
    .table-container { overflow-x: auto; border-radius: 8px; border: 1px solid rgba(128,128,128,0.15); }
    .pro-table { width: 100%; border-collapse: collapse; }
    .pro-table th { opacity: 0.6; font-size: 0.8rem; padding: 6px 12px; }
    .pro-table td { font-size: 0.9rem; padding: 6px 12px; }
    .stButton>button { border-radius: 8px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# ==================== 路径动态适配 ====================
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

def load_dashboard_data(username):
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    json_file = os.path.join(REPORT_DIR, username, f"dashboard_{today_str}.json")
    if os.path.exists(json_file):
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def format_date_str(date_str):
    if date_str and len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str

# ==================== 侧边栏与登录 ====================
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

# ==================== 核心业务逻辑 ====================
username = st.session_state.username
portfolio = load_holdings(username)
pool = load_pool()
dash_data = load_dashboard_data(username)

actual_mkt_val = 0.0
total_cost = 0.0
for c, h in portfolio['holdings'].items():
    curr_p = get_latest_price(c) or h['cost']
    actual_mkt_val += curr_p * h['qty']
    total_cost += h['cost'] * h['qty']

total_assets = portfolio['cash'] + actual_mkt_val
total_profit = actual_mkt_val - total_cost
profit_pct = (total_profit / (portfolio['cash'] + total_cost) * 100) if (portfolio['cash'] + total_cost) > 0 else 0.0

# V3 状态直接读取 last_state.json ，确保即使没有 dashboard 也能展示
v3_state = load_v3_state()
light_text = "未知"
if v3_state:
    s = v3_state.get("state", "")
    light_map = {"SYSTEMIC_BULL": "🟢 牛市", "SYSTEMIC_BEAR": "🔴 熊市", "SIDEWAYS_UP": "🟡 震荡偏强", "SIDEWAYS_DOWN": "🟠 震荡偏弱", "SIDEWAYS": "⚪ 中性震荡"}
    light_text = light_map.get(s, s)

if not dash_data:
    st.warning("今日决策数据尚未生成。请等待 GitHub Actions 自动运行（每个交易日 8:30 后），或手动触发一次。")
    st.stop()

# 提取 V3 详细指标
v3_info = dash_data.get('v3_state', {})
state_raw = v3_info.get('state', 'UNKNOWN')
state_color_map = {
    "SYSTEMIC_BULL": ("#10B981", "rgba(16, 185, 129, 0.12)", "🟢 系统性牛市"),
    "SYSTEMIC_BEAR": ("#EF4444", "rgba(239, 68, 68, 0.12)", "🔴 系统性熊市"),
    "SIDEWAYS_UP": ("#F59E0B", "rgba(245, 158, 11, 0.12)", "🟡 震荡偏强"),
    "SIDEWAYS_DOWN": ("#F97316", "rgba(249, 115, 22, 0.12)", "🟠 震荡偏弱"),
    "SIDEWAYS": ("#6B7280", "rgba(107, 114, 128, 0.12)", "⚪ 中性震荡")
}
v3_color, v3_bg, v3_cn = state_color_map.get(state_raw, ("#6B7280", "rgba(107, 114, 128, 0.12)", f"⚪ {state_raw}"))
raw_trade_date = dash_data.get('trade_date', '今日')
display_trade_date = format_date_str(raw_trade_date)

# ----------------- 决策大屏 -----------------
if "决策大屏" in page:
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.markdown(f"""
        <div class="flex-header">
            <h3><span class='ms-icon'>dashboard</span>Decision Dashboard</h3>
            <span class="date-badge"><span class="ms-icon">calendar_today</span>基于 {display_trade_date} 盘后数据</span>
        </div>
        """, unsafe_allow_html=True)
    with head_col2:
        st.write("")
        # 按钮仅作提示，不再尝试运行子进程
        st.button("🔄 数据由 Actions 自动更新", disabled=True, help="每日 8:30 自动运行，或手动触发 GitHub Actions", use_container_width=True)

    # 顶部卡片
    st.markdown(f"""
    <div class="grid-4" style="margin-bottom:24px;">
        <div class="za-card"><div class="metric-label">账户最新估值</div><div class="metric-value tabular-num">{total_assets:,.2f} <span class="metric-unit">CNY</span></div>
        <div style="font-size:0.85rem; color:{'var(--bull-red)' if total_profit>0 else 'var(--bear-green)' if total_profit<0 else 'gray'}; font-weight:700;">{'+' if total_profit>0 else ''}{total_profit:,.2f} ({profit_pct:+.2f}%)</div></div>
        <div class="za-card"><div class="metric-label">配置战备</div><div class="metric-value tabular-num">{len(portfolio['holdings'])} <span class="metric-unit">Positions</span></div></div>
        <div class="za-card"><div class="metric-label">宏观气温 (V3)</div><div style="margin-top:10px;"><span style="background:{v3_bg}; color:{v3_color}; padding:6px 14px; border-radius:8px; font-size:0.95rem; font-weight:700; border:1px solid {v3_color}40;">{v3_cn}</span></div></div>
        <div class="za-card"><div class="metric-label">状态延续</div><div class="metric-value tabular-num">{v3_info.get('duration', 0)} <span class="metric-unit">Days</span></div></div>
    </div>
    """, unsafe_allow_html=True)

    # 核心盘面参数
    hs300_close = v3_info.get('close', 0)
    ma20 = v3_info.get('ma20', 0)
    ma60 = v3_info.get('ma60', 0)
    sz_close = v3_info.get('sz_close', 0)
    lower = v3_info.get('lower', 0)
    upper = v3_info.get('upper', 0)
    vol_ratio = v3_info.get('vol_ratio', 0)
    bias_60 = v3_info.get('bias_60', 0) * 100
    up_ratio = v3_info.get('up_ratio', 0.5)
    a_above = v3_info.get('a_above', False)

    if a_above and up_ratio > 0.55:
        money_effect = f'🟢 全A同步走强，真实上涨占比 {up_ratio*100:.0f}%'
    elif a_above and up_ratio <= 0.55:
        money_effect = f'⚠️ 指数走强但真实上涨仅 {up_ratio*100:.0f}%'
    elif not a_above and up_ratio > 0.55:
        money_effect = f'🟡 全A走弱但上涨占比 {up_ratio*100:.0f}%'
    else:
        money_effect = f'🔴 全A走弱，上涨家数占比仅 {up_ratio*100:.0f}%'

    st.markdown(f"""<div class="za-card" style="padding: 24px;">
<div style="font-size:1.1rem; font-weight:800; margin-bottom:20px;"><span class="ms-icon" style="color:var(--accent-blue);">analytics</span>核心盘面参数</div>
<div class="grid-3" style="margin-bottom:20px;">
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px;">
<div style="font-size:0.85rem; opacity:0.6; font-weight:600;">沪深300阵地</div>
<div style="font-size:1.8rem; font-weight:800;">{hs300_close:,.2f}</div>
<div style="font-size:0.85rem; display:flex; gap:16px;"><span>MA20: {ma20:,.2f}</span><span>MA60: {ma60:,.2f}</span></div>
</div>
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px;">
<div style="font-size:0.85rem; opacity:0.6; font-weight:600;">上证与动能监控</div>
<div style="font-size:1.8rem; font-weight:800;">{sz_close:,.2f}</div>
<div style="font-size:0.85rem; display:flex; gap:16px;"><span>量能倍率: {vol_ratio:.2f}x</span><span>乖离率: {bias_60:+.2f}%</span></div>
</div>
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px;">
<div style="font-size:0.85rem; opacity:0.6; font-weight:600;">V3滤波缓冲带</div>
<div style="font-size:1.3rem; font-weight:700;">{lower:,.2f} ~ {upper:,.2f}</div>
<div style="font-size:0.8rem; opacity:0.5;">跌破下沿触发系统性熊市预警</div>
</div>
</div>
<div style="background:rgba(59,130,246,0.08); border-left:4px solid var(--accent-blue); padding:14px 20px; border-radius:8px;">
<div style="font-size:0.9rem; color:var(--accent-blue); font-weight:800;">赚钱效应雷达</div>
<div style="font-size:0.95rem; opacity:0.9; font-weight:600;">{money_effect}</div>
</div>
</div>""", unsafe_allow_html=True)

    # AI 推演层
    ai_data = dash_data.get('ai_analysis', {})
    raw_v3_interp = ai_data.get('v3_interp', '')
    main_interp = raw_v3_interp
    core_focus = ""
    if "【核心关注点】" in raw_v3_interp:
        parts = raw_v3_interp.split("【核心关注点】")
        main_interp = parts[0].strip()
        core_focus = parts[1].strip()
    if "【情景A" in main_interp:
        main_interp = "【情景A" + main_interp.split("【情景A", 1)[1]

    col_ai_1, col_ai_2 = st.columns([1, 1.5])
    with col_ai_1:
        html_col1 = f"""<div class="ai-insight-box" style="flex-grow:1;">
<div style="color:var(--ai-purple); font-weight:800; margin-bottom:14px;"><span class="ms-icon">security</span>风控建议</div>
<div style="font-size:0.95rem; line-height:1.7;">{ai_data.get('risk_tip', '系统平稳运行').replace(chr(10), '<br>')}</div>
</div>"""
        if core_focus:
            html_col1 += f"""<div class="focus-box" style="margin-top:16px;">
<div style="font-weight:800; color:var(--focus-amber); margin-bottom:8px;"><span class="ms-icon">my_location</span>核心观察锚点</div>
<div style="font-size:0.95rem;">{core_focus}</div>
</div>"""
        st.markdown(html_col1, unsafe_allow_html=True)

    with col_ai_2:
        if raw_v3_interp:
            st.markdown(f"""<div class="za-card" style="border-top:3px solid rgba(128,128,128,0.3);">
<h4><span class="ms-icon">account_tree</span>情景推演与路由</h4>
<div style="font-size:0.95rem; line-height:1.8; opacity:0.85;">{main_interp.replace(chr(10), '<br>')}</div>
</div>""", unsafe_allow_html=True)

    st.write("---")

    # 交易指令与排行
    col_left, col_right = st.columns([1.5, 1])
    with col_left:
        st.markdown("<h4><span class='ms-icon'>receipt_long</span>绝对执行清单</h4>", unsafe_allow_html=True)
        orders = dash_data.get('orders', [])
        orders_html = "<div class='za-card' style='min-height:240px;'>"
        if not orders:
            orders_html += "<div style='text-align:center; opacity:0.4; padding:40px;'><span class='ms-icon' style='font-size:3rem;'>check_circle</span><br>仓位结构稳定，今日无调仓信号。</div>"
        else:
            for o in orders:
                is_buy = o['action'] == '买入'
                clss = "order-buy" if is_buy else "order-sell"
                icon_name = "trending_up" if is_buy else "trending_down"
                color = "var(--bull-red)" if is_buy else "var(--bear-green)"
                orders_html += f"""<div class="order-item {clss}">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
<span style="font-size:1.1rem; font-weight:800; color:{color};"><span class="ms-icon">{icon_name}</span>{o['action']} {o['name']} ({o['code']})</span>
<span style="background:rgba(128,128,128,0.06); padding:6px 12px; border-radius:6px; font-weight:700;">{o['qty']} 股</span>
</div>"""
                if o.get('reason'): orders_html += f"<div style='font-size:0.9rem; opacity:0.8; margin-bottom:6px;'><b>触发机制:</b> {o['reason']}</div>"
                if o.get('range'): orders_html += f"<div style='font-size:0.9rem; opacity:0.8;'><b>执行区间:</b> {o['range']} 元</div>"
                orders_html += "</div>"
        orders_html += "</div>"
        st.markdown(orders_html, unsafe_allow_html=True)

    with col_right:
        st.markdown("<h4><span class='ms-icon'>leaderboard</span>动量势能榜 Top 5</h4>", unsafe_allow_html=True)
        ranks = dash_data.get('rankings', [])
        ranks_html = "<div class='za-card' style='min-height:240px;'>"
        if not ranks:
            ranks_html += "<div style='text-align:center; opacity:0.4; padding:40px;'><span class='ms-icon' style='font-size:3rem;'>blur_on</span><br>无标的上榜</div>"
        else:
            for r in ranks:
                n_clss = "rank-num-top" if int(r['num']) <= 3 else ""
                ranks_html += f"""<div class="rank-row">
<div style="display:flex; align-items:center;"><div class="rank-num {n_clss}">{r['num']}</div><div style="font-weight:600;">{r['name']} <span style="opacity:0.5; margin-left:6px;">{r['code']}</span></div></div>
<div style="color:var(--bull-red); font-weight:800;">S={r['score']}</div>
</div>"""
        ranks_html += "</div>"
        st.markdown(ranks_html, unsafe_allow_html=True)

# ----------------- 资产账本 -----------------
elif "资产账本" in page:
    st.markdown("<h3><span class='ms-icon'>account_balance_wallet</span>Portfolio Ledger</h3>", unsafe_allow_html=True)
    st.markdown(f"""
    <div class="za-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:20px; background:linear-gradient(135deg, rgba(59,130,246,0.08) 0%, transparent 100%);">
        <div>
            <div class="metric-label">总资产净值 (CNY)</div>
            <div style="font-size:2.8rem; font-weight:800;" class="tabular-num">{total_assets:,.2f}</div>
            <div style="font-size:1.05rem; color:{'var(--bull-red)' if total_profit>0 else 'var(--bear-green)' if total_profit<0 else 'gray'}; font-weight:700;">总持仓盈亏：{'+' if total_profit>0 else ''}{total_profit:,.2f} ({profit_pct:+.2f}%)</div>
        </div>
        <div style="text-align:right;">
            <div class="metric-label">可用现金余额</div>
            <div style="font-size:1.6rem; font-weight:800; color:#3B82F6;">{portfolio['cash']:,.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<h4><span class='ms-icon'>inventory_2</span>当前持有仓位明细</h4>", unsafe_allow_html=True)
    if portfolio['holdings']:
        html_table = '''<div class="table-container"><table class="pro-table"><thead><tr>
        <th>标的资产</th><th>持有数量</th><th>持仓均价</th><th>最新现价</th><th>止盈价格</th><th>止损价格</th><th>浮动盈亏</th></tr></thead><tbody>'''
        for c, h in portfolio['holdings'].items():
            curr_p = get_latest_price(c) or h['cost']
            cost, qty = h['cost'], h['qty']
            highest = h.get('highest', cost)
            pct = (curr_p - cost) / cost * 100
            amt = (curr_p - cost) * qty
            color = "#EF4444" if pct > 0 else ("#10B981" if pct < 0 else "gray")
            stop_loss = cost * 0.92
            if pct >= 20: take_profit = highest * 0.88
            elif pct >= 8: take_profit = highest * 0.92
            else: take_profit = stop_loss
            actual_take_profit = max(take_profit, stop_loss)
            actual_stop_loss = stop_loss
            price_color = "#EF4444" if curr_p > cost else ("#10B981" if curr_p < cost else "gray")
            html_table += f'''<tr>
                <td><b>{h['name']}</b> {c}</td>
                <td>{qty:,}</td><td>{cost:.3f}</td><td style="color:{price_color}">{curr_p:.3f}</td>
                <td>{actual_take_profit:.3f}</td><td>{actual_stop_loss:.3f}</td>
                <td style="color:{color}">{'+' if pct>0 else ''}{amt:,.2f} ({'+' if pct>0 else ''}{pct:.2f}%)</td></tr>'''
        html_table += '</tbody></table></div>'
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.info("空仓")

    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<h5><span class='ms-icon'>edit_square</span>交易流水补录</h5>", unsafe_allow_html=True)
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
        cq, cp = st.columns(2)
        with cq: qty = st.number_input("成交量 (股)", min_value=100, step=100)
        with cp: prc = st.number_input("成交价 (元)", min_value=0.001, format="%.3f")
        dt = st.text_input("确认日期", value=datetime.datetime.now().strftime('%Y%m%d'))
        if st.button("提交记录", type="primary", use_container_width=True):
            if not final_code or (manual and not matched_name): st.error("证券代码或名称不完整")
            else:
                name = matched_name or pool.get(final_code, final_code)
                if act == "买入":
                    cost_amt = qty * prc
                    if cost_amt > portfolio['cash']: st.error("可用资金不足")
                    else:
                        portfolio['cash'] -= cost_amt
                        if final_code in portfolio['holdings']:
                            h = portfolio['holdings'][final_code]
                            h['cost'] = round((h['qty']*h['cost'] + cost_amt)/(h['qty']+qty), 4)
                            h['qty'] += qty; h['highest'] = max(h.get('highest', 0.0), prc)
                        else: portfolio['holdings'][final_code] = {"name": name, "qty": qty, "cost": prc, "buy_date": dt, "highest": prc}
                        save_holdings(username, portfolio); st.success("记录成功"); st.rerun()
                else:
                    if final_code not in portfolio['holdings']: st.error("查无此持仓")
                    elif qty > portfolio['holdings'][final_code]['qty']: st.error("超过实际持仓数量")
                    else:
                        portfolio['cash'] += qty * prc
                        portfolio['holdings'][final_code]['qty'] -= qty
                        if portfolio['holdings'][final_code]['qty'] <= 0: del portfolio['holdings'][final_code]
                        save_holdings(username, portfolio); st.success("记录成功"); st.rerun()
    with c2:
        st.markdown("<h5><span class='ms-icon'>account_balance</span>资金划转</h5>", unsafe_allow_html=True)
        f_act = st.selectbox("业务类型", ["入金 (转入证券账户)", "出金 (转出至银行卡)"])
        f_amt = st.number_input("划转金额 (CNY)", min_value=0.0, step=1000.0)
        if st.button("确认划转", use_container_width=True):
            if "入金" in f_act: 
                portfolio['cash'] += f_amt; save_holdings(username, portfolio); st.rerun()
            elif f_amt <= portfolio['cash']: 
                portfolio['cash'] -= f_amt; save_holdings(username, portfolio); st.rerun()
            else: st.error("可用现金不足")
