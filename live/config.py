import os
import importlib

# ========== 你的 API Token（必须修改）==========
TS_TOKEN = "9946fc50def862e5d4e3b620abcf2f32ab1945d95e6e2d2187fb81a0"  
DS_API_KEY = "sk-02523eca6446488ba739f9f76ce87615"
DS_BASE_URL = "https://api.deepseek.com"
PUSHPLUS_TOKEN = "dadf9d4d0ee14899b3bd89b6cbcd9b89"   # 可以不填，不影响网页使用

# ========== 路径配置 ==========
BASE_DIR = "/Users/aranwong/Documents/quant app/量化策略"
DATA_DIR = os.path.join(BASE_DIR, "backtestdata")
HFQ_DIR = os.path.join(DATA_DIR, "hfq")
INDEX_DIR = DATA_DIR
BREADTH_FILE = os.path.join(DATA_DIR, "market_breadth.csv")
V3_STATES_FILE = os.path.join(DATA_DIR, "v3_states.csv")
V3_LAST_STATE_FILE = os.path.join(BASE_DIR, "live", "last_state.json")
INIT_CASH = 100000.0
HOLDINGS_FILE = os.path.join(BASE_DIR, "live", "current_holdings.json")   # 保留旧版兼容


# ========== 动态策略加载 ==========
# 你要使用的策略文件（放在 live 目录下）
STRATEGY_FILE = "alpha_engine.py"   # 或者 "strategy_v2.py" 等
STRATEGY_MODULE = STRATEGY_FILE.replace(".py", "")

def load_strategy():
    """动态加载策略模块，返回 (AlphaEnginePro类, Holding类)"""
    spec = importlib.util.spec_from_file_location(
        STRATEGY_MODULE,
        os.path.join(BASE_DIR, "live", STRATEGY_FILE)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 假设策略文件中定义了 AlphaEnginePro 和 Holding
    return module.AlphaEnginePro, module.Holding


# ========== 多账户持仓文件 ==========
def get_holdings_file(account="main"):
    """返回指定账户的持仓文件路径"""
    if account == "main":
        return os.path.join(BASE_DIR, "live", "current_holdings.json")
    else:
        return os.path.join(BASE_DIR, "live", f"holdings_{account}.json")