原本的app.py代码如下：
#!/usr/bin/env python3
# app.py - AlphaEngine 2026 现代金融级专业版 (V3色彩标签 + 紧凑数据表 + 动态风控可视化)
import streamlit as st
import json, os, subprocess, sys, datetime
import pandas as pd
import auth

# ==================== 1. 全局配置与现代专业 UI 注入 ====================
st.set_page_config(page_title="AlphaEngine Pro", layout="wide", initial_sidebar_state="expanded")

# 引入 Google Material Symbols 矢量图标库 & 现代金融响应式样式
st.markdown("""
<style>
    @import url('https://gs.jurieo.com/gemini/fonts-googleapis/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');
    
    /* 核心语义色彩 */
    :root {
        --bull-red: #EF4444;
        --bear-green: #10B981;
        --ai-purple: #818CF8;
        --focus-amber: #F59E0B;
        --accent-blue: #3B82F6;
    }
    
    /* 矢量图标基础类 */
    .ms-icon {
        font-family: 'Material Symbols Rounded';
        font-weight: normal; font-style: normal; font-size: 1.2rem;
        line-height: 1; vertical-align: middle; margin-right: 6px;
        -webkit-font-smoothing: antialiased;
    }
    
    .stApp { font-family: 'Inter', "PingFang SC", -apple-system, sans-serif; }
    
    
    /* 核心便当盒 (Bento Box) */
    .za-card {
        background-color: var(--secondary-background-color);
        border-radius: 14px; padding: 24px; margin-bottom: 20px;
        border: 1px solid rgba(128, 128, 128, 0.15);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03);
        transition: all 0.3s ease;
    }
    .za-card:hover {
        box-shadow: 0 6px 24px rgba(0, 0, 0, 0.06);
    }
    
    /* 数据排版层级 */
    .metric-group { display: flex; flex-direction: column; gap: 4px; }
    .metric-label { font-size: 0.85rem; color: var(--text-color); opacity: 0.6; font-weight: 600; margin-bottom: 4px;}
    .metric-value { font-size: 2.2rem; font-weight: 800; color: var(--text-color); font-family: ui-sans-serif, system-ui; display: flex; align-items: baseline; gap: 8px; font-variant-numeric: tabular-nums;}
    .metric-unit { font-size: 0.9rem; color: var(--text-color); opacity: 0.5; font-weight: 500; }
    
    /* 专业金融数值字体类（等宽数字） */
    .tabular-num { font-variant-numeric: tabular-nums; font-family: ui-sans-serif, system-ui; }
    
    /* 指令清单优化 */
    .order-item {
        background-color: var(--background-color);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-left: 4px solid var(--bull-red);
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
    }
    .order-buy { border-left-color: var(--bull-red); }
    .order-sell { border-left-color: var(--bear-green); }
    
    /* AI 解析模块 */
    .ai-insight-box {
        background-color: var(--background-color);
        border: 1px solid rgba(129, 140, 248, 0.2);
        border-radius: 12px; padding: 20px; position: relative; overflow: hidden;
    }
    .ai-insight-box::before { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--ai-purple); }
    
    /* 核心关注点高亮框 */
    .focus-box {
        padding: 16px; background-color: rgba(245, 158, 11, 0.06);
        border-left: 4px solid var(--focus-amber); border-radius: 8px;
    }
    
    /* 排行榜 */
    .rank-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px dashed rgba(128, 128, 128, 0.15); }
    .rank-row:last-child { border-bottom: none; }
    .rank-num { width: 26px; height: 26px; border-radius: 6px; background: rgba(128, 128, 128, 0.1); color: var(--text-color); display: flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: 700; margin-right: 12px; }
    .rank-num-top { background: rgba(239, 68, 68, 0.12) !important; color: var(--bull-red) !important; }
    
    /* 日期标签 */
    .date-badge {
        font-size: 0.85rem; font-weight: 600; color: var(--text-color); opacity: 0.8;
        background: rgba(128, 128, 128, 0.08); padding: 6px 12px; border-radius: 8px;
        display: inline-flex; align-items: center; border: 1px solid rgba(128,128,128,0.1);
    }

    /* ★ 紧凑版高定数据表 CSS ★ */
    .table-container { overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; border-radius: 8px; border: 1px solid rgba(128,128,128,0.15); }
    .pro-table { width: 100%; border-collapse: collapse; min-width: 700px; background: var(--background-color); }
    .pro-table th { color: var(--text-color); opacity: 0.6; font-weight: 600; font-size: 0.8rem; padding: 10px 14px; border-bottom: 1px solid rgba(128,128,128,0.2); white-space: nowrap; background: rgba(128,128,128,0.03); }
    .pro-table td { color: var(--text-color); font-weight: 600; font-size: 0.9rem; padding: 12px 14px; border-bottom: 1px solid rgba(128,128,128,0.1); vertical-align: middle; }
    .pro-table tr:last-child td { border-bottom: none; }
    .pro-table tr:hover { background-color: rgba(128,128,128,0.04); }
    .text-left { text-align: left; }
    .text-right { text-align: right; }
    
    /* 响应式网格 */
    .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
    .flex-header { display: flex; align-items: baseline; gap: 16px; margin-bottom: 0; flex-wrap: wrap; }
    
    @media (max-width: 1024px) {
        .grid-4 { grid-template-columns: repeat(2, 1fr); }
    }
    @media (max-width: 768px) {
        .grid-4 { grid-template-columns: 1fr; }
        .grid-3 { grid-template-columns: 1fr; }
        .metric-value { font-size: 1.8rem; }
        .za-card { padding: 16px; }
    }
    
    div[data-testid="stVerticalBlock"] > div[style*="flex-direction: column;"] > div[data-testid="stVerticalBlock"] {
        border: none !important; box-shadow: none !important; background: transparent !important;
    }
    .stButton>button { border-radius: 8px !important; font-weight: 600 !important; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. 数据读取逻辑 ====================
BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略/live"
DATA_DIR = "/Users/aranwong/Documents/quant app/量化策略/backtestdata"
POOL_FILE = os.path.join(BASE_DIR, "etf_pool.csv")
REPORT_DIR = os.path.join(BASE_DIR, "logs")

def load_pool():
    if os.path.exists(POOL_FILE):
        return dict(zip(pd.read_csv(POOL_FILE, encoding='utf-8')['code'].str.strip(), pd.read_csv(POOL_FILE, encoding='utf-8')['name'].str.strip()))
    return {}

def load_holdings(username):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    if os.path.exists(file):
        with open(file, encoding='utf-8') as f: return json.load(f)
    return {"cash": 100000.0, "holdings": {}, "peak_nav": 100000.0}

def save_holdings(username, data):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    with open(file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

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

def get_latest_price(code):
    file_path = os.path.join(DATA_DIR, f"etf_{code}.csv")
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            return float(df['close'].iloc[-1])
        except:
            pass
    return 0.0

# ==================== 3. 侧边栏与导航 ====================
if "logged_in" not in st.session_state: st.session_state.logged_in = False

with st.sidebar:
    st.markdown("<h2 style='font-weight:800; color:var(--text-color); margin-bottom:4px;'><span class='ms-icon' style='color:#3B82F6;'>monitoring</span>AlphaEngine</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:0.85rem; opacity:0.5; margin-left: 32px;'>量化决策中枢 Pro</p>", unsafe_allow_html=True)
    st.write("")
    
    if st.session_state.logged_in:
        username = st.session_state.username
        st.markdown(f"<div style='font-size:0.85rem; padding:12px; background:rgba(128,128,128,0.05); border-radius:8px; margin-bottom:24px; border:1px solid rgba(128,128,128,0.1);'><span style='opacity:0.6;'>操作员：</span><span style='color:var(--text-color); font-weight:700;'>{username}</span></div>", unsafe_allow_html=True)
        
        page = st.radio("系统导航", ["决策大屏 (Dashboard)", "资产账本 (Portfolio)"], label_visibility="collapsed")
        
        st.write("")
        st.write("")
        if st.button("安全退出", icon=":material/logout:", use_container_width=True): auth.logout()
        with st.expander("高级设置"):
            if st.button("注销并删除数据", type="primary", use_container_width=True):
                auth.delete_account(username)
                st.rerun()
    else:
        st.info("请完成身份验证")

# 处理新用户注册后的建仓
if st.session_state.get("new_user_registered"):
    new_user = st.session_state.new_user_registered
    cash = st.session_state.get("initial_cash", 1000000.0)
    save_holdings(new_user, {
        "cash": cash,
        "holdings": {},
        "peak_nav": cash,
        "cooling": {},
        "cooling_type": {},
        "frozen_until": None
    })
    st.session_state.new_user_registered = None
    st.session_state.initial_cash = None
    st.success(f"账户 `{new_user}` 已创建，起始资金 ¥{cash:,.2f}。请登录。")

if not st.session_state.logged_in:
    col_a, col_b, col_c = st.columns([1, 1.5, 1])
    with col_b:
        st.write("")
        st.write("")
        tab1, tab2 = st.tabs(["系统登录", "注册账户"])
        with tab1: auth.login()
        with tab2: auth.register()
    st.stop()

# ==================== 4. 核心业务逻辑 ====================
username = st.session_state.username
portfolio = load_holdings(username)
pool = load_pool()
dash_data = load_dashboard_data(username)

# 核算真实资产
actual_mkt_val = 0.0
total_cost = 0.0
for c, h in portfolio['holdings'].items():
    curr_p = get_latest_price(c)
    if curr_p <= 0: curr_p = h['cost']
    actual_mkt_val += curr_p * h['qty']
    total_cost += h['cost'] * h['qty']

total_assets = portfolio['cash'] + actual_mkt_val
total_profit = actual_mkt_val - total_cost
base_capital = portfolio['cash'] + total_cost
total_profit_pct = (total_profit / base_capital * 100) if base_capital > 0 else 0.0

profit_color = "var(--bull-red)" if total_profit > 0 else ("var(--bear-green)" if total_profit < 0 else "var(--text-color)")
profit_sign = "+" if total_profit > 0 else ""

if not dash_data:
    st.warning("今日尚未生成决策数据。")
    if st.button("启动量化计算引擎", icon=":material/rocket_launch:", type="primary"):
        with st.spinner("系统运算中..."):
            subprocess.run([sys.executable, os.path.join(BASE_DIR, "run_daily.py"), "--account", username], cwd=BASE_DIR)
        st.rerun()
    st.stop()

# ★ 提取 V3 状态并应用专属颜色方案 ★
v3_info = dash_data.get('v3_state', {})
state_raw = v3_info.get('state', 'UNKNOWN')

# 颜色映射表: (文字颜色, 背景色, 中文描述)
state_color_map = {
    "SYSTEMIC_BULL": ("#10B981", "rgba(16, 185, 129, 0.12)", "🟢 系统性牛市"),
    "SYSTEMIC_BEAR": ("#EF4444", "rgba(239, 68, 68, 0.12)", "🔴 系统性熊市"),
    "SIDEWAYS_UP": ("#F59E0B", "rgba(245, 158, 11, 0.12)", "🟡 震荡偏强"),
    "SIDEWAYS_DOWN": ("#F97316", "rgba(249, 115, 22, 0.12)", "🟠 震荡偏弱"),
    "SIDEWAYS": ("#6B7280", "rgba(107, 114, 128, 0.12)", "⚪ 中性震荡")
}
# 匹配状态，没有匹配到则默认灰色
v3_color, v3_bg, v3_cn = state_color_map.get(state_raw, ("#6B7280", "rgba(107, 114, 128, 0.12)", f"⚪ {state_raw}"))

raw_trade_date = dash_data.get('trade_date', '今日')
display_trade_date = format_date_str(raw_trade_date)

# ----------------- 页面 A: 决策大屏 -----------------
if "决策大屏" in page:
    head_col1, head_col2 = st.columns([4, 1])
    with head_col1:
        st.markdown(f"""
        <div class="flex-header">
            <h3 style='color:var(--text-color); font-weight:800; margin:0; letter-spacing: -0.5px;'><span class='ms-icon'>dashboard</span>Decision Dashboard</h3>
            <span class="date-badge">
                <span class="ms-icon" style="font-size:1.1rem; margin-right:4px;">calendar_today</span>基于 {display_trade_date} 盘后数据
            </span>
        </div>
        """, unsafe_allow_html=True)
    with head_col2:
        st.write("") 
        if st.button("手动同步最新行情", icon=":material/sync:", use_container_width=True):
            with st.spinner("请求最新行情中..."): 
                subprocess.run([sys.executable, os.path.join(BASE_DIR, "run_daily.py"), "--account", username], cwd=BASE_DIR)
            st.rerun()
    
    st.write("") 

    # 1. 顶部数据卡片
    st.markdown(f"""
    <div class="grid-4" style="margin-bottom:24px;">
        <div class="za-card" style="margin-bottom:0; padding:20px;">
            <div class="metric-label">账户最新估值</div>
            <div class="metric-value tabular-num">{total_assets:,.2f} <span class="metric-unit">CNY</span></div>
            <div style="font-size:0.85rem; color:{profit_color}; font-weight:700; margin-top:6px; font-family: ui-sans-serif, system-ui;">
                {profit_sign}{total_profit:,.2f} ({profit_sign}{total_profit_pct:.2f}%)
            </div>
        </div>
        <div class="za-card" style="margin-bottom:0; padding:20px;">
            <div class="metric-label">配置战备</div>
            <div class="metric-value tabular-num">{len(portfolio['holdings'])} <span class="metric-unit">Positions</span></div>
            <div style="font-size:0.85rem; color:var(--text-color); opacity:0.5; margin-top:6px; font-weight:500;">当前持仓标的数量</div>
        </div>
        <div class="za-card" style="margin-bottom:0; padding:20px;">
            <div class="metric-label" style="margin-bottom: 8px;">宏观气温 (V3)</div>
            <div style="margin-top:10px;">
                <span style="background-color: {v3_bg}; color: {v3_color}; padding: 6px 14px; border-radius: 8px; font-size: 0.95rem; font-weight: 700; border: 1px solid {v3_color}40; display: inline-block;">
                    {v3_cn}
                </span>
            </div>
        </div>
        <div class="za-card" style="margin-bottom:0; padding:20px;">
            <div class="metric-label">状态延续</div>
            <div class="metric-value tabular-num">{v3_info.get('duration', 0)} <span class="metric-unit">Days</span></div>
            <div style="font-size:0.85rem; color:var(--text-color); opacity:0.5; margin-top:6px; font-weight:500;">当前周期持续天数</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 1.5 核心盘面指标仪表盘
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
        money_effect = f'🟢 全A同步走强，真实上涨占比 {up_ratio*100:.0f}%，赚钱效应良好'
    elif a_above and up_ratio <= 0.55:
        money_effect = f'⚠️ 指数走强但真实上涨仅 {up_ratio*100:.0f}%，权重护盘特征明显'
    elif not a_above and up_ratio > 0.55:
        money_effect = f'🟡 全A走弱但上涨占比 {up_ratio*100:.0f}%，个股活跃度尚可'
    else:
        money_effect = f'🔴 全A走弱，上涨家数占比仅 {up_ratio*100:.0f}%，个股普遍下跌'

    st.markdown(f"""<div class="za-card" style="padding: 24px;">
<div style="font-size:1.1rem; font-weight:800; color:var(--text-color); margin-bottom:20px; display:flex; align-items:center;">
<span class="ms-icon" style="color:var(--accent-blue);">analytics</span>核心盘面参数
</div>
<div class="grid-3" style="margin-bottom:20px;">
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px; border:1px solid rgba(128,128,128,0.08);">
<div style="font-size:0.85rem; color:var(--text-color); opacity:0.6; margin-bottom:6px; font-weight:600;">沪深 300 阵地</div>
<div style="font-size:1.8rem; font-weight:800; color:var(--text-color); margin-bottom:8px;" class="tabular-num">{hs300_close:,.2f}</div>
<div style="font-size:0.85rem; color:var(--text-color); opacity:0.8; display:flex; gap:16px; font-weight:500;" class="tabular-num">
<span>MA20: {ma20:,.2f}</span>
<span>MA60: {ma60:,.2f}</span>
</div>
</div>
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px; border:1px solid rgba(128,128,128,0.08);">
<div style="font-size:0.85rem; color:var(--text-color); opacity:0.6; margin-bottom:6px; font-weight:600;">上证与动能监控</div>
<div style="font-size:1.8rem; font-weight:800; color:var(--text-color); margin-bottom:8px;" class="tabular-num">{sz_close:,.2f}</div>
<div style="font-size:0.85rem; color:var(--text-color); opacity:0.8; display:flex; gap:16px; font-weight:500;" class="tabular-num">
<span>量能倍率: {vol_ratio:.2f}x</span>
<span>乖离率: {bias_60:+.2f}%</span>
</div>
</div>
<div style="background:rgba(128,128,128,0.04); padding:16px 20px; border-radius:10px; border:1px solid rgba(128,128,128,0.08);">
<div style="font-size:0.85rem; color:var(--text-color); opacity:0.6; margin-bottom:6px; font-weight:600;">V3 系统滤波缓冲带</div>
<div style="font-size:1.3rem; font-weight:700; color:var(--text-color); margin-top:12px; margin-bottom:12px; letter-spacing:0.5px;" class="tabular-num">
{lower:,.2f} <span style="opacity:0.3; font-weight:normal; margin:0 6px;">~</span> {upper:,.2f}
</div>
<div style="font-size:0.8rem; color:var(--text-color); opacity:0.5; font-weight:500;">
*跌破下沿即触发系统性熊市预警
</div>
</div>
</div>
<div style="background:rgba(59, 130, 246, 0.08); border-left: 4px solid var(--accent-blue); padding:14px 20px; border-radius:8px; display:flex; align-items:center; flex-wrap:wrap; gap:16px;">
<div style="font-size:0.9rem; color:var(--accent-blue); font-weight:800; white-space:nowrap;">赚钱效应雷达</div>
<div style="font-size:0.95rem; color:var(--text-color); opacity:0.9; font-weight:600;">{money_effect}</div>
</div>
</div>""", unsafe_allow_html=True)

    # 2. AI 全景推演层 
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
        html_col1 = f"""<div style="display:flex; flex-direction:column; gap:20px; height:100%;">
<div class="ai-insight-box" style="flex-grow:1; box-shadow: 0 4px 15px rgba(0,0,0,0.02);">
<div style="color:var(--ai-purple); font-weight:800; font-size:1.05rem; margin-bottom:14px; display:flex; align-items:center;">
<span class="ms-icon">security</span>风控建议
</div>
<div style="font-size:0.95rem; line-height:1.7; color:var(--text-color); font-weight:500;">
{ai_data.get('risk_tip', '系统平稳运行，暂无特殊风控警示。').replace(chr(10), '<br>')}
</div>
</div>"""
        if core_focus:
            html_col1 += f"""<div class="focus-box" style="box-shadow: 0 4px 15px rgba(0,0,0,0.01);">
<div style="font-size:0.9rem; color:var(--focus-amber); font-weight:800; margin-bottom:8px;"><span class="ms-icon" style="font-size:1.1rem;">my_location</span>核心观察锚点</div>
<div style="font-size:0.95rem; color:var(--text-color); opacity:0.9; line-height:1.6; font-weight:500;">{core_focus}</div>
</div>"""
        html_col1 += "</div>"
        st.markdown(html_col1, unsafe_allow_html=True)
        
    with col_ai_2:
        if raw_v3_interp:
            html_col2 = f"""<div class="za-card" style="margin-bottom:0; height:100%; border-top: 3px solid rgba(128,128,128,0.3);">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
<h4 style="font-size:1.05rem; color:var(--text-color); font-weight:800; opacity:0.9; margin:0;"><span class="ms-icon" style="font-size:1.2rem;">account_tree</span>情景推演与路由</h4>
</div>
<div style="font-size:0.95rem; line-height:1.8; color:var(--text-color); opacity:0.85; font-weight:400;">
{main_interp.replace(chr(10), '<br>')}
</div>
</div>"""
            st.markdown(html_col2, unsafe_allow_html=True)

    st.write("---") 

    # 3. 交易指令与排行
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.markdown("<h4 style='font-size:1.1rem; font-weight:800; color:var(--text-color); margin-bottom:20px;'><span class='ms-icon'>receipt_long</span>绝对执行清单</h4>", unsafe_allow_html=True)
        orders = dash_data.get('orders', [])
        
        orders_html = "<div class='za-card' style='min-height: 240px; padding: 20px;'>"
        if not orders:
            orders_html += """<div style="height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0.4; padding: 40px 0;">
<span class="ms-icon" style="font-size: 3rem; margin-bottom: 16px;">check_circle</span>
<div style="font-size: 1rem; font-weight:600;">仓位结构稳定，今日无调仓信号。</div>
</div>"""
        else:
            for o in orders:
                is_buy = o['action'] == '买入'
                clss = "order-buy" if is_buy else "order-sell"
                icon_name = "trending_up" if is_buy else "trending_down"
                color = "var(--bull-red)" if is_buy else "var(--bear-green)"
                
                orders_html += f"""<div class="order-item {clss}" style="box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; flex-wrap:wrap; gap:8px;">
<span style="font-size:1.1rem; font-weight:800; color:{color};"><span class="ms-icon">{icon_name}</span>{o['action']} {o['name']} ({o['code']})</span>
<span style="background:rgba(128,128,128,0.06); color:var(--text-color); border: 1px solid rgba(128,128,128,0.12); font-size:0.85rem; padding:6px 12px; border-radius:6px; font-weight:700;" class="tabular-num">{o['qty']} 股</span>
</div>"""
                if o.get('reason'): orders_html += f"<div style='font-size:0.9rem; color:var(--text-color); opacity:0.8; margin-bottom:6px; font-weight:500;'><b>触发机制:</b> {o['reason']}</div>"
                if o.get('range'): orders_html += f"<div style='font-size:0.9rem; color:var(--text-color); opacity:0.8; font-weight:500;'><b>执行区间:</b> {o['range']} 元</div>"
                orders_html += "</div>"
        orders_html += "</div>"
        st.markdown(orders_html, unsafe_allow_html=True)

    with col_right:
        st.markdown("<h4 style='font-size:1.1rem; font-weight:800; color:var(--text-color); margin-bottom:20px;'><span class='ms-icon'>leaderboard</span>动量势能榜 Top 5</h4>", unsafe_allow_html=True)
        ranks = dash_data.get('rankings', [])
        
        ranks_html = "<div class='za-card' style='min-height: 240px; padding: 20px;'>"
        if not ranks:
            ranks_html += """<div style="height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; opacity: 0.4; padding: 40px 0;">
<span class="ms-icon" style="font-size: 3rem; margin-bottom: 16px;">blur_on</span>
<div style="font-size: 1rem; text-align:center; font-weight:600;">市场动能极弱<br>无标的满足上榜基准</div>
</div>"""
        else:
            for r in ranks:
                n_clss = "rank-num-top" if int(r['num']) <= 3 else ""
                ranks_html += f"""<div class="rank-row" style="padding: 14px 0;">
<div style="display:flex; align-items:center;">
<div class="rank-num {n_clss}">{r['num']}</div>
<div style="font-weight:600; font-size:1rem; color:var(--text-color);">{r['name']} <span style="font-size:0.8rem; color:var(--text-color); opacity:0.5; font-weight:normal; margin-left:6px;">{r['code']}</span></div>
</div>
<div style="color:var(--bull-red); font-size:1.15rem; font-weight:800;" class="tabular-num">S={r['score']}</div>
</div>"""
        ranks_html += "</div>"
        st.markdown(ranks_html, unsafe_allow_html=True)

# ----------------- 页面 B: 资产账本 -----------------
elif "资产账本" in page:
    st.markdown("<h3 style='color:var(--text-color); font-weight:800; margin-bottom:24px; letter-spacing: -0.5px;'><span class='ms-icon'>account_balance_wallet</span>Portfolio Ledger</h3>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="za-card" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:20px; background:linear-gradient(135deg, rgba(59, 130, 246, 0.08) 0%, transparent 100%); border:1px solid rgba(59, 130, 246, 0.2); padding: 30px;">
        <div>
            <div style="font-size:0.9rem; color:var(--text-color); opacity:0.7; font-weight:600; margin-bottom:8px;">总资产净值 (CNY)</div>
            <div style="font-size:2.8rem; font-weight:800; color:var(--text-color);" class="tabular-num">{total_assets:,.2f}</div>
            <div style="font-size:1.05rem; color:{profit_color}; font-weight:700; margin-top:8px; font-family: ui-sans-serif, system-ui;">
                总持仓盈亏：{profit_sign}{total_profit:,.2f} ({profit_sign}{total_profit_pct:.2f}%)
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-size:0.9rem; color:var(--text-color); opacity:0.6; font-weight:600; margin-bottom:4px;">最新持仓市值</div>
            <div style="font-size:1.6rem; font-weight:800; color:var(--text-color); margin-bottom:16px;" class="tabular-num">{actual_mkt_val:,.2f}</div>
            <div style="font-size:0.9rem; color:var(--text-color); opacity:0.6; font-weight:600; margin-bottom:4px;">可用现金余额</div>
            <div style="font-size:1.6rem; font-weight:800; color:#3B82F6;" class="tabular-num">{portfolio['cash']:,.2f}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<h4 style='font-size:1.1rem; font-weight:800; color:var(--text-color); margin-top:10px; margin-bottom:16px;'><span class='ms-icon'>inventory_2</span>当前持有仓位明细</h4>", unsafe_allow_html=True)
    
    # ★ 紧凑 HTML 高定数据表 + 动态风控可视化解读 ★

    if portfolio['holdings']:
        html_table = '''
        <div class="table-container">
        <table class="pro-table" style="border-collapse: collapse; border-spacing: 0;">
        <thead><tr>
        <th class="text-left" style="width:20%; padding: 6px 12px; vertical-align: middle;">标的资产</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">持有数量</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">持仓均价</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">最新现价</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">止盈价格</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">止损价格</th>
        <th class="text-right" style="padding: 6px 12px; vertical-align: middle;">浮动盈亏</th>
        </tr></thead><tbody>'''

        for c, h in portfolio['holdings'].items():
            curr_p = get_latest_price(c)
            cost = h['cost']
            qty = h['qty']
            highest = h.get('highest', cost)

            if curr_p > 0:
                pct = (curr_p - cost) / cost * 100
                amt = (curr_p - cost) * qty
            else:
                curr_p = cost
                pct = 0.0
                amt = 0.0

            color = "#EF4444" if pct > 0 else ("#10B981" if pct < 0 else "gray")
            sign = "+" if pct > 0 else ""

            # 止盈/止损价计算
            stop_loss = cost * 0.92
            if pct >= 20:
                take_profit = highest * 0.88
            elif pct >= 8:
                take_profit = highest * 0.92
            else:
                take_profit = stop_loss
            actual_take_profit = max(take_profit, stop_loss)
            actual_stop_loss = stop_loss

            # 最新现价涨红跌绿
            price_color = "#EF4444" if curr_p > cost else ("#10B981" if curr_p < cost else "gray")

            html_table += f'''
            <tr style="line-height:1.2; border: none; margin:0; padding:0; vertical-align: middle;">
                <td class="text-left" style="padding: 6px 12px; vertical-align: middle;">
                    <div style="font-weight:800; font-size:1.05rem; margin:0; padding:0; line-height:1.2;">{h["name"]}</div>
                    <div style="font-size:0.72rem; opacity:0.6; font-weight:500; margin:0; padding:0; line-height:1.2;">{c}</div>
                </td>
                <td class="text-right tabular-num" style="font-size:1rem; padding: 6px 12px; vertical-align: middle;">{qty:,}</td>
                <td class="text-right tabular-num" style="font-size:1rem; padding: 6px 12px; vertical-align: middle;">{cost:.3f}</td>
                <td class="text-right tabular-num" style="font-size:1rem; font-weight:800; color:{price_color}; padding: 6px 12px; vertical-align: middle;">{curr_p:.3f}</td>
                <td class="text-right tabular-num" style="font-size:1rem; padding: 6px 12px; vertical-align: middle;">{actual_take_profit:.3f}</td>
                <td class="text-right tabular-num" style="font-size:1rem; padding: 6px 12px; vertical-align: middle;">{actual_stop_loss:.3f}</td>
                <td class="text-right tabular-num" style="color:{color}; padding: 6px 12px; vertical-align: middle;">
                    <div style="font-size:1.05rem; font-weight:800; margin:0; padding:0; line-height:1.2;">{sign}{amt:,.2f}</div>
                    <div style="font-size:0.85rem; font-weight:700; margin:0; padding:0; line-height:1.2;">{sign}{pct:.2f}%</div>
                </td>
            </tr>'''

        html_table += '</tbody></table></div>'
        st.markdown(html_table, unsafe_allow_html=True)


    
    else:
        st.info("当前资金均在现金池中，无权益敞口。")
        
    st.write("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("<h5 style='font-weight:700; color:var(--text-color); margin-bottom:16px;'><span class='ms-icon'>edit_square</span>交易流水补录</h5>", unsafe_allow_html=True)
        act = st.radio("交易方向", ["买入", "卖出"], horizontal=True, label_visibility="collapsed")
        is_manual = st.checkbox("自定义池外资产")
        code_in = st.text_input("证券代码 (如 510300)", placeholder="输入后按回车自动匹配")
        matched_name, final_code = "", None
        
        if code_in:
            raw = code_in.strip()
            final_code = raw if '.' in raw else None
            if not final_code:
                for sfx in ['.SZ', '.SH', '.HK']:
                    if (raw+sfx) in pool or (raw+sfx) in portfolio.get('holdings', {}):
                        final_code = raw+sfx; break
            if not final_code: final_code = raw
            
            if final_code in pool:
                matched_name = pool[final_code]
                st.success(f"已锁定：{matched_name}")
            elif is_manual:
                matched_name = st.text_input("资产名称")
        
        cq, cp = st.columns(2)
        with cq: qty = st.number_input("成交量 (股)", min_value=100, step=100)
        with cp: prc = st.number_input("成交价 (元)", min_value=0.001, format="%.3f")
        dt = st.text_input("确认日期", value=datetime.datetime.now().strftime('%Y%m%d'))
        
        st.write("")
        if st.button("提交记录", type="primary", use_container_width=True):
            if not final_code or (is_manual and not matched_name): 
                st.error("证券代码或名称不完整")
            else:
                name = matched_name if matched_name else (pool.get(final_code, final_code))
                if act == "买入":
                    cost_amt = qty * prc
                    if cost_amt > portfolio['cash']: st.error("可用资金不足")
                    else:
                        portfolio['cash'] -= cost_amt
                        if final_code in portfolio['holdings']:
                            h = portfolio['holdings'][final_code]
                            h['cost'] = round((h['qty']*h['cost'] + cost_amt)/(h['qty']+qty), 4)
                            h['qty'] += qty
                            h['highest'] = max(h.get('highest', 0.0), prc)
                        else: portfolio['holdings'][final_code] = {"name": name, "qty": qty, "cost": prc, "buy_date": dt, "highest": prc}
                        save_holdings(username, portfolio); st.success("记录成功"); st.rerun()
                else:
                    if final_code not in portfolio['holdings']: st.error("查无此持仓")
                    elif qty > portfolio['holdings'][final_code]['qty']: st.error("超过实际持仓数量")
                    else:
                        portfolio['cash'] += (qty * prc)
                        portfolio['holdings'][final_code]['qty'] -= qty
                        if portfolio['holdings'][final_code]['qty'] <= 0: del portfolio['holdings'][final_code]
                        save_holdings(username, portfolio); st.success("记录成功"); st.rerun()

    with c2:
        st.markdown("<h5 style='font-weight:700; color:var(--text-color); margin-bottom:16px;'><span class='ms-icon'>account_balance</span>资金划转</h5>", unsafe_allow_html=True)
        f_act = st.selectbox("业务类型", ["入金 (转入证券账户)", "出金 (转出至银行卡)"])
        f_amt = st.number_input("划转金额 (CNY)", min_value=0.0, step=1000.0)
        st.write("")
        if st.button("确认划转", use_container_width=True):
            if "入金" in f_act: 
                portfolio['cash'] += f_amt
                save_holdings(username, portfolio); st.rerun()
            elif f_amt <= portfolio['cash']: 
                portfolio['cash'] -= f_amt
                save_holdings(username, portfolio); st.rerun()
            else: 
                st.error("可用现金不足")
