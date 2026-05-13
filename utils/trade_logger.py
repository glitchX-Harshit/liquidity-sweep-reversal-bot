"""
utils/trade_logger.py
CSV + in-memory trade log.  Now stores source_tf and rr per trade.
"""

import csv
import logging
import os
from datetime import datetime
from typing import List, Dict

logger = logging.getLogger(__name__)

FIELDS = [
    "ticket", "open_time", "close_time", "direction", "lots",
    "entry", "sl", "tp", "close_px", "pnl", "result",
    "source_tf", "rr", "description",
]


class TradeLogger:

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._records: Dict[int, dict] = {}
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        if not os.path.exists(csv_path):
            with open(csv_path, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=FIELDS).writeheader()

    def log_open(self, ticket, direction, lots, entry, sl, tp,
                 source_tf, rr, description):
        rec = {
            "ticket"     : ticket,
            "open_time"  : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "close_time" : "",
            "direction"  : direction,
            "lots"       : lots,
            "entry"      : entry,
            "sl"         : sl,
            "tp"         : tp,
            "close_px"   : "",
            "pnl"        : "",
            "result"     : "OPEN",
            "source_tf"  : source_tf,
            "rr"         : rr,
            "description": description,
        }
        self._records[ticket] = rec
        with open(self.csv_path, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(
                {k: rec.get(k, "") for k in FIELDS}
            )
        logger.info("[LOG] OPEN  ticket=%d  %s  TF=%s  RR=1:%.1f  entry=%.2f",
                    ticket, direction, source_tf, rr, entry)

    def log_close(self, ticket, close_px, pnl, result):
        if ticket not in self._records:
            logger.warning("log_close: unknown ticket %d", ticket)
            return
        rec = self._records[ticket]
        rec.update(close_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   close_px=close_px, pnl=round(pnl, 2), result=result)
        self._rewrite()
        emoji = "✅" if result == "WIN" else "❌"
        logger.info("[LOG] CLOSE %s ticket=%d  pnl=%.2f", emoji, ticket, pnl)

    def get_open_records(self) -> List[dict]:
        return [r for r in self._records.values() if r["result"] == "OPEN"]

    def print_summary(self):
        closed = [r for r in self._records.values() if r["result"] != "OPEN"]
        if not closed:
            logger.info("No closed trades."); return
        wins   = [r for r in closed if r["result"] == "WIN"]
        losses = [r for r in closed if r["result"] == "LOSS"]
        pnl    = sum(float(r["pnl"]) for r in closed if r["pnl"] != "")
        wr     = len(wins) / len(closed) * 100 if closed else 0
        # Per-TF breakdown
        tf_stats = {}
        for r in closed:
            tf = r.get("source_tf", "?")
            if tf not in tf_stats:
                tf_stats[tf] = {"w": 0, "l": 0, "pnl": 0.0}
            tf_stats[tf]["pnl"] += float(r["pnl"]) if r["pnl"] != "" else 0
            if r["result"] == "WIN":  tf_stats[tf]["w"] += 1
            else:                     tf_stats[tf]["l"] += 1
        logger.info("=" * 55)
        logger.info("TRADE SUMMARY")
        logger.info("  Total : %d  |  Wins: %d  |  Losses: %d", len(closed), len(wins), len(losses))
        logger.info("  Win Rate: %.1f%%  |  Total PnL: $%.2f", wr, pnl)
        logger.info("  Per-Timeframe breakdown:")
        for tf, s in sorted(tf_stats.items()):
            total_tf = s["w"] + s["l"]
            wr_tf    = s["w"] / total_tf * 100 if total_tf else 0
            logger.info("    %s: %d trades  WR=%.0f%%  PnL=$%.2f", tf, total_tf, wr_tf, s["pnl"])
        logger.info("=" * 55)

    def _rewrite(self):
        with open(self.csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for rec in self._records.values():
                w.writerow({k: rec.get(k, "") for k in FIELDS})
