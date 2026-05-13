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

## Run

```bash
python bot.py              # Live
python bot.py --dry-run    # Paper trade
python bot.py --summary    # Show stats
```

## Tuning Sweeps (config.py)

```python
SWEEP_BUFFER_PIPS  = 1     # 1 pip = catches even tiny sweeps
MIN_SWEEP_WICK_PCT = 0.25  # 25% wick minimum (very relaxed)
REJECTION_BODY_PCT = 0.60  # up to 60% body allowed
```

## Project Structure

```
xauusd_sweep_bot/
├── bot.py                  # Main loop (M1 clock, MTF analysis, 2-trade gate)
├── config.py               # All settings — MTF_CONFIG, credentials, risk params
├── requirements.txt
├── core/
│   ├── mt5_connector.py    # MT5 API wrapper + multi-TF candle fetcher
│   ├── sweep_detector.py   # MultiTFSweepDetector — scans M1/M5/M15/H1/H4
│   ├── risk_manager.py     # Lot sizing, daily loss, spread, 2-trade gate
│   └── trade_executor.py   # Order placement + position monitoring
└── utils/
    ├── trade_logger.py     # CSV log with source_tf and rr per trade
    └── logger_setup.py     # Rotating file logger
```

## Notes
- MT5 Python API is **Windows only**
- Enable algo trading in MT5: Tools → Options → Expert Advisors → Allow algorithmic trading
- Some brokers use `GOLD` instead of `XAUUSD` — change `SYMBOL` in config.py
