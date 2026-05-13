# ============================================================
#  XAUUSD Multi-Timeframe Liquidity Sweep Reversal Bot
#  Configuration — edit this file with your MT5 credentials
# ============================================================

# ── MT5 Connection ────────────────────────────────────────────
MT5_LOGIN    = 5049682276          # Your MT5 account number
MT5_PASSWORD = "2dIh!qEd"      # Your MT5 password
MT5_SERVER   = "MetaQuotes-Demo"    # e.g. "ICMarkets-Live04"
MT5_PATH     = r"C:\Program Files\MetaTrader 5\terminal64.exe"                   # Optional full path to terminal64.exe

# ── Symbol & Entry Timeframe ──────────────────────────────────
SYMBOL          = "XAUUSD"
ENTRY_TIMEFRAME = "M1"              # Always M1 — entries on 1-min candles

# ── Multi-Timeframe Analysis Config ──────────────────────────
#  Each analysis TF has its own lookback and RR.
#  Signals from higher TFs override lower TFs (higher TF = stronger signal).
MTF_CONFIG = {
    # tf_name : { lookback, rr, priority (higher = stronger) }
    "M1"  : {"lookback": 40, "rr": 1.5, "priority": 1},
    "M5"  : {"lookback": 30, "rr": 2.0, "priority": 2},
    "M15" : {"lookback": 30, "rr": 3.0, "priority": 3},
    "H1"  : {"lookback": 20, "rr": 6.0, "priority": 4},
    "H4"  : {"lookback": 15, "rr": 5.0, "priority": 5},
}

# Analysis timeframes in priority order (lowest → highest)
ANALYSIS_TIMEFRAMES = ["H1"]

# ── Risk Management ───────────────────────────────────────────
RISK_PERCENT        = 0.5     # % of account balance risked per trade
MAX_DAILY_LOSS_PCT  = 5.0     # Bot pauses if daily drawdown hits this
MAX_OPEN_TRADES     = 2       # Max concurrent positions (across all TFs)
MAX_TRADES_PER_DAY  = 6       # Max total trades per day (None = unlimited)
MIN_LOT             = 0.01
MAX_LOT             = 5.0

# ── Sweep Detection ───────────────────────────────────────────
SWEEP_BUFFER_PIPS   = 40      # Min pips beyond high/low to count as sweep
REJECTION_BODY_PCT  = 0.60    # Max body/range ratio (0.60 = relaxed)
MIN_SWEEP_WICK_PCT  = 0.25    # Min wick/range ratio (0.25 = catches minor sweeps)

# ── Execution ─────────────────────────────────────────────────
MAX_SPREAD_POINTS   = 35      # Skip trade if spread > this
SLIPPAGE            = 5       # Max slippage in points
MAGIC_NUMBER        = 20250101

# ── Logging ───────────────────────────────────────────────────
LOG_DIR             = "logs"
LOG_LEVEL           = "INFO"
TRADE_LOG_CSV       = "logs/trades.csv"

# ── Internal TF map (auto-built — do not edit) ────────────────
import MetaTrader5 as mt5

TF_MAP = {
    "M1" : mt5.TIMEFRAME_M1,
    "M5" : mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "H1" : mt5.TIMEFRAME_H1,
    "H4" : mt5.TIMEFRAME_H4,
}
