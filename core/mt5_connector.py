"""
core/mt5_connector.py
MetaTrader 5 connection manager + data fetcher.
Supports fetching candles for multiple timeframes in one call.
"""

import MetaTrader5 as mt5
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class MT5Connector:
    """Manages MT5 terminal connection lifecycle (context manager)."""

    def __init__(self, config):
        self.cfg       = config
        self.connected = False

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        kwargs = {}
        if self.cfg.MT5_PATH:
            kwargs["path"] = self.cfg.MT5_PATH
        if not mt5.initialize(**kwargs):
            logger.error("mt5.initialize() failed: %s", mt5.last_error())
            return False
        if not mt5.login(self.cfg.MT5_LOGIN, self.cfg.MT5_PASSWORD, self.cfg.MT5_SERVER):
            logger.error("mt5.login() failed: %s", mt5.last_error())
            mt5.shutdown()
            return False
        info = mt5.account_info()
        logger.info("Connected: login=%s  name=%s  balance=%.2f %s",
                    info.login, info.name, info.balance, info.currency)
        self.connected = True
        return True

    def disconnect(self):
        if self.connected:
            mt5.shutdown()
            logger.info("MT5 disconnected.")
            self.connected = False

    # ── Account ───────────────────────────────────────────────────────────────
    def get_balance(self) -> float:
        info = mt5.account_info()
        return float(info.balance) if info else 0.0

    def get_equity(self) -> float:
        info = mt5.account_info()
        return float(info.equity) if info else 0.0

    def get_account_info(self) -> dict:
        info = mt5.account_info()
        if not info:
            return {}
        return dict(login=info.login, name=info.name, balance=info.balance,
                    equity=info.equity, currency=info.currency,
                    leverage=info.leverage, server=info.server)

    # ── Market data ───────────────────────────────────────────────────────────
    def get_candles(self, symbol: str, timeframe: int, count: int):
        """
        Fetch `count` closed candles (strips the forming bar).
        Returns numpy structured array or None on failure.
        """
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count + 1)
        if rates is None or len(rates) < 2:
            logger.warning("get_candles failed for TF=%s count=%d: %s",
                           timeframe, count, mt5.last_error())
            return None
        return rates[:-1]   # strip the still-forming candle

    def get_all_tf_candles(self, symbol: str, tf_map: dict, mtf_config: dict) -> dict:
        """
        Fetch candles for ALL configured timeframes in one call.

        Returns dict[tf_name -> np.array] with enough bars for each TF's
        lookback + a few extra for the signal candle.
        """
        result = {}
        for tf_name, tf_int in tf_map.items():
            lookback = mtf_config[tf_name]["lookback"]
            # fetch lookback + 5 extra bars for safety
            candles = self.get_candles(symbol, tf_int, lookback + 5)
            if candles is not None:
                result[tf_name] = candles
            else:
                logger.warning("Could not fetch candles for TF=%s", tf_name)
        return result

    def get_current_price(self, symbol: str) -> float:
        """Return latest ask price (used as M1 entry for long/short)."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0.0
        return float(tick.ask)

    def get_spread(self, symbol: str) -> int:
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            return 9999
        return round((tick.ask - tick.bid) / info.point)

    # ── Positions ─────────────────────────────────────────────────────────────
    def get_open_positions(self, symbol: str = None, magic: int = None):
        positions = mt5.positions_get(symbol=symbol) or []
        if magic is not None:
            positions = [p for p in positions if p.magic == magic]
        return list(positions)

    # ── Orders ────────────────────────────────────────────────────────────────
    def send_order(self, request: dict):
        return mt5.order_send(request)

    def close_position(self, position, comment: str = "bot_close"):
        tick     = mt5.symbol_info_tick(position.symbol)
        sym_info = mt5.symbol_info(position.symbol)
        if not tick or not sym_info:
            logger.error("Cannot close position %d — no tick/info", position.ticket)
            return None
        if position.type == mt5.ORDER_TYPE_BUY:
            price      = tick.bid
            order_type = mt5.ORDER_TYPE_SELL
        else:
            price      = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
        request = {
            "action"      : mt5.TRADE_ACTION_DEAL,
            "symbol"      : position.symbol,
            "volume"      : position.volume,
            "type"        : order_type,
            "position"    : position.ticket,
            "price"       : price,
            "deviation"   : 10,
            "magic"       : position.magic,
            "comment"     : comment,
            "type_time"   : mt5.ORDER_TIME_GTC,
            "type_filling": sym_info.filling_mode,
        }
        return mt5.order_send(request)
