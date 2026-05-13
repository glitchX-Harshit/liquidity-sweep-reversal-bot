import logging

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self, config):
        self.config = config
        self.pip = 0.10 # Assuming XAUUSD
        
    def simulate_execution(self, signal, current_m1_candle, is_spread_enabled=True, is_slippage_enabled=True):
        """
        Simulates entering a trade based on the signal and the current M1 candle.
        Returns the actual entry price or None if rejected.
        """
        spread = current_m1_candle['spread'] * 0.001 if is_spread_enabled else 0.0 # Assuming spread is in points, point is 0.001 for XAUUSD? MT5 usually uses 0.01 for XAUUSD points, let's assume raw spread in points. 1 point = 0.01 for XAUUSD.
        # Actually in config MAX_SPREAD_POINTS = 35. So spread is in points. 1 point = 0.01
        
        point = 0.01 # standard for XAUUSD
        spread_val = current_m1_candle['spread'] * point if is_spread_enabled else 0.0
        slippage_val = self.config.SLIPPAGE * point if is_slippage_enabled else 0.0
        
        if is_spread_enabled and current_m1_candle['spread'] > self.config.MAX_SPREAD_POINTS:
            # logger.debug(f"Trade rejected due to high spread: {current_m1_candle['spread']}")
            return None
            
        entry_price = float(current_m1_candle['close']) # Market order at close of signal candle
        
        if signal.direction == 'LONG':
            actual_entry = entry_price + spread_val + slippage_val
        else:
            actual_entry = entry_price - slippage_val # bid price usually, but since close is usually bid, spread is added for ask (buy)
            # wait, if close is bid:
            # BUY entry = ask = bid + spread. slippage usually worsens it. So actual_entry = close + spread_val + slippage_val
            # SELL entry = bid = close. actual_entry = close - slippage_val
        
        return actual_entry
    
    def simulate_tp_sl(self, position, current_candle):
        """
        Checks if the current candle hits TP or SL for a given position.
        position is a dict: {'direction': 'LONG'/'SHORT', 'entry': float, 'sl': float, 'tp': float, 'status': 'OPEN'}
        Returns 'TP', 'SL', or None
        """
        high = float(current_candle['high'])
        low = float(current_candle['low'])
        
        if position['direction'] == 'LONG':
            if low <= position['sl']:
                return 'SL'
            if high >= position['tp']:
                return 'TP'
        elif position['direction'] == 'SHORT':
            if high >= position['sl']:
                return 'SL'
            if low <= position['tp']:
                return 'TP'
                
        return None
