#!/usr/bin/env python3
# auth.py - 用户认证（登录、注册、注销）最终版
import yaml
import bcrypt
import os
import streamlit as st

AUTH_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.yaml")

def load_users():
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_users(users):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(users, f)

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def login():
    users = load_users()
    st.markdown("<h2 style='text-align: center; color: #2E86C1;'>🔐 登录</h2>", unsafe_allow_html=True)
    with st.form("login_form"):
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")
        if st.form_submit_button("🚀 登录"):
            if username in users and check_password(password, users[username]["password"]):
                st.session_state["logged_in"] = True
                st.session_state["username"] = username
                st.success("登录成功！正在跳转...")
                st.rerun()
            else:
                st.error("用户名或密码错误")

def register():
    users = load_users()
    st.title("📝 注册新用户")
    new_user = st.text_input("用户名", key="reg_username")
    new_pass = st.text_input("密码", type="password", key="reg_password")
    confirm_pass = st.text_input("确认密码", type="password", key="reg_confirm")
    initial_cash = st.number_input(
        "起始本金 (元)",
        min_value=10000, value=1000000, step=10000,
        key="reg_cash"
    )
    if st.button("注册", key="reg_btn"):
        if not new_user or not new_pass:
            st.error("用户名和密码不能为空")
        elif new_user in users:
            st.error("用户名已存在")
        elif new_pass != confirm_pass:
            st.error("两次密码不一致")
        else:
            users[new_user] = {
                "password": hash_password(new_pass),
                "initial_cash": initial_cash      # 保存本金
            }
            save_users(users)
            st.success("注册成功！请先登录，然后系统会自动创建账户。")
            # 注意：这里不直接登录，而是让用户去登录页面

def logout():
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.rerun()

def delete_account(username):
    users = load_users()
    if username in users:
        del users[username]
        save_users(users)
        # 删除持仓文件
        holdings_file = "/Users/aranwong/Documents/quant app/量化策略/live/holdings_{}.json".format(username)
        if os.path.exists(holdings_file):
            os.remove(holdings_file)
        if username == "main":
            main_file = "/Users/aranwong/Documents/quant app/量化策略/live/current_holdings.json"
            if os.path.exists(main_file):
                os.remove(main_file)
        st.session_state["logged_in"] = False
        st.session_state["username"] = None
        st.success("账户已注销")
        st.rerun()
