"""
AlphaEnginePro - 100% 高保真回测引擎
完全还原 PRD V4.1.1 的生产策略逻辑
包含完整冷却期管理、主动减仓、汰弱留强换仓及超额收益报告
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import warnings

# ============================================================
# 红绿灯优化参数（用于参数扫描）
# ============================================================
WEIGHT_TREND_DEFAULT = 0.5          # 趋势权重的默认值（最终固化）

# 低优先级参数（固定值）
EMOTION_WINDOW = 20                 # 情绪Z-score窗口
VOLUME_WINDOW = 20                  # 成交Z-score窗口
TREND_WINDOW = 60                   # 趋势偏离度窗口（MA60）
WEIGHT_EMOTION = 0.2                # 情绪权重
WEIGHT_VOLUME = 0.2                 # 成交权重
BASE_COEFF = 0.5                    # 系数映射基准
SLOPE_COEFF = 0.25                  # 系数映射斜率
ALL_A_FILTER = False                # 是否启用全A等权过滤（关闭）

# 高优先级参数（仅用于历史扫描，现固化）
TREND_WEIGHTS = [0.5]              # 只保留0.5
SMOOTH_WINDOWS = [1]               # 只保留1
DELAY_DAYS = [1]                   # 只保留1

# ============================================================
# 1. 基础配置
# ============================================================
# 数据中枢根目录（包含指数、市场广度）
DATA_PATH = r"/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata"

# ETF 后复权数据专用目录（回测用）
ETF_HFQ_PATH = r"/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata/hfq"

INITIAL_CAPITAL = 1000000.0
COMMISSION = 0.0005
SLIPPAGE = 0.003

# V4.1.1 降维后的极速突破阈值
#FAST_BREAK_PCT = 2.5      # 常规极速突破涨幅 > 2.5%
#FAST_BREAK_VOL = 1.5      # 常规极速突破量比 > 1.5

#再次降维后的极速突破阈值
#FAST_BREAK_PCT = 2.0      # 常规极速突破涨幅 > 2.0%
#FAST_BREAK_VOL = 1.2      # 常规极速突破量比 > 1.2

#升维后的极速突破阈值
FAST_BREAK_PCT = 2.0     # 常规极速突破涨幅 > 2.0%
FAST_BREAK_VOL = 1.5      # 常规极速突破量比 > 1.5

# 海外资产专用阈值（慢牛、低波动）
OVERSEAS_BREAK_PCT = 1.5
OVERSEAS_BREAK_VOL = 1.3

# 红灯特赦阈值（与常规阈值相同，但代码中独立判断，无价格位置要求）
RED_FAST_BREAK_PCT = 2.5
RED_FAST_BREAK_VOL = 1.5

# 冷却期特赦阈值（PRD V4.1.1 规定：涨幅 > 5%，量比 > 2）
COOLDOWN_FAST_BREAK_PCT = 5.0
COOLDOWN_FAST_BREAK_VOL = 2.0

# ============================================================
# 2. ETF标的池 - 43只，精简 + 加 asset_class 字段 + 加国债
# ============================================================
ETF_POOL = [
    # =====================================================================
    # A股 - 核心宽基（Low Vol偏多，趋势为王，成交量权重低）
    # =====================================================================
    {"code": "563360.SH", "name": "中证A500", "asset_class": "宽基", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "510050.SH", "name": "上证50",   "asset_class": "宽基", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "510300.SH", "name": "沪深300",  "asset_class": "宽基", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "510500.SH", "name": "中证500",  "asset_class": "宽基", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512100.SH", "name": "中证1000", "asset_class": "宽基", "vol_class": "High", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "588000.SH", "name": "科创50",   "asset_class": "宽基", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159682.SZ", "name": "创业板50", "asset_class": "宽基", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159915.SZ", "name": "创业板",   "asset_class": "宽基", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},

    # =====================================================================
    # A股 - 行业赛道（High Vol偏多，动量+成交量驱动，快进快出）
    # =====================================================================
    {"code": "515220.SH", "name": "煤炭",     "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159611.SZ", "name": "电力",     "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512890.SH", "name": "红利低波", "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    #{"code": "510880.SH", "name": "红利",     "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512800.SH", "name": "银行",     "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "561960.SH", "name": "央企回报", "asset_class": "行业", "vol_class": "Low", "benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512400.SH", "name": "有色金属", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "562500.SH", "name": "机器人",   "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159667.SZ", "name": "工业母机", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "560710.SH", "name": "船舶",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512660.SH", "name": "军工",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "560280.SH", "name": "工程机械", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "516510.SH", "name": "云计算",   "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "588200.SH", "name": "科创芯片", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159516.SZ", "name": "半导体设备","asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
#    {"code": "159558.SZ", "name": "半导体设备","asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "515880.SH", "name": "通信",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512980.SH", "name": "传媒",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159888.SZ", "name": "智能汽车", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "516160.SH", "name": "新能源",   "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "515790.SH", "name": "光伏",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159755.SZ", "name": "电池",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159566.SZ", "name": "储能",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "516150.SH", "name": "稀土",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "516220.SH", "name": "细分化工", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512000.SH", "name": "证券",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "515170.SH", "name": "食品饮料", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159996.SZ", "name": "家电",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159873.SZ", "name": "医疗设备", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "512170.SH", "name": "综合医疗", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "560080.SH", "name": "中药",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159206.SZ", "name": "卫星",     "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159326.SZ", "name": "电网设备", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},
    {"code": "159363.SZ", "name": "人工智能", "asset_class": "行业", "vol_class": "High","benchmark_1": "000300.SH", "benchmark_2": "000852.SH", "m_group": "A股"},

    # =====================================================================
    # 跨境ETF（独立逻辑，不受A股红绿灯/基准约束）
    # =====================================================================
    {"code": "513100.SH", "name": "纳指100",   "asset_class": "跨境", "vol_class": "High", "benchmark_1": "NDX.GI",   "benchmark_2": None, "m_group": "跨境"},
    {"code": "513500.SH", "name": "标普500",   "asset_class": "跨境", "vol_class": "High", "benchmark_1": "SPX.GI",   "benchmark_2": None, "m_group": "跨境"},
    {"code": "513180.SH", "name": "恒生科技",  "asset_class": "跨境", "vol_class": "High", "benchmark_1": "HSTECH.HK", "benchmark_2": None, "m_group": "跨境"},
    {"code": "513050.SH", "name": "中概互联网","asset_class": "跨境", "vol_class": "High", "benchmark_1": "H30533.CSI","benchmark_2": None, "m_group": "跨境"},
    {"code": "159570.SZ", "name": "港股创新药","asset_class": "跨境", "vol_class": "High", "benchmark_1": "HSBI.HK",  "benchmark_2": None, "m_group": "跨境"},
    {"code": "513060.SH", "name": "恒生医疗",  "asset_class": "跨境", "vol_class": "High", "benchmark_1": "HSHCI.HK", "benchmark_2": None, "m_group": "跨境"},
    {"code": "513880.SH", "name": "日经225",   "asset_class": "跨境", "vol_class": "High", "benchmark_1": "N225",     "benchmark_2": None, "m_group": "跨境"},

    # =====================================================================
    # 商品ETF（配置属性，与股债低相关，长期持有）
    # =====================================================================
    {"code": "518880.SH", "name": "黄金",     "asset_class": "商品", "vol_class": "Low", "benchmark_1": "AU9999.SGE","benchmark_2": None, "m_group": "商品"},

    # =====================================================================
    # 避险资产（特殊用途，不参与排名，由红绿灯直接控制买卖）
    # =====================================================================
    #{"code": "511010.SH", "name": "国债ETF",  "asset_class": "国债", "vol_class": "Low", "benchmark_1": None,        "benchmark_2": None, "m_group": "避险"},
]


@dataclass
class Holding:
    """持仓数据结构"""
    code: str
    name: str
    qty: int
    cost: float
    highest: float
    buy_date: str
    signal_history: List[int] = field(default_factory=list)
    last_price: float = 0.0


@dataclass
class PendingOrder:
    """挂单数据结构"""
    type: str  # 'BUY' or 'SELL'
    code: str
    name: str
    qty: int
    reason: str
    price_limit: Optional[float] = None  # 限价单价格


@dataclass
class BuySignalResult:
    """买入信号分析结果"""
    is_std_break: bool
    is_fast_break: bool
    signal_score: int
    phase_ratio: float
    phase_name: str
    price_lower: float
    price_upper: float
    current_price: float


@dataclass
class RankingItem:
    """排行榜条目"""
    code: str
    name: str
    m_group: str
    ret_20d: float
    daily_change: float
    T: int
    V: int
    R: int
    penalty: bool
    vol_class: str
    price: float
    ma20: float
    ma60: float
    volume: float
    vol_ratio: float
    benchmark_vol: float
    # ↑ 以上都是没有默认值的字段，asset_class 必须放在它们之后
    asset_class: str = '宽基'          # ← 有默认值，放这里
    M: float = 0.0
    S: float = 0.0
    max_weight: float = 0.0
    initial_weight: float = 0.0
    normalize_weight: float = 0.0


class AlphaEnginePro:
    """
    100% 高保真回测引擎 - 完全还原生产策略逻辑 (PRD V4.1.1)
    """

    def __init__(self, data_path: str, etf_path: str = None):
        self.path = data_path
        # 如果未指定 ETF 路径，默认与主数据路径相同（兼容旧用法）
        self.etf_path = etf_path if etf_path is not None else data_path
        self.etf_data: Dict[str, pd.DataFrame] = {}
        self.index_data: Dict[str, pd.DataFrame] = {}
        self.breadth: Optional[pd.DataFrame] = None
        self.all_trade_dates: List[str] = []
        self.reset_state()
    
    def reset_state(self):
        """重置回测状态"""
        self.cash = INITIAL_CAPITAL
        self.holdings: Dict[str, Holding] = {}
        self.cooling: Dict[str, str] = {}  # {code: cool_until_date}
        self.cooling_type: Dict[str, str] = {}  # {code: cool_type} 用于特赦判断
        self.history: List[Dict] = []
        self.trades: List[Dict] = []       # 交易流水（用于统计）
        self.frozen_until: Optional[str] = None
        self.peak_nav = INITIAL_CAPITAL
        self.pending_orders: List[PendingOrder] = []
        # 新增用于报告的变量
        self.daily_records: List[Dict] = []          # 每日记录：日期、净值、红绿灯状态、持仓数等
        self.daily_trade_volume: Dict[str, Tuple[float, float]] = {}  # {date: (buy_amt, sell_amt)}
        self.switch_events: List[Dict] = []          # 红绿灯切换事件列表
        self.prev_light: Optional[str] = None        # 用于切换检测
        self.is_long_bull: bool = False              # ★ 长期牛市标志
        self.coeff_history = {}                      # 新增：用于平滑的历史系数
        self.is_long_bull = False

    def load_data(self):
        """加载本地数据并预计算所有技术指标（修复版：增加容错和警告）"""
        print("📂 正在加载数据并预计算技术指标...")
        
        # 加载市场广度
        breadth_file = os.path.join(self.path, "market_breadth.csv")
        if os.path.exists(breadth_file):
            self.breadth = pd.read_csv(breadth_file).set_index('trade_date')
            self.breadth.index = self.breadth.index.astype(str)
            self.breadth = self.breadth[~self.breadth.index.duplicated(keep='first')]
            self.all_trade_dates = sorted(self.breadth.index.tolist())
        else:
            raise FileNotFoundError(f"市场广度文件不存在: {breadth_file}")
        
        # 加载指数数据（增加容错，缺失时警告）
        index_codes = ["000300.SH", "000852.SH", "000001.SH", "399001.SZ", "000985.SH", "SPX.GI"]
        for idx in index_codes:
            file = os.path.join(self.path, f"index_{idx}.csv")
            if not os.path.exists(file):
                warnings.warn(f"指数文件不存在: {file}，相关指标将使用默认值（0）")
                continue
            try:
                df = pd.read_csv(file).set_index('trade_date')
                df.index = df.index.astype(str)
                df = df[~df.index.duplicated(keep='first')]
                
                # 确保存在 close 列
                if 'close' not in df.columns:
                    warnings.warn(f"指数文件 {file} 缺少 close 列，跳过")
                    continue
                
                # 计算技术指标
                df['ma40'] = df['close'].rolling(40).mean()
                df['ma60'] = df['close'].rolling(60).mean()
                df['ma200'] = df['close'].rolling(200).mean()

                # ============================================================
                # ★ 新增：计算 ATR(20) 用于风险平价 (Risk Parity)
                # ============================================================
                prev_close = df['close'].shift(1)
                tr1 = df['high'] - df['low']
                tr2 = (df['high'] - prev_close).abs()
                tr3 = (df['low'] - prev_close).abs()
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                df['atr20'] = tr.rolling(20).mean()

                df['ret_20d'] = (df['close'] / df['close'].shift(20) - 1) * 100
                
                self.index_data[idx] = df
                print(f"  ✅ 加载指数 {idx}，共 {len(df)} 条记录")
            except Exception as e:
                warnings.warn(f"加载指数 {idx} 失败: {e}")
        
        # 检查必需指数
        if '000300.SH' not in self.index_data:
            warnings.warn("⚠️ 沪深300指数(000300.SH)未加载，基准收益将无法计算！")
        if '000852.SH' not in self.index_data:
            warnings.warn("⚠️ 中证1000指数(000852.SH)未加载，部分排行榜基准可能失效")
        
        # 加载ETF数据
        loaded_etf_count = 0
        for cfg in ETF_POOL:
            code = cfg['code']
            file = os.path.join(self.etf_path, f"etf_{code}.csv")
            if not os.path.exists(file):
                continue
            
            try:
                df = pd.read_csv(file).set_index('trade_date')
                df.index = df.index.astype(str)
                df = df[~df.index.duplicated(keep='first')]
                
                # 计算技术指标（与生产环境完全一致）
                df['ma20'] = df['close'].rolling(20).mean()
                df['ma60'] = df['close'].rolling(60).mean()
                df['ma20_vol'] = df['vol'].rolling(20).mean()
                df['ma5_vol'] = df['vol'].rolling(5).mean()
                df['ret_20d'] = (df['close'] / df['close'].shift(20) - 1) * 100
                
                # ATR计算
                tr = pd.concat([
                    df['high'] - df['low'],
                    (df['high'] - df['close'].shift(1)).abs(),
                    (df['low'] - df['close'].shift(1)).abs()
                ], axis=1).max(axis=1)
                df['atr20'] = tr.rolling(20).mean()
                df['atr10'] = tr.rolling(10).mean()
                
                # MACD计算
                ema12 = df['close'].ewm(span=12, adjust=False).mean()
                ema26 = df['close'].ewm(span=26, adjust=False).mean()
                df['dif'] = ema12 - ema26
                df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
                df['macd_bar'] = 2 * (df['dif'] - df['dea'])
                
                self.etf_data[code] = df
                loaded_etf_count += 1
            except Exception as e:
                warnings.warn(f"加载ETF {code} 失败: {e}")

        # ★ 加载 V3 市场判读状态标签（用于熊市拦截）
        self.v3_states = {}
        self.v3_states_dict = {}  # ★ 新增：专门为卖出逻辑准备的纯状态字典
        v3_file = os.path.join(self.path, "v3_states.csv")
        if os.path.exists(v3_file):
            df_v3 = pd.read_csv(v3_file, dtype={'date': str})
            for _, row in df_v3.iterrows():
                # 原有的保持不变
                self.v3_states[row['date']] = (row['state'], int(row['state_duration']))
                # ★ 新增：只提取纯粹的宏观状态（SIDEWAYS / SYSTEMIC_BEAR）供卖出逻辑快速查询
                self.v3_states_dict[row['date']] = row['state']
            print(f"  ✅ 加载 V3 状态标签，共 {len(self.v3_states)} 个交易日")
        else:
            print(f"  ⚠️ V3 状态文件未找到: {v3_file}")
        
        print(f"✅ 数据加载完成，共 {loaded_etf_count} 只ETF，{len(self.all_trade_dates)} 个交易日")
    
    # ============================================================
    # 3. 大盘体温计 - 调优方案测试
    # ============================================================
    
    def get_market_temperature(self, t_date: str, params=None) -> Tuple[float, bool, int, bool]:
        #print(f"调试：t_date={t_date}, params={params}")
        """
        新版大盘体温计：支持参数化配置
        params 为字典，可包含以下键：
            w_trend, w_emotion, w_volume, N_emotion, N_volume, N_trend,
            smooth, delay, base_coeff, slope_coeff, all_a_filter
        """
        # 使用传入参数，否则使用全局默认
        if params is None:
            params = {}
        w_trend = params.get('w_trend', WEIGHT_TREND_DEFAULT)
        w_emotion = params.get('w_emotion', WEIGHT_EMOTION)
        w_volume = params.get('w_volume', WEIGHT_VOLUME)
        N_emotion = params.get('N_emotion', EMOTION_WINDOW)
        N_volume = params.get('N_volume', VOLUME_WINDOW)
        N_trend = params.get('N_trend', TREND_WINDOW)
        smooth = int(params.get('smooth', 1))
        delay = int(params.get('delay', 1))
        base = params.get('base_coeff', BASE_COEFF)
        slope = params.get('slope_coeff', SLOPE_COEFF)
        all_a_filter = params.get('all_a_filter', ALL_A_FILTER)

        # 1. 情绪得分（Z-score，滚动窗口）
        emotion_score = 0
        if self.breadth is not None and t_date in self.breadth.index:
            breadth_series = self.breadth['breadth'].loc[:t_date].tail(N_emotion+1)
            if len(breadth_series) >= N_emotion+1:
                curr = breadth_series.iloc[-1]
                mean = breadth_series.iloc[:-1].mean()
                std = breadth_series.iloc[:-1].std()
                if std > 0:
                    emotion_score = (curr - mean) / std
                    emotion_score = max(-1, min(1, emotion_score))

        # 2. 成交得分（Z-score，滚动窗口）
        volume_score = 0
        if '000001.SH' in self.index_data and '399001.SZ' in self.index_data:
            try:
                amt_sh = self.index_data['000001.SH']['amount']
                amt_sz = self.index_data['399001.SZ']['amount']
                total_amt = amt_sh + amt_sz
                total_amt = total_amt.loc[:t_date].tail(N_volume+1)
                if len(total_amt) >= N_volume+1:
                    curr = total_amt.iloc[-1]
                    mean = total_amt.iloc[:-1].mean()
                    std = total_amt.iloc[:-1].std()
                    if std > 0:
                        volume_score = (curr - mean) / std
                        volume_score = max(-1, min(1, volume_score))
            except:
                pass

        # 3. 趋势得分（连续偏离度）
        trend_score = 0
        if '000300.SH' in self.index_data and '000852.SH' in self.index_data:
            try:
                idx300 = self.index_data['000300.SH'].loc[t_date]
                idx1000 = self.index_data['000852.SH'].loc[t_date]
                close300 = float(idx300['close'].iloc[-1] if isinstance(idx300['close'], pd.Series) else idx300['close'])
                ma60_300 = float(idx300['ma60'].iloc[-1] if isinstance(idx300['ma60'], pd.Series) else idx300['ma60'])
                close1000 = float(idx1000['close'].iloc[-1] if isinstance(idx1000['close'], pd.Series) else idx1000['close'])
                ma60_1000 = float(idx1000['ma60'].iloc[-1] if isinstance(idx1000['ma60'], pd.Series) else idx1000['ma60'])
                dev300 = (close300 - ma60_300) / ma60_300 if ma60_300 > 0 else 0
                dev1000 = (close1000 - ma60_1000) / ma60_1000 if ma60_1000 > 0 else 0
                dev = max(dev300, dev1000)
                trend_score = max(-1, min(1, dev / 0.2))
            except:
                pass

        total_score = w_emotion*emotion_score + w_volume*volume_score + w_trend*trend_score
        coeff = base + slope * total_score
        coeff = max(0, min(1, coeff))

        # 平滑处理
        if not hasattr(self, 'coeff_history'):
            self.coeff_history = {}
        if t_date not in self.coeff_history:
            self.coeff_history[t_date] = coeff
        dates = sorted(self.coeff_history.keys())
        recent = [self.coeff_history[d] for d in dates if d <= t_date][-smooth:]
        smooth_coeff = sum(recent) / len(recent)
        final_coeff = smooth_coeff

        if '000300.SH' in self.index_data and '000852.SH' in self.index_data:
            try:
                idx300 = self.index_data['000300.SH'].loc[t_date]
                idx1000 = self.index_data['000852.SH'].loc[t_date]
                close300 = float(idx300['close'].iloc[-1] if isinstance(idx300['close'], pd.Series) else idx300['close'])
                ma60_300 = float(idx300['ma60'].iloc[-1] if isinstance(idx300['ma60'], pd.Series) else idx300['ma60'])
                close1000 = float(idx1000['close'].iloc[-1] if isinstance(idx1000['close'], pd.Series) else idx1000['close'])
                ma60_1000 = float(idx1000['ma60'].iloc[-1] if isinstance(idx1000['ma60'], pd.Series) else idx1000['ma60'])
                if (close300 > ma60_300) and (close1000 > ma60_1000) and (close300/ma60_300 - 1) > 0:
                    pass
                else:
                    final_coeff = min(final_coeff, 0.8)
            except:
                pass

        if all_a_filter and '000985.SH' in self.index_data:
            try:
                idx_all = self.index_data['000985.SH'].loc[t_date]
                close_all = float(idx_all['close'].iloc[-1] if isinstance(idx_all['close'], pd.Series) else idx_all['close'])
                ma60_all = float(idx_all['ma60'].iloc[-1] if isinstance(idx_all['ma60'], pd.Series) else idx_all['ma60'])
                if close_all < ma60_all:
                    final_coeff = min(final_coeff, 0.3)
            except:
                pass

        is_bull_enhanced = False
        if final_coeff > 0.6 and '000300.SH' in self.index_data:
            try:
                idx300 = self.index_data['000300.SH'].loc[t_date]
                close300 = float(idx300['close'].iloc[-1] if isinstance(idx300['close'], pd.Series) else idx300['close'])
                ma60_300 = float(idx300['ma60'].iloc[-1] if isinstance(idx300['ma60'], pd.Series) else idx300['ma60'])
                if close300 > ma60_300:
                    is_bull_enhanced = True
            except:
                pass

        is_red_light = (final_coeff < 0.3)
        total_score_int = int(round(total_score * 3))

        # ★ 趋势确认开关：沪深300连续20日在MA60之上，强制提升仓位系数
        # 但增加20日动量反转保护防止牛市顶点急跌
        try:
            if '000300.SH' in self.index_data:
                idx300_df = self.index_data['000300.SH'].loc[:t_date]
                # ✅ 修复：将 >= 20 改为 >= 21，防止下面取 iloc[-21] 时数组越界闪崩
                if len(idx300_df) >= 21:  
                    close_series = idx300_df['close']
                    ma60_series = idx300_df['ma60']
                    if all(close_series.iloc[-20:].values > ma60_series.iloc[-20:].values):
                        final_coeff = 0.95
                        is_red_light = False
                        total_score_int = 3
                        
                        # ★ 20日动量反转保护：市场宽度恶化时关闭增强
                        ret_300_20d = (close300 - idx300_df['close'].iloc[-21]) / idx300_df['close'].iloc[-21] * 100
                        ret_1000_20d = 0
                        if '000852.SH' in self.index_data:
                            idx1000_df = self.index_data['000852.SH'].loc[:t_date]
                            if len(idx1000_df) >= 21:
                                ret_1000_20d = (idx1000_df['close'].iloc[-1] - idx1000_df['close'].iloc[-21]) / idx1000_df['close'].iloc[-21] * 100
                        
                        if ret_300_20d < 0 and ret_1000_20d < 0:
                            # 市场宽度恶化，退回原始Z-score系数
                            final_coeff = base + slope * total_score
                            is_red_light = final_coeff < 0.3
                            total_score_int = int(round(total_score * 3))
        except:
            pass

        # ★ 动态回撤保护：趋势确认时，若自身回撤过大，强制降仓
        # 获取当前净值（这里我们需要从 engine 的属性中获取）
        # 由于 get_market_temperature 无法直接访问 nav，我们通过 peak_nav 和 current_nav 计算
        if hasattr(self, 'peak_nav') and hasattr(self, 'current_nav') and self.peak_nav > 0:
            current_drawdown = (self.peak_nav - self.current_nav) / self.peak_nav * 100
            if current_drawdown >= 8:
                # 回撤超过8%，强制将系数降到0.30以下
                final_coeff = min(final_coeff, 0.30)
                is_red_light = True
                total_score_int = min(total_score_int, -3)
            elif current_drawdown >= 6:
                # 回撤超过6%，趋势确认的增强系数失效，退回原始系数
                # 获取原始Z-score系数（未增强的）
                original_coeff = max(0, min(1, base + slope * total_score))
                final_coeff = original_coeff
                is_red_light = original_coeff < 0.3
                total_score_int = int(round(total_score * 3))


        # ★ 长期牛市判定：双均线+中期趋势向上
        is_long_bull = False
        if '000300.SH' in self.index_data:
            idx300_df = self.index_data['000300.SH'].loc[:t_date]
            if len(idx300_df) >= 120:
                ma20_series = idx300_df['close'].rolling(20).mean()
                ma60_series = idx300_df['close'].rolling(60).mean()
                if ma20_series.iloc[-1] > ma60_series.iloc[-1]:
                    if ma60_series.iloc[-1] > ma60_series.iloc[-60] * 1.03:
                        is_long_bull = True
        self.is_long_bull = is_long_bull


        return final_coeff, is_bull_enhanced, total_score_int, is_red_light

    def get_v3_state(self, t_date: str):
        """查询 V3 市场判读系统的状态和持续天数"""
        if hasattr(self, 'v3_states') and t_date in self.v3_states:
            return self.v3_states[t_date]
        return None, 0
    
    # ============================================================
    # 4. 动态生命线 - 基于百分比的自适应移动止盈（Phase 1-2 修正版）
    # ============================================================
    
    def get_dynamic_sell_price(self, holding: Holding, row: pd.Series) -> Tuple[float, str]:
        """
        计算动态生命线（基于百分比的自适应移动止盈/止损）
        
        逻辑：
        - 初始止损：成本 - 8%（硬止损，不受ATR影响）
        - 浮盈 > 8%：移动止盈线 = 最高价 - 8%（锁定利润）
        - 浮盈 > 20%：移动止盈线 = 最高价 - 12%（给趋势更多空间）
        - 最终取两者中较高者
        """
        cost = holding.cost
        highest = holding.highest
        current_price = row['close']
        profit_pct = (current_price - cost) / cost * 100
        
        # 初始止损线（成本下方 8%）
        stop_loss_trigger = cost * 0.92
        
        # 根据浮盈动态调整回撤容忍度
        if profit_pct >= 20:
            # 大趋势阶段：允许从最高点回撤 12%
            take_profit_trigger = highest * 0.88
        elif profit_pct >= 8:
            # 初步盈利阶段：允许从最高点回撤 8%
            take_profit_trigger = highest * 0.92
        else:
            # 未进入盈利保护阶段，只用初始止损
            take_profit_trigger = stop_loss_trigger
        
        # 取两者中较高者
        trigger_price = max(take_profit_trigger, stop_loss_trigger)
        
        # 判断卖出类型
        if current_price <= stop_loss_trigger:
            sell_type = 'stop_loss'
        else:
            sell_type = 'take_profit'
        
        return trigger_price, sell_type
    
    # ============================================================
    # 5. MACD完整计算 - 还原生产环境（无修改）
    # ============================================================
    
    def calculate_macd_status(self, df: pd.DataFrame) -> Dict[str, bool]:
        """
        完整MACD状态计算
        返回: {golden_cross, red_increasing, above_zero}
        """
        if len(df) < 30:
            return {"golden_cross": False, "red_increasing": False, "above_zero": False}
        
        last_dif = df['dif'].iloc[-1]
        last_dea = df['dea'].iloc[-1]
        last_macd = df['macd_bar'].iloc[-1]
        prev_macd = df['macd_bar'].iloc[-2]
        prev_dif = df['dif'].iloc[-2]
        prev_dea = df['dea'].iloc[-2]
        
        # 金叉判断
        golden_cross = (last_dif > last_dea and prev_dif <= prev_dea)
        
        # 红柱连续增长判断（至少2日连续增长且为正）
        red_increasing = (last_macd > prev_macd and last_macd > 0)
        
        # 零轴上方
        above_zero = (last_dif > 0)
        
        return {"golden_cross": golden_cross, "red_increasing": red_increasing, "above_zero": above_zero}
    
    # ============================================================
    # 6. 买入信号分析 - 完全还原生产逻辑 (V4.1.1)（无修改）
    # ============================================================
    
    def analyze_buy_signal(self, code: str, t_date: str, market_coeff: float, 
                           is_red_light: bool, is_bull_enhanced: bool) -> Optional[BuySignalResult]:
        """
        买入信号分析 - 100%还原生产逻辑
        """
        if code not in self.etf_data:
            return None
        
        df = self.etf_data[code].loc[:t_date]
        if len(df) < 65:
            return None
        
        df = df.sort_index()
        last = df.iloc[-1]
        prev = df.iloc[-2]
        prev_2 = df.iloc[-3]
        
        # ============================================================
        # 步骤1: 核心趋势条件检查 (V4.1.1 降维阈值)
        # ============================================================
        
        # 标准突破检查
        cond1 = (last['close'] > last['ma60'] and 
                 prev['close'] > prev['ma60'] and 
                 prev_2['close'] > prev_2['ma60'])
        
        is_std_break = False
        if cond1 and len(df) >= 6:
            ma60_5d_ago = df['ma60'].iloc[-6]
            if last['ma60'] > ma60_5d_ago:
                is_std_break = True
        
        # 极速突破检查 (V4.1.1: 涨幅>2.5%, 量比>1.5, 价格>MA20, 价格位置≥0.75)
        daily_ret = (last['close'] / prev['close'] - 1) * 100
        vol_ratio_5d = last['vol'] / last['ma5_vol'] if last['ma5_vol'] > 0 else 1
        price_position = (last['close'] - last['low']) / (last['high'] - last['low']) if last['high'] != last['low'] else 0
        
        # 获取该资产的 m_group
        m_group = 'A股'
        for cfg in ETF_POOL:
            if cfg['code'] == code:
                m_group = cfg['m_group']
                break
        
        if m_group in ['跨境', '商品']:
            pct_th = OVERSEAS_BREAK_PCT
            vol_th = OVERSEAS_BREAK_VOL
        else:
            pct_th = FAST_BREAK_PCT
            vol_th = FAST_BREAK_VOL
        
        is_fast_break = (daily_ret > pct_th and 
                         vol_ratio_5d > vol_th and 
                         last['close'] > last['ma20'] and 
                         price_position >= 0.75)
        
        
        if not (is_std_break or is_fast_break):
            return None
        
        # ============================================================
        # 步骤2: 计算信号分（0-2分）
        # ============================================================
        
        signal_score = 0
        macd_status = self.calculate_macd_status(df)
        
        # 动量因子：MACD金叉 + 红柱连续增长
        if macd_status['golden_cross'] and macd_status['red_increasing']:
            signal_score += 1
        
        # 量价因子
        if is_fast_break:
            signal_score += 1
        else:
            if last['vol'] > last['ma5_vol'] * 1.2:
                signal_score += 1
        
        # ============================================================
        # 步骤3: 阶段判定矩阵 (PRD V4.1.1)
        # ============================================================
        
        # 正常情况（绿灯/黄灯）
        if is_fast_break:
            # 强力突破
            phase_ratio = 1.0
            phase_name = "强力突破"
        else:
            # 标准突破
            if signal_score == 2:
                phase_ratio = 1.0 if market_coeff >= 0.9 else 0.8
                phase_name = "趋势确认"
            elif signal_score == 1:
                phase_ratio = 0.8 if market_coeff >= 0.9 else 0.5
                phase_name = "稳健跟进"
            else:
                phase_ratio = 0.5 if market_coeff >= 0.9 else 0.3
                phase_name = "试探买入"
        
        # ============================================================
        # 步骤4: 价格区间 (PRD V4.1.1)
        # ============================================================
        price_lower = max(last['ma20'], last['close'] * 0.98)
        price_upper = max(df.iloc[-2]['high'], last['close'] * 1.02)
        
        return BuySignalResult(
            is_std_break=is_std_break,
            is_fast_break=is_fast_break,
            signal_score=signal_score,
            phase_ratio=phase_ratio,
            phase_name=phase_name,
            price_lower=round(price_lower, 3),
            price_upper=round(price_upper, 3),
            current_price=last['close']
        )
    
    # ============================================================
    # 7. ETF排行榜 - 完全还原生产逻辑（无修改）
    # ============================================================
    
    def get_benchmark_returns(self, t_date: str) -> Dict[str, float]:
        """获取基准指数20日收益率"""
        returns = {}
        for bc in ["000300.SH", "000852.SH"]:
            if bc in self.index_data:
                idx_df = self.index_data[bc]
                if t_date in idx_df.index:
                    ret = idx_df.loc[t_date, 'ret_20d']
                    returns[bc] = float(ret.iloc[-1] if isinstance(ret, pd.Series) else ret)
                else:
                    returns[bc] = 0
            else:
                returns[bc] = 0
        return returns


    def get_dynamic_caps(self, t_date: str):
            """
            根据沪深300偏离度返回动态仓位上限
            返回: (max_holdings, low_weight_max, high_weight_max)
            """
            dev = 0
            if '000300.SH' in self.index_data and t_date in self.index_data['000300.SH'].index:
                try:
                    idx300 = self.index_data['000300.SH'].loc[t_date]
                    close = float(idx300['close'].iloc[-1] if isinstance(idx300['close'], pd.Series) else idx300['close'])
                    ma60 = float(idx300['ma60'].iloc[-1] if isinstance(idx300['ma60'], pd.Series) else idx300['ma60'])
                    if ma60 > 0:
                        dev = (close - ma60) / ma60 * 100
                except:
                    pass
            
            # 恢复大容量持仓，彻底消灭牛市的资金闲置问题
            if dev > 10:
                return 8, 0.35, 0.25   # 最大持仓8只，低波上限0.35，高波上限0.25
            elif dev > 5:
                return 6, 0.30, 0.20   
            elif dev > -10:
                return 4, 0.25, 0.15   
            else:
                return 2, 0.20, 0.10
    
    def get_rankings(self, t_date: str, is_bull_enhanced: bool) -> List[RankingItem]:
            """
            计算ETF排行榜 - 10.51% 圣杯版：保留S分宏观调控，恢复战术红绿灯底线
            """
            rankings: List[RankingItem] = []
            benchmark_returns = self.get_benchmark_returns(t_date)

            for cfg in ETF_POOL:
                code = cfg['code']
                if code not in self.etf_data or t_date not in self.etf_data[code].index:
                    continue
                
                df = self.etf_data[code]
                
                # 1. 上市日期检查
                df_history = df.loc[:t_date]
                if len(df_history) < 60:
                    continue
                
                row = df.loc[t_date]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                
                m_group = cfg['m_group']
                ma_period = 40 if m_group in ['跨境', '商品'] else 60
                ma_col = f'ma{ma_period}'
                
                if ma_col not in df.columns:
                    df[ma_col] = df['close'].rolling(ma_period).mean()
                
                # 硬门槛过滤
                try:
                    hist_3 = df.loc[:t_date, 'close'].tail(3)
                    ma_3 = df.loc[:t_date, ma_col].tail(3)
                    if not (hist_3 > ma_3).all():
                        continue
                    if len(df) >= ma_period + 5:
                        ma_5d_ago = df[ma_col].shift(5).loc[t_date]
                        if pd.isna(ma_5d_ago) or row[ma_col] <= ma_5d_ago:
                            continue
                    else:
                        continue
                except:
                    continue
                
                ret_20d = float(row['ret_20d'].iloc[-1] if isinstance(row['ret_20d'], pd.Series) else row['ret_20d'])
                
                daily_change = 0
                if len(df) >= 2:
                    prev_close = df.iloc[-2]['close']
                    daily_change = (row['close'] - prev_close) / prev_close * 100
                
                T = 100 if row['close'] > row['ma20'] else 60
                
                vol_ratio = row['vol'] / row['ma20_vol'] if row['ma20_vol'] > 0 else 1
                vol_ratios_history = []
                for i in range(-21, -1):
                    if i >= -len(df):
                        day_vol = df.iloc[i]['volume'] if 'volume' in df.columns else df.iloc[i]['vol']
                        day_ma20_vol = df.iloc[i]['ma20_vol']
                        if day_ma20_vol > 0:
                            vol_ratios_history.append(day_vol / day_ma20_vol)
                benchmark_vol = np.mean(vol_ratios_history) if vol_ratios_history else 1
                
                if vol_ratio > benchmark_vol * 1.5:
                    V = 100
                elif vol_ratio > benchmark_vol * 1.2:
                    V = 80
                elif vol_ratio > benchmark_vol * 0.8:
                    V = 50
                else:
                    V = 0
                
                # R因子修复
                bench1_ret = benchmark_returns.get(cfg['benchmark_1'], 0)
                bench2_ret = benchmark_returns.get(cfg['benchmark_2'], 0) if cfg['benchmark_2'] else None
                
                penalty = False
                if m_group == "A股":
                    if ret_20d > bench1_ret or (bench2_ret is not None and ret_20d > bench2_ret):
                        R = 100
                    else:
                        R = 0
                        penalty = True
                elif m_group in ["跨境", "商品"]:
                    if ret_20d > 0:
                        R = 100
                        penalty = False
                    else:
                        R = 0
                        penalty = True
                else:
                    R = 50
                    penalty = False
                
                rankings.append(RankingItem(
                    code=code, name=cfg['name'], m_group=m_group, ret_20d=ret_20d,
                    daily_change=daily_change, T=T, V=V, R=R, penalty=penalty,
                    vol_class=cfg['vol_class'], price=row['close'], ma20=row['ma20'],
                    ma60=row['ma60'], volume=row['vol'], vol_ratio=vol_ratio,
                    benchmark_vol=benchmark_vol, asset_class=cfg.get('asset_class', '宽基')
                ))
            
            if not rankings:
                return []
            
            # 计算M分
            groups: Dict[str, List[RankingItem]] = {}
            for item in rankings:
                if item.m_group not in groups:
                    groups[item.m_group] = []
                groups[item.m_group].append(item)
            
            for group, items in groups.items():
                items.sort(key=lambda x: x.ret_20d, reverse=True)
                total = len(items)
                for rank, item in enumerate(items, 1):
                    item.M = 100 * (1 - (rank - 1) / total)
            
            # ★ 提取全球宏观状态 (保留！这是S分的核心)
            params = getattr(self, 'market_temp_params', None)
            _, _, _, is_red_light_today = self.get_market_temperature(t_date, params)
            is_danger_macro = is_red_light_today
            v3_state, _ = self.get_v3_state(t_date)
            if v3_state == 'SYSTEMIC_BEAR':
                is_danger_macro = True

            is_us_bull = False
            if 'SPX.GI' in self.index_data and t_date in self.index_data['SPX.GI'].index:
                spx_df = self.index_data['SPX.GI'].loc[:t_date]
                if len(spx_df) >= 200:
                    spx_close = float(spx_df['close'].iloc[-1])
                    spx_ma200 = float(spx_df['close'].rolling(200).mean().iloc[-1])
                    if spx_close > spx_ma200:
                        is_us_bull = True

            # S分计算
            for item in rankings:
                ac = item.asset_class if hasattr(item, 'asset_class') else '宽基'
                if ac == '宽基':
                    S = 0.5 * item.T + 0.3 * item.M + 0.1 * item.V + 0.1 * item.R
                    if hasattr(self, 'is_long_bull') and self.is_long_bull:
                        S += 3
                elif ac == '行业':
                    S = 0.2 * item.T + 0.3 * item.M + 0.4 * item.V + 0.1 * item.R
                elif ac == '跨境':
                    S = 0.3 * item.T + 0.4 * item.M + 0.2 * item.V + 0.1 * item.R
                    if not is_us_bull:
                        S -= 50
                    elif is_us_bull and is_danger_macro:
                        S += 20
                elif ac == '商品':
                    S = 0.4 * item.T + 0.3 * item.M + 0.2 * item.V + 0.1 * item.R
                    if not is_us_bull and is_danger_macro:
                        S += 30
                    elif is_danger_macro or not is_us_bull:
                        S += 10
                else:
                    S = 0.4 * item.T + 0.3 * item.M + 0.2 * item.V + 0.1 * item.R
                
                if item.penalty:
                    S = S * 0.8
                item.S = S

            for item in rankings:
                if item.vol_class == 'High':
                    item.S = item.S * 0.9
            
            # ★ 10.51% 核心：只使用战术牛市(is_bull_enhanced)解封波动率惩罚底线！
            BASE_TARGET_VOL = 0.015  
            for item in rankings:
                current_vol = BASE_TARGET_VOL 
                if item.code in self.etf_data and t_date in self.etf_data[item.code].index:
                    row = self.etf_data[item.code].loc[t_date]
                    if 'atr20' in row:
                        atr_val = row['atr20']
                        if isinstance(atr_val, pd.Series): atr_val = atr_val.iloc[-1]
                        if item.price > 0:
                            current_vol = atr_val / item.price
                
                rp_floor = 0.7 if is_bull_enhanced else 0.3
                item.rp_multiplier = min(1.2, max(rp_floor, BASE_TARGET_VOL / current_vol)) if current_vol > 0 else 1.0

            # 计算权重归一化
            max_holdings, low_max, high_max = self.get_dynamic_caps(t_date)
            for item in rankings:
                if item.vol_class == 'Low':
                    item.max_weight = low_max
                else:
                    item.max_weight = high_max        

            for item in rankings:
                item.initial_weight = item.max_weight * item.rp_multiplier
            
            top6 = rankings[:6]
            sum_top6_initial = sum(item.initial_weight for item in top6)
            if 0 < sum_top6_initial < 1.0:
                normalize_factor = 1.0 / sum_top6_initial
            else:
                normalize_factor = 1.0
            
            for item in rankings:
                if item in top6:
                    item.normalize_weight = item.initial_weight * normalize_factor
                else:
                    item.normalize_weight = item.initial_weight
            
            return rankings[:15]
    
    # ============================================================
    # 8. 汰弱留强换仓逻辑 - 完全还原（无修改）
    # ============================================================
    
    def check_rebalance(self, t_date: str, rankings: List[RankingItem], 
                        coeff: float, is_red_light: bool, nav: float,
                        buy_count: int, max_buy_per_day: int) -> int:
        """
        汰弱留强主动换仓 - 100%还原生产逻辑
        条件: 持仓≥动态持仓上限，找出强势新标的，替换弱势持仓
        返回: 本次生成的买入数量
        """
        # 获取动态最大持仓数（只用到 max_holdings，其他返回值用 _ 忽略）
        max_holdings, _, _ = self.get_dynamic_caps(t_date)
        if len(self.holdings) < max_holdings:
            return 0
        
        generated_buys = 0
        
        # 获取持仓当前价格
        for code, holding in self.holdings.items():
            if code in self.etf_data and t_date in self.etf_data[code].index:
                row = self.etf_data[code].loc[t_date]
                price = float(row['close'].iloc[-1] if isinstance(row['close'], pd.Series) else row['close'])
                holding.last_price = price
        
        # 找出强势候选标的（S分≥70 或 触发极速突破）
        strong_candidates = []
        for item in rankings[:15]:
            # 跳过已有持仓
            if item.code in self.holdings:
                continue
            
            is_strong = False
            if item.S >= 70:
                is_strong = True
            else:
                # 检查极速突破（使用常规极速突破条件，含价格位置）
                if item.code in self.etf_data:
                    df = self.etf_data[item.code].loc[:t_date]
                    if len(df) >= 2:
                        last = df.iloc[-1]
                        prev = df.iloc[-2]
                        daily_ret = (last['close'] / prev['close'] - 1) * 100
                        vol_ratio = last['vol'] / last['ma5_vol'] if last['ma5_vol'] > 0 else 1
                        price_position = (last['close'] - last['low']) / (last['high'] - last['low']) if last['high'] != last['low'] else 0
                        price_above_ma20 = last['close'] > last['ma20']
                        
                        if (daily_ret > FAST_BREAK_PCT and 
                            vol_ratio > FAST_BREAK_VOL and 
                            price_above_ma20 and 
                            price_position >= 0.75):
                            is_strong = True
            
            if is_strong:
                strong_candidates.append(item)
        
        if not strong_candidates:
            return 0
        
        
        # 找出弱势持仓（浮盈<5% 且 S分<50）
        # ✅ 修复 Bug：补全跌出榜单的数据，并引入基准收益算R分
        weak_holdings = []
        benchmark_returns = self.get_benchmark_returns(t_date)

        for code, holding in self.holdings.items():
            profit_pct = (holding.last_price - holding.cost) / holding.cost * 100
            
            # ✅ 新增：计算这只标的已经持有了多少天
            days_held = (datetime.strptime(t_date, '%Y%m%d') - datetime.strptime(holding.buy_date, '%Y%m%d')).days
            
            s_score = 0
            weak_ret_20d = 0
            r_score = 0
            found_in_top = False
            
            # 尝试从前15名中获取
            for item in rankings:
                if item.code == code:
                    s_score = item.S
                    weak_ret_20d = item.ret_20d
                    r_score = item.R
                    found_in_top = True
                    break
            
            # 如果跌出前15名，手动从底层提取并补算R分，防止死扛垃圾
            if not found_in_top and code in self.etf_data:
                df = self.etf_data[code]
                if t_date in df.index:
                    row = df.loc[t_date]
                    weak_ret_20d = float(row['ret_20d'].iloc[-1] if isinstance(row['ret_20d'], pd.Series) else row['ret_20d'])
                    
                    cfg = next((c for c in ETF_POOL if c['code'] == code), None)
                    if cfg:
                        b1 = benchmark_returns.get(cfg['benchmark_1'], 0)
                        b2 = benchmark_returns.get(cfg['benchmark_2'], 0) if cfg['benchmark_2'] else None
                        if cfg['m_group'] == 'A股':
                            r_score = 100 if (weak_ret_20d > b1 or (b2 is not None and weak_ret_20d > b2)) else 0
                        else:
                            # 跨境资产：如果缺失基准数据(b1==0)，则只要它自己20日收益为负，就视为跑输(R=0)允许卖出
                            if b1 == 0:
                                r_score = 0 if weak_ret_20d < 0 else 100
                            else:
                                r_score = 100 if weak_ret_20d > b1 else 0

            # 3. 判定弱势：浮盈<5% 且 S分<50 且 ✅ 新增：持仓超过 10 天（度过免死金牌期）
            if profit_pct < 5 and s_score < 50 and days_held >= 10:
                weak_holdings.append({
                    "code": code,
                    "holding": holding,
                    "S": s_score,
                    "profit_pct": profit_pct,
                    "ret_20d": weak_ret_20d,   # 塞入计算好的 20日收益
                    "R": r_score               # 塞入计算好的 R分
                })
        
        if not weak_holdings:
            return 0
        
        # 按S分排序（最弱的在前）
        weak_holdings.sort(key=lambda x: x['S'])

        # Phase 1-3：提高汰弱留强门槛    
        # ✅ 修复 Bug：解除通道堵死，采用交叉匹配遍历
        for strong in strong_candidates:
            if not weak_holdings:
                break
            if buy_count + generated_buys >= max_buy_per_day:
                break
            
            swapped = False
            
            # 遍历寻找能匹配上的弱鸡，而不是只死磕第一个
            for i, weakest in enumerate(weak_holdings):
                # ★★★ 换仓条件提高 ★★★
                # 1. 势能差：维持 2.0 倍
                s_diff_ok = strong.S > weakest['S'] * 2.0
                
                # 2. ✅ 第三步修改：强标门槛。强势标的必须是真正的强者（S分及格且有余力）
                is_true_dragon = strong.S >= 70
                
                # 3. ✅ 第三步修改：弱标门槛。除了20日收益为负，浮亏必须达到一定痛点（<-2.0%）才换，防止错杀洗盘
                is_truly_weak = weakest['ret_20d'] < 0 and weakest['profit_pct'] < -2.0
                
                r_zero_ok = weakest['R'] == 0
                
                # 综合判断：必须同时满足四个严格条件才允许汰弱留强
                if s_diff_ok and is_true_dragon and is_truly_weak and r_zero_ok:
                    # 卖出弱势标的（全部持仓）
                    self.pending_orders.append(PendingOrder(
                        type='SELL',
                        code=weakest['code'],
                        name=weakest['holding'].name,
                        qty=weakest['holding'].qty,
                        reason='汰弱留强'
                    ))
                    
                    # 添加汰弱留强冷却期（10天，无特赦）
                    self.add_cooldown(weakest['code'], t_date, 'rebalance_sell')
                    
                    # 获取当前市场状态并计算买入金额
                    
                    is_bull_enhanced = coeff == 1.0 and self.get_market_temperature(t_date)[1]
                    
                    # ====================================================
                    # ★ 全球宏观保护：如果买入的是跨境资产，检查标普500是否跌破MA200
                    # ====================================================
                    if getattr(item, 'asset_class', '') == '跨境' and 'SPX.GI' in self.index_data:
                        spx_df = self.index_data['SPX.GI'].loc[:t_date]
                        if len(spx_df) >= 200:
                            spx_close = float(spx_df['close'].iloc[-1])
                            spx_ma200 = float(spx_df['close'].rolling(200).mean().iloc[-1])
                            if spx_close < spx_ma200:
                                # 标普500跌破牛熊分界线，全球宏观恶化，直接跳过买入（空仓避险）
                                continue 
                    # ====================================================

                    
                    target_value, approved_amount = self.calculate_buy_amount(
                        strong, nav, coeff, is_red_light, is_bull_enhanced
                    )
                    
                    if approved_amount > 0:
                        buy_shares = int(approved_amount // strong.price // 100) * 100
                        if buy_shares >= 100:
                            self.pending_orders.append(PendingOrder(
                                type='BUY',
                                code=strong.code,
                                name=strong.name,
                                qty=buy_shares,
                                reason='汰弱留强-换入'
                            ))
                            generated_buys += 1
                    
                    # 踢出已处理的弱势标的，跳出寻找下一个强标的
                    weak_holdings.pop(i)
                    swapped = True
                    break 
            
            # 如果发生了置换，说明当前的 strong 已经被消化了，跳过本次外层循环
            if swapped:
                continue
        
        return generated_buys

    
    def calculate_buy_amount(self, item: RankingItem, nav: float, coeff: float,
                                is_red_light: bool, is_bull_enhanced: bool) -> Tuple[float, float]:
            """
            根据排行榜条目和当前市场状态计算目标买入金额 - 10.51% 圣杯版：全量进攻，消灭闲置
            """
            phase_ratio = 1.0
            
            if not is_red_light:
                # 1. 提取风险乘数
                rp_multiplier = getattr(item, 'rp_multiplier', 1.0)
                
                # 2. 目标市值使用已经包含风险修正的 normalize_weight
                target_value = nav * coeff * item.normalize_weight * phase_ratio
                
                existing_value = 0
                gap = max(0, target_value - existing_value)

                # ★ 10.51% 核心：绝对上限完全放开，不被 rp_multiplier 压制，满血进攻
                absolute_max = nav * item.max_weight
                
                approved_amount = min(gap, absolute_max, self.cash)
            else:
                target_value = 0
                approved_amount = 0
            
            return target_value, approved_amount
    
    # ============================================================
    # 9. 主动减仓检查（无修改）
    # ============================================================
    
    def check_active_reduction(self, holding: Holding, t_date: str, current_price: float,
                               holdings_count: int, rankings: List[RankingItem]) -> Tuple[bool, int, str]:
        """
        检查是否需要主动减仓
        返回: (should_reduce, sell_qty, cool_type)
        """
        # 获取动态最大持仓数
        max_holdings, _, _ = self.get_dynamic_caps(t_date)
        
        if len(holding.signal_history) < 10:
            return False, 0, None
        
        # 检查最近10日信号分是否全部为0
        if sum(holding.signal_history[-10:]) > 0:
            return False, 0, None
        
        # 检查浮亏是否超过5%
        profit_pct = (current_price - holding.cost) / holding.cost * 100
        if profit_pct >= -5:
            return False, 0, None
        
        # 条件判断：持仓数<动态最大数 或 没有强势候选
        if holdings_count < max_holdings:
            # 持仓不足动态最大数，允许主动减仓
            return True, holding.qty, 'active_reduction'
        
        # 持仓>=动态最大数，检查是否有强势候选（S>=70 或 极速突破）
        has_strong = False
        for item in rankings[:15]:
            if item.code in self.holdings:
                continue
            if item.S >= 70:
                has_strong = True
                break
            # 极速突破检查
            if item.code in self.etf_data:
                df = self.etf_data[item.code].loc[:t_date]
                if len(df) >= 2:
                    last = df.iloc[-1]
                    prev = df.iloc[-2]
                    daily_ret = (last['close'] / prev['close'] - 1) * 100
                    vol_ratio = last['vol'] / last['ma5_vol'] if last['ma5_vol'] > 0 else 1
                    price_position = (last['close'] - last['low']) / (last['high'] - last['low']) if last['high'] != last['low'] else 0
                    if daily_ret > FAST_BREAK_PCT and vol_ratio > FAST_BREAK_VOL and last['close'] > last['ma20'] and price_position >= 0.75:
                        has_strong = True
                        break
        
        if not has_strong:
            # 没有强势候选，允许主动减仓
            return True, holding.qty, 'active_reduction'
        
        return False, 0, None       

    # ============================================================
    # 10. 冷却期管理 (PRD V4.1.1 完整版)（无修改）
    # ============================================================
    
    def is_in_cooldown(self, code: str, t_date: str) -> bool:
        """检查是否在冷却期内"""
        if code not in self.cooling:
            return False
        return t_date < self.cooling[code]
    
    def add_cooldown(self, code: str, t_date: str, cool_type: str):
        """
        添加冷却期
        cool_type: 'stop_loss' -> 10天; 'take_profit' -> 5天; 'rebalance_sell' -> 10天; 'active_reduction' -> 5天
        """
        if cool_type == 'stop_loss':
            days = 10
        elif cool_type == 'take_profit':
            days = 5
        elif cool_type == 'rebalance_sell':
            # ✅ 第二步修改：冷却期调整为20（翻倍），防止在震荡市中反复调仓摩擦
            days = 20
        elif cool_type == 'active_reduction':
            days = 5
        else:
            days = 5  # 默认
        cool_until = (datetime.strptime(t_date, '%Y%m%d') + timedelta(days=days)).strftime('%Y%m%d')
        self.cooling[code] = cool_until
        self.cooling_type[code] = cool_type
    
    def force_remove_cooldown(self, code: str):
        """强制解除冷却期"""
        if code in self.cooling:
            del self.cooling[code]
            if code in self.cooling_type:
                del self.cooling_type[code]
    
    def check_cooldown_amnesty(self, code: str, t_date: str) -> bool:
        """
        检查冷却期是否可特赦解除（仅止损冷却适用）
        返回 True 表示可解除
        """
        if code not in self.cooling_type:
            return False
        cool_type = self.cooling_type.get(code)
        if cool_type != 'stop_loss':
            return False
        # 检查极速突破（涨幅>5%、量比>2、价格>MA20）
        if code in self.etf_data and t_date in self.etf_data[code].index:
            df = self.etf_data[code].loc[:t_date]
            if len(df) >= 2:
                last = df.iloc[-1]
                prev = df.iloc[-2]
                daily_ret = (last['close'] / prev['close'] - 1) * 100
                vol_ratio = last['vol'] / last['ma5_vol'] if last['ma5_vol'] > 0 else 1
                if daily_ret > COOLDOWN_FAST_BREAK_PCT and vol_ratio > COOLDOWN_FAST_BREAK_VOL and last['close'] > last['ma20']:
                    return True
        return False
    
    # ============================================================
    # 11. 熔断机制 (PRD V4.1.1)（无修改）
    # ============================================================
    
    def check_circuit_breaker(self, t_date: str, nav: float, drawdown: float) -> bool:
        """
        检查熔断机制
        返回: True表示触发熔断
        """
        if drawdown >= 10.0 and not self.frozen_until:
            # 触发熔断，清仓所有持仓
            for code, holding in list(self.holdings.items()):
                cfg = None
                for c in ETF_POOL:
                    if c['code'] == code:
                        cfg = c
                        break
                if cfg and cfg['m_group'] == 'A股':
                    # 计算当前浮盈
                    if code in self.etf_data and t_date in self.etf_data[code].index:
                        row = self.etf_data[code].loc[t_date]
                        current_price = float(row['close'].iloc[-1] if isinstance(row['close'], pd.Series) else row['close'])
                        profit_pct = (current_price - holding.cost) / holding.cost * 100
                        if profit_pct < 0:
                            # 只清仓浮亏的A股
                            self.pending_orders.append(PendingOrder(
                                type='SELL',
                                code=code,
                                name=holding.name,
                                qty=holding.qty,
                                reason='熔断清仓(亏损)'
                            ))
                        # 浮盈的A股保留，不卖出
            
            # 设置冰封期 (14天)
            self.frozen_until = (datetime.strptime(t_date, '%Y%m%d') + timedelta(days=14)).strftime('%Y%m%d')
            
            # 关键修复：重置历史最高净值，避免解冻后无限熔断
            self.peak_nav = nav
            return True
        
        return False
    
    # ============================================================
    # 12. 执行挂单 (使用开盘价)（无修改）
    # ============================================================
    
    def execute_pending_orders(self, t_date: str):
        """
        执行T-1日产生的挂单（使用T日开盘价）
        手续费包含最低5元限制（不免5）
        """
        if not self.pending_orders:
            return
        
        for order in self.pending_orders:
            if order.code not in self.etf_data or t_date not in self.etf_data[order.code].index:
                continue
            
            # 获取执行价格（开盘价）
            row = self.etf_data[order.code].loc[t_date]
            try:
                price_val = row['open']
                exec_price = float(price_val.iloc[-1] if isinstance(price_val, pd.Series) else price_val)
                if exec_price <= 0 or pd.isna(exec_price):
                    continue
            except (KeyError, IndexError, TypeError):
                continue
            
            if order.type == 'BUY':
                # 买入执行（含滑点、手续费，手续费最低5元）
                raw_commission = order.qty * exec_price * COMMISSION
                commission = max(raw_commission, 5.0)   # 最低5元
                slippage_cost = order.qty * exec_price * SLIPPAGE
                cost = order.qty * exec_price + slippage_cost + commission
                
                if self.cash >= cost:
                    self.cash -= cost
                    
                    # 记录买入金额
                    trade_amount = order.qty * exec_price
                    if t_date not in self.daily_trade_volume:
                        self.daily_trade_volume[t_date] = [0, 0]
                    self.daily_trade_volume[t_date][0] += trade_amount
                    
                    if order.code not in self.holdings:
                        self.holdings[order.code] = Holding(
                            code=order.code,
                            name=order.name,
                            qty=order.qty,
                            cost=exec_price,
                            highest=exec_price,
                            buy_date=t_date,
                            signal_history=[]
                        )
                    else:
                        # 加仓：更新均价
                        h = self.holdings[order.code]
                        new_total_qty = h.qty + order.qty
                        h.cost = (h.qty * h.cost + order.qty * exec_price) / new_total_qty
                        h.qty = new_total_qty
                        
            elif order.type == 'SELL':
                # 卖出执行（含滑点、手续费，手续费最低5元）
                if order.code in self.holdings:
                    h = self.holdings[order.code]
                    actual_qty = min(order.qty, h.qty)
                    
                    if actual_qty > 0:
                        raw_commission = actual_qty * exec_price * COMMISSION
                        commission = max(raw_commission, 5.0)   # 最低5元
                        slippage_cost = actual_qty * exec_price * SLIPPAGE
                        sell_amount = actual_qty * exec_price - slippage_cost - commission
                        self.cash += sell_amount
                        
                        profit_pct = (exec_price / h.cost - 1) * 100
                        days_held = (datetime.strptime(t_date, '%Y%m%d') - datetime.strptime(h.buy_date, '%Y%m%d')).days
                        
                        # 记录交易流水
                        self.trades.append({
                            "code": order.code,
                            "name": order.name,
                            "profit_pct": profit_pct,
                            "days": days_held,
                            "reason": order.reason,
                            "sell_date": t_date
                        })
                        
                        # 记录卖出金额
                        trade_amount = actual_qty * exec_price
                        if t_date not in self.daily_trade_volume:
                            self.daily_trade_volume[t_date] = [0, 0]
                        self.daily_trade_volume[t_date][1] += trade_amount
                        
                        # 添加冷却期（根据卖出原因）
                        if '止损' in order.reason or 'stop_loss' in order.reason.lower():
                            self.add_cooldown(order.code, t_date, 'stop_loss')
                        elif '止盈' in order.reason or 'take_profit' in order.reason.lower():
                            self.add_cooldown(order.code, t_date, 'take_profit')
                        elif '汰弱留强' in order.reason:
                            self.add_cooldown(order.code, t_date, 'rebalance_sell')
                        elif '主动减仓' in order.reason:
                            self.add_cooldown(order.code, t_date, 'active_reduction')
                        # 熔断清仓不添加冷却期（冰封期已单独处理）
                        
                        if actual_qty >= h.qty:
                            del self.holdings[order.code]
                        else:
                            h.qty -= actual_qty
        
        # 清空已执行的挂单
        self.pending_orders = []
    
    # ============================================================
    # 13. 生成买入信号（每日盘后）- 增加净持仓数限制（无修改）
    # ============================================================
    
    def _net_holdings_count_after_pending_sells(self) -> int:
        """
        计算净持仓数 = 当前持仓数 - 即将执行的换仓卖出数量
        （换仓卖出后这些持仓会被移除，因此净持仓会减少）
        """
        sell_codes = set()
        for order in self.pending_orders:
            if order.type == 'SELL' and '汰弱留强' in order.reason:
                sell_codes.add(order.code)
        return len(self.holdings) - len(sell_codes)
    
    def generate_buy_signals(self, t_date: str, rankings: List[RankingItem], 
                             nav: float, coeff: float, is_red_light: bool,
                             is_bull_enhanced: bool, buy_count: int, max_buy_per_day: int) -> int:
        """
        生成买入信号 - 100%还原生产逻辑 (V4.1.1)
        返回: 本次生成的买入数量
        """
        # 获取沪深300的20日收益率（用于红灯特赦）
        hs300_20d_ret = 0
        if is_red_light:
            if '000300.SH' in self.index_data and t_date in self.index_data['000300.SH'].index:
                ret = self.index_data['000300.SH'].loc[t_date, 'ret_20d']
                hs300_20d_ret = float(ret.iloc[-1] if isinstance(ret, pd.Series) else ret)
        
        # 用户可用购买力（现金）
        available_buying_power = self.cash
        
        # 每日最多买入数量
        generated_buys = 0
        
        # 计算净持仓数（考虑待执行的换仓卖出）
        net_holdings = self._net_holdings_count_after_pending_sells()

        # 获取动态上限
        max_holdings, _, _ = self.get_dynamic_caps(t_date)        
        
        for item in rankings[:15]:
            if buy_count + generated_buys >= max_buy_per_day:
                break
            
            # 跳过已有持仓
            if item.code in self.holdings:
                continue
            
            # 净持仓数已达上限，不再新开仓
            if net_holdings >= max_holdings:
                continue
            
            # 海外资产永远绿灯
            if item.m_group in ['跨境', '商品']:
                eff_coeff = 1.0
                eff_red = False
            else:
                eff_coeff = coeff
                eff_red = is_red_light
                        

            # 买入信号分析
            buy_result = self.analyze_buy_signal(
                item.code, t_date, coeff, is_red_light, is_bull_enhanced
            )
            
            if not buy_result:
                continue
            
            # ============================================================
            # 建仓拦截检查
            # ============================================================
            
            # 拦截1: 相对强度拦截
            if item.m_group == "A股":
                if item.R == 0:
                    continue
            else:
                if item.R == 0:
                    continue
            
            # 拦截2: 冷却期检查（带特赦）
            if self.is_in_cooldown(item.code, t_date):
                if self.check_cooldown_amnesty(item.code, t_date):
                    self.force_remove_cooldown(item.code)
                else:
                    continue
            
            # ============================================================
            # 金额计算
            # ============================================================
            
            current_price = buy_result.current_price
            phase_ratio = buy_result.phase_ratio

            
            # 情景A: 正常情况（非红灯）
            if not eff_red:
                target_value = nav * eff_coeff * item.normalize_weight * phase_ratio
                existing_value = 0
                gap = max(0, target_value - existing_value)
                absolute_max = nav * item.max_weight
                approved_amount = min(gap, absolute_max, available_buying_power)
            
            # 情景B: 红灯特赦
            else:
                beats_hs300 = (item.ret_20d - hs300_20d_ret) > 10
                fast_break_for_red = False
                if item.code in self.etf_data and t_date in self.etf_data[item.code].index:
                    df = self.etf_data[item.code].loc[:t_date]
                    if len(df) >= 2:
                        last = df.iloc[-1]
                        prev = df.iloc[-2]
                        daily_ret = (last['close'] / prev['close'] - 1) * 100
                        vol_ratio_5d = last['vol'] / last['ma5_vol'] if last['ma5_vol'] > 0 else 1
                        if (daily_ret > RED_FAST_BREAK_PCT and 
                            vol_ratio_5d > RED_FAST_BREAK_VOL and 
                            last['close'] > last['ma20']):
                            fast_break_for_red = True
                
                if fast_break_for_red and beats_hs300:
                    absolute_max = nav * 0.05
                    approved_amount = min(absolute_max, available_buying_power)
                else:
                    continue
            
            if approved_amount <= 0:
                continue
            
            # 股数换算
            buy_shares = int(approved_amount // current_price // 100) * 100
            
            if buy_shares == 0:
                if 'gap' in locals() and 0 < gap < 2000:
                    buy_shares = 100
                else:
                    continue
            
            # 创建买入挂单
            self.pending_orders.append(PendingOrder(
                type='BUY',
                code=item.code,
                name=item.name,
                qty=buy_shares,
                reason=f"买入信号: {buy_result.phase_name} (S={item.S:.1f})"
            ))
            generated_buys += 1
            
            # 每生成一个买入，净持仓数+1（因为不会立即卖出，但为了后续循环中不超限，更新一下）
            net_holdings += 1
        
        return generated_buys
    
    # ============================================================
    # 14. 生成卖出信号（每日盘后）（无修改）
    # ============================================================
    
    def generate_sell_signals(self, t_date: str, rankings: List[RankingItem], holdings_count: int):
        """
        生成卖出信号 - 10.51% 圣杯版：死拿 15% 主升浪
        """
        for code, holding in list(self.holdings.items()):
            if code not in self.etf_data:
                continue
            
            df = self.etf_data[code].loc[:t_date]
            if len(df) < 20:
                continue
                
            row = df.iloc[-1]
            current_price = float(row['close'].iloc[-1] if isinstance(row['close'], pd.Series) else row['close'])
            holding.last_price = current_price
            
            # ============================================================
            # ★ 10.51% 核心：均线乖离率 (Bias) 15% 固定极速止盈，不看宏观脸色
            # ============================================================
            is_bias_triggered = False
            if 'ma20' in row and pd.notna(row['ma20']):
                ma20_val = float(row['ma20'].iloc[-1] if isinstance(row['ma20'], pd.Series) else row['ma20'])
                if ma20_val > 0:
                    bias = (current_price - ma20_val) / ma20_val * 100
                    
                    if bias >= 15.0 and not getattr(holding, 'bias_tp_triggered', False):
                        sell_qty = int(holding.qty * 0.5)  # 强制卖出 50%
                        
                        if sell_qty > 0:
                            self.pending_orders.append(PendingOrder(
                                type='SELL',
                                code=code,
                                name=holding.name,
                                qty=sell_qty,
                                reason="极端疯牛乖离>15%极速止盈一半"
                            ))
                            holding.bias_tp_triggered = True 
                            is_bias_triggered = True
            
            if is_bias_triggered:
                continue

            # ============================================================
            # 检查1: 动态生命线（止损/止盈）
            # ============================================================
            trigger_price, sell_type = self.get_dynamic_sell_price(holding, row)
            
            if current_price <= trigger_price:
                self.pending_orders.append(PendingOrder(
                    type='SELL',
                    code=code,
                    name=holding.name,
                    qty=holding.qty,
                    reason=f"{sell_type}触发"
                ))
                continue
            
            # ============================================================
            # 检查2: 主动减仓 (汰弱留强由外部 check_rebalance 接管)
            # ============================================================
            should_reduce, sell_qty, cool_type = self.check_active_reduction(
                holding, t_date, current_price, holdings_count, rankings
            )
            
            if should_reduce:
                self.pending_orders.append(PendingOrder(
                    type='SELL',
                    code=code,
                    name=holding.name,
                    qty=sell_qty,
                    reason="主动减仓"
                ))
            
            # ============================================================
            # 更新信号历史
            # ============================================================
            params = getattr(self, 'market_temp_params', None)
            coeff, is_bull_enhanced, total_score, is_red_light = self.get_market_temperature(t_date, params)
            buy_result = self.analyze_buy_signal(code, t_date, coeff, is_red_light, is_bull_enhanced)
            
            if buy_result:
                holding.signal_history.append(buy_result.signal_score)
            else:
                holding.signal_history.append(0)
            
            if len(holding.signal_history) > 30:
                holding.signal_history = holding.signal_history[-30:]
    
    # ============================================================
    # 15. 更新持仓最高价（无修改）
    # ============================================================
    
    def update_holdings_highest(self, t_date: str):
        """更新持仓最高价"""
        for code, holding in self.holdings.items():
            if code in self.etf_data and t_date in self.etf_data[code].index:
                row = self.etf_data[code].loc[t_date]
                current_price = float(row['close'].iloc[-1] if isinstance(row['close'], pd.Series) else row['close'])
                if current_price > holding.highest:
                    holding.highest = current_price
                holding.last_price = current_price
    
    # ============================================================
    # 16. 计算账户净值（无修改）
    # ============================================================
    
    def calculate_nav(self, t_date: str) -> Tuple[float, float]:
        """
        计算账户净值
        返回: (nav, drawdown)
        """
        mv = 0
        for code, holding in self.holdings.items():
            if code in self.etf_data and t_date in self.etf_data[code].index:
                row = self.etf_data[code].loc[t_date]
                price = float(row['close'].iloc[-1] if isinstance(row['close'], pd.Series) else row['close'])
                mv += price * holding.qty
        
        nav = self.cash + mv
        
        if nav > self.peak_nav:
            self.peak_nav = nav
        
        drawdown = (self.peak_nav - nav) / self.peak_nav * 100
        
        return nav, drawdown
    
    # ============================================================
    # 17. 主回测循环（无修改）
    # ============================================================
    
    def run(self, start_date: str, end_date: str, verbose: bool = True) -> Dict[str, Any]:
        """
        执行回测
        """
        self.reset_state()

        #print(f"\n🔍 调试信息 - 任务: {start_date}->{end_date}")
        #print(f"   market_temp_params = {getattr(self, 'market_temp_params', '未设置')}")
        #print(f"   v3_states 数量 = {len(self.v3_states) if hasattr(self, 'v3_states') else 0}")
        
        # 筛选交易日
        dates = [d for d in self.all_trade_dates if start_date <= d <= end_date]
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"🚀 开始回测: {start_date} -> {end_date}")
            print(f"📊 交易日数量: {len(dates)}")
            print(f"{'='*60}\n")
        
        for i, t_date in enumerate(dates):
            # ============================================================
            # 1. 更新持仓价格和净值
            # ============================================================
            self.update_holdings_highest(t_date)
            nav, drawdown = self.calculate_nav(t_date)
            
            # ============================================================
            # 2. 执行昨日挂单（T日开盘价成交）
            # ============================================================
            self.execute_pending_orders(t_date)
            
            # 重新计算净值（挂单执行后）
            nav, drawdown = self.calculate_nav(t_date)
            
            # ============================================================
            # 3. 熔断检查
            # ============================================================
            if self.check_circuit_breaker(t_date, nav, drawdown):
                # 熔断后继续执行挂单
                self.execute_pending_orders(t_date)
                nav, drawdown = self.calculate_nav(t_date)
                self.history.append({
                    "date": t_date,
                    "nav": nav,
                    "drawdown": drawdown,
                    "status": "熔断",
                    "holdings_count": len(self.holdings)
                })
                # 记录每日状态
                self.daily_records.append({
                    'date': t_date,
                    'nav': nav,
                    'light': '🚨 熔断',
                    'light_score': -3,
                    'holdings_count': len(self.holdings),
                    'cash': self.cash,
                    'total_assets': nav,
                })
                continue
            
            # ============================================================
            # 4. 冰封期检查
            # ============================================================
            if self.frozen_until and t_date < self.frozen_until:
                self.history.append({
                    "date": t_date,
                    "nav": nav,
                    "drawdown": drawdown,
                    "status": "冰封",
                    "holdings_count": len(self.holdings)
                })
                self.daily_records.append({
                    'date': t_date,
                    'nav': nav,
                    'light': '❄️ 冰封',
                    'light_score': -999,
                    'holdings_count': len(self.holdings),
                    'cash': self.cash,
                    'total_assets': nav,
                })
                continue
            
            if self.frozen_until and t_date >= self.frozen_until:
                self.frozen_until = None
            
            # ============================================================
            # 5. 获取市场状态
            # ============================================================
            params = getattr(self, 'market_temp_params', None)

            # ★ 记录当前净值用于动态回撤保护
            self.current_nav = nav

            coeff, is_bull_enhanced, total_score, is_red_light = self.get_market_temperature(t_date, params)

            #if t_date == dates[0]:  # 只在第一天打印
            #    print(f"   首日红绿灯: coeff={coeff:.3f}, is_red_light={is_red_light}, total_score={total_score}")
            
            # 生成红绿灯图标
            if coeff >= 0.6:
                light_icon = "🟢 绿灯"
            elif coeff >= 0.4:
                light_icon = "🟡 黄灯"
            else:
                light_icon = "🔴 红灯"
            
            # 检测红绿灯切换
            if self.prev_light is not None and self.prev_light != light_icon:
                self.switch_events.append({
                    'date': t_date,
                    'from': self.prev_light,
                    'to': light_icon,
                })
            self.prev_light = light_icon

            self.prev_light = light_icon

            # ★ V3 熊市拦截：当 V3 确认熊市（5-30天）时，强制压制 A 股仓位系数
            # 跨境和商品 ETF 的"永远绿灯"逻辑在后续买入时会自动豁免，此处只影响 A 股
            v3_state, v3_duration = self.get_v3_state(t_date)
            if v3_state == 'SYSTEMIC_BEAR' and 5 <= v3_duration <= 30:
                coeff = min(coeff, 0.10)      # 此刻将 A 股仓位系数压到极低
                is_red_light = True
                # 重新生成红绿灯图标
                light_icon = "🔴 红灯"
                # 总得分也相应降低
                total_score = min(total_score, -3)

            
            # ============================================================
            # 6. 更新冷却期
            # ============================================================
            self.cooling = {k: v for k, v in self.cooling.items() if v > t_date}
            # 同步清理冷却类型
            self.cooling_type = {k: v for k, v in self.cooling_type.items() if k in self.cooling}
            
            # ============================================================
            # 7. 生成卖出信号（盘后）
            # ============================================================
            # 注意：需要先获取排行榜用于主动减仓判断
            rankings = self.get_rankings(t_date, is_bull_enhanced)
            self.generate_sell_signals(t_date, rankings, len(self.holdings))
            
            # ============================================================
            # 8. 汰弱留强换仓
            # ============================================================
            # 每日买入计数器（固定每日买入上限）
            max_buy_per_day = 3
            buy_count = 0
            
            # 先执行汰弱留强换仓（产生买卖挂单）
            buy_count += self.check_rebalance(t_date, rankings, coeff, is_red_light, nav, buy_count, max_buy_per_day)
            
            # ============================================================
            # 9. 生成买入信号
            # ============================================================
            buy_count += self.generate_buy_signals(t_date, rankings, nav, coeff, is_red_light, is_bull_enhanced, buy_count, max_buy_per_day)
            
            # ============================================================
            # 10. 记录历史
            # ============================================================
            if t_date == dates[0]:
                print(f"首日持仓: {[(h.code, h.qty, h.cost) for h in self.holdings.values()]}")
                print(f"首日现金: {self.cash:.2f}")
                print(f"首日净值: {nav:.2f}")

            self.history.append({
                "date": t_date,
                "nav": nav,
                "drawdown": drawdown,
                "cash": self.cash,
                "holdings_count": len(self.holdings),
                "status": light_icon,
                "mkt_score": total_score
            })
            self.daily_records.append({
                'date': t_date,
                'nav': nav,
                'light': light_icon,
                'light_score': total_score,
                'holdings_count': len(self.holdings),
                'cash': self.cash,
                'total_assets': nav,
            })
            
            if verbose and (i + 1) % 100 == 0:
                print(f"  进度: {i+1}/{len(dates)} | 净值: {nav:,.2f} | 持仓: {len(self.holdings)}")
        
        # 计算统计指标
        stats = self.calculate_stats(start_date, end_date)
        
        if verbose:
            self.print_report(start_date, end_date, stats)
        
        return stats
    
    # ============================================================
    # 18. 统计指标计算 (增强版) - 修正基准收益计算
    # ============================================================
    
    def calculate_stats(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """计算回测统计指标（修正基准收益计算版）"""
        if not self.history:
            return {}
        
        df = pd.DataFrame(self.history)
        # 将日期列转为 datetime，并设为索引
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df['daily_ret'] = df['nav'].pct_change().fillna(0)
        
        # 基础收益
        initial_nav = INITIAL_CAPITAL
        final_nav = df['nav'].iloc[-1]
        total_ret = (final_nav / initial_nav - 1) * 100
        years = (datetime.strptime(end_date, '%Y%m%d') - datetime.strptime(start_date, '%Y%m%d')).days / 365.25
        ann_ret = (1 + total_ret / 100) ** (1 / years) - 1 if years > 0 else 0
        
        # 基准收益（沪深300）- 修复：确保能正确获取价格
        bench_ret = 0
        bench_daily = pd.Series(0, index=df.index)
        if '000300.SH' in self.index_data:
            bench_df = self.index_data['000300.SH']
            
            # 辅助函数：获取指定日期的收盘价，若日期不存在则向前找最近的有效日期
            def get_close(date_str):
                if date_str in bench_df.index:
                    val = bench_df.loc[date_str, 'close']
                    if isinstance(val, pd.Series):
                        val = val.iloc[0]
                    return float(val)
                else:
                    # 找到小于等于 date_str 的最大日期
                    candidates = [d for d in bench_df.index if d <= date_str]
                    if candidates:
                        actual = max(candidates)
                        val = bench_df.loc[actual, 'close']
                        if isinstance(val, pd.Series):
                            val = val.iloc[0]
                        return float(val)
                    else:
                        return None
            
            start_close = get_close(start_date)
            end_close = get_close(end_date)
            
            if start_close is not None and end_close is not None and start_close > 0:
                bench_ret = (end_close / start_close - 1) * 100
            else:
                print(f"警告：无法获取基准指数在 {start_date} 或 {end_date} 附近的收盘价，基准收益设为0")
            
            # 计算日收益率序列（用于跑赢月份占比）
            bench_daily_raw = bench_df['close'].pct_change().fillna(0)
            bench_daily_raw.index = pd.to_datetime(bench_daily_raw.index)
            bench_daily = bench_daily_raw.reindex(df.index, method='ffill').fillna(0)
        else:
            print("警告：未找到沪深300指数数据，基准收益无法计算")    
        
        # 跑赢基准月份占比
        df['month'] = df.index.to_period('M')
        monthly_ret = df['nav'].resample('ME').last().pct_change().fillna(0)
        monthly_ret.index = monthly_ret.index.to_period('M')
        # 基准月收益
        bench_monthly = bench_daily.resample('ME').apply(lambda x: (1+x).prod() - 1).fillna(0)
        bench_monthly.index = bench_monthly.index.to_period('M')
        # 对齐
        common_months = monthly_ret.index.intersection(bench_monthly.index)
        beat_months = (monthly_ret[common_months] > bench_monthly[common_months]).sum()
        total_months = len(common_months)
        beat_month_ratio = beat_months / total_months if total_months > 0 else 0
        
        # 最大回撤及相关
        df['cummax'] = df['nav'].cummax()
        df['drawdown_pct'] = (df['nav'] - df['cummax']) / df['cummax'] * 100
        max_dd = df['drawdown_pct'].min()
        # 最大回撤发生日期（使用索引）
        max_dd_date = df['drawdown_pct'].idxmin().strftime('%Y%m%d') if not df['drawdown_pct'].isnull().all() else None
        
        # 基准最大回撤
        bench_df = self.index_data.get('000300.SH')
        bench_max_dd = 0
        if bench_df is not None:
            # 获取回测区间内的基准数据
            bench_series = bench_df.loc[start_date:end_date, 'close'] if start_date in bench_df.index and end_date in bench_df.index else pd.Series()
            if not bench_series.empty:
                bench_series = bench_series[~bench_series.index.duplicated(keep='first')]
                bench_cummax = bench_series.cummax()
                bench_drawdown = (bench_series - bench_cummax) / bench_cummax * 100
                bench_max_dd = bench_drawdown.min()
        dd_diff = max_dd - bench_max_dd if bench_max_dd != 0 else max_dd
        
        # 年化波动率
        vol = df['daily_ret'].std() * np.sqrt(252)
        
        # 下行风险
        down_returns = df[df['daily_ret'] < 0]['daily_ret']
        down_risk = down_returns.std() * np.sqrt(252) if len(down_returns) > 0 else 0
        
        # 风险调整指标
        rf = 0.03
        sharpe = (ann_ret - rf) / vol if vol > 0 else 0
        sortino = (ann_ret - rf) / down_risk if down_risk > 0 else 0
        calmar = ann_ret / abs(max_dd/100) if max_dd != 0 else 0
        
        # 交易与持仓指标
        trades_df = pd.DataFrame(self.trades)
        if not trades_df.empty:
            win_rate_trade = (trades_df['profit_pct'] > 0).mean() * 100
            avg_win = trades_df[trades_df['profit_pct'] > 0]['profit_pct'].mean() if (trades_df['profit_pct'] > 0).any() else 0
            avg_loss = trades_df[trades_df['profit_pct'] < 0]['profit_pct'].mean() if (trades_df['profit_pct'] < 0).any() else 0
            profit_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            avg_hold_days = trades_df['days'].mean()
        else:
            win_rate_trade = 0
            profit_loss_ratio = 0
            avg_hold_days = 0
        
        # 日胜率
        daily_win_rate = (df['daily_ret'] > 0).mean() * 100
        
        # 换手率
        if self.daily_trade_volume:
            df_trade = pd.DataFrame(self.daily_trade_volume.values(), index=pd.to_datetime(list(self.daily_trade_volume.keys())))
            df_trade.columns = ['buy_amt', 'sell_amt']
            df_trade = df_trade.reindex(df.index, fill_value=0)
            df['turnover'] = (df_trade['buy_amt'] + df_trade['sell_amt']) / (2 * df['nav'])
            avg_daily_turnover = df['turnover'].mean() * 100
            annual_turnover = avg_daily_turnover * 252
        else:
            avg_daily_turnover = 0
            annual_turnover = 0
        
        # 持仓数量统计
        df['holdings_count'] = [h['holdings_count'] for h in self.history]
        avg_holdings = df['holdings_count'].mean()
        max_holdings = df['holdings_count'].max()
        zero_holdings_days = (df['holdings_count'] == 0).sum()
        zero_holdings_ratio = zero_holdings_days / len(df) * 100
        
        # 超额收益（相对沪深300）
        excess_return = total_ret - bench_ret
        
        return {
            "任务名称": "",
            "区间": f"{start_date}-{end_date}",
            "区间收益率": f"{total_ret:.2f}%",
            "年化收益率": f"{ann_ret*100:.2f}%",
            "基准收益": f"{bench_ret:.2f}%",
            "超额收益": f"{excess_return:+.2f}%",
            "跑赢基准月份占比": f"{beat_month_ratio*100:.1f}%",
            "最大回撤": f"{max_dd:.2f}%",
            "最大回撤发生日期": max_dd_date,
            "与沪深300回撤差": f"{dd_diff:+.2f}%",
            "年化波动率": f"{vol*100:.2f}%",
            "下行风险": f"{down_risk*100:.2f}%",
            "夏普比率": f"{sharpe:.2f}",
            "索提诺比率": f"{sortino:.2f}",
            "卡玛比率": f"{calmar:.2f}",
            "日均换手率": f"{avg_daily_turnover:.2f}%",
            "年化换手率": f"{annual_turnover:.2f}%",
            "胜率（日）": f"{daily_win_rate:.1f}%",
            "胜率（交易）": f"{win_rate_trade:.1f}%",
            "盈亏比": f"{profit_loss_ratio:.2f}",
            "平均持仓天数": f"{avg_hold_days:.1f}",
            "平均持仓数量": f"{avg_holdings:.1f}",
            "最大持仓数量": max_holdings,
            "空仓天数占比": f"{zero_holdings_ratio:.1f}%",
        }
    
    def print_report(self, start_date: str, end_date: str, stats: Dict[str, Any]):
        """打印详细报告（控制台）"""
        print("\n" + "█"*80)
        print("      🚀 AlphaEnginePro 高保真回测报告 (PRD V4.1.1)")
        print("█"*80)
        print(f"\n【回测区间】{start_date} → {end_date}")
        print(f"【初始资金】{INITIAL_CAPITAL:,.0f} 元")
        print(f"【最终净值】{self.history[-1]['nav']:,.2f} 元" if self.history else "N/A")
        
        print("\n【收益指标】")
        print(f"  区间收益率: {stats.get('区间收益率', 'N/A')}")
        print(f"  年化收益率: {stats.get('年化收益率', 'N/A')}")
        print(f"  基准收益: {stats.get('基准收益', 'N/A')}")
        print(f"  超额收益: {stats.get('超额收益', 'N/A')}")
        print(f"  跑赢基准月份占比: {stats.get('跑赢基准月份占比', 'N/A')}")
        
        print("\n【风险指标】")
        print(f"  最大回撤: {stats.get('最大回撤', 'N/A')} (发生日: {stats.get('最大回撤发生日期', 'N/A')})")
        print(f"  与沪深300回撤差: {stats.get('与沪深300回撤差', 'N/A')}")
        print(f"  年化波动率: {stats.get('年化波动率', 'N/A')}")
        print(f"  下行风险: {stats.get('下行风险', 'N/A')}")
        
        print("\n【风险调整指标】")
        print(f"  夏普比率: {stats.get('夏普比率', 'N/A')}")
        print(f"  索提诺比率: {stats.get('索提诺比率', 'N/A')}")
        print(f"  卡玛比率: {stats.get('卡玛比率', 'N/A')}")
        
        print("\n【交易统计】")
        print(f"  交易次数: {len(self.trades)}")
        print(f"  胜率（交易）: {stats.get('胜率（交易）', 'N/A')}")
        print(f"  盈亏比: {stats.get('盈亏比', 'N/A')}")
        print(f"  平均持仓天数: {stats.get('平均持仓天数', 'N/A')}")
        print(f"  日均换手率: {stats.get('日均换手率', 'N/A')}")
        print(f"  年化换手率: {stats.get('年化换手率', 'N/A')}")
        
        print("\n【持仓统计】")
        print(f"  平均持仓数量: {stats.get('平均持仓数量', 'N/A')}")
        print(f"  最大持仓数量: {stats.get('最大持仓数量', 'N/A')}")
        print(f"  空仓天数占比: {stats.get('空仓天数占比', 'N/A')}")
        
        # 红绿灯分布
        df_daily = pd.DataFrame(self.daily_records)
        if not df_daily.empty:
            print("\n【红绿灯状态分布】")
            light_counts = df_daily['light'].value_counts()
            total_days = len(df_daily)
            for light, cnt in light_counts.items():
                print(f"  {light}: {cnt} 天 ({cnt/total_days*100:.1f}%)")
            
            print("\n【仓位调节效果（按红绿灯状态）】")
            avg_holdings_by_light = df_daily.groupby('light')['holdings_count'].mean()
            for light, avg_h in avg_holdings_by_light.items():
                print(f"  {light} 期间平均持仓数: {avg_h:.1f}")
        
        if self.switch_events:
            print("\n【红绿灯切换事件】")
            for evt in self.switch_events:
                print(f"  {evt['date']}: {evt['from']} → {evt['to']}")
        else:
            print("\n【红绿灯切换】无状态变化")
        
        print("\n" + "█"*80 + "\n")


# ============================================================
# 19. 多时段回测与Excel导出（无修改）
# ============================================================
def run_parameter_scan(engine, train_start, train_end, param_grid):
    """执行参数扫描，返回结果DataFrame"""
    results = []
    for w_trend in param_grid['w_trend']:
        for smooth in param_grid['smooth']:
            for delay in param_grid['delay']:
                # 构建参数字典
                params = {
                    'w_trend': w_trend,
                    'w_emotion': WEIGHT_EMOTION,
                    'w_volume': WEIGHT_VOLUME,
                    'N_emotion': EMOTION_WINDOW,
                    'N_volume': VOLUME_WINDOW,
                    'N_trend': TREND_WINDOW,
                    'smooth': smooth,
                    'delay': delay,
                    'base_coeff': BASE_COEFF,
                    'slope_coeff': SLOPE_COEFF,
                    'all_a_filter': ALL_A_FILTER
                }
                print(f"\n测试参数: w_trend={w_trend}, smooth={smooth}, delay={delay}")
                # 重置引擎
                engine.reset_state()
                # 将参数存入引擎
                engine.market_temp_params = params
                # 运行回测
                stats = engine.run(train_start, train_end, verbose=False)
                if stats:
                    results.append({
                        'w_trend': w_trend,
                        'smooth': smooth,
                        'delay': delay,
                        'ann_ret': float(stats['年化收益率'].strip('%')),
                        'max_dd': float(stats['最大回撤'].strip('%')),
                        'sharpe': float(stats['夏普比率']),
                        'turnover': float(stats['年化换手率'].strip('%')),
                        'beat_ratio': float(stats['跑赢基准月份占比'].strip('%')) / 100,
                    })
    return pd.DataFrame(results)

if __name__ == "__main__":
    # 数据中枢根目录（指数、市场广度）
    DATA_PATH = "/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata"
    # ETF 后复权目录（回测专用）
    ETF_HFQ_PATH = "/Users/aranwong/Documents/quant app/量化数据中枢/backtestdata/hfq"
    
    engine = AlphaEnginePro(DATA_PATH, etf_path=ETF_HFQ_PATH)
    engine.load_data()
    
    SCAN_MODE = False   # 改为 True 进行参数扫描
    

    if SCAN_MODE:
        # 参数扫描模式
        param_grid = {
            'w_trend': TREND_WEIGHTS,
            'smooth': SMOOTH_WINDOWS,
            'delay': DELAY_DAYS
        }
        train_start = "20190101"
        train_end = "20221231"   # 训练期
        results_df = run_parameter_scan(engine, train_start, train_end, param_grid)

        # 计算综合得分
        results_df['score'] = (results_df['sharpe'] 
                               - 0.1 * results_df['max_dd'] 
                               - 0.01 * results_df['turnover'] 
                               + 0.5 * results_df['beat_ratio'])
        results_df.sort_values('score', ascending=False, inplace=True)
        print("\n参数扫描结果（按综合得分排序）：")
        print(results_df[['w_trend','smooth','delay','ann_ret','max_dd','sharpe','turnover','beat_ratio','score']])
        
        # 保存结果到CSV
        results_df.to_csv("param_scan_results.csv", index=False)
        print("\n扫描结果已保存到 param_scan_results.csv")

        # 选出前3个组合进行验证期回测
        top3 = results_df.head(3)
        print("\n前3个最佳参数组合：")
        print(top3[['w_trend','smooth','delay','score']])

        # 验证期
        val_start = "20230101"
        val_end = "20260329"
        print(f"\n在验证期 {val_start} - {val_end} 测试这些组合...")
        for idx, row in top3.iterrows():
            params = {
                'w_trend': row['w_trend'],
                'smooth': row['smooth'],
                'delay': row['delay'],
                'w_emotion': WEIGHT_EMOTION,
                'w_volume': WEIGHT_VOLUME,
                'N_emotion': EMOTION_WINDOW,
                'N_volume': VOLUME_WINDOW,
                'N_trend': TREND_WINDOW,
                'base_coeff': BASE_COEFF,
                'slope_coeff': SLOPE_COEFF,
                'all_a_filter': ALL_A_FILTER
            }
            engine.reset_state()
            engine.market_temp_params = params
            stats = engine.run(val_start, val_end, verbose=False)
            print(f"\n参数组合 {row['w_trend']},{row['smooth']},{row['delay']} 在验证期表现：")
            if stats:
                print(f"  年化收益率: {stats['年化收益率']}")
                print(f"  最大回撤: {stats['最大回撤']}")
                print(f"  夏普比率: {stats['夏普比率']}")
                print(f"  跑赢基准月份占比: {stats['跑赢基准月份占比']}")

    else:
        # 设置优化后的红绿灯参数（方案A）
        engine.market_temp_params = {
            'w_trend': 0.5,
            'smooth': 1,
            'delay': 1,
            'w_emotion': 0.2,
            'w_volume': 0.2,
            'N_emotion': 20,
            'N_volume': 20,
            'N_trend': 60,
            'base_coeff': 0.5,
            'slope_coeff': 0.25,
            'all_a_filter': False   # 注意这里要改为 True 才能启用全A过滤，否则 False
        }
        # 严格遵守 训练集 + 验证集 模式，盲盒测试集被注释掉！
        #test_periods = [
        #    {"name": "训练集", "start": "20180903", "end": "20230331"},
        #    {"name": "验证集", "start": "20230401", "end": "20240930"},
        #    # 🛑 警告：在策略定稿前，绝对不允许解开下面这行的注释！
        #    {"name": "测试集", "start": "20241001", "end": "20260327"},
        #]
        
        
        # 原有多时段回测
        test_periods = [
            {"name": "训练期", "start": "20150101", "end": "20211231"},
            {"name": "验证期", "start": "20220104", "end": "20231229"},
            {"name": "盲测期", "start": "20240102", "end": "20260413"},
            {"name": "吃肉阶段", "start": "20190101", "end": "20210218"},
            {"name": "逃顶阶段", "start": "20210219", "end": "20221031"},
            {"name": "抗折磨阶段", "start": "20230101", "end": "20251231"},
        #    {"name": "实盘演习", "start": "20260101", "end": "20260329"},
            {"name": "熔断股灾", "start": "20150612", "end": "20160128"},
            {"name": "近三年", "start": "20230101", "end": "20260424"},
        #    {"name": "21~23", "start": "20210101", "end": "20231231"},
            {"name": "26年", "start": "20260101", "end": "20260424"},
            {"name": "21年超长", "start": "20050104", "end": "20260424"},
        #    {"name": "全时段4月", "start": "20190101", "end": "20260413"},
            {"name": "全时段", "start": "20190101", "end": "20260329"},
        #    {"name": "单日测试", "start": "20260105", "end": "20260105"},
        ]   
              
        # 这里放置你原来的多时段回测代码（保持不变）
    
        all_results = []
        all_period_details = []
        
        print("\n" + "="*80)
        print("🚀 开始多时段并行回测（仅输出最终报告）")
        print("="*80)
        
        for i, period in enumerate(test_periods):
            print(f"\n{'#'*80}")
            print(f"# 第 {i+1}/{len(test_periods)} 个回测: {period['name']}")
            print(f"# 区间: {period['start']} → {period['end']}")
            print(f"{'#'*80}")
            
            # 运行回测，verbose=True 输出详细信息，但为了简洁可设为False
            stats = engine.run(period['start'], period['end'], verbose=False)
            if stats:
                stats['任务名称'] = period['name']
                all_results.append(stats)
                
                # 保存详细数据用于Excel导出
                period_detail = {
                    'name': period['name'],
                    'start': period['start'],
                    'end': period['end'],
                    'stats': stats,
                    'trades': pd.DataFrame(engine.trades) if engine.trades else pd.DataFrame(),
                    'daily_records': pd.DataFrame(engine.daily_records) if engine.daily_records else pd.DataFrame(),
                    'switch_events': pd.DataFrame(engine.switch_events) if engine.switch_events else pd.DataFrame(),
                    'daily_trade_volume': pd.DataFrame(engine.daily_trade_volume.items(), columns=['date', 'amounts']) if engine.daily_trade_volume else pd.DataFrame(),
                }
                all_period_details.append(period_detail)
            
            engine.reset_state()
            print(f"\n✅ {period['name']} 回测完成")
        
        # 导出Excel
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        excel_filename = f"backtest_results_100pct_{timestamp}.xlsx"
        
        with pd.ExcelWriter(excel_filename, engine='openpyxl') as writer:
            # 汇总报告
            if all_results:
                summary_df = pd.DataFrame(all_results)
                # 调整列顺序，只保留需要的
                cols = ['任务名称', '区间', '区间收益率', '年化收益率', '基准收益', '超额收益', '跑赢基准月份占比',
                        '最大回撤', '最大回撤发生日期', '与沪深300回撤差', '年化波动率', '下行风险',
                        '夏普比率', '索提诺比率', '卡玛比率', '日均换手率', '年化换手率',
                        '胜率（日）', '胜率（交易）', '盈亏比', '平均持仓天数', '平均持仓数量', '最大持仓数量', '空仓天数占比']
                # 确保列存在
                summary_df = summary_df[[c for c in cols if c in summary_df.columns]]
                summary_df.to_excel(writer, sheet_name='0_汇总报告', index=False)
            
            # 每个时段的详细数据
            for detail in all_period_details:
                safe_name = detail['name'].replace('/', '_').replace('\\', '_').replace('*', '_').replace('?', '_').replace(':', '_')[:28]
                # 指标 sheet
                stats_df = pd.DataFrame([detail['stats']])
                stats_df.to_excel(writer, sheet_name=f"{safe_name}_指标", index=False)
                # 交易明细
                if not detail['trades'].empty:
                    detail['trades'].to_excel(writer, sheet_name=f"{safe_name}_交易明细", index=False)
                # 每日记录（含红绿灯状态、持仓数）
                if not detail['daily_records'].empty:
                    detail['daily_records'].to_excel(writer, sheet_name=f"{safe_name}_每日状态", index=False)
                # 红绿灯切换事件
                if not detail['switch_events'].empty:
                    detail['switch_events'].to_excel(writer, sheet_name=f"{safe_name}_切换事件", index=False)
        
        print(f"\n✅ 详细报告已导出到: {excel_filename}")
        print("   - 0_汇总报告: 所有时段指标对比")
        print("   - [时段]_指标: 该时段的完整指标")
        print("   - [时段]_交易明细: 每笔交易的盈亏和持股天数")
        print("   - [时段]_每日状态: 每日净值、红绿灯、持仓数等")
        print("   - [时段]_切换事件: 红绿灯状态切换记录")