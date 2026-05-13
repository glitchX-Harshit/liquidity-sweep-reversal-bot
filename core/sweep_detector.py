"""
core/sweep_detector.py
Multi-Timeframe Liquidity Sweep Detector for XAUUSD.

HOW MTF ANALYSIS WORKS
  Every M1 candle close triggers analysis across ALL configured timeframes
  (M1 -> M5 -> M15 -> H1 -> H4). Each TF has its own lookback + rr + priority.
  If multiple TFs fire, the HIGHEST PRIORITY (highest TF) signal wins.

TF CONFIG (from config.py MTF_CONFIG):
  M1  -> lookback=40  rr=1.5  priority=1
  M5  -> lookback=30  rr=2.0  priority=2
  M15 -> lookback=25  rr=3.0  priority=3
  H1  -> lookback=20  rr=4.0  priority=4
  H4  -> lookback=15  rr=5.0  priority=5

ENTRY: Always on M1 price (current_m1_price), regardless of which TF swept.
SL   : 3 pips beyond the sweep wick of the signal candle.
TP   : entry +/- (sl_dist x rr) where rr comes from the signal TF.
"""

import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np

logger = logging.getLogger(__name__)

PIP = 0.10  # XAUUSD: 1 pip = $0.10


@dataclass
class SweepSignal:
    direction   : str    # "LONG" or "SHORT"
    sweep_type  : str    # "buy_side" or "sell_side"
    source_tf   : str    # TF where sweep was detected e.g. "H1"
    rr          : float  # Risk:Reward assigned to this TF
    priority    : int    # Higher = stronger signal
    swept_level : float  # The liq high/low that was swept
    entry_price : float  # M1 market-order entry price
    stop_loss   : float  # Beyond the wick tip
    take_profit : float  # entry +/- (sl_dist x rr)
    wick_pct    : float  # Wick / range ratio
    body_pct    : float  # Body / range ratio
    description : str


class MultiTFSweepDetector:
    """
    Analyse candle data from multiple timeframes, return the highest-priority
    SweepSignal or None.

    Usage:
        detector = MultiTFSweepDetector(config)
        signal   = detector.analyse(tf_candles_dict, current_m1_price)

    tf_candles_dict: dict[tf_name -> np.structured_array]
      Arrays must already have the forming candle stripped (rates[:-1]).
    """

    def __init__(self, config):
        self.cfg = config

    def analyse(self, tf_candles: dict, current_m1_price: float) -> Optional[SweepSignal]:
        best = None
        for tf_name in self.cfg.ANALYSIS_TIMEFRAMES:
            candles = tf_candles.get(tf_name)
            if candles is None:
                continue
            tf_cfg   = self.cfg.MTF_CONFIG[tf_name]
            lookback = tf_cfg["lookback"]
            rr       = tf_cfg["rr"]
            priority = tf_cfg["priority"]

            if len(candles) < lookback + 2:
                continue

            pool          = candles[-(lookback + 1):-1]
            signal_candle = candles[-1]

            liq_high = self._liq_high(pool)
            liq_low  = self._liq_low(pool)

            signal = (
                self._check_bearish(signal_candle, liq_high, rr, priority, tf_name, current_m1_price)
                or
                self._check_bullish(signal_candle, liq_low,  rr, priority, tf_name, current_m1_price)
            )

            if signal and (best is None or signal.priority > best.priority):
                logger.info(
                    "MTF sweep on %s: %s  swept=%.2f  entry=%.2f  SL=%.2f  TP=%.2f  RR=1:%.1f",
                    tf_name, signal.direction, signal.swept_level,
                    signal.entry_price, signal.stop_loss, signal.take_profit, rr,
                )
                best = signal
        return best

    # ── Bearish sweep ─────────────────────────────────────────────────────────
    def _check_bearish(self, candle, liq_high, rr, priority, tf_name, m1_price):
        o = float(candle["open"]); h = float(candle["high"])
        l = float(candle["low"]);  c = float(candle["close"])
        rng = h - l
        if rng < PIP * 2:
            return None
        buf = self.cfg.SWEEP_BUFFER_PIPS * PIP
        if h < liq_high + buf:       return None   # level not breached
        if c >= o:                    return None   # not bearish
        upper_wick = h - max(o, c)
        wick_pct   = upper_wick / rng
        if wick_pct < self.cfg.MIN_SWEEP_WICK_PCT: return None
        body_pct = abs(c - o) / rng
        if body_pct > self.cfg.REJECTION_BODY_PCT: return None
        if c > liq_high:              return None   # closed above level — not a sweep

        entry = m1_price
        sl    = round(h + PIP * 3, 2)
        tp    = round(entry - (sl - entry) * rr, 2)
        if tp >= entry or sl <= entry:
            return None
        return SweepSignal(
            direction="SHORT", sweep_type="sell_side", source_tf=tf_name,
            rr=rr, priority=priority, swept_level=round(liq_high, 2),
            entry_price=round(entry, 2), stop_loss=sl, take_profit=tp,
            wick_pct=round(wick_pct, 3), body_pct=round(body_pct, 3),
            description=(
                f"[{tf_name}] Sell-side sweep above {liq_high:.2f}. "
                f"Wick {h:.2f}, close {c:.2f}. M1 entry={entry:.2f} "
                f"SL={sl:.2f} TP={tp:.2f} RR=1:{rr}"
            ),
        )

    # ── Bullish sweep ─────────────────────────────────────────────────────────
    def _check_bullish(self, candle, liq_low, rr, priority, tf_name, m1_price):
        o = float(candle["open"]); h = float(candle["high"])
        l = float(candle["low"]);  c = float(candle["close"])
        rng = h - l
        if rng < PIP * 2:
            return None
        buf = self.cfg.SWEEP_BUFFER_PIPS * PIP
        if l > liq_low - buf:         return None
        if c <= o:                     return None
        lower_wick = min(o, c) - l
        wick_pct   = lower_wick / rng
        if wick_pct < self.cfg.MIN_SWEEP_WICK_PCT: return None
        body_pct = abs(c - o) / rng
        if body_pct > self.cfg.REJECTION_BODY_PCT: return None
        if c < liq_low:                return None

        entry = m1_price
        sl    = round(l - PIP * 3, 2)
        tp    = round(entry + (entry - sl) * rr, 2)
        if tp <= entry or sl >= entry:
            return None
        return SweepSignal(
            direction="LONG", sweep_type="buy_side", source_tf=tf_name,
            rr=rr, priority=priority, swept_level=round(liq_low, 2),
            entry_price=round(entry, 2), stop_loss=sl, take_profit=tp,
            wick_pct=round(wick_pct, 3), body_pct=round(body_pct, 3),
            description=(
                f"[{tf_name}] Buy-side sweep below {liq_low:.2f}. "
                f"Wick {l:.2f}, close {c:.2f}. M1 entry={entry:.2f} "
                f"SL={sl:.2f} TP={tp:.2f} RR=1:{rr}"
            ),
        )

    # ── Liquidity helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _liq_high(pool):
        highs  = pool["high"].astype(float)
        swings = MultiTFSweepDetector._swing_highs(highs)
        return float(max(swings)) if swings else float(np.max(highs))

    @staticmethod
    def _liq_low(pool):
        lows   = pool["low"].astype(float)
        swings = MultiTFSweepDetector._swing_lows(lows)
        return float(min(swings)) if swings else float(np.min(lows))

    @staticmethod
    def _swing_highs(arr, pivot=2):
        result = []
        for i in range(pivot, len(arr) - pivot):
            if (all(arr[i] >= arr[i-j] for j in range(1, pivot+1)) and
                    all(arr[i] >= arr[i+j] for j in range(1, pivot+1))):
                result.append(float(arr[i]))
        return result

    @staticmethod
    def _swing_lows(arr, pivot=2):
        result = []
        for i in range(pivot, len(arr) - pivot):
            if (all(arr[i] <= arr[i-j] for j in range(1, pivot+1)) and
                    all(arr[i] <= arr[i+j] for j in range(1, pivot+1))):
                result.append(float(arr[i]))
        return result
