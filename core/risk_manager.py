"""
core/risk_manager.py
Position sizing, daily loss guard, spread filter, open trade limiter.
MAX_OPEN_TRADES = 2 (per config) — blocks analysis when 2 trades are open.
"""

import logging
import MetaTrader5 as mt5
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class RiskManager:

    def __init__(self, config, connector):
        self.cfg              = config
        self.conn             = connector
        self._day_start_bal   : Optional[float] = None
        self._trade_day       : Optional[date]  = None

    # ── Daily loss guard ──────────────────────────────────────────────────────
    def _refresh_day(self):
        today = date.today()
        if self._trade_day != today:
            self._trade_day     = today
            self._day_start_bal = self.conn.get_balance()
            logger.info("New trading day. Start balance: %.2f", self._day_start_bal)

    def is_daily_loss_exceeded(self) -> bool:
        self._refresh_day()
        if not self._day_start_bal:
            return False
        equity   = self.conn.get_equity()
        drawdown = (self._day_start_bal - equity) / self._day_start_bal * 100
        if drawdown >= self.cfg.MAX_DAILY_LOSS_PCT:
            logger.warning("Daily loss limit hit: %.2f%% (limit=%.2f%%)",
                           drawdown, self.cfg.MAX_DAILY_LOSS_PCT)
            return True
        return False

    # ── Spread guard ──────────────────────────────────────────────────────────
    def is_spread_ok(self) -> bool:
        spread = self.conn.get_spread(self.cfg.SYMBOL)
        if spread > self.cfg.MAX_SPREAD_POINTS:
            logger.warning("Spread too wide: %d pts (max=%d)", spread, self.cfg.MAX_SPREAD_POINTS)
            return False
        return True

    # ── Open trade gate ───────────────────────────────────────────────────────
    def can_open_trade(self) -> bool:
        """
        Returns False (block new trade) if:
          - daily loss limit exceeded
          - spread too wide
          - already at MAX_OPEN_TRADES (2) positions
        If we already have 2 trades open, analysis is paused until one closes.
        """
        if self.is_daily_loss_exceeded():
            return False
        if not self.is_spread_ok():
            return False
        open_trades = self.conn.get_open_positions(
            symbol=self.cfg.SYMBOL, magic=self.cfg.MAGIC_NUMBER
        )
        count = len(open_trades)
        if count >= self.cfg.MAX_OPEN_TRADES:
            logger.info(
                "MAX_OPEN_TRADES reached (%d/%d) — pausing analysis until a position closes.",
                count, self.cfg.MAX_OPEN_TRADES,
            )
            return False
        return True

    def open_trade_count(self) -> int:
        return len(self.conn.get_open_positions(
            symbol=self.cfg.SYMBOL, magic=self.cfg.MAGIC_NUMBER
        ))

    # ── Position sizing ───────────────────────────────────────────────────────
    def calculate_lot_size(self, entry: float, stop_loss: float) -> float:
        """
        Fixed fractional sizing for XAUUSD.
        XAUUSD: 1 standard lot = 100 oz => $1 move = $100 P&L per lot.
        lots = (balance * risk%) / (sl_distance * 100)
        """
        balance  = self.conn.get_balance()
        risk_amt = balance * (self.cfg.RISK_PERCENT / 100.0)
        sl_dist  = abs(entry - stop_loss)
        if sl_dist < 0.05:
            logger.error("SL distance too small (%.4f) — defaulting to MIN_LOT", sl_dist)
            return self.cfg.MIN_LOT
        lots = risk_amt / (sl_dist * 100.0)
        return self._clamp_lot(lots)

    def _clamp_lot(self, lots: float) -> float:
        sym = mt5.symbol_info(self.cfg.SYMBOL)
        if sym:
            step = sym.volume_step
            lots = round(lots / step) * step
        return round(max(self.cfg.MIN_LOT, min(self.cfg.MAX_LOT, lots)), 2)

    # ── Build order request ───────────────────────────────────────────────────
    def build_order_request(
        self, direction: str, stop_loss: float, take_profit: float,
        lots: float, comment: str = "sweep_mtf"
    ) -> dict:
        sym_info = mt5.symbol_info(self.cfg.SYMBOL)
        tick     = mt5.symbol_info_tick(self.cfg.SYMBOL)
        if not sym_info or not tick:
            logger.error("Cannot build order — no symbol/tick info")
            return {}
        if direction == "LONG":
            order_type = mt5.ORDER_TYPE_BUY
            price      = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price      = tick.bid
            
        filling_type = mt5.ORDER_FILLING_RETURN
        if sym_info.filling_mode & 1:
            filling_type = mt5.ORDER_FILLING_FOK
        elif sym_info.filling_mode & 2:
            filling_type = mt5.ORDER_FILLING_IOC

        return {
            "action"      : mt5.TRADE_ACTION_DEAL,
            "symbol"      : self.cfg.SYMBOL,
            "volume"      : lots,
            "type"        : order_type,
            "price"       : price,
            "sl"          : stop_loss,
            "tp"          : take_profit,
            "deviation"   : self.cfg.SLIPPAGE,
            "magic"       : self.cfg.MAGIC_NUMBER,
            "comment"     : comment,
            "type_time"   : mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }
