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
        
    def _get_closed_candles(self, tf_name, current_time_m1_close):
        """
        Returns an array of candles that have fully closed by current_time_m1_close.
        """
        arr = self.data_dict[tf_name]
        tf_duration = TF_DURATIONS[tf_name]
        
        # A candle is closed if its open time + its duration <= current M1 close time
        # Example: M5 opens at 12:00, duration 300s. Closes at 12:05.
        # If current M1 closed at 12:05, M5 is closed.
        closed_mask = (arr['time'] + tf_duration) <= current_time_m1_close
        
        return arr[closed_mask]

    def _get_tf_candles_dict(self, m1_close_time):
        """Builds the dictionary of np arrays expected by sweep_detector"""
        tf_candles = {}
        for tf_name in self.config.ANALYSIS_TIMEFRAMES:
            if tf_name not in self.data_dict: continue
            
            closed = self._get_closed_candles(tf_name, m1_close_time)
            
            # The detector expects lookback + a few extra bars.
            lookback = self.config.MTF_CONFIG[tf_name]["lookback"]
            if len(closed) > 0:
                tf_candles[tf_name] = closed[-(lookback+5):] # Get enough historical candles
                
        return tf_candles

    def run(self):
        if "M1" not in self.data_dict:
            logger.error("M1 data is required for backtesting simulation.")
            return pd.DataFrame()
            
        m1_data = self.data_dict["M1"]
        total_candles = len(m1_data)
        logger.info(f"Starting backtest over {total_candles} M1 candles...")
        
        for i in range(total_candles):
            current_m1 = m1_data[i]
            m1_open_time = current_m1['time']
            m1_close_time = m1_open_time + 60
            
            current_price = float(current_m1['close']) # Use M1 close as current price for the tick
            
            # Monitor open positions for SL/TP hits using current M1 candle (intra-bar simulation)
            # High/Low of M1 are used to check if SL/TP hit during this minute
            for pos in self.positions[:]:
                outcome = self.execution_engine.simulate_tp_sl(pos, current_m1)
                if outcome:
                    self._close_position(pos, outcome, current_m1)
            
            # Check if we can open new positions
            if len(self.positions) >= self.config.MAX_OPEN_TRADES:
                continue
                
            # Construct multi-tf context without lookahead bias
            tf_candles = self._get_tf_candles_dict(m1_close_time)
            
            # Multi-TF Sweep analysis
            signal = self.detector.analyse(tf_candles, current_price)
            if signal:
                actual_entry = self.execution_engine.simulate_execution(
                    signal, 
                    current_m1, 
                    self.use_spread, 
                    self.use_slippage
                )
                
                if actual_entry is not None:
                    # Calculate position size (simplified risk based on distance)
                    sl_dist = abs(actual_entry - signal.stop_loss)
                    if sl_dist > 0:
                        risk_amount = self.balance * (self.config.RISK_PERCENT / 100)
                        # Assume 1 standard lot = 100,000 units. XAUUSD 1 pip = $0.10 for 0.01 lot.
                        # Wait, standard MT5 lot calculation:
                        # 1 lot XAUUSD = 100 oz. 1 point ($0.01) move = $1.
                        # Risk Amount = Volume * ContractSize * SL_Points * PointValue
                        # Simplified: 
                        volume = risk_amount / (sl_dist * 100) # Assuming contract size 100
                        volume = max(self.config.MIN_LOT, min(self.config.MAX_LOT, round(volume, 2)))
                        
                        self.positions.append({
                            'id': len(self.trades_history) + len(self.positions) + 1,
                            'entry_time': m1_close_time,
                            'direction': signal.direction,
                            'source_tf': signal.source_tf,
                            'entry': actual_entry,
                            'sl': signal.stop_loss,
                            'tp': signal.take_profit,
                            'rr': signal.rr,
                            'volume': volume,
                            'spread': current_m1['spread']
                        })
                        # logger.debug(f"Opened {signal.direction} on {signal.source_tf} at {actual_entry}")

            if i % 50000 == 0 and i > 0:
                logger.info(f"Processed {i}/{total_candles} candles... Balance: ${self.balance:.2f}")

        # Close any remaining open positions at the end of the data
        if len(self.positions) > 0:
            last_m1 = m1_data[-1]
            for pos in self.positions[:]:
                self._close_position(pos, 'END_OF_DATA', last_m1)
                
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
