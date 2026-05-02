# config.py
import os

# ========== 你的 API Token（必须修改）==========
TS_TOKEN = "9946fc50def862e5d4e3b620abcf2f32ab1945d95e6e2d2187fb81a0"                  # 去 tushare.pro 复制
DS_API_KEY = "sk-02523eca6446488ba739f9f76ce87615"          # 去 platform.deepseek.com 复制
DS_BASE_URL = "https://api.deepseek.com"

# ========== 推送 Token（可选）==========
PUSHPLUS_TOKEN = "dadf9d4d0ee14899b3bd89b6cbcd9b89"                         # 去 pushplus.plus 注册获取

# ========== 路径配置（不用改）==========
BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略"
DATA_DIR = os.path.join(BASE_DIR, "backtestdata")
HFQ_DIR = os.path.join(DATA_DIR, "hfq")
INDEX_DIR = DATA_DIR
BREADTH_FILE = os.path.join(DATA_DIR, "market_breadth.csv")
V3_STATES_FILE = os.path.join(DATA_DIR, "v3_states.csv")
V3_LAST_STATE_FILE = os.path.join(BASE_DIR, "live", "last_state.json")
HOLDINGS_FILE = os.path.join(BASE_DIR, "live", "current_holdings.json")

# ---------- 初始本金 ----------
INIT_CASH = 100000.0