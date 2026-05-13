import os
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class ReportGenerator:
    def __init__(self):
        self.output_dir = "reports"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_html(self, metrics: dict, config, trades_df: pd.DataFrame = None, start_date=None, end_date=None):
        html_content = f"""
        <html>
        <head>
            <title>Backtest Report - {config.SYMBOL}</title>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; padding: 20px; }}
                h1, h2 {{ color: #00ffcc; }}
                .metric-box {{ background-color: #1e1e1e; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: inline-block; width: 20%; margin-right: 1%; }}
                .metric-title {{ font-size: 14px; color: #aaaaaa; }}
                .metric-value {{ font-size: 24px; font-weight: bold; margin-top: 5px; }}
                .positive {{ color: #00ff00; }}
                .negative {{ color: #ff0000; }}
                .container {{ display: flex; flex-wrap: wrap; }}
                .chart-container {{ margin-top: 30px; }}
                img {{ max-width: 100%; border: 1px solid #333; border-radius: 8px; }}
                .heatmap {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; margin-bottom: 30px; }}
                .heatmap-day {{ width: 30px; height: 30px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; cursor: pointer; }}
                .day-profit {{ background-color: #2e7d32; }}
                .day-loss {{ background-color: #c62828; }}
                .day-neutral {{ background-color: #333333; }}
            </style>
        </head>
        <body>
            <h1>Backtest Report: {config.SYMBOL}</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <h2>Key Metrics</h2>
            <div class="container">
                <div class="metric-box">
                    <div class="metric-title">Total Return</div>
                    <div class="metric-value {'positive' if metrics.get('total_return', 0) >= 0 else 'negative'}">{metrics.get('total_return', 0)*100:.2f}%</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Win Rate</div>
                    <div class="metric-value">{metrics.get('winrate', 0)*100:.1f}%</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Profit Factor</div>
                    <div class="metric-value">{metrics.get('profit_factor', 0):.2f}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Max Drawdown</div>
                    <div class="metric-value negative">{metrics.get('max_drawdown', 0)*100:.2f}%</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Total Trades</div>
                    <div class="metric-value">{metrics.get('total_trades', 0)}</div>
                </div>
                <div class="metric-box">
                    <div class="metric-title">Sharpe Ratio</div>
                    <div class="metric-value">{metrics.get('sharpe_ratio', 0):.2f}</div>
                </div>
            </div>
            
            {self._generate_heatmap_html(trades_df, start_date, end_date)}
            
            <h2>Visualizations</h2>
            <div class="chart-container">
                <img src="equity_drawdown.png" alt="Equity & Drawdown">
            </div>
            <div class="chart-container" style="display: flex; gap: 20px; flex-wrap: wrap;">
                <div style="width: 48%;"><img src="monthly_returns.png" alt="Monthly Returns"></div>
                <div style="width: 48%;"><img src="win_loss_dist.png" alt="Win/Loss Distribution"></div>
                <div style="width: 48%;"><img src="pnl_by_tf.png" alt="PnL by Timeframe"></div>
            </div>
        </body>
        </html>
        """
        
        report_path = os.path.join(self.output_dir, "backtest_report.html")
        with open(report_path, "w") as f:
            f.write(html_content)
        
        logger.info(f"HTML report generated: {report_path}")

    def _generate_heatmap_html(self, trades_df, start_date, end_date):
        if trades_df is None or start_date is None or end_date is None:
            return ""
            
        heatmap_html = "<h2>Daily PnL Heatmap</h2>\n<div class='heatmap'>\n"
        
        daily_pnl = {}
        if not trades_df.empty:
            df = trades_df.copy()
            df['close_date'] = pd.to_datetime(df['close_time']).dt.date
            daily_pnl = df.groupby('close_date')['pnl'].sum().to_dict()
            
        curr_date = start_date.date()
        end_d = end_date.date()
        
        while curr_date <= end_d:
            pnl = daily_pnl.get(curr_date, 0.0)
            css_class = "day-neutral"
            if pnl > 0:
                css_class = "day-profit"
            elif pnl < 0:
                css_class = "day-loss"
            
            title = f"{curr_date.strftime('%Y-%m-%d')}: ${pnl:.2f}"
            day_str = str(curr_date.day)
            heatmap_html += f"<div class='heatmap-day {css_class}' title='{title}'>{day_str}</div>\n"
            
            curr_date += timedelta(days=1)
            
        heatmap_html += "</div>\n"
        return heatmap_html

    def export_trade_logs(self, trades_df: pd.DataFrame):
        csv_path = os.path.join(self.output_dir, "trades.csv")
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Trade logs exported to {csv_path}")

    def generate_pdf(self):
        # Placeholder for PDF generation
        # Typically requires wkhtmltopdf and pdfkit which might not be installed.
        # Informing user that PDF can be printed from HTML.
        logger.info("PDF generation requires external dependencies (wkhtmltopdf). Please open the HTML report and 'Print to PDF'.")
