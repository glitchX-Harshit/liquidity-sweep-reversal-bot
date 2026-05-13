import MetaTrader5 as mt5
import config

def main():
    if not mt5.initialize(
        path=config.MT5_PATH,
        login=config.MT5_LOGIN,
        password=config.MT5_PASSWORD,
        server=config.MT5_SERVER,
    ):
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return

    for count in [99999, 90000, 80000, 70000, 60000]:
        print(f"Testing M1 pos {count}...")
        rates_m1_pos = mt5.copy_rates_from_pos(config.SYMBOL, mt5.TIMEFRAME_M1, 0, count)
        if rates_m1_pos is None:
            print(f"Failed: {mt5.last_error()}")
        else:
            print(f"Success: {len(rates_m1_pos)} bars")
            break

    mt5.shutdown()

if __name__ == '__main__':
    main()
