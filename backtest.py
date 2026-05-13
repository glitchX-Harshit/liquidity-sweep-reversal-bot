import argparse
import logging
import sys
import os

from utils.logger_setup import setup_logging
import config
from backtesting.historical_data import DataHandler
from backtesting.backtester import Backtester
from backtesting.metrics import MetricsCalculator
from backtesting.visualizer import Visualizer
from backtesting.report_generator import ReportGenerator

# Ensure logs and data dirs exist
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)
os.makedirs("reports", exist_ok=True)

setup_logging(log_dir=config.LOG_DIR, level=config.LOG_LEVEL)
logger = logging.getLogger("backtest.main")

def run_backtest(years: int, visualize: bool, export_report: bool):
    logger.info("=" * 60)
    logger.info(f"  Historical Backtesting Engine - {config.SYMBOL}")
    logger.info(f"  Period: {years} Year(s)")
    logger.info("=" * 60)

    # 1. Load or fetch data
    data_handler = DataHandler(config)
    
    # Try loading first
    data_dict = data_handler.load_data(years)
    if data_dict is None:
        logger.info("Local data not found or incomplete. Fetching from MT5...")
        if data_handler.fetch_mt5_history(years):
            data_dict = data_handler.load_data(years)
        else:
            logger.error("Failed to fetch historical data. Make sure MT5 is running.")
            sys.exit(1)
            
    if not data_dict or "M1" not in data_dict:
        logger.error("Data loading failed.")
        sys.exit(1)

    # 2. Run simulation
    logger.info("Initializing Backtester...")
    initial_balance = 10000.0
    backtester = Backtester(data_dict, initial_balance=initial_balance, use_spread=True, use_slippage=True)
    trades_df = backtester.run()
    
    if trades_df.empty:
        logger.warning("No trades were executed during the backtest.")
        sys.exit(0)
        
    logger.info(f"Backtest completed. Total trades: {len(trades_df)}")

    # 3. Calculate metrics
    metrics_calc = MetricsCalculator()
    metrics = metrics_calc.calculate(trades_df, initial_balance)
    
    logger.info("--- Performance Summary ---")
    logger.info(f"Total Return : {metrics.get('total_return', 0)*100:.2f}%")
    logger.info(f"Win Rate     : {metrics.get('winrate', 0)*100:.2f}%")
    logger.info(f"Max Drawdown : {metrics.get('max_drawdown', 0)*100:.2f}%")
    logger.info(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
    logger.info(f"Sharpe Ratio : {metrics.get('sharpe_ratio', 0):.2f}")
    
    report_gen = ReportGenerator()
    
    if export_report or visualize:
        report_gen.export_trade_logs(trades_df)

    # 4. Visualizations
    if visualize:
        logger.info("Generating visualizations...")
        vis = Visualizer()
        vis.generate_all(trades_df)
        
    # 5. Reports
    if export_report:
        logger.info("Generating reports...")
        report_gen.generate_html(metrics, config)
        report_gen.generate_pdf() # Will output placeholder message

    logger.info("Backtesting pipeline finished successfully.")

def main():
    parser = argparse.ArgumentParser(description="Historical Backtesting Engine")
    parser.add_argument("--years", type=int, default=1, help="Years of historical data to backtest (default 1)")
    parser.add_argument("--visualize", action="store_true", help="Generate quant-style charts (PNGs)")
    parser.add_argument("--export-report", action="store_true", help="Generate HTML report and trade CSV")
    
    args = parser.parse_args()
    
    run_backtest(args.years, args.visualize, args.export_report)

if __name__ == "__main__":
    main()
