#!/usr/bin/env python3
# app.py - 登录、持仓管理、策略运行、日报展示（多账户）

import streamlit as st
import json, os, subprocess, sys, datetime
import pandas as pd
import auth   # 我们刚写的用户认证模块

# 路径
BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略/live"
POOL_FILE = os.path.join(BASE_DIR, "etf_pool.csv")
REPORT_DIR = os.path.join(BASE_DIR, "logs")

def load_pool():
    if os.path.exists(POOL_FILE):
        df = pd.read_csv(POOL_FILE, encoding='utf-8')
        return dict(zip(df['code'].str.strip(), df['name'].str.strip()))
    return {}

def load_holdings(username):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    if os.path.exists(file):
        with open(file, encoding='utf-8') as f:
            return json.load(f)
    return {"cash": 1000000.0, "holdings": {}, "peak_nav": 1000000.0, "cooling": {}, "cooling_type": {}, "frozen_until": None}

def save_holdings(username, data):
    file = os.path.join(BASE_DIR, f"holdings_{username}.json") if username != "main" else os.path.join(BASE_DIR, "current_holdings.json")
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# 检查登录状态
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = None

st.sidebar.title("AlphaEngine 控制台")

if not st.session_state["logged_in"]:
    tab1, tab2 = st.tabs(["登录", "注册"])
    with tab1:
        auth.login()
    with tab2:
        auth.register()
else:
    # 已登录
    username = st.session_state["username"]
    st.sidebar.success(f"当前用户：{username}")
    if st.sidebar.button("退出登录"):
        auth.logout()
    if st.sidebar.button("注销账户"):
        if st.sidebar.checkbox("确定永久删除账户及数据？"):
            auth.delete_account(username)
    pool = load_pool()
    tab1, tab2, tab3 = st.tabs(["📋 日报", "💼 持仓", "📈 排行榜"])

    with tab1:
        st.subheader("最新交易日报")
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        report_dir = os.path.join(REPORT_DIR, username)
        report_file = os.path.join(report_dir, f"report_{today}.txt")
        if os.path.exists(report_file):
            with open(report_file) as f:
                st.text(f.read())
        else:
            st.warning("今日日报尚未生成")
        if st.button("🔄 立刻运行策略（当前账户）"):
            with st.spinner("正在生成..."):
                subprocess.run([sys.executable, os.path.join(BASE_DIR, "run_daily.py"), "--account", username],
                               cwd=BASE_DIR, timeout=180)
                if os.path.exists(report_file):
                    with open(report_file) as f:
                        st.success("日报已生成")
                        st.text(f.read())
                else:
                    st.error("日报生成失败，请检查终端报错")

    with tab2:
        st.subheader("持仓管理")
        data = load_holdings(username)
        col1, col2 = st.columns(2)
        with col1:
            st.metric("可用现金", f"{data['cash']:,.2f} 元")
        with col2:
            st.metric("持仓品种数", len(data['holdings']))
        if not data['holdings']:
            st.info("空仓")
        else:
            for code, h in data['holdings'].items():
                st.write(f"**{h['name']}** ({code})")
                st.write(f"数量：{h['qty']} 股 | 成本：{h['cost']:.4f} | 最高价：{h['highest']:.4f}")


        st.subheader("下单")
        col1, col2 = st.columns(2)
        with col1:
            action = st.radio("操作", ["买入", "卖出"])
            code_input = st.text_input("ETF代码 (如 159682)")
            qty = st.number_input("数量", min_value=100, step=100, value=100)
            price = st.number_input("价格", min_value=0.001, format="%.3f", value=1.000)
            trade_date = st.text_input("交易日期 (YYYYMMDD，留空为今天)", value="")
        with col2:
            if st.button("✅ 提交"):
                data = load_holdings(username)
                full_code = None
                name = code_input.strip()
                if '.' in name:
                    full_code = name
                else:
                    for suffix in ['.SZ', '.SH']:
                        tmp = name + suffix
                        if tmp in pool or tmp in data.get('holdings', {}):
                            full_code = tmp
                            break
                if not full_code:
                    st.error("代码未找到")
                else:
                    name = pool.get(full_code, full_code)
                    if action == "买入":
                        cost = qty * price
                        if cost > data['cash']:
                            st.error("现金不足")
                        else:
                            data['cash'] -= cost
                            if full_code in data['holdings']:
                                h = data['holdings'][full_code]
                                total_qty = h['qty'] + qty
                                h['cost'] = round((h['qty']*h['cost'] + cost)/total_qty, 4)
                                h['qty'] = total_qty
                                h['highest'] = max(h['highest'], price)
                                st.success(f"加仓 {name} {qty}股")
                            else:
                                date_val = trade_date.strip() if trade_date.strip() else datetime.datetime.now().strftime('%Y%m%d')
                                data['holdings'][full_code] = {
                                    "name": name, "qty": qty, "cost": price,
                                    "highest": price, "buy_date": date_val,
                                    "signal_history": []
                                }
                                st.success(f"已买入 {name} {qty}股 @{price:.3f}")
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
                                st.success("卖出成功")
                    save_holdings(username, data)
                    st.rerun()


    with tab3:
        st.subheader("ETF 候选池")
        if pool:
            st.dataframe(pd.DataFrame(list(pool.items()), columns=["代码", "名称"]))
        else:
            st.warning("候选池文件未找到")