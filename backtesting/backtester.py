import logging
import pandas as pd
import numpy as np
from datetime import datetime
from core.sweep_detector import MultiTFSweepDetector
from core.risk_manager import RiskManager
from backtesting.execution_engine import ExecutionEngine
import config

logger = logging.getLogger(__name__)

TF_DURATIONS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "H1": 3600,
    "H4": 14400
}

class Backtester:
    def __init__(self, data_dict, initial_balance=10000.0, use_spread=True, use_slippage=True):
        self.data_dict = data_dict
        self.balance = initial_balance
        self.use_spread = use_spread
        self.use_slippage = use_slippage
        
        # Override config risk manager for backtest
        self.config = config
        self.detector = MultiTFSweepDetector(self.config)
        self.execution_engine = ExecutionEngine(self.config)
        
        self.positions = []
        self.trades_history = []
        
    def _get_closed_candles(self, tf_name, current_time_close):
        """
        Returns an array of candles that have fully closed by current_time_close.
        Optimized with an internal pointer to avoid O(N^2) searching.
        """
        if not hasattr(self, 'tf_pointers'):
            self.tf_pointers = {tf: 0 for tf in self.config.ANALYSIS_TIMEFRAMES}
            
        arr = self.data_dict[tf_name]
        tf_duration = TF_DURATIONS[tf_name]
        idx = self.tf_pointers[tf_name]
        
        while idx < len(arr) and (arr[idx]['time'] + tf_duration) <= current_time_close:
            idx += 1
            
        self.tf_pointers[tf_name] = idx
        return arr[:idx]

    def _get_tf_candles_dict(self, current_time_close):
        """Builds the dictionary of np arrays expected by sweep_detector"""
        tf_candles = {}
        for tf_name in self.config.ANALYSIS_TIMEFRAMES:
            if tf_name not in self.data_dict: continue
            
            closed = self._get_closed_candles(tf_name, current_time_close)
            
            # The detector expects lookback + a few extra bars.
            lookback = self.config.MTF_CONFIG[tf_name]["lookback"]
            if len(closed) > 0:
                tf_candles[tf_name] = closed[-(lookback+5):] # Get enough historical candles
                
        return tf_candles

    def run(self):
        if "M1" not in self.data_dict:
            logger.error("M1 data is missing. It is strictly required for highly-accurate tick-level backtesting simulation.")
            return pd.DataFrame()
            
        base_tf = "M1"
        base_data = self.data_dict[base_tf]
        base_duration = TF_DURATIONS[base_tf]
        total_candles = len(base_data)
        logger.info(f"Starting backtest over {total_candles} {base_tf} candles...")
        
        current_day = None
        trades_today = 0
        
        for i in range(total_candles):
            current_base = base_data[i]
            base_open_time = current_base['time']
            base_close_time = base_open_time + base_duration
            
            # Date tracking for max trades per day limit
            current_date = datetime.utcfromtimestamp(base_open_time).date()
            if current_day != current_date:
                current_day = current_date
                trades_today = 0
            
            current_price = float(current_base['close'])
            
            # Monitor open positions for SL/TP hits using current base candle (intra-bar simulation)
            for pos in self.positions[:]:
                outcome = self.execution_engine.simulate_tp_sl(pos, current_base)
                if outcome:
                    self._close_position(pos, outcome, current_base)
            
            # Check if we can open new positions
            if len(self.positions) >= self.config.MAX_OPEN_TRADES:
                continue
                
            if self.config.MAX_TRADES_PER_DAY is not None and trades_today >= self.config.MAX_TRADES_PER_DAY:
                continue
                
            # Construct multi-tf context without lookahead bias
            tf_candles = self._get_tf_candles_dict(base_close_time)
            
            # Multi-TF Sweep analysis
            signal = self.detector.analyse(tf_candles, current_price)
            if signal:
                actual_entry = self.execution_engine.simulate_execution(
                    signal, 
                    current_base, 
                    self.use_spread, 
                    self.use_slippage
                )
                
                if actual_entry is not None:
                    sl_dist = abs(actual_entry - signal.stop_loss)
                    if sl_dist > 0:
                        risk_amount = self.balance * (self.config.RISK_PERCENT / 100)
                        volume = risk_amount / (sl_dist * 100)
                        volume = max(self.config.MIN_LOT, min(self.config.MAX_LOT, round(volume, 2)))
                        
                        self.positions.append({
                            'id': len(self.trades_history) + len(self.positions) + 1,
                            'entry_time': base_close_time,
                            'direction': signal.direction,
                            'source_tf': signal.source_tf,
                            'entry': actual_entry,
                            'sl': signal.stop_loss,
                            'tp': signal.take_profit,
                            'rr': signal.rr,
                            'volume': volume,
                            'spread': current_base['spread']
                        })
                        trades_today += 1

            if i % 50000 == 0 and i > 0:
                logger.info(f"Processed {i}/{total_candles} candles... Balance: ${self.balance:.2f}")

        # Close any remaining open positions at the end of the data
        if len(self.positions) > 0:
            last_base = base_data[-1]
            for pos in self.positions[:]:
                self._close_position(pos, 'END_OF_DATA', last_base)
                
        logger.info(f"Backtest completed. Final Balance: ${self.balance:.2f}")
        return pd.DataFrame(self.trades_history)

    def _get_session(self, timestamp_s):
        dt = datetime.utcfromtimestamp(timestamp_s)
        hour = dt.hour
        if 8 <= hour < 13: return 'London'
        elif 13 <= hour < 17: return 'London/NY Overlap'
        elif 17 <= hour < 22: return 'New York'
        else: return 'Asian'

    def _close_position(self, pos, reason, current_candle):
        if reason == 'SL':
            close_price = pos['sl']
        elif reason == 'TP':
            close_price = pos['tp']
        else:
            close_price = float(current_candle['close'])
            
        # PnL Calculation
        if pos['direction'] == 'LONG':
            pnl = (close_price - pos['entry']) * pos['volume'] * 100 # XAUUSD standard contract
        else:
            pnl = (pos['entry'] - close_price) * pos['volume'] * 100
            
        self.balance += pnl
        
        self.trades_history.append({
            'timestamp': datetime.utcfromtimestamp(pos['entry_time']).strftime('%Y-%m-%d %H:%M:%S'),
            'close_time': datetime.utcfromtimestamp(current_candle['time']).strftime('%Y-%m-%d %H:%M:%S'),
            'direction': pos['direction'],
            'source_tf': pos['source_tf'],
            'entry': pos['entry'],
            'stop_loss': pos['sl'],
            'take_profit': pos['tp'],
            'rr': pos['rr'],
            'pnl': pnl,
            'balance': self.balance,
            'session': self._get_session(pos['entry_time']),
            'spread': pos['spread'],
            'trade_duration': (current_candle['time'] - pos['entry_time']) / 60.0 # in minutes
        })
        
        self.positions.remove(pos)
