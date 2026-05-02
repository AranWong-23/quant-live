#!/usr/bin/env python3
# app.py - AlphaEngine 完美夜间模式 + 防重叠解析 + 经典三段布局
import streamlit as st
import json, os, subprocess, sys, datetime, re
import pandas as pd
import auth

# ==================== 1. 全局配置与自适应 UI 注入 ====================
st.set_page_config(page_title="AlphaEngine", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# 采用 CSS 变量 (var) 适配原生亮/暗模式
st.markdown("""
<style>
    /* 全局字体 */
    .stApp { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; }
    header {visibility: hidden;}
    
    /* 核心色彩：使用 rgba 适配深色/浅色模式背景 */
    .text-red { color: #FF4D4F !important; font-weight: 600; }
    .text-green { color: #00B42A !important; font-weight: 600; }
    .bg-red-light { background-color: rgba(255, 77, 79, 0.15) !important; color: #FF4D4F !important; }
    .bg-green-light { background-color: rgba(0, 180, 42, 0.15) !important; color: #00B42A !important; }
    .bg-neutral-light { background-color: rgba(128, 128, 128, 0.15) !important; color: var(--text-color) !important; }
    
    /* 自适应卡片 */
    .za-card {
        background-color: var(--secondary-background-color);
        border-radius: 16px; padding: 24px; margin-bottom: 16px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    
    /* 文本层级 */
    .metric-label { font-size: 0.85rem; color: var(--text-color); opacity: 0.7; margin-bottom: 6px; }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: var(--text-color); font-family: ui-sans-serif, system-ui; }
    
    /* 排行榜 */
    .rank-row { display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid rgba(128,128,128,0.1); }
    .rank-row:last-child { border-bottom: none; }
    .rank-num { width: 24px; height: 24px; border-radius: 6px; background: rgba(128,128,128,0.15); color: var(--text-color); display: flex; align-items: center; justify-content: center; font-size: 0.85rem; font-weight: bold; margin-right: 12px; }
    .rank-num-top { background: rgba(255, 77, 79, 0.15) !important; color: #FF4D4F !important; }
    
    /* 指令清单 */
    .order-item { padding: 16px; border-radius: 12px; margin-bottom: 12px; border: 1px solid rgba(128,128,128,0.2); background-color: var(--background-color); border-left: 5px solid #FF4D4F; }
    .order-item-sell { border-left-color: #00B42A; }
    
    /* 深度解析部分 */
    .depth-box { background-color: var(--background-color); border-radius: 8px; padding: 16px; margin-bottom: 16px; border: 1px solid rgba(128,128,128,0.2); border-left: 4px solid #165DFF; }
    .depth-title { font-size: 0.95rem; font-weight: 700; color: var(--text-color); margin-bottom: 8px; }
    .depth-content { font-size: 0.9rem; color: var(--text-color); opacity: 0.85; line-height: 1.6; }
    
    /* 侧边栏按钮 */
    .stButton>button { border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

# ==================== 2. 严格的数据解析逻辑 ====================
BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略/live"
POOL_FILE = os.path.join(BASE_DIR, "etf_pool.csv")
REPORT_DIR = os.path.join(BASE_DIR, "logs")
V3_STATE_FILE = os.path.join(BASE_DIR, "last_state.json")

def load_pool():
    if os.path.exists(POOL_FILE):
        return dict(zip(pd.read_csv(POOL_FILE, encoding='utf-8')['code'].str.strip(), pd.read_csv(POOL_FILE, encoding='utf-8')['name'].str.strip()))
    return {}

def load_v3_state():
    if os.path.exists(V3_STATE_FILE):
        with open(V3_STATE_FILE, encoding='utf-8') as f: return json.load(f)
    return None

def load_holdings(username):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    if os.path.exists(file):
        with open(file, encoding='utf-8') as f: return json.load(f)
    return {"cash": 100000.0, "holdings": {}, "peak_nav": 100000.0}

def save_holdings(username, data):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    with open(file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2, ensure_ascii=False)

# ★ 修复解析重叠的终极武器：精准阶段截断
def extract_strict(text, start_marker, possible_end_markers):
    start = text.find(start_marker)
    if start == -1: return ""
    start += len(start_marker)
    end = len(text)
    for marker in possible_end_markers:
        idx = text.find(marker, start)
        if idx != -1 and idx < end:
            end = idx
    return text[start:end].strip()

def parse_orders(raw_text):
    if not raw_text or "今日无交易动作" in raw_text: return []
    orders, current_order = [], None
    for line in raw_text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('买入') or line.startswith('卖出'):
            if current_order: orders.append(current_order)
            current_order = {'action': line[:2], 'details': line[2:].strip(), 'reason': '', 'range': '', 'strategy': ''}
        elif current_order:
            if '原因：' in line: current_order['reason'] = line.split('原因：')[-1].strip()
            elif '建议买入区间：' in line: current_order['range'] = line.split('建议买入区间：')[-1].strip()
            elif '最佳建议价：' in line: current_order['range'] += f" (最优 {line.split('最佳建议价：')[-1].strip()})"
            elif '策略：' in line or line.startswith('↳') or line.startswith('🔖'): current_order['strategy'] = line.replace('↳', '').replace('🔖', '').strip()
    if current_order: orders.append(current_order)
    return orders

def parse_rankings(raw_text):
    rankings = []
    if not raw_text: return rankings
    for line in raw_text.splitlines():
        line = line.strip()
        m = re.match(r'^(\d+)\.\s+(.+?)\s*\((.+?)\)\s*S=([\d.]+)', line)
        if m: rankings.append({"num": m.group(1), "name": m.group(2), "code": m.group(3), "score": m.group(4)})
    return rankings

# ==================== 3. 侧边栏 ====================
if "logged_in" not in st.session_state: st.session_state.logged_in = False

with st.sidebar:
    st.markdown("<h2 style='font-weight:800; margin-bottom:4px;'>AlphaEngine</h2>", unsafe_allow_html=True)
    st.markdown("<p style='font-size:0.85rem; opacity:0.7;'>核心量化交易中枢</p>", unsafe_allow_html=True)
    st.divider()
    
    if st.session_state.logged_in:
        username = st.session_state.username
        st.markdown(f"<div style='font-size:0.9rem; margin-bottom:20px;'>操作员: <span style='color:#165DFF; font-weight:600;'>{username}</span></div>", unsafe_allow_html=True)
        page = st.radio("导航菜单", ["今日看板", "资产与持仓"], label_visibility="collapsed")
        st.divider()
        if st.button("🚪 退出登录", use_container_width=True): auth.logout()
        # 增加注销按钮
        with st.expander("⚠️ 危险操作"):
            if st.button("注销并删除账户", type="secondary", use_container_width=True):
                auth.delete_account(username)
                st.rerun()
    else:
        st.info("请先完成身份验证")

if not st.session_state.logged_in:
    col_a, col_b, col_c = st.columns([1, 1.5, 1])
    with col_b:
        st.write(" ")
        tab1, tab2 = st.tabs(["🔐 登录", "📝 注册"])
        with tab1: auth.login()
        with tab2: auth.register()
    st.stop()

# ==================== 4. 业务逻辑 ====================
username = st.session_state.username
data = load_holdings(username)
pool = load_pool()
v3 = load_v3_state()
today_str = datetime.datetime.now().strftime('%Y-%m-%d')
report_file = os.path.join(REPORT_DIR, username, f"report_{today_str}.txt")
full_report = open(report_file, encoding='utf-8').read() if os.path.exists(report_file) else ""

# ----------------- 页面 A: 今日看板 -----------------
if page == "今日看板":
    
    # 1. 顶部：账户汇总数据
    total_assets = data['cash'] + sum(h['qty'] * h['cost'] for h in data['holdings'].values())
    state = v3.get('state', '未知') if v3 else '未知'
    duration = v3.get("duration", "0") if v3 else "0"
    is_bull = "BULL" in state or "UP" in state
    state_cn = {"SYSTEMIC_BULL": "系统性牛市", "SYSTEMIC_BEAR": "系统性熊市", "SIDEWAYS_UP": "震荡偏强", "SIDEWAYS_DOWN": "震荡偏弱", "SIDEWAYS": "中性震荡"}.get(state, state)
    state_class = "bg-red-light" if is_bull else "bg-green-light"

    st.markdown(f"""<div class="za-card" style="display:flex; justify-content:space-between; flex-wrap:wrap; padding: 20px 30px;">
<div><div class="metric-label">账户总估值 (CNY)</div><div class="metric-value">{total_assets:,.2f}</div></div>
<div><div class="metric-label">持仓标数</div><div class="metric-value">{len(data['holdings'])} <span style="font-size:1rem; font-weight:normal; opacity:0.7;">只</span></div></div>
<div><div class="metric-label">V3 宏观气温</div><div style="margin-top:4px;"><span style="padding:6px 14px; border-radius:8px; font-weight:600; font-size:1rem;" class="{state_class}">{state_cn}</span></div></div>
<div><div class="metric-label">状态延续</div><div class="metric-value">{duration} <span style="font-size:1rem; font-weight:normal; opacity:0.7;">天</span></div></div>
</div>""", unsafe_allow_html=True)

    # 2. 中层：市场深度解析 (全宽)
    with st.container(border=True):
        st.markdown("#### 🧠 市场深度解析")
        
        # 提取 AI 风控
        ai_tip = extract_strict(full_report, "🤖 【DeepSeek风控参谋】", ["━━━ V3 市场深度报告"])
        if ai_tip:
            st.markdown(f"""<div style="background:rgba(22, 93, 255, 0.1); border:1px solid rgba(22, 93, 255, 0.2); border-radius:8px; padding:16px; margin-bottom:16px;">
<div style="color:#165DFF; font-weight:700; margin-bottom:8px;">🤖 AI 核心风控建议</div>
<div style="font-size:0.9rem; line-height:1.6; color:var(--text-color);">{ai_tip.replace(chr(10), '<br>')}</div></div>""", unsafe_allow_html=True)
        
        # 提取底层报告并严格分块防重复
        v3_raw = extract_strict(full_report, "━━━ V3 市场深度报告 ━━━", ["💼 【账户快照】"])
        if v3_raw:
            metrics = extract_strict(v3_raw, "【核心指标】", ["【关键信号解读】", "【短线交易信号】", "【策略路由建议】"])
            signals = extract_strict(v3_raw, "【关键信号解读】", ["【短线交易信号】", "【策略路由建议】", "【DeepSeek市场解读】"])
            strategy = extract_strict(v3_raw, "【策略路由建议】", ["【DeepSeek市场解读】", "【DeepSeek 辅助评分】", "💼"])
            deduction = extract_strict(v3_raw, "【DeepSeek市场解读】", ["💼", "【账户快照】"])
            
            # 双栏显示指标和异动
            ca, cb = st.columns(2)
            if metrics: ca.markdown(f'<div class="depth-box"><div class="depth-title">📊 核心指标快照</div><div class="depth-content">{metrics.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
            if signals: cb.markdown(f'<div class="depth-box" style="border-left-color:#F53F3F;"><div class="depth-title">🔍 盘面异动解析</div><div class="depth-content">{signals.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
            
            # 全宽显示策略和推演
            if strategy: st.markdown(f'<div class="depth-box" style="border-left-color:#00B42A;"><div class="depth-title">🧭 路由建议</div><div class="depth-content">{strategy.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
            if deduction: st.markdown(f'<div class="depth-box" style="border-left-color:#722ED1; background:rgba(114, 46, 209, 0.05) !important;"><div class="depth-title" style="color:#722ED1 !important;">🔮 情景推演与应对</div><div class="depth-content">{deduction.replace(chr(10), "<br>")}</div></div>', unsafe_allow_html=True)
        else:
            st.info("今日尚未生成深度报告。")

    st.write("")
    
    # 3. 底层：指令清单(左) & 排行榜(右)
    cl, cr = st.columns([1.2, 1])
    with cl:
        with st.container(border=True):
            cta, ctb = st.columns([1.5, 1])
            cta.markdown("#### ⚡ 今日执行清单")
            if ctb.button("🔄 刷新引擎信号", use_container_width=True):
                with st.spinner("计算中..."): subprocess.run([sys.executable, os.path.join(BASE_DIR, "run_daily.py"), "--account", username], cwd=BASE_DIR)
                st.rerun()
            
            orders = parse_orders(extract_strict(full_report, "📋 【今日绝对执行指令】", ["🏆 【今日ETF排行榜"]))
            if not orders: st.info("☕ 暂无触发指令。")
            else:
                for o in orders:
                    ic = "📈" if o['action'] == '买入' else "📉"
                    clss = "" if o['action'] == '买入' else "order-item-sell"
                    tx = "text-red" if o['action'] == '买入' else "text-green"
                    html = f"""<div class="order-item {clss}">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
<span class="{tx}" style="font-size:1.15rem;">{ic} {o['action']} {o['details']}</span>
<span style="background:rgba(128,128,128,0.15); color:var(--text-color); opacity:0.8; font-size:0.75rem; padding:4px 8px; border-radius:4px;">待执行</span></div>"""
                    if o['reason']: html += f'<div style="font-size:0.9rem; margin-bottom:4px; opacity:0.9;"><b>触发原因:</b> {o["reason"]}</div>'
                    if o['range']: html += f'<div style="font-size:0.9rem; margin-bottom:4px; opacity:0.9;"><b>操作区间:</b> {o["range"]}</div>'
                    if o['strategy']: html += f'<div style="font-size:0.85rem; opacity:0.7; margin-top:8px; padding-top:8px; border-top:1px dashed rgba(128,128,128,0.3);">💡 {o["strategy"]}</div>'
                    st.markdown(html + "</div>", unsafe_allow_html=True)

    with cr:
        with st.container(border=True):
            st.markdown("#### 🏆 ETF 势能排行榜 (Top 5)")
            rank_raw = extract_strict(full_report, "🏆 【今日ETF排行榜", ["══════════════════════", "🤖 【DeepSeek风控参谋】", "━━━ V3 市场深度报告"])
            ranks = parse_rankings(rank_raw)
            if not ranks: st.info("暂无排行数据。")
            else:
                for r in ranks:
                    n_clss = "rank-num-top" if int(r['num']) <= 3 else ""
                    st.markdown(f"""<div class="rank-row">
<div style="display:flex; align-items:center;">
<div class="rank-num {n_clss}">{r['num']}</div>
<div style="font-weight:600; font-size:1.05rem;">{r['name']} <span style="font-size:0.85rem; opacity:0.6; font-weight:normal;">({r['code']})</span></div>
</div><div class="text-red" style="font-size:1.2rem; font-weight:800;">S={r['score']}</div></div>""", unsafe_allow_html=True)


# ----------------- 页面 B: 资产与持仓 -----------------
elif page == "资产与持仓":
    total_assets = data['cash'] + sum(h['qty'] * h['cost'] for h in data['holdings'].values())
    mkt_val = sum(h['qty'] * h['cost'] for h in data['holdings'].values())
    
    st.markdown(f"""<div style="background: linear-gradient(135deg, #165DFF 0%, #0F3294 100%); padding: 30px; border-radius: 16px; color: #FFFFFF !important; margin-bottom: 20px;">
<div style="font-size:0.9rem; opacity:0.8; margin-bottom:4px; color:#FFFFFF !important;">账户可用购买力 + 持仓总市值 (CNY)</div>
<div style="font-size:2.4rem; font-weight:700; margin-bottom:16px; color:#FFFFFF !important;">{total_assets:,.2f}</div>
<div style="display:flex; gap:40px; border-top:1px solid rgba(255,255,255,0.15); padding-top:16px;">
<div><div style="font-size:0.85rem; opacity:0.8; color:#FFFFFF !important;">持仓总市值</div><div style="font-size:1.2rem; font-weight:600; color:#FFFFFF !important;">{mkt_val:,.2f}</div></div>
<div><div style="font-size:0.85rem; opacity:0.8; color:#FFFFFF !important;">本金/可用现金</div><div style="font-size:1.2rem; font-weight:600; color:#00B42A !important;">{data['cash']:,.2f}</div></div>
</div></div>""", unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("#### 📦 当前持仓明细")
        if data['holdings']:
            df_h = pd.DataFrame([{"标的名称": h['name'], "代码": c, "股数": h['qty'], "均价": h['cost'], "日期": h['buy_date']} for c, h in data['holdings'].items()])
            st.dataframe(df_h, use_container_width=True, hide_index=True)
        else: st.info("空仓中。")
        
    st.write("")
    ct, cf = st.columns(2)
    with ct:
        with st.container(border=True):
            st.markdown("#### ⚡ 交易记录器")
            act = st.radio("方向", ["买入", "卖出"], horizontal=True)
            is_manual = st.checkbox("标的池外自定义录入")
            
            code_in = st.text_input("证券代码 (如 510300)", key="c_in", placeholder="输入代码自动匹配名称")
            matched_name, final_code = "", None
            if code_in:
                raw = code_in.strip()
                final_code = raw if '.' in raw else None
                if not final_code:
                    for sfx in ['.SZ', '.SH']:
                        if (raw+sfx) in pool or (raw+sfx) in data.get('holdings', {}):
                            final_code = raw+sfx; break
                if not final_code: final_code = raw
                
                if final_code in pool:
                    matched_name = pool[final_code]
                    st.success(f"✅ 匹配标的: **{matched_name}** ({final_code})")
                elif is_manual:
                    matched_name = st.text_input("请输入自定义名称", key="m_name")
                else: st.error("❌ 池内未找到，若需强制录入请开启上方“自定义录入”。")

            dt = st.text_input("日期", value=datetime.datetime.now().strftime('%Y%m%d'))
            cq, cp = st.columns(2)
            with cq: qty = st.number_input("股数", min_value=100, step=100)
            with cp: prc = st.number_input("价格", min_value=0.001, format="%.3f")
            
            if st.button("提交交易记录", type="primary", use_container_width=True):
                if not final_code or (is_manual and not matched_name): st.error("信息不完整")
                else:
                    name = matched_name if matched_name else (pool.get(final_code, final_code))
                    if act == "买入":
                        if qty*prc > data['cash']: st.error("资金不足")
                        else:
                            data['cash'] -= qty*prc
                            if final_code in data['holdings']:
                                h = data['holdings'][final_code]
                                h['cost'] = round((h['qty']*h['cost'] + qty*prc)/(h['qty']+qty), 4)
                                h['qty'] += qty
                            else: data['holdings'][final_code] = {"name": name, "qty": qty, "cost": prc, "buy_date": dt}
                            save_holdings(username, data); st.rerun()
                    else:
                        if final_code not in data['holdings']: st.error("未持仓")
                        elif qty > data['holdings'][final_code]['qty']: st.error("持仓不足")
                        else:
                            data['cash'] += qty*prc
                            data['holdings'][final_code]['qty'] -= qty
                            if data['holdings'][final_code]['qty'] <= 0: del data['holdings'][final_code]
                            save_holdings(username, data); st.rerun()
                            
    with cf:
        with st.container(border=True):
            st.markdown("#### 💸 资金出入")
            f_act = st.selectbox("操作", ["入金 (增加本金)", "出金 (减少现金)"])
            f_amt = st.number_input("金额 (CNY)", min_value=0.0, step=1000.0)
            st.write("")
            st.write("")
            if st.button("确认划转", use_container_width=True):
                if "入金" in f_act: data['cash'] += f_amt
                elif f_amt <= data['cash']: data['cash'] -= f_amt
                else: st.error("现金不足")
                save_holdings(username, data); st.rerun()