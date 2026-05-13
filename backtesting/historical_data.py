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

    def _get_filename(self, tf_name: str, start_date: datetime, end_date: datetime) -> str:
        s_str = start_date.strftime('%Y%m%d')
        e_str = end_date.strftime('%Y%m%d')
        return os.path.join(self.data_dir, f"{self.config.SYMBOL}_{tf_name}_{s_str}_{e_str}.csv")

    def fetch_mt5_history(self, start_date: datetime, end_date: datetime):
        """Connects to MT5 and downloads data if CSV does not exist."""
        if not mt5.initialize(
            path=self.config.MT5_PATH,
            login=self.config.MT5_LOGIN,
            password=self.config.MT5_PASSWORD,
            server=self.config.MT5_SERVER,
        ):
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        logger.info(f"Fetching historical data from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        for tf_name, tf_val in self.tf_map.items():
            filename = self._get_filename(tf_name, start_date, end_date)
            if os.path.exists(filename):
                logger.info(f"Data for {tf_name} already exists. Skipping download.")
                continue
            
            logger.info(f"Downloading {tf_name} data in batches...")
            
            all_rates = []
            current_end = end_date

            while current_end > start_date:
                # Fetch up to 90,000 bars ending at current_end
                rates = mt5.copy_rates_from(self.config.SYMBOL, tf_val, current_end, 90000)
                if rates is None or len(rates) == 0:
                    logger.warning(f"Stopped fetching {tf_name} early. MT5 Error: {mt5.last_error()}")
                    break
                    
                df_batch = pd.DataFrame(rates)
                df_batch['time_dt'] = pd.to_datetime(df_batch['time'], unit='s')
                
                # Filter the batch strictly between start_date and current_end
                mask = (df_batch['time_dt'] >= start_date) & (df_batch['time_dt'] < current_end)
                df_filtered = df_batch[mask]
                
                if not df_filtered.empty:
                    all_rates.append(df_filtered)
                
                # Update current_end to the oldest time fetched in this batch
                oldest_time = pd.to_datetime(rates[0]['time'], unit='s')
                
                # If we aren't moving backwards (e.g., reached start of broker history), break
                if oldest_time >= current_end:
                    break
                    
                current_end = oldest_time

            if not all_rates:
                logger.error(f"Failed to download data for {tf_name}. Ensure MT5 has history available.")
                continue
                
            # Combine all batches, sort chronologically, and drop duplicates
            df = pd.concat(all_rates).sort_values('time').drop_duplicates(subset='time').reset_index(drop=True)
            df.drop(columns=['time_dt'], inplace=True)
            
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.to_csv(filename, index=False)
            logger.info(f"Saved {tf_name} ({len(df)} candles) to {filename}")

        mt5.shutdown()
        return True

    def load_data(self, start_date: datetime, end_date: datetime) -> dict:
        """Loads data from CSVs and returns a dict of numpy structured arrays."""
        data_dict = {}
        for tf_name in self.tf_map.keys():
            filename = self._get_filename(tf_name, start_date, end_date)
            if not os.path.exists(filename):
                logger.warning(f"File not found: {filename}. Missing {tf_name} data.")
                continue
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
