import os
import pandas as pd
import numpy as np
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class DataHandler:
    def __init__(self, config):
        self.config = config
        self.data_dir = "data"
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        self.tf_map = config.TF_MAP

    def _get_filename(self, tf_name: str, years: int) -> str:
        return os.path.join(self.data_dir, f"{self.config.SYMBOL}_{tf_name}_{years}Y.csv")

    def fetch_mt5_history(self, years: int):
        """Connects to MT5 and downloads data if CSV does not exist."""
        if not mt5.initialize(
            path=self.config.MT5_PATH,
            login=self.config.MT5_LOGIN,
            password=self.config.MT5_PASSWORD,
            server=self.config.MT5_SERVER,
        ):
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=365 * years)

        logger.info(f"Fetching historical data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        for tf_name, tf_val in self.tf_map.items():
            filename = self._get_filename(tf_name, years)
            if os.path.exists(filename):
                logger.info(f"Data for {tf_name} already exists. Skipping download.")
                continue
            
            logger.info(f"Downloading {tf_name} data...")
            rates = mt5.copy_rates_range(self.config.SYMBOL, tf_val, start_date, end_date)
            if rates is None or len(rates) == 0:
                logger.error(f"Failed to download data for {tf_name}")
                continue
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.to_csv(filename, index=False)
            logger.info(f"Saved {tf_name} to {filename}")

        mt5.shutdown()
        return True

    def load_data(self, years: int) -> dict:
        """Loads data from CSVs and returns a dict of numpy structured arrays."""
        data_dict = {}
        for tf_name in self.tf_map.keys():
            filename = self._get_filename(tf_name, years)
            if not os.path.exists(filename):
                logger.error(f"File not found: {filename}. Run fetch_mt5_history first.")
                return None
            df = pd.read_csv(filename)
            df['time'] = pd.to_datetime(df['time']).astype('int64') // 10**9 # Convert back to unix timestamp
            
            # Create a structured array exactly like MT5 returns
            dtype = [('time', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'), 
                     ('close', 'f8'), ('tick_volume', 'i8'), ('spread', 'i4'), ('real_volume', 'i8')]
            
            arr = np.zeros(len(df), dtype=dtype)
            arr['time'] = df['time']
            arr['open'] = df['open']
            arr['high'] = df['high']
            arr['low'] = df['low']
            arr['close'] = df['close']
            arr['tick_volume'] = df['tick_volume']
            arr['spread'] = df['spread']
            arr['real_volume'] = df['real_volume']
            
            data_dict[tf_name] = arr
            
        return data_dict
