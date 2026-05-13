"""
bot.py
XAUUSD Multi-Timeframe Liquidity Sweep Reversal Bot — main runner.

LOGIC SUMMARY
─────────────
• Entry timeframe   : M1 (candle close every 60 seconds)
• Analysis TFs      : M1, M5, M15, H1, H4
• Per-TF lookback   : M1=40, M5=30, M15=25, H1=20, H4=15
• Per-TF RR         : M1=1:1.5, M5=1:2, M15=1:3, H1=1:4, H4=1:5
• Max open trades   : 2  — analysis PAUSED when 2 trades are open
• On every M1 close : fetch all TF candles, scan all TFs for sweeps,
                      take the highest-priority (highest TF) signal found,
                      enter at current M1 price.

Usage:
  python bot.py               # Live trading
  python bot.py --dry-run     # Paper mode — signals logged, no orders
  python bot.py --summary     # Print trade summary from CSV and exit
"""

import sys
import time
import signal
import logging
import argparse
from datetime import datetime

import config
from utils.logger_setup  import setup_logging
from utils.trade_logger  import TradeLogger
from core.mt5_connector  import MT5Connector
from core.sweep_detector import MultiTFSweepDetector
from core.risk_manager   import RiskManager
from core.trade_executor import TradeExecutor

setup_logging(log_dir=config.LOG_DIR, level=config.LOG_LEVEL)
logger = logging.getLogger("bot.main")

# ── Graceful shutdown ─────────────────────────────────────────────────────────
_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    logger.info("Shutdown signal (%s) received — finishing current loop…", sig)
    _shutdown = True

signal.signal(signal.SIGINT,  _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── Timing: wait for next M1 close ───────────────────────────────────────────
def _sleep_to_next_m1():
    """
    Sleep until 2 seconds after the next M1 candle close.
    Checks _shutdown flag every second so Ctrl+C is responsive.
    """
    M1 = 60
    now  = time.time()
    wait = M1 - (now % M1) + 2.0
    deadline = now + wait
    while time.time() < deadline and not _shutdown:
        time.sleep(1.0)


# ── Banner ────────────────────────────────────────────────────────────────────
def _banner(acc: dict, dry_run: bool):
    mode = "DRY-RUN" if dry_run else "LIVE"
    active_tfs = ", ".join(config.ANALYSIS_TIMEFRAMES)
    logger.info("=" * 60)
    logger.info("  XAUUSD Multi-Timeframe Sweep Reversal Bot  [%s]", mode)
    logger.info("  Account : %s  (%s)", acc.get("login"), acc.get("name"))
    logger.info("  Balance : %.2f %s", acc.get("balance", 0), acc.get("currency", ""))
    logger.info("  Entry TF: M1   |   Analysis TFs: %s", active_tfs)
    logger.info("  TF Rules:")
    for tf in config.ANALYSIS_TIMEFRAMES:
        if tf in config.MTF_CONFIG:
            cfg_tf = config.MTF_CONFIG[tf]
            logger.info("    %-4s  lookback=%-3d  rr=1:%.1f  priority=%d",
                        tf, cfg_tf["lookback"], cfg_tf["rr"], cfg_tf["priority"])
    logger.info("  Max open trades : %d", config.MAX_OPEN_TRADES)
    logger.info("  Max trades/day  : %s", config.MAX_TRADES_PER_DAY)
    logger.info("  Risk per trade  : %.1f%%", config.RISK_PERCENT)
    logger.info("  Daily loss limit: %.1f%%", config.MAX_DAILY_LOSS_PCT)
    logger.info("=" * 60)


# ── Main loop ─────────────────────────────────────────────────────────────────
def run(dry_run: bool = False):
    trade_log = TradeLogger(config.TRADE_LOG_CSV)

    with MT5Connector(config) as conn:
        acc = conn.get_account_info()
        if not acc:
            logger.error("Failed to get account info. Exiting.")
            sys.exit(1)

        _banner(acc, dry_run)

        detector = MultiTFSweepDetector(config)
        risk_mgr = RiskManager(config, conn)
        executor = TradeExecutor(config, conn, risk_mgr, trade_log)

        logger.info("Bot started. Waiting for first M1 candle close…")

        while not _shutdown:
            # ── 1. Wait for M1 candle close ───────────────────────────────────
            _sleep_to_next_m1()
            if _shutdown:
                break

            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            logger.info("── M1 tick @ %s UTC ──────────────────────────────────", ts)

            # ── 2. Monitor existing positions (detect broker-closed SL/TP) ───
            executor.monitor_positions()

            # ── 3. Gate: if 2 trades already open, skip analysis ─────────────
            open_count = risk_mgr.open_trade_count()
            if open_count >= config.MAX_OPEN_TRADES:
                logger.info(
                    "Trades open: %d/%d — skipping analysis until one closes.",
                    open_count, config.MAX_OPEN_TRADES,
                )
                continue

            # ── 4. Fetch all TF candles in one pass ───────────────────────────
            tf_candles = conn.get_all_tf_candles(
                symbol     = config.SYMBOL,
                tf_map     = config.TF_MAP,
                mtf_config = config.MTF_CONFIG,
            )
            if not tf_candles:
                logger.warning("No candle data received — skipping.")
                continue

            # ── 5. Get current M1 price (entry price) ─────────────────────────
            m1_price = conn.get_current_price(config.SYMBOL)
            if m1_price <= 0:
                logger.warning("Invalid M1 price %.2f — skipping.", m1_price)
                continue

            m1_close = float(tf_candles["M1"][-1]["close"]) if "M1" in tf_candles else m1_price
            logger.info("M1 close=%.2f  current=%.2f  open_trades=%d/%d",
                        m1_close, m1_price, open_count, config.MAX_OPEN_TRADES)

            # ── 6. Multi-TF sweep analysis ────────────────────────────────────
            signal = detector.analyse(tf_candles, m1_price)

            if signal is None:
                active_tfs_str = "/".join(config.ANALYSIS_TIMEFRAMES)
                logger.info(f"No sweep signal across {active_tfs_str}. Watching…")
                continue

            logger.info(
                "SIGNAL [%s] %s  swept=%.2f  entry=%.2f  SL=%.2f  TP=%.2f  RR=1:%.1f",
                signal.source_tf, signal.direction, signal.swept_level,
                signal.entry_price, signal.stop_loss, signal.take_profit, signal.rr,
            )
            logger.info("  → %s", signal.description)

            # ── 7. Execute or dry-run ─────────────────────────────────────────
            if dry_run:
                logger.info("[DRY-RUN] Would enter %s on M1 — no order sent.", signal.direction)
                continue

            ok = executor.execute(signal)
            if ok:
                logger.info("Trade opened. Open trades: %d/%d",
                            risk_mgr.open_trade_count(), config.MAX_OPEN_TRADES)
            else:
                logger.warning("Trade skipped or rejected by broker.")

        # ── Clean shutdown ────────────────────────────────────────────────────
        logger.info("Shutting down — closing all open positions…")
        executor.close_all_positions(reason="bot_shutdown")
        trade_log.print_summary()
        logger.info("Bot stopped cleanly.")


def execute_debug_trade(direction: str):
    from core.sweep_detector import SweepSignal
    trade_log = TradeLogger(config.TRADE_LOG_CSV)
    with MT5Connector(config) as conn:
        acc = conn.get_account_info()
        if not acc:
            logger.error("Failed to get account info. Exiting.")
            sys.exit(1)
        
        m1_price = conn.get_current_price(config.SYMBOL)
        if m1_price <= 0:
            logger.error("Invalid M1 price %.2f — cannot execute debug trade.", m1_price)
            sys.exit(1)

        sl_dist = 2.0
        sl = m1_price - sl_dist if direction == "LONG" else m1_price + sl_dist
        tp = m1_price + (sl_dist * 2) if direction == "LONG" else m1_price - (sl_dist * 2)

        signal = SweepSignal(
            direction=direction,
            sweep_type="debug_buy" if direction == "LONG" else "debug_sell",
            source_tf="DEBUG",
            rr=2.0,
            priority=99,
            swept_level=m1_price,
            entry_price=m1_price,
            stop_loss=round(sl, 2),
            take_profit=round(tp, 2),
            wick_pct=0.5,
            body_pct=0.5,
            description=f"[DEBUG] Executing {direction} at current market price {m1_price:.2f}"
        )

        risk_mgr = RiskManager(config, conn)
        executor = TradeExecutor(config, conn, risk_mgr, trade_log)
        
        logger.info("Executing debug %s order at %.2f", direction, m1_price)
        ok = executor.execute(signal)
        if ok:
            logger.info("Debug trade opened successfully.")
        else:
            logger.warning("Debug trade failed.")



# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="XAUUSD MTF Sweep Reversal Bot")
    ap.add_argument("--dry-run", action="store_true", help="Paper trade — no real orders")
    ap.add_argument("--summary", action="store_true", help="Print trade summary and exit")
    ap.add_argument("--buy_current", action="store_true", help="Execute a BUY order at current market price and exit")
    ap.add_argument("--sell_current", action="store_true", help="Execute a SELL order at current market price and exit")
    args = ap.parse_args()

    if args.summary:
        TradeLogger(config.TRADE_LOG_CSV).print_summary()
        return

    if args.buy_current:
        execute_debug_trade("LONG")
        return
        
    if args.sell_current:
        execute_debug_trade("SHORT")
        return

    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
