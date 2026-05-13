import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

class Visualizer:
    def __init__(self):
        self.output_dir = "reports"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Quant style
        plt.style.use('dark_background')
        self.colors = {
            'primary': '#00ffcc',
            'secondary': '#ff00ff',
            'win': '#00ff00',
            'loss': '#ff0000',
            'drawdown': '#ff3333'
        }

    def generate_all(self, trades_df: pd.DataFrame):
        if trades_df.empty:
            logger.warning("No trades to visualize.")
            return

        trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
        
        self.plot_equity_drawdown(trades_df)
        self.plot_monthly_returns(trades_df)
        self.plot_pnl_by_timeframe(trades_df)
        self.plot_win_loss_distribution(trades_df)
        
        logger.info("Visualizations saved to reports/")

    def plot_equity_drawdown(self, df):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
        
        # Equity Curve
        ax1.plot(df['timestamp'], df['balance'], color=self.colors['primary'], linewidth=2)
        ax1.set_title("Equity Curve", fontsize=14, color='white')
        ax1.set_ylabel("Balance ($)", fontsize=12)
        ax1.grid(color='#333333', linestyle='--', linewidth=0.5)
        
        # Drawdown
        df['peak'] = df['balance'].cummax()
        df['drawdown'] = (df['balance'] - df['peak']) / df['peak'] * 100
        
        ax2.fill_between(df['timestamp'], df['drawdown'], 0, color=self.colors['drawdown'], alpha=0.5)
        ax2.plot(df['timestamp'], df['drawdown'], color=self.colors['drawdown'], linewidth=1)
        ax2.set_title("Drawdown (%)", fontsize=12, color='white')
        ax2.set_ylabel("Drawdown %", fontsize=10)
        ax2.grid(color='#333333', linestyle='--', linewidth=0.5)
        
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        fig.autofmt_xdate()
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "equity_drawdown.png"), dpi=150)
        plt.close()

    def plot_monthly_returns(self, df):
        df_copy = df.copy()
        df_copy['month'] = df_copy['timestamp'].dt.to_period('M')
        monthly_pnl = df_copy.groupby('month')['pnl'].sum()
        
        fig, ax = plt.subplots(figsize=(10, 5))
        colors = [self.colors['win'] if val >= 0 else self.colors['loss'] for val in monthly_pnl.values]
        
        monthly_pnl.plot(kind='bar', ax=ax, color=colors)
        ax.set_title("Monthly PnL", fontsize=14)
        ax.set_ylabel("PnL ($)")
        ax.grid(color='#333333', linestyle='--', linewidth=0.5, axis='y')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "monthly_returns.png"), dpi=150)
        plt.close()

    def plot_pnl_by_timeframe(self, df):
        if 'source_tf' not in df.columns: return
        
        pnl_tf = df.groupby('source_tf')['pnl'].sum()
        
        fig, ax = plt.subplots(figsize=(8, 5))
        colors = [self.colors['win'] if val >= 0 else self.colors['loss'] for val in pnl_tf.values]
        
        pnl_tf.plot(kind='bar', ax=ax, color=colors)
        ax.set_title("PnL by Timeframe", fontsize=14)
        ax.set_ylabel("PnL ($)")
        ax.grid(color='#333333', linestyle='--', linewidth=0.5, axis='y')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "pnl_by_tf.png"), dpi=150)
        plt.close()

    def plot_win_loss_distribution(self, df):
        wins = df[df['pnl'] > 0]['pnl']
        losses = df[df['pnl'] <= 0]['pnl']
        
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.hist(wins, bins=20, color=self.colors['win'], alpha=0.7, label='Wins')
        ax.hist(losses, bins=20, color=self.colors['loss'], alpha=0.7, label='Losses')
        
        ax.set_title("Trade PnL Distribution", fontsize=14)
        ax.set_xlabel("PnL ($)")
        ax.set_ylabel("Frequency")
        ax.legend()
        ax.grid(color='#333333', linestyle='--', linewidth=0.5)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "win_loss_dist.png"), dpi=150)
        plt.close()
