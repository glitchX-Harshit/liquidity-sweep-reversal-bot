import argparse
import logging
import sys
import os
from datetime import datetime, timedelta

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

def run_backtest(start_date: datetime, end_date: datetime, visualize: bool, export_report: bool, timeframes: list, rr_overrides: list, risk_override: float, sweep_buffer: int, max_trades: int):
    logger.info("=" * 60)
    logger.info(f"  Historical Backtesting Engine - {config.SYMBOL}")
    logger.info(f"  Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    if timeframes:
        logger.info(f"  Target Timeframes: {', '.join(timeframes)}")
    
    if risk_override is not None:
        config.RISK_PERCENT = risk_override
        logger.info(f"  Override Risk: {risk_override}% per trade")
        
    if sweep_buffer is not None:
        config.SWEEP_BUFFER_PIPS = sweep_buffer
        logger.info(f"  Override Sweep Buffer: {sweep_buffer} pips")
        
    if max_trades is not None:
        config.MAX_TRADES_PER_DAY = max_trades
        logger.info(f"  Override Max Trades/Day: {max_trades}")
        
    if rr_overrides:
        if len(rr_overrides) == 1 and "=" not in rr_overrides[0]:
            global_rr = float(rr_overrides[0])
            for tf in config.MTF_CONFIG:
                config.MTF_CONFIG[tf]["rr"] = global_rr
            logger.info(f"  Override RR: {global_rr} (All timeframes)")
        else:
            override_str = []
            for item in rr_overrides:
                if "=" in item:
                    tf, val = item.split("=")
                    if tf in config.MTF_CONFIG:
                        config.MTF_CONFIG[tf]["rr"] = float(val)
                        override_str.append(f"{tf}={val}")
            if override_str:
                logger.info(f"  Override RR: {', '.join(override_str)}")
                
    logger.info("=" * 60)

    if timeframes:
        config.ANALYSIS_TIMEFRAMES = timeframes

    # 1. Load or fetch data
    data_handler = DataHandler(config)
    
    # Try loading first
    data_dict = data_handler.load_data(start_date, end_date)
    if not data_dict:
        logger.info("Local data not found or incomplete. Fetching from MT5...")
        if data_handler.fetch_mt5_history(start_date, end_date):
            data_dict = data_handler.load_data(start_date, end_date)
        else:
            logger.error("Failed to fetch historical data. Make sure MT5 is running.")
            sys.exit(1)
            
    if not data_dict:
        logger.error("Data loading failed. No data available.")
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
        report_gen.generate_html(metrics, config, trades_df=trades_df, start_date=start_date, end_date=end_date)
        report_gen.generate_pdf() # Will output placeholder message

    logger.info("Backtesting pipeline finished successfully.")

def main():
    parser = argparse.ArgumentParser(description="Historical Backtesting Engine")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD). If omitted, defaults to 1 year ago.")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD). Defaults to today.")
    parser.add_argument("--years", type=int, default=1, help="Legacy: Years of history (used if dates omitted)")
    parser.add_argument("--visualize", action="store_true", help="Generate quant-style charts (PNGs)")
    parser.add_argument("--export-report", action="store_true", help="Generate HTML report and trade CSV")
    parser.add_argument("--timeframes", nargs='+', help="Specific timeframes to analyze (e.g. H1 H4)")
    parser.add_argument("--rr", nargs='+', help="Override RR. Format: 3.0 (all) OR M1=2.0 H1=3.0 (specific)")
    parser.add_argument("--risk", type=float, help="Override risk percentage per trade (e.g., 2.0 for 2%)")
    parser.add_argument("--sweep-buffer", type=int, help="Override SWEEP_BUFFER_PIPS (e.g., 1 or 2)")
    parser.add_argument("--max-trades", type=int, help="Maximum number of trades to execute per day")
    
    args = parser.parse_args()
    
    if args.end_date:
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
    else:
        end_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
    if args.start_date:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    else:
        start_date = end_date - timedelta(days=365 * args.years)
        
    run_backtest(start_date, end_date, args.visualize, args.export_report, args.timeframes, args.rr, args.risk, args.sweep_buffer, args.max_trades)

if __name__ == "__main__":
    main()
