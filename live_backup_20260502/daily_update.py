#!/usr/bin/env python3
# daily_update.py - 只更新国内指数、港股指数、ETF（前+后复权）、市场广度

import pandas as pd
import tushare as ts
import requests
import time
import os
from datetime import datetime, timedelta

# 直接导入 config
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import TS_TOKEN, DATA_DIR, HFQ_DIR, BREADTH_FILE

ts.set_token(TS_TOKEN)
pro = ts.pro_api()

DOMESTIC_INDEX = {
    "000300.SH": "index_000300.SH.csv",
    "000852.SH": "index_000852.SH.csv",
    "000001.SH": "index_000001.SH.csv",
    "399001.SZ": "index_399001.SZ.csv",
    "000985.SH": "index_000985.SH.csv",
}

HK_INDEX_EM = {
    "HSI.HK": ("100.HSI", "index_HSI.HK.csv"),
    "HSTECH.HK": ("124.HSTECH", "index_HSTECH.HK.csv"),
    "HSHCI.HK": ("124.HSHCI", "index_HSHCI.HK.csv"),
}

COPY_FROM_HSI = ["HSI.HI", "HSBI.HK"]

POOL_FILE = os.path.join(os.path.dirname(__file__), "etf_pool.csv")
ETF_CODES = []
try:
    pool_df = pd.read_csv(POOL_FILE, encoding='utf-8')
    ETF_CODES = pool_df['code'].tolist()
    print(f"✅ 加载 ETF 池 {len(ETF_CODES)} 只")
except Exception as e:
    print(f"❌ 加载 ETF 池失败: {e}")

def load_csv(path):
    if os.path.exists(path):
        df = pd.read_csv(path, dtype={'trade_date': str})
        last_date = df['trade_date'].max() if not df.empty else '20050101'
        return df, last_date
    return pd.DataFrame(), '20050101'

def save_csv(df, path):
    df = df.drop_duplicates('trade_date', keep='last').sort_values('trade_date')
    df.to_csv(path, index=False)

def download_em(secid, start, end):
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "klt": "101", "fqt": "1",
        "end": "20500101", "lmt": "10000",
        "secid": secid,
    }
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        data = resp.json().get("data")
        if not data or not data.get("klines"):
            return pd.DataFrame()
        records = [k.split(",") for k in data["klines"]]
        if len(records[0]) < 6:
            return pd.DataFrame()
        cols = {0: "trade_date", 1: "open", 2: "close", 3: "high", 4: "low", 5: "volume"}
        df = pd.DataFrame(records).rename(columns=cols)
        df["trade_date"] = df["trade_date"].str.replace("-", "")
        for c in ["open","high","low","close","volume"]:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        return df[df['trade_date'].between(start, end)]
    except:
        return pd.DataFrame()

def update_domestic():
    today = datetime.today().strftime('%Y%m%d')
    for code, fname in DOMESTIC_INDEX.items():
        path = os.path.join(DATA_DIR, fname)
        df, last = load_csv(path)
        if last >= today: continue
        start = (pd.to_datetime(last) + timedelta(days=1)).strftime('%Y%m%d')
        try:
            new = pro.index_daily(ts_code=code, start_date=start, end_date=today)
            if not new.empty:
                if 'vol' in new.columns: new = new.rename(columns={'vol': 'volume'})
                df = pd.concat([df, new])
                save_csv(df, path)
                print(f"  ✅ {code} 更新 {len(new)} 条")
        except Exception as e:
            print(f"  ❌ {code} 失败: {e}")

def update_hk():
    today = datetime.today().strftime('%Y%m%d')
    for code, (secid, fname) in HK_INDEX_EM.items():
        path = os.path.join(DATA_DIR, fname)
        df, last = load_csv(path)
        if last >= today: continue
        start = (pd.to_datetime(last) + timedelta(days=1)).strftime('%Y%m%d')
        df_new = download_em(secid, start, today)
        if not df_new.empty:
            df = pd.concat([df, df_new])
            save_csv(df, path)
            print(f"  ✅ {code} 更新 {len(df_new)} 条")
        else:
            print(f"  ⚠️ {code} 暂无新数据")

def update_etf():
    today = datetime.today().strftime('%Y%m%d')
    for code in ETF_CODES:
        fq_path = os.path.join(DATA_DIR, f"etf_{code}.csv")
        hfq_path = os.path.join(HFQ_DIR, f"etf_{code}.csv")
        os.makedirs(HFQ_DIR, exist_ok=True)
        df_fq, last_fq = load_csv(fq_path)
        df_hfq, last_hfq = load_csv(hfq_path)
        last = min(last_fq, last_hfq)
        if last >= today: continue
        start = (pd.to_datetime(last) + timedelta(days=1)).strftime('%Y%m%d')
        try:
            daily = pro.fund_daily(ts_code=code, start_date=start, end_date=today)
            if daily.empty: continue
            if 'vol' in daily.columns: daily = daily.rename(columns={'vol': 'volume'})
            daily['trade_date'] = daily['trade_date'].astype(str)
            base = daily[['trade_date','open','high','low','close','volume','amount']]
            df_fq = pd.concat([df_fq, base])
            save_csv(df_fq, fq_path)
            try: adj = pro.fund_adj(ts_code=code, start_date=start, end_date=today)
            except: adj = pd.DataFrame()
            if not adj.empty:
                merged = daily.merge(adj[['trade_date','adj_factor']], on='trade_date', how='left')
                merged['close_hfq'] = merged['close'] / merged['adj_factor'].fillna(1)
                hfq_out = merged[['trade_date','open','high','low','close_hfq','volume','amount']]
                hfq_out.columns = ['trade_date','open','high','low','close','volume','amount']
            else:
                hfq_out = base.copy()
            df_hfq = pd.concat([df_hfq, hfq_out])
            save_csv(df_hfq, hfq_path)
            print(f"  ✅ ETF {code} 更新")
        except Exception as e:
            print(f"  ❌ ETF {code} 失败: {e}")

def update_breadth():
    today = datetime.today().strftime('%Y%m%d')
    df, last = load_csv(BREADTH_FILE)
    if last >= today:
        print("  ✅ 广度已最新")
        return
    cal = pro.trade_cal(exchange='SSE', start_date=datetime.strptime(last, '%Y%m%d').strftime('%Y%m%d'), end_date=today, is_open='1')
    missing = cal['cal_date'].tolist()
    if not missing: return
    new_rows = []
    for d in missing:
        try:
            daily = pro.daily(trade_date=d)
            if not daily.empty:
                up = (daily['pct_chg'] > 0).sum()
                down = (daily['pct_chg'] < 0).sum()
                bre = (up - down) / len(daily) if len(daily) else 0
            else: bre = 0
        except: bre = 0
        new_rows.append([d, bre])
        time.sleep(0.15)
    df_new = pd.DataFrame(new_rows, columns=['trade_date','breadth'])
    df = pd.concat([df, df_new])
    save_csv(df, BREADTH_FILE)
    print(f"  ✅ 广度新增 {len(df_new)} 条")

def update_all():
    print("=== 数据更新（最终稳定版）===")
    update_domestic()
    update_hk()
    update_etf()
    update_breadth()
    hsi = os.path.join(DATA_DIR, "index_HSI.HK.csv")
    if os.path.exists(hsi):
        import shutil
        for code in COPY_FROM_HSI:
            dest = os.path.join(DATA_DIR, f"index_{code}.csv")
            if not os.path.exists(dest):
                shutil.copy(hsi, dest)
    print("=== 完成 ===")

if __name__ == "__main__":
    update_all()