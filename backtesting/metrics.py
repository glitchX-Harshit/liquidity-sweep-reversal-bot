import pandas as pd
import numpy as np

class MetricsCalculator:
    def __init__(self):
        pass

    def calculate(self, trades_df: pd.DataFrame, initial_balance: float):
        if trades_df.empty:
            return {}

        trades_df['pnl'] = trades_df['pnl'].astype(float)
        trades_df['balance'] = trades_df['balance'].astype(float)
        
        total_trades = len(trades_df)
        winning_trades = trades_df[trades_df['pnl'] > 0]
        losing_trades = trades_df[trades_df['pnl'] < 0]
        
        winrate = len(winning_trades) / total_trades if total_trades > 0 else 0
        
        gross_profit = winning_trades['pnl'].sum()
        gross_loss = abs(losing_trades['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
        
        avg_win = winning_trades['pnl'].mean() if not winning_trades.empty else 0
        avg_loss = abs(losing_trades['pnl'].mean()) if not losing_trades.empty else 0
        expectancy = (winrate * avg_win) - ((1 - winrate) * avg_loss)
        
        # Drawdown
        trades_df['peak'] = trades_df['balance'].cummax()
        trades_df['drawdown'] = (trades_df['peak'] - trades_df['balance']) / trades_df['peak']
        max_drawdown = trades_df['drawdown'].max()
        
        # Total Return
        final_balance = trades_df['balance'].iloc[-1]
        total_return = (final_balance - initial_balance) / initial_balance
        
        # Risk Ratios (Simplified annualized, assuming trades_df is sorted by time)
        # Assuming ~252 trading days per year
        if len(trades_df) > 1:
            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            days = (trades_df['timestamp'].iloc[-1] - trades_df['timestamp'].iloc[0]).days
            years = days / 365.25 if days > 0 else 1
            if years == 0: years = 1
        else:
            years = 1

        returns = trades_df['pnl'] / initial_balance # Simplified trade-by-trade return
        mean_return = returns.mean()
        std_return = returns.std()
        
        sharpe_ratio = (mean_return / std_return) * np.sqrt(total_trades / years) if std_return > 0 else 0
        
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std()
        sortino_ratio = (mean_return / downside_std) * np.sqrt(total_trades / years) if downside_std > 0 else 0
        
        annualized_return = (1 + total_return) ** (1 / years) - 1
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else 0
        
        avg_rr = trades_df['rr'].astype(float).mean() if 'rr' in trades_df else 0

        # Consecutive losses
        is_loss = trades_df['pnl'] < 0
        consecutive_losses = is_loss.groupby((~is_loss).cumsum()).sum().max()

        # PnL by timeframe
        pnl_by_timeframe = trades_df.groupby('source_tf')['pnl'].sum().to_dict() if 'source_tf' in trades_df else {}
        
        # PnL by session
        pnl_by_session = trades_df.groupby('session')['pnl'].sum().to_dict() if 'session' in trades_df else {}
        
        return {
            'total_trades': total_trades,
            'total_return': total_return,
            'winrate': winrate,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'avg_rr': avg_rr,
            'consecutive_losses': consecutive_losses,
            'pnl_by_timeframe': pnl_by_timeframe,
            'pnl_by_session': pnl_by_session,
            'final_balance': final_balance
        }
