"""
core/trade_executor.py
Executes and monitors trades.  Supports up to MAX_OPEN_TRADES=2 concurrent positions.
Each position is tagged by source_tf so the log shows which TF generated the signal.
"""

import logging
import MetaTrader5 as mt5
from core.sweep_detector import SweepSignal

logger = logging.getLogger(__name__)


class TradeExecutor:

    def __init__(self, config, connector, risk_manager, trade_logger):
        self.cfg   = config
        self.conn  = connector
        self.risk  = risk_manager
        self.tlog  = trade_logger

    # ── Open a trade ──────────────────────────────────────────────────────────
    def execute(self, signal: SweepSignal) -> bool:
        if not self.risk.can_open_trade():
            return False

        lots    = self.risk.calculate_lot_size(signal.entry_price, signal.stop_loss)
        comment = f"sweep_{signal.source_tf}_{signal.sweep_type[:3]}"
        request = self.risk.build_order_request(
            direction   = signal.direction,
            stop_loss   = signal.stop_loss,
            take_profit = signal.take_profit,
            lots        = lots,
            comment     = comment,
        )
        if not request:
            return False

        logger.info(
            "ORDER: %s  tf=%s  rr=1:%.1f  entry=%.2f  SL=%.2f  TP=%.2f  lots=%.2f",
            signal.direction, signal.source_tf, signal.rr,
            request["price"], signal.stop_loss, signal.take_profit, lots,
        )

        result = self.conn.send_order(request)
        if result is None:
            logger.error("order_send returned None: %s", mt5.last_error())
            return False
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error("Order rejected: retcode=%d", result.retcode)
            return False

        logger.info("FILLED: ticket=%d  price=%.2f  lots=%.2f",
                    result.order, result.price, result.volume)

        self.tlog.log_open(
            ticket     = result.order,
            direction  = signal.direction,
            lots       = result.volume,
            entry      = result.price,
            sl         = signal.stop_loss,
            tp         = signal.take_profit,
            source_tf  = signal.source_tf,
            rr         = signal.rr,
            description= signal.description,
        )
        return True

    # ── Monitor open positions ────────────────────────────────────────────────
    def monitor_positions(self):
        """
        Detect positions that the broker closed via SL or TP and log the result.
        MT5 handles SL/TP natively — we just detect the disappearance.
        """
        open_tickets = {
            p.ticket
            for p in self.conn.get_open_positions(
                symbol=self.cfg.SYMBOL, magic=self.cfg.MAGIC_NUMBER
            )
        }
        for record in self.tlog.get_open_records():
            if record["ticket"] not in open_tickets:
                self._handle_closed(record)

    def _handle_closed(self, record: dict):
        deals = mt5.history_deals_get(position=record["ticket"])
        if not deals:
            logger.warning("No deal history for ticket %d", record["ticket"])
            return
        close_deals = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
        if not close_deals:
            return
        d      = close_deals[-1]
        pnl    = d.profit + d.commission + d.swap
        result = "WIN" if pnl > 0 else "LOSS"
        logger.info("CLOSED ticket=%d  %s  close=%.2f  pnl=%.2f",
                    record["ticket"], result, d.price, pnl)
        self.tlog.log_close(
            ticket   = record["ticket"],
            close_px = d.price,
            pnl      = pnl,
            result   = result,
        )

    # ── Emergency close all ───────────────────────────────────────────────────
    def close_all_positions(self, reason: str = "shutdown"):
        for pos in self.conn.get_open_positions(
            symbol=self.cfg.SYMBOL, magic=self.cfg.MAGIC_NUMBER
        ):
            r = self.conn.close_position(pos, comment=reason)
            if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info("Closed ticket=%d (%s)", pos.ticket, reason)
            else:
                logger.error("Failed to close ticket=%d", pos.ticket)
