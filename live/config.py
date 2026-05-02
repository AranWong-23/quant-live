import os
import importlib

# ========== API Token（优先从环境变量读取，更安全）==========
TS_TOKEN = os.environ.get("TS_TOKEN", "9946fc50def862e5d4e3b620abcf2f32ab1945d95e6e2d2187fb81a0")
DS_API_KEY = os.environ.get("DS_API_KEY", "sk-02523eca6446488ba739f9f76ce87615")
DS_BASE_URL = "https://api.deepseek.com"
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "dadf9d4d0ee14899b3bd89b6cbcd9b89")

# 如果本地有 .env 文件，用其覆盖默认值（本地运行时会用到）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    TS_TOKEN = os.getenv("TS_TOKEN", TS_TOKEN)
    DS_API_KEY = os.getenv("DS_API_KEY", DS_API_KEY)
    PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", PUSHPLUS_TOKEN)
except ImportError:
    pass

# ========== 路径配置（自动适配本地与云端环境）==========
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "backtestdata")
HFQ_DIR = os.path.join(DATA_DIR, "hfq")
INDEX_DIR = DATA_DIR
BREADTH_FILE = os.path.join(DATA_DIR, "market_breadth.csv")
V3_STATES_FILE = os.path.join(DATA_DIR, "v3_states.csv")
V3_LAST_STATE_FILE = os.path.join(BASE_DIR, "live", "last_state.json")
INIT_CASH = 100000.0
HOLDINGS_FILE = os.path.join(BASE_DIR, "live", "current_holdings.json")

# ========== 动态策略加载 ==========
STRATEGY_FILE = "alpha_engine.py"
STRATEGY_MODULE = STRATEGY_FILE.replace(".py", "")

def load_strategy():
    spec = importlib.util.spec_from_file_location(
        STRATEGY_MODULE,
        os.path.join(BASE_DIR, "live", STRATEGY_FILE)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AlphaEnginePro, module.Holding

# ========== 多账户持仓文件 ==========
def get_holdings_file(account="main"):
    if account == "main":
        return os.path.join(BASE_DIR, "live", "current_holdings.json")
    else:
        return os.path.join(BASE_DIR, "live", f"holdings_{account}.json")
