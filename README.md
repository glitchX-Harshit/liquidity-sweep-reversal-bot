# XAUUSD Multi-Timeframe Liquidity Sweep Reversal Bot

## Strategy — How It Works

Every M1 candle close triggers sweep detection across **5 timeframes simultaneously**:

| Analysis TF | Lookback | RR   | Priority |
|-------------|----------|------|----------|
| M1          | 40 bars  | 1:1.5 | 1 (lowest) |
| M5          | 30 bars  | 1:2  | 2 |
| M15         | 25 bars  | 1:3  | 3 |
| H1          | 20 bars  | 1:4  | 4 |
| H4          | 15 bars  | 1:5  | 5 (highest) |

**Entry is always on M1 price** — regardless of which TF generated the signal.
**If multiple TFs sweep simultaneously, the highest TF (H4 > H1 > M15 > M5 > M1) wins.**

## Max Open Trades = 2

- If 2 trades are already open, the bot **stops all analysis** until one closes (win or loss).
- This prevents over-exposure and respects the 2-position cap strictly.

## Setup

```bash
pip install -r requirements.txt
```

Edit `config.py`:
```python
MT5_LOGIN    = 123456789
MT5_PASSWORD = "your_password"
MT5_SERVER   = "YourBroker-Live"
```

## Historical Backtesting Engine

The bot includes a full-featured local historical backtesting pipeline. It reuses the exact same logic as the live bot to ensure consistency between simulation and execution.

### Key Features:
- **Event-Driven Simulation**: Replays market candle-by-candle (M1).
- **Realistic Execution**: Simulates spread, slippage, and TP/SL hits intra-bar.
- **No Lookahead Bias**: Strictly enforces that only closed candles from higher TFs are used.
- **Quant Analytics**: Generates detailed metrics (Sharpe, Drawdown, Profit Factor, etc.).
- **Visual Reporting**: Produces an HTML report with equity curves, monthly returns, and trade distributions.

### How to Run:
```bash
# Run a 1-year backtest with visualizations and HTML report
python backtest.py --years 1 --visualize --export-report

# Options:
# --years [N]      : Set historical period (default: 1)
# --visualize      : Generate charts (PNGs) in reports/
# --export-report  : Generate HTML report and trade CSV in reports/
```

## Project Structure

```
xauusd_sweep_bot/
├── bot.py                  # Main live runner (M1 clock, MTF analysis)
├── backtest.py             # CLI entry for the backtesting engine
├── config.py               # All settings (MTF_CONFIG, credentials, risk params)
├── requirements.txt
├── backtesting/            # Backtesting Engine Modules
│   ├── historical_data.py  # MT5 data downloader and cache manager
│   ├── backtester.py       # Event-driven simulation engine
│   ├── execution_engine.py # Realistic trade execution simulation
│   ├── metrics.py          # Quant stats (Sharpe, MaxDD, Winrate)
│   ├── visualizer.py       # Matplotlib chart generation
│   └── report_generator.py # HTML and CSV report exports
├── core/
│   ├── mt5_connector.py    # MT5 API wrapper + multi-TF candle fetcher
│   ├── sweep_detector.py   # MultiTFSweepDetector — shared by live/backtest
│   ├── risk_manager.py     # Lot sizing, daily loss, spread, 2-trade gate
│   └── trade_executor.py   # Order placement + position monitoring
├── utils/
│   ├── trade_logger.py     # CSV log with source_tf and rr per trade
│   └── logger_setup.py     # Rotating file logger
├── data/                   # Cached historical CSVs
├── reports/                # Backtest results and charts
└── logs/                   # Live trading logs
```

## Notes
- MT5 Python API is **Windows only**
- Enable algo trading in MT5: Tools → Options → Expert Advisors → Allow algorithmic trading
- Some brokers use `GOLD` instead of `XAUUSD` — change `SYMBOL` in config.py
