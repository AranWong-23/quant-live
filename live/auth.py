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

def git_sync(file_path=".", message="update"):
    """将指定文件或当前目录变更推送到 GitHub"""
    try:
        subprocess.run(["git", "config", "user.name", "Streamlit Cloud"], check=True)
        subprocess.run(["git", "config", "user.email", "streamlit@cloud.com"], check=True)
        subprocess.run(["git", "add", file_path], check=True, capture_output=True)
        # 仅当有变更时才提交
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True, capture_output=True)
            subprocess.run(["git", "push"], check=True, capture_output=True)
            return True
    except Exception:
        pass
    return False

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
            users[new_user] = {
                "password": hash_password(new_pass),
                "initial_cash": initial_cash
            }
            # 1. 更新用户文件
            save_users(users)

            # 2. 立即在本地创建持仓文件
            import os, json
            import traceback
            try:
                holdings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"holdings_{new_user}.json")
                default_holdings = {
                    "cash": initial_cash,
                    "holdings": {},
                    "peak_nav": initial_cash,
                    "cooling": {},
                    "cooling_type": {},
                    "frozen_until": None
                }
                with open(holdings_file, 'w', encoding='utf-8') as f:
                    json.dump(default_holdings, f, indent=2, ensure_ascii=False)
            except Exception as e:
                st.error(f"本地创建持仓文件失败，请检查权限！错误：{e}")
                return

            st.success("注册成功！请先登录，然后系统会自动创建账户。")

            # 3. 将用户文件和持仓文件提交到 GitHub（保证持久化）
            try:
                import subprocess
                git_sync(AUTH_FILE, f"注册新用户 {new_user}")
                git_sync(holdings_file, f"创建持仓文件 {new_user}")
            except Exception as e:
                st.warning(f"用户数据已创建，但同步到云端仓库失败：{e}")

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
