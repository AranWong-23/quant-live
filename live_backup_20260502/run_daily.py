#!/usr/bin/env python3
# run_daily.py - 每日主控（清晰排版，实时显示关键信息）

import subprocess, sys, os, json, datetime, requests, tushare as ts
from openai import OpenAI

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import (TS_TOKEN, DS_API_KEY, DS_BASE_URL, PUSHPLUS_TOKEN,
                    HOLDINGS_FILE, DATA_DIR)
from amsis_v3_live import LiveAMSI, generate_report as v3_gen_report, get_deepseek_interpretation
from amsis_v3_live import get_recent_history as v3_get_recent
from daily_signal import LiveStrategy

ts.set_token(TS_TOKEN)
pro = ts.pro_api()
ds_client = OpenAI(api_key=DS_API_KEY, base_url=DS_BASE_URL) if DS_API_KEY else None
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.csv")

def push_wechat(title, content):
    if not PUSHPLUS_TOKEN:
        return
    url = "http://www.pushplus.plus/send"
    data = {"token": PUSHPLUS_TOKEN, "title": title,
            "content": content.replace("\n", "<br>"), "template": "html"}
    requests.post(url, json=data)

def latest_trade_date():
    today = datetime.date.today()
    for i in range(5):
        d = (today - datetime.timedelta(days=i)).strftime('%Y%m%d')
        try:
            if pro.trade_cal(exchange='SSE', start_date=d, end_date=d).iloc[0]['is_open'] == 1:
                return d
        except:
            pass
    return today.strftime('%Y%m%d')

def main():
    trade_day = latest_trade_date()
    print(f"ℹ️ 最近交易日：{trade_day}")

    # 1. 数据更新
    subprocess.run([sys.executable, "daily_update.py"], cwd=os.path.dirname(os.path.abspath(__file__)))

    # 2. V3判读
    v3 = LiveAMSI()
    v3_data = v3.run()
    v3_report = v3_gen_report(v3_data)
    if ds_client:
        state_dist, _ = v3_get_recent()
        interp, _ = get_deepseek_interpretation(v3_report, state_dist, None)
        if interp:
            v3_report += f"\n【DeepSeek市场解读】\n{interp}"

    # 3. V2信号
    strategy = LiveStrategy()
    strategy_report = strategy.daily_run()

    # 构造最终报告
    today = datetime.date.today().strftime('%Y-%m-%d')
    full = f"📊 AlphaEngine 日报 ({today})\n"
    full += f"⏱️ 基于交易日：{trade_day}\n\n"

    # 提取指令
    actions = "今日无交易动作。"
    for title in ["【今日拟交易指令】", "【今日拟交易信号】"]:
        if title in strategy_report:
            start = strategy_report.find(title) + len(title)
            end = strategy_report.find("\n【", start)
            extracted = strategy_report[start:end].strip() if end != -1 else strategy_report[start:].strip()
            if extracted:
                actions = extracted
            break
    full += "══════════════════════\n"
    full += "📋 【今日绝对执行指令】\n" + actions + "\n"
    full += "══════════════════════\n\n"

    # AI参谋（100字以内）
    if ds_client:
        prompt = f"""当前信号：{strategy_report[:800]}
请用不超过100字给出风控红绿灯（格式：【风控红绿灯】🟢平稳/🟡谨慎/🔴高危），然后只用一句话给出今日执行建议。"""
        try:
            resp = ds_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": "量化助手"},
                          {"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=120, timeout=30)
            ai_tip = resp.choices[0].message.content
            full += f"🤖 【DeepSeek风控参谋】\n{ai_tip}\n\n"
        except:
            full += "🤖 【DeepSeek风控参谋】\n暂时不可用\n\n"

    # V3摘要
    v3_short = []
    for line in v3_report.splitlines():
        if "状态:" in line or "赚钱效应" in line or "策略路由建议" in line or "核心关注点" in line:
            v3_short.append(line)
    full += "━━━ V3市场状态 ━━━\n" + "\n".join(v3_short) + "\n\n"

    # 持仓快照
    full += "💼 【账户快照】\n"
    try:
        with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
            p = json.load(f)
        full += f"  现金：{p['cash']:,.2f} 元\n"
        if not p['holdings']:
            full += "  持仓：空仓\n"
        else:
            full += "  持仓：\n"
            for code, h in p['holdings'].items():
                full += f"    - {h['name']} ({code}) {h['qty']}股  成本{h['cost']:.3f}\n"
    except:
        full += "  读取失败，请检查 current_holdings.json\n"

    full += "\n🔔 完成交易后请手动更新 current_holdings.json"

    # 保存日志与推送
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"report_{today}.txt"), 'w', encoding='utf-8') as f:
        f.write(full)
    print("\n" + full)
    push_wechat(f"AlphaEngine {today}", full)
    print("✅ 全流程完成")

if __name__ == "__main__":
    main()