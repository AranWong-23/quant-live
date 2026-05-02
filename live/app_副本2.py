#!/usr/bin/env python3
# app.py - 基于真实日报结构优化版（含交易日显示）
import streamlit as st
import json, os, subprocess, sys, datetime, re
import pandas as pd
import auth

st.set_page_config(page_title="AlphaEngine", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .main, .stApp { background-color: #F5F6FA; }
    .card {
        background: #FFFFFF; border-radius: 16px; padding: 24px;
        margin: 12px 0; box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid #F0F0F0;
    }
    .big-number { font-size: clamp(2rem, 3vw, 2.8rem); font-weight: 700; color: #1A1A2E; }
    .status-badge { display: inline-block; padding: 6px 16px; border-radius: 24px; font-size: 1rem; font-weight: 600; }
    .badge-bull { background: #D5F5E3; color: #1E8449; }
    .badge-bear { background: #FADBD8; color: #C0392B; }
    .badge-sideways { background: #FCF3CF; color: #B7950B; }
    .stButton>button { border-radius: 10px; font-weight: 600; border: none; background: #1A73E8; color: white; padding: 10px 20px; }
    .stButton>button:hover { background: #1557B0; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input { border-radius: 8px; border: 1px solid #D0D5DD; }
    [data-testid="stSidebar"] { background-color: #FFFFFF; border-right: 1px solid #F0F0F0; }
</style>
""", unsafe_allow_html=True)

BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略/live"
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
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    return {"cash": 1_000_000.0, "holdings": {}, "peak_nav": 1_000_000.0, "cooling": {}, "cooling_type": {}, "frozen_until": None}

def save_holdings(username, data):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_traffic_light():
    v3 = load_v3_state()
    if not v3: return "未知", ""
    state = v3.get("state", "未知")
    return {
        "SYSTEMIC_BULL": ("🟢 牛市", "badge-bull"),
        "SYSTEMIC_BEAR": ("🔴 熊市", "badge-bear"),
        "SIDEWAYS_UP": ("🟡 震荡偏强", "badge-sideways"),
        "SIDEWAYS_DOWN": ("🟠 震荡偏弱", "badge-sideways"),
        "SIDEWAYS": ("⚪ 中性震荡", "badge-sideways"),
    }.get(state, (state, ""))

def latest_trade_date():
    import tushare as ts
    from config import TS_TOKEN
    ts.set_token(TS_TOKEN)
    pro = ts.pro_api()
    today = datetime.date.today()
    for i in range(5):
        d = (today - datetime.timedelta(days=i)).strftime('%Y%m%d')
        try:
            if pro.trade_cal(exchange='SSE', start_date=d, end_date=d).iloc[0]['is_open'] == 1:
                return d
        except:
            pass
    return today.strftime('%Y%m%d')

def extract_block(text, start_marker, end_marker=None):
    start = text.find(start_marker)
    if start == -1: return ""
    start += len(start_marker)
    if end_marker:
        end = text.find(end_marker, start)
        return text[start:end].strip() if end != -1 else text[start:].strip()
    return text[start:].strip()

# ==================== 登录 ====================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None

with st.sidebar:
    st.markdown("<h2 style='color:#1A73E8;'>🚀 AlphaEngine</h2>", unsafe_allow_html=True)
    st.caption("全球动量轮动 · V3 拦截版")
    st.divider()
    if st.session_state.logged_in:
        username = st.session_state.username
        st.success(f"👤 {username}")
        st.divider()
        if st.button("🚪 退出登录"): auth.logout()
        with st.expander("⚠️ 危险操作"):
            if st.button("注销账户") and st.checkbox("确认永久删除账户及所有数据"):
                auth.delete_account(username)
    else:
        st.info("请先登录")

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        with st.container():
            tab1, tab2 = st.tabs(["🔐 登录", "📝 注册"])
            with tab1: auth.login()
            with tab2: auth.register()
else:
    username = st.session_state.username
    pool = load_pool()
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    report_dir = os.path.join(REPORT_DIR, username)
    report_file = os.path.join(report_dir, f"report_{today_str}.txt")
    data = load_holdings(username)

    tab_main, tab_portfolio = st.tabs(["📊 今日概览", "💼 持仓管理"])

    with tab_main:
        if st.button("🔄 刷新信号", use_container_width=True):
            subprocess.run([sys.executable, os.path.join(BASE_DIR, "run_daily.py"), "--account", username],
                           cwd=BASE_DIR, timeout=180)
            st.success("策略运行完毕，页面将刷新...")
            st.rerun()

        trade_day = latest_trade_date()
        light_text, badge = get_traffic_light()
        if light_text:
            v3 = load_v3_state()
            st.markdown(f"""
            <div class="card">
                <span class="status-badge {badge}">{light_text}</span>
                <span style="margin-left:12px;">基于交易日：{trade_day} | 持续 {v3.get('duration', '?') if v3 else '?'} 天</span>
            </div>
            """, unsafe_allow_html=True)

        if not os.path.exists(report_file):
            st.warning("今日日报尚未生成")
        else:
            full_report = open(report_file, encoding='utf-8').read()

            # 指令
            orders_raw = extract_block(full_report, "📋 【今日绝对执行指令】", "🏆 【今日ETF排行榜")
            if orders_raw:
                st.markdown("### 📋 今日交易指令")
                st.markdown(f'<div class="card">{orders_raw.strip().replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
            else:
                st.info("今日无交易动作")

            # AI 解读
            st.markdown("### 🤖 今日 AI 综合解读")
            v3_full = extract_block(full_report, "━━━ V3 市场深度报告 ━━━", "💼 【账户快照】")
            strategy_ai = extract_block(full_report, "🤖 【DeepSeek风控参谋】", "━━━ V3 市场深度报告")
            combined = ""
            if v3_full:
                # 把里面的 【DeepSeek市场解读】 独立为小标题
                v3_full = v3_full.replace("【DeepSeek市场解读】", "\n\n**📡 情景推演与AI解读**\n")
                combined += f"**📡 V3 市场判读**<br>{v3_full.replace(chr(10), '<br>')}<br><br>"
            if strategy_ai:
                combined += f"**⚡ 策略风控参谋**<br>{strategy_ai.replace(chr(10), '<br>')}"
            if combined:
                st.markdown(f'<div class="card">{combined}</div>', unsafe_allow_html=True)
            else:
                st.info("暂无 AI 解读")

            # 排行榜
            st.markdown("### 🏆 今日 TOP5 信号")
            rankings_block = extract_block(full_report, "🏆 【今日ETF排行榜", "══════════════════════")
            if not rankings_block:
                rankings_block = extract_block(full_report, "🏆 【今日ETF排行榜", "🤖 【DeepSeek风控参谋】")
            if not rankings_block:
                rankings_block = extract_block(full_report, "🏆 【今日ETF排行榜", "━━━ V3 市场深度报告")
            rankings = []
            if rankings_block:
                for line in rankings_block.splitlines():
                    m = re.match(r'(\d+)\.\s+(.+?)\s+\((\d+\.(?:SZ|SH))\)\s+S=([\d.]+)', line)
                    if m:
                        rankings.append({"排名": m.group(1), "名称": m.group(2), "代码": m.group(3), "S分": float(m.group(4))})
                        if len(rankings) == 5: break
            if rankings:
                st.dataframe(pd.DataFrame(rankings), use_container_width=True, hide_index=True)
            else:
                st.info("暂无排行榜数据")

    # 持仓管理
    with tab_portfolio:
        total = data['cash'] + sum(h['qty'] * h['highest'] for h in data['holdings'].values())
        st.markdown(f"""
        <div class="card">
            <p>总资产</p>
            <p class="big-number">¥{total:,.2f}</p>
            <p>可用现金：¥{data['cash']:,.2f}  ·  持仓品种：{len(data['holdings'])}</p>
        </div>
        """, unsafe_allow_html=True)

    # ---------- 入金 / 出金 ----------
    st.markdown("#### 💰 资金调整（入金/出金）")
    col_fund1, col_fund2, col_fund3 = st.columns([1, 1, 1])
    with col_fund1:
        fund_action = st.selectbox("操作", ["入金", "出金"], key="fund_action")
    with col_fund2:
        fund_amount = st.number_input("金额", min_value=0.0, step=1000.0, value=0.0, key="fund_amount")
    with col_fund3:
        if st.button("执行", key="fund_exec"):
            data = load_holdings(username)
            if fund_action == "入金":
                data['cash'] += fund_amount
                st.success(f"入金成功，当前现金：{data['cash']:,.2f}")
            else:
                if fund_amount > data['cash']:
                    st.error("出金金额不可超过当前现金")
                else:
                    data['cash'] -= fund_amount
                    st.success(f"出金成功，当前现金：{data['cash']:,.2f}")
            save_holdings(username, data)
            st.rerun()
        
        if data['holdings']:
            st.markdown("#### 当前持仓")
            for code, h in data['holdings'].items():
                st.markdown(f"""
                <div class="card">
                    <b>{h['name']}</b> ({code})<br>
                    数量：{h['qty']} 股 | 成本：¥{h['cost']:.4f} | 最高价：¥{h['highest']:.4f}
                </div>
                """, unsafe_allow_html=True)
        st.divider()
        st.markdown("#### ⚡ 下单录入")
        col_l, col_r = st.columns(2)
        with col_l:
            action = st.radio("操作", ["买入", "卖出"], horizontal=True)
            manual = st.checkbox("手动输入完整代码（候选池外ETF）")
            if manual:
                code_in = st.text_input("完整代码", key="man_code")
                name_in = st.text_input("ETF名称", key="man_name")
            else:
                code_in = st.text_input("ETF代码", key="auto_code")
                name_in = ""
            trade_date = st.text_input("交易日期 (YYYYMMDD)")
            qty = st.number_input("数量", min_value=100, step=100)
            price = st.number_input("价格", min_value=0.001, format="%.3f")
        with col_r:
            if st.button("✅ 确认提交"):
                data = load_holdings(username)
                if manual:
                    full_code = code_in.strip()
                    name = name_in.strip() or full_code
                else:
                    full_code = None
                    raw = code_in.strip()
                    if '.' in raw: full_code = raw
                    else:
                        for suffix in ['.SZ', '.SH']:
                            tmp = raw + suffix
                            if tmp in pool or tmp in data.get('holdings', {}):
                                full_code = tmp; break
                    if not full_code:
                        st.error("代码未找到")
                        st.stop()
                    name = pool.get(full_code, full_code)
                buy_date = trade_date.strip() or datetime.datetime.now().strftime('%Y%m%d')
                if action == "买入":
                    cost = qty * price
                    if cost > data['cash']:
                        st.error("现金不足")
                    else:
                        data['cash'] -= cost
                        if full_code in data['holdings']:
                            h = data['holdings'][full_code]
                            total_qty = h['qty'] + qty
                            h['cost'] = round((h['qty']*h['cost']+cost)/total_qty, 4)
                            h['qty'] = total_qty
                            h['highest'] = max(h['highest'], price)
                            st.success(f"加仓 {name} {qty}股")
                        else:
                            data['holdings'][full_code] = {
                                "name": name, "qty": qty, "cost": price,
                                "highest": price, "buy_date": buy_date, "signal_history": []
                            }
                            st.success(f"买入 {name} {qty}股 @ ¥{price:.3f}")
                else:
                    if full_code not in data['holdings']:
                        st.error("无此持仓")
                    else:
                        h = data['holdings'][full_code]
                        if qty > h['qty']:
                            st.error("数量超过持仓")
                        else:
                            data['cash'] += qty * price
                            h['qty'] -= qty
                            if h['qty'] == 0:
                                del data['holdings'][full_code]
                                st.success(f"已清仓 {full_code}")
                            else:
                                st.success(f"卖出 {full_code} {qty}股，剩余 {h['qty']} 股")
                save_holdings(username, data)
                st.rerun()
        with st.expander("📈 全部候选池 ETF"):
            if pool:
                st.dataframe(pd.DataFrame(list(pool.items()), columns=["代码", "名称"]), use_container_width=True)