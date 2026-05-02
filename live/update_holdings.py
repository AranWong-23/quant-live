#!/usr/bin/env python3
# update_holdings.py — 支持池外ETF手动添加

import json
import os
import pandas as pd
from datetime import datetime

HOLDINGS_FILE = "/Users/aranwong/Documents/quant app/量化策略/live/current_holdings.json"
POOL_FILE = "/Users/aranwong/Documents/quant app/量化策略/live/etf_pool.csv"

POOL_MAP = {}
if os.path.exists(POOL_FILE):
    try:
        df = pd.read_csv(POOL_FILE, encoding='utf-8')
        for _, row in df.iterrows():
            code = str(row['code']).strip()
            name = str(row['name']).strip()
            if code:
                POOL_MAP[code] = name
    except Exception as e:
        print(f"⚠️ 加载 etf_pool.csv 失败: {e}")

def load():
    if os.path.exists(HOLDINGS_FILE):
        with open(HOLDINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "cash": 1000000.0,
        "holdings": {},
        "peak_nav": 1000000.0,
        "cooling": {},
        "cooling_type": {},
        "frozen_until": None
    }

def save(data):
    with open(HOLDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("✅ 持仓已保存")

def show(data):
    print("\n" + "=" * 40)
    print("💰 当前现金余额：", f"{data['cash']:,.2f} 元")
    print("📦 当前持仓：")
    if not data['holdings']:
        print("  （空仓）")
    else:
        for code, h in data['holdings'].items():
            print(f"  {h['name']} ({code})")
            print(f"    数量：{h['qty']} 股")
            print(f"    成本：{h['cost']:.4f} 元")
            print(f"    最高价：{h['highest']:.4f} 元")
            print(f"    买入日期：{h.get('buy_date', '无记录')}")
    print("=" * 40 + "\n")

def find_full_code(input_code, data):
    """查找完整代码，优先持仓，其次池子"""
    if "." in input_code:
        if input_code in data['holdings']:
            return input_code, data['holdings'][input_code]['name']
        if input_code in POOL_MAP:
            return input_code, POOL_MAP[input_code]
        return input_code, None

    for suffix in ['.SZ', '.SH']:
        full = input_code + suffix
        if full in data['holdings']:
            return full, data['holdings'][full]['name']
        if full in POOL_MAP:
            return full, POOL_MAP[full]
    return None, None

def manual_add_etf():
    """手动添加池外ETF"""
    code = input("请输入完整代码（如 159845.SZ）：").strip()
    if not code:
        return None, None
    name = input("ETF名称（如 中证1000增强）：").strip()
    return code, name

def get_date(prompt):
    today = datetime.now().strftime('%Y%m%d')
    date_str = input(prompt).strip()
    if not date_str:
        return today
    if len(date_str) != 8 or not date_str.isdigit():
        print("⚠️ 日期格式不正确，将默认使用今天。")
        return today
    return date_str

def main():
    global data
    data = load()
    show(data)

    while True:
        print("请选择操作：")
        print("  b = 买入（系统自动识别加仓）")
        print("  s = 卖出")
        print("  c = 直接修改现金余额")
        print("  d = 删除某个持仓")
        print("  q = 退出")
        choice = input("➜ ").strip().lower()

        if choice == 'q':
            break

        elif choice == 'b':
            user_input = input("ETF代码（如 159682，不用加 .SZ/.SH）：").strip()
            if not user_input:
                continue

            full_code, name = find_full_code(user_input, data)

            # 如果找不到，提供手动添加选项
            if full_code is None:
                print("⚠️ 该ETF不在候选池或当前持仓中。")
                manual = input("是否手动添加持仓？(y/n)：").strip().lower()
                if manual == 'y':
                    full_code, name = manual_add_etf()
                    if not full_code:
                        continue
                else:
                    continue

            if full_code in data['holdings']:
                name = data['holdings'][full_code].get('name', name)
                print(f"  已持有 {name}，将进行加仓。")
            else:
                if not name:
                    name = input("ETF名称（系统未识别，请手动输入）：").strip()
                    if not name:
                        name = full_code
                print(f"  将新建持仓：{name} ({full_code})")

            trade_date = get_date("请输入交易日期（格式 YYYYMMDD，直接回车默认为今天）：")
            try:
                qty = int(input("数量（股）："))
                price = float(input("成交均价（元）："))
            except ValueError:
                print("❌ 数量和价格必须是数字")
                continue

            cost = round(qty * price, 2)
            if cost > data['cash']:
                print("❌ 现金不足，无法买入")
                continue

            data['cash'] = round(data['cash'] - cost, 2)
            if full_code in data['holdings']:
                old = data['holdings'][full_code]
                total_qty = old['qty'] + qty
                old['cost'] = round((old['qty'] * old['cost'] + qty * price) / total_qty, 4)
                old['qty'] = total_qty
                old['highest'] = max(old['highest'], price)
                print(f"✅ 加仓成功！{name} 现持有 {total_qty} 股，均价 {old['cost']:.4f}")
            else:
                data['holdings'][full_code] = {
                    "name": name,
                    "qty": qty,
                    "cost": price,
                    "highest": price,
                    "buy_date": trade_date,
                    "signal_history": []
                }
                print(f"✅ 已买入 {name}({full_code}) {qty} 股 @{price:.4f}")
                print("⚠️ 提醒：该ETF不在你的候选人池中，策略不会主动管理该持仓，需自行决定卖出。")
            save(data)

        elif choice == 's':
            user_input = input("ETF代码（如 159682，不用加 .SZ/.SH）：").strip()
            full_code, _ = find_full_code(user_input, data)
            if full_code is None or full_code not in data['holdings']:
                print("❌ 持仓中没有该 ETF")
                continue
            h = data['holdings'][full_code]
            try:
                qty = int(input(f"卖出数量（当前持有 {h['qty']} 股）："))
                price = float(input("成交均价（元）："))
            except ValueError:
                print("❌ 数量和价格必须是数字")
                continue
            if qty > h['qty']:
                print("❌ 卖出数量超过持有数量")
                continue
            proceeds = round(qty * price, 2)
            data['cash'] = round(data['cash'] + proceeds, 2)
            h['qty'] -= qty
            if h['qty'] == 0:
                del data['holdings'][full_code]
                print(f"✅ 已清仓 {full_code}")
            else:
                print(f"✅ 已卖出 {full_code} {qty} 股，剩余 {h['qty']} 股")
            save(data)

        elif choice == 'c':
            try:
                new_cash = float(input("请输入正确的现金余额（元）："))
                if new_cash < 0:
                    print("❌ 不能为负数")
                    continue
                data['cash'] = round(new_cash, 2)
                print(f"✅ 现金余额已修正为 {data['cash']:,.2f}")
                save(data)
            except ValueError:
                print("❌ 请输入数字")

        elif choice == 'd':
            user_input = input("请输入要删除的 ETF 代码（如 159682）：").strip()
            full_code, _ = find_full_code(user_input, data)
            if full_code is None or full_code not in data['holdings']:
                print("❌ 持仓中没有该 ETF")
                continue
            confirm = input(f"确定要删除 {data['holdings'][full_code]['name']}({full_code}) 吗？(y/n)：").strip().lower()
            if confirm == 'y':
                del data['holdings'][full_code]
                print(f"✅ 已删除 {full_code}")
                save(data)
            else:
                print("已取消")

        else:
            print("无效的选择，请重新输入。")

        show(data)

if __name__ == "__main__":
    main()