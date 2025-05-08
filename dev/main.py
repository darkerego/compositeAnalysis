import argparse
import ccxt
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
import pandas as pd
import numpy as np
import talib


def fetch_data(client: ccxt.Exchange, ticker: str, interval: str, lookback: int):
    klines = client.fetch_ohlcv(ticker, interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['OpenTime', 'Open', 'High', 'Low', 'Close', 'Volume'])
    df['OpenTime'] = pd.to_datetime(df['OpenTime'], unit='ms')
    df[['Open', 'High', 'Low', 'Close']] = df[['Open', 'High', 'Low', 'Close']].astype(float)
    df['DateNum'] = mdates.date2num(df['OpenTime'])
    return df


def generate_composite_index(base_df, quote_df):
    composite_df = base_df.copy()
    composite_df['Composite'] = base_df['Close'] / quote_df['Close']
    composite_df['High'] = base_df['High'] / quote_df['High']
    composite_df['Low'] = base_df['Low'] / quote_df['Low']
    composite_df['Open'] = base_df['Open'] / quote_df['Open']
    return composite_df


def plot_signals(base_df, quote_df, composite_df, base, quote):
    plt.style.use('dark_background')
    composite_df['EMA'] = talib.EMA(composite_df['Composite'], timeperiod=14)
    composite_df['SAR'] = talib.SAR(composite_df['High'], composite_df['Low'], acceleration=0.02, maximum=0.2)
    macd, macdsignal, macdhist = talib.MACD(composite_df['Composite'], fastperiod=12, slowperiod=26, signalperiod=9)
    composite_df['MACD'] = macd
    composite_df['MACDsignal'] = macdsignal

    macd_cross = (macd < macdhist)

    bullish = (composite_df['Composite'] > composite_df['EMA']) & macd_cross
    bearish = (composite_df['Composite'] < composite_df['EMA']) & (~macd_cross)

    composite_df['BuySignal'] = np.nan
    composite_df['SellSignal'] = np.nan

    last_signal = None
    for i in range(len(composite_df)):
        if bullish.iloc[i] and composite_df['Composite'].iloc[i] > composite_df['SAR'].iloc[i]:
            if last_signal != 'buy':
                composite_df.at[composite_df.index[i], 'BuySignal'] = composite_df['Composite'].iloc[i]
                last_signal = 'buy'
        elif bearish.iloc[i] and composite_df['Composite'].iloc[i] < composite_df['SAR'].iloc[i]:
            if last_signal != 'sell':
                composite_df.at[composite_df.index[i], 'SellSignal'] = composite_df['Composite'].iloc[i]
                last_signal = 'sell'

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(16, 12), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})

    candlestick_ohlc(ax1, base_df[['DateNum', 'Open', 'High', 'Low', 'Close']].values, width=0.0005, colorup='lime', colordown='red', alpha=0.5)
    ax1.plot(composite_df['DateNum'], composite_df['EMA'], label='EMA (14)', linewidth=1, color='yellow')
    ax1.scatter(composite_df['DateNum'], composite_df['BuySignal'], label='Buy Signal', marker='^', color='green', s=100)
    ax1.scatter(composite_df['DateNum'], composite_df['SellSignal'], label='Sell Signal', marker='v', color='red', s=100)

    ax2.plot(composite_df['DateNum'], composite_df['MACD'], label='MACD', color='cyan')
    ax2.plot(composite_df['DateNum'], composite_df['MACDsignal'], label='MACD Signal', color='magenta')
    ax2.bar(composite_df['DateNum'], macdhist, label='MACD Histogram', color='grey', alpha=0.3)

    ax3.plot(composite_df['DateNum'], composite_df['SAR'], label='Parabolic SAR', linestyle=':', linewidth=1, color='orange')

    ax1.set_title(f'{base} / {quote} Composite Index with Trading Signals')
    ax3.set_xlabel('Time')
    ax1.set_ylabel('Composite Index')
    ax2.set_ylabel('MACD')
    ax3.set_ylabel('SAR')

    ax1.legend()
    ax2.legend()
    ax3.legend()

    ax1.grid(True, linestyle='--', alpha=0.5)
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax3.grid(True, linestyle='--', alpha=0.5)

    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()


def main():
    parser = argparse.ArgumentParser(description='Composite Index Chart Generator')
    parser.add_argument('--base', required=True, help='Base asset ticker (e.g., BTC/USDT)')
    parser.add_argument('--quote', required=True, help='Quote asset ticker (e.g., ETH/USDT)')
    parser.add_argument('--interval', default='1h', help='Interval for candlesticks (default: 1h)')
    parser.add_argument('--lookback', default=100, type=int, help='Number of candles to fetch (default: 100)')

    args = parser.parse_args()

    client = ccxt.binance()

    base_df = fetch_data(client, args.base, args.interval, args.lookback)
    quote_df = fetch_data(client, args.quote, args.interval, args.lookback)

    composite_df = generate_composite_index(base_df, quote_df)

    plot_signals(base_df, quote_df, composite_df, args.base, args.quote)


if __name__ == '__main__':
    main()
