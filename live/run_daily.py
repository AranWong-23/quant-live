#!/usr/bin/env python3
# run_daily.py - 每日主控（支持结构化数据输出的现代 UI 版）
import subprocess, sys, os, json, datetime, argparse
from openai import OpenAI
import requests
import tushare as ts

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import (TS_TOKEN, DS_API_KEY, DS_BASE_URL, PUSHPLUS_TOKEN,
                    get_holdings_file, BASE_DIR)
from amsis_v3_live import LiveAMSI, generate_report as v3_gen_report, get_deepseek_interpretation
from amsis_v3_live import get_recent_history as v3_get_recent
from daily_signal import LiveStrategy

ts.set_token(TS_TOKEN)
pro = ts.pro_api()
ds_client = OpenAI(api_key=DS_API_KEY, base_url=DS_BASE_URL) if DS_API_KEY else None

def push_wechat(title, content):
    if not PUSHPLUS_TOKEN:
        return
    url = "http://www.pushplus.plus/send"
    data = {"token": PUSHPLUS_TOKEN, "title": title, "content": content.replace("\n", "<br>"), "template": "html"}
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", type=str, default="main", help="账户名")
    args = parser.parse_args()
    account = args.account
    print(f"当前账户：{account}")

    trade_day = latest_trade_date()
    print(f"ℹ️ 最近交易日为 {trade_day}")

    # 1. 数据更新
    subprocess.run([sys.executable, "daily_update.py"], cwd=os.path.dirname(os.path.abspath(__file__)))

    # 2. V3 判读
    v3 = LiveAMSI()
    v3_data = v3.run()
    v3_report = v3_gen_report(v3_data)

    # 3. DeepSeek 对 V3 的解读
    ds_v3_interp = ""
    if ds_client:
        state_dist, _ = v3_get_recent()
        ds_v3_interp, _ = get_deepseek_interpretation(v3_report, state_dist, None)
        if ds_v3_interp:
            v3_report += f"\n【DeepSeek市场解读】\n{ds_v3_interp}"

    # 4. 策略信号
    strategy = LiveStrategy(account=account)
    strategy_report = strategy.daily_run()

    today = datetime.date.today().strftime('%Y-%m-%d')
    full_report = f"📊 AlphaEngine 日报 ({today}) - 账户：{account}\n"
    full_report += f"⏱️ 基于交易日：{trade_day}\n\n"

    # 提取指令用于文本报告
    actions = "今日无交易动作。"
    for title in ["【今日拟交易指令】", "【今日拟交易信号】"]:
        if title in strategy_report:
            start = strategy_report.find(title) + len(title)
            end = strategy_report.find("\n【", start)
            extracted = strategy_report[start:end].strip() if end != -1 else strategy_report[start:].strip()
            if extracted:
                actions = extracted
            break

    full_report += "══════════════════════\n"
    full_report += "📋 【今日绝对执行指令】\n" + actions + "\n"
    full_report += "══════════════════════\n\n"

    # 策略风控参谋
    ai_tip = ""
    if ds_client:
        prompt = f"""当前信号：{strategy_report[:800]}
请用不超过100字给出风控红绿灯（格式：【风控红绿灯】🟢平稳/🟡谨慎/🔴高危），然后只用一句话给出今日执行建议。"""
        try:
            resp = ds_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "system", "content": "量化助手"}, {"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=120, timeout=30)
            ai_tip = resp.choices[0].message.content
            full_report += f"🤖 【DeepSeek风控参谋】\n{ai_tip}\n\n"
        except:
            full_report += "🤖 【DeepSeek风控参谋】\n暂时不可用\n\n"

    full_report += "━━━ V3 市场深度报告 ━━━\n"
    full_report += v3_report + "\n"

    # 账户快照
    hf = get_holdings_file(account)
    full_report += "💼 【账户快照】\n"
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            portfolio = json.load(f)
        full_report += f"  现金：{portfolio['cash']:,.2f} 元\n"
        if not portfolio.get('holdings'):
            full_report += "  持仓：空仓\n"
        else:
            full_report += "  持仓：\n"
            for code, h in portfolio['holdings'].items():
                full_report += f"    - {h['name']} ({code}) {h['qty']}股\n"
    except:
        full_report += "  读取失败\n"

    full_report += "\n🔔 完成交易后请手动更新持仓文件"

    # ============================================================
    # ★ 新增：为 2026 现代 UI 提取纯净的 JSON 结构化数据 ★
    # ============================================================
    dashboard_data = {
        "date": str(today),
        "trade_date": str(trade_day),
        "v3_state": {
            "state": str(v3_data.get('state', '未知')),
            "duration": int(v3_data.get('duration', 0)),
            "vol_ratio": float(v3_data.get('vol_ratio', 0)),
            "up_ratio": float(v3_data.get('up_ratio', 0)),
            "close": float(v3_data.get('close', 0)),
            "ma20": float(v3_data.get('ma20', 0)),
            "ma60": float(v3_data.get('ma60', 0)),
            "sz_close": float(v3_data.get('sz_close', 0)),
            "lower": float(v3_data.get('lower', 0)),
            "upper": float(v3_data.get('upper', 0)),
            "bias_60": float(v3_data.get('bias_60', 0)),
            "a_above": bool(v3_data.get('a_above', False))  # <--- 就是这里修复了报错
        },
        "ai_analysis": {
            "v3_interp": str(ds_v3_interp) if ds_v3_interp else "",
            "risk_tip": str(ai_tip)
        },
        "orders": [],
        "rankings": []
    }

    # 提取订单数据
    for o in strategy.pending_orders:
        act = "买入" if o.type == "BUY" else "卖出"
        order_dict = {
            "action": str(act),
            "code": str(o.code),
            "name": str(o.name),
            "qty": int(o.qty),
            "reason": str(o.reason),
            "range": ""
        }
        if o.type == "BUY":
            try:
                buy_sig = strategy.analyze_buy_signal(o.code, trade_day, 0.5, False, False)
                if buy_sig:
                    order_dict["range"] = f"{float(buy_sig.price_lower):.3f} ~ {float(buy_sig.price_upper):.3f}"
            except:
                pass
        dashboard_data["orders"].append(order_dict)

    # 提取排行榜数据
    if hasattr(strategy, 'rankings') and strategy.rankings:
        top5 = sorted(strategy.rankings, key=lambda x: x.S, reverse=True)[:5]
        for i, item in enumerate(top5, 1):
            dashboard_data["rankings"].append({
                "num": int(i),
                "name": str(item.name),
                "code": str(item.code),
                "score": float(round(item.S, 1))
            })

    # 保存日志和 JSON 数据
    log_dir = os.path.join(os.path.dirname(__file__), "logs", account)
    os.makedirs(log_dir, exist_ok=True)
    
    # 1. 保存旧的 txt 文本报告 (兼容微信推送)
    with open(os.path.join(log_dir, f"report_{today}.txt"), 'w', encoding='utf-8') as f:
        f.write(full_report)
        
    # 2. 保存新的 json 结构化数据 (供漂亮网页读取)
    with open(os.path.join(log_dir, f"dashboard_{today}.json"), 'w', encoding='utf-8') as f:
        json.dump(dashboard_data, f, ensure_ascii=False, indent=2)

    print("\n" + full_report)
    push_wechat(f"AlphaEngine {today} [{account}]", full_report)
    print("✅ 全流程完成，结构化数据已生成")

if __name__ == "__main__":
    main()