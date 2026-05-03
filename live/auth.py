#!/usr/bin/env python3
# auth.py - 支持 GitHub API 持久化的用户管理模块
import yaml
import bcrypt
import os
import json
import base64
import requests
import streamlit as st

# ==================== 路径 ====================
AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.yaml")
HOLDINGS_DIR = os.path.dirname(os.path.abspath(__file__))

def load_users():
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}

def save_users(users):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        yaml.dump(users, f, allow_unicode=True)

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())

def commit_file_to_github(token, repo, path, content, message):
    """通过 GitHub API 提交单个文件"""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    # 获取当前文件的 sha（如果已存在）
    resp = requests.get(url, headers=headers)
    sha = resp.json().get("sha") if resp.status_code == 200 else None
    data = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": "main"
    }
    if sha:
        data["sha"] = sha
    resp = requests.put(url, json=data, headers=headers)
    return resp.status_code in (200, 201)

def login():
    users = load_users()
    st.title("🔐 登录")
    username = st.text_input("用户名", key="login_username")
    password = st.text_input("密码", type="password", key="login_password")
    if st.button("登录", key="login_btn"):
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
            # 更新用户列表
            users[new_user] = {
                "password": hash_password(new_pass),
                "initial_cash": initial_cash
            }
            save_users(users)

            # 创建持仓文件内容
            default_holdings = {
                "cash": initial_cash,
                "holdings": {},
                "peak_nav": initial_cash,
                "cooling": {},
                "cooling_type": {},
                "frozen_until": None
            }
            holdings_json = json.dumps(default_holdings, indent=2, ensure_ascii=False)

            # 提交到 GitHub
            token = st.secrets.get("GH_TOKEN", "")
            if not token:
                st.error("GitHub Token 未配置，无法保存用户数据。请检查 Streamlit Cloud Secrets。")
                return

            users_yaml = yaml.dump(users, allow_unicode=True)
            try:
                commit_file_to_github(token, "AranWong-23/quant-live", "live/users.yaml", users_yaml, f"注册新用户 {new_user}")
                commit_file_to_github(token, "AranWong-23/quant-live", f"live/holdings_{new_user}.json", holdings_json, f"创建持仓文件 {new_user}")
                st.success("注册成功！请前往登录页面登录。")
            except Exception as e:
                st.warning(f"用户已创建，但同步到云端失败：{e}")

def logout():
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.rerun()

def logout():
    st.session_state["logged_in"] = False
    st.session_state["username"] = None
    st.rerun()

def delete_account(username):
    # 此功能在云端暂不实现，如需删除请手动修改 users.yaml
    pass
