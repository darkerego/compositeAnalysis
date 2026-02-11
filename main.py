#!/usr/bin/env python3
import argparse
import time

import pandas as pd

import talib as ta
import mplfinance as mpf
import matplotlib.pyplot as plt
import numpy as np
from ccxt import binance
#from ccxt.base.types import Market


#class Kraken(kraken):
#    def parse_ohlcv(self, ohlcv, market: Market = None) -> list:


class Binance(binance):
    def parse_ohlcv(self, ohlcv, market=None):
        return [
            self.safe_integer(ohlcv, 0),
            self.safe_number(ohlcv, 1),
            self.safe_number(ohlcv, 2),
            self.safe_number(ohlcv, 3),
            self.safe_number(ohlcv, 4),
            self.safe_number(ohlcv, 5),
            self.safe_number(ohlcv, 6),
            self.safe_number(ohlcv, 7),
            self.safe_number(ohlcv, 8),
            self.safe_number(ohlcv, 9),
            self.safe_number(ohlcv, 10),
        ]


class CompositeGenerator:
    def __init__(self):
        self.exchange = Binance()
        self.exchange.load_markets()  # Critical – loads and validates all symbols

    def fetch_klines(self, symbol: str, interval: str = '1h', lookback: int = 100):
        pd.set_option('future.no_silent_downcasting', True)
        klines = self.exchange.fetch_ohlcv(symbol, interval, limit=lookback)
        if not klines:
            raise ValueError(f"No OHLCV data returned for {symbol} {interval}. Check symbol/interval availability.")
        # assert(len(klines) > 0)
        df = pd.DataFrame(klines, columns=[
            'Open Time', 'Open', 'High', 'Low', 'Close', 'Volume',
            'Close Time', 'Quote Asset Volume', 'Number of Trades',
            'Taker Buy Base Asset Volume', 'Taker Buy Quote Asset Volume'
        ])
        df['Open Time'] = pd.to_datetime(df['Open Time'], unit='ms')
        df.set_index('Open Time', inplace=True)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = df[col].astype(float)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def generate_chart(self, base_ticker, quote_ticker, interval, lookback):
        base_df = self.fetch_klines(base_ticker, interval, lookback)
        quote_df = self.fetch_klines(quote_ticker, interval, lookback)

        base_symbol, base_quote = base_ticker.split('/')
        quote_symbol, quote_quote = quote_ticker.split('/')

        merged_df = pd.merge(
            base_df,
            quote_df,
            left_index=True,
            right_index=True,
            suffixes=(f'_{base_symbol}', f'_{quote_symbol}')
        )

        ratio_df = pd.DataFrame(index=merged_df.index)
        ratio_df['Open'] = merged_df[f'Open_{base_symbol}'] / merged_df[f'Open_{quote_symbol}']
        ratio_df['High'] = merged_df[f'High_{base_symbol}'] / merged_df[f'High_{quote_symbol}']
        ratio_df['Low'] = merged_df[f'Low_{base_symbol}'] / merged_df[f'Low_{quote_symbol}']
        ratio_df['Close'] = merged_df[f'Close_{base_symbol}'] / merged_df[f'Close_{quote_symbol}']
        ratio_df['Volume'] = (merged_df[f'Volume_{base_symbol}'] + merged_df[f'Volume_{quote_symbol}']) / 2

        ratio_df['SAR'] = ta.SAR(ratio_df['High'], ratio_df['Low'])

        macd, macdsignal, macdhist = ta.MACD(
            ratio_df['Close'],
            fastperiod=12,
            slowperiod=26,
            signalperiod=9
        )


        ratio_df['MACD'] = macd
        ratio_df['MACD_Signal'] = macdsignal
        ratio_df['MACD_Hist'] = macdhist
        bullish_macd = macdhist > 0

        # macd_cross = macd < macdhist

        ratio_df['EMA'] = ta.EMA(ratio_df['Close'], timeperiod=14)
        ratio_df['EMA_Signal'] = ratio_df['Close'] > ratio_df['EMA']
        ratio_df['SAR_Signal'] = ratio_df['Close'] > ratio_df['SAR']

        ratio_df['Bullish_Signal'] = (
                ratio_df['SAR_Signal'] & ratio_df['EMA_Signal'] & bullish_macd
        )

        ratio_df['Bearish_Signal'] = (
                (~ratio_df['SAR_Signal']) & (~ratio_df['EMA_Signal']) & (~bullish_macd)
        )

        ratio_df['Entry'] = ratio_df['Bullish_Signal'] & ~ratio_df['Bullish_Signal'].shift(1).fillna(False)
        ratio_df['Exit'] = ratio_df['Bearish_Signal'] & ~ratio_df['Bearish_Signal'].shift(1).fillna(False)

        # =========================
        # 🔥 FIX: VERTICAL PLACEMENT
        # =========================
        #price_range = ratio_df['High'] - ratio_df['Low']
        #offset = price_range * 0.003
        overall_range = ratio_df['High'].max() - ratio_df['Low'].min()
        offset = overall_range * 0.02  # 2% of total visible range – adjust 0.01–0.03 if needed

        entry_plot = np.where(
            ratio_df['Entry'],
            ratio_df['Low'] - offset,
            np.nan
        )

        exit_plot = np.where(
            ratio_df['Exit'],
            ratio_df['High'] + offset,
            np.nan
        )

        apdict = [
            mpf.make_addplot(ratio_df['EMA'], color='blue', panel=0, ylabel='Price Ratio'),
            mpf.make_addplot(ratio_df['SAR'], color='white', scatter=True, markersize=30, marker='o', panel=0),

            # Brighter colors + larger markers for dark theme
            mpf.make_addplot(entry_plot, type='scatter', color='lime', markersize=200, marker='^', panel=0),
            mpf.make_addplot(exit_plot, type='scatter', color='crimson', markersize=200, marker='v', panel=0),

            mpf.make_addplot(ratio_df['MACD'], panel=2, color='yellow', ylabel='MACD'),
            mpf.make_addplot(ratio_df['MACD_Signal'], panel=2, color='orange'),
            mpf.make_addplot(ratio_df['MACD_Hist'], panel=2, type='bar', color='purple')
        ]

        fig, axes = mpf.plot(
            ratio_df,
            type='candle',
            title=f'{base_ticker}:{quote_ticker} Composite Candles @ {interval}',
            ylabel='Price',
            style='binancedark',
            ylabel_lower='Volume',
            figratio=(14, 7),
            figscale=1.2,
            tight_layout=False,
            addplot=apdict,
            volume=True,
            panel_ratios=(3, 1, 1),
            returnfig=True
        )

        axes[0].legend(
            handles=[
                plt.Line2D([0], [0], color='blue', label='EMA(14)'),
                plt.Line2D([0], [0], color='white', marker='o', linestyle='None', markersize=10, label='SAR'),
                plt.Line2D([0], [0], color='lime', marker='^', linestyle='None', markersize=5, label='Entry'),
                plt.Line2D([0], [0], color='crimson', marker='v', linestyle='None', markersize=5, label='Exit'),
                plt.Line2D([0], [0], color='yellow', label='MACD'),
                plt.Line2D([0], [0], color='orange', label='MACD Signal'),
                plt.Line2D([0], [0], color='purple', label='MACD Histogram')
            ],
            loc='upper left',  # Better placement to avoid overlapping price
            fontsize='medium',
            frameon=True,
            fancybox=True
        )

        plt.savefig(f'images/{base_symbol}{base_quote}_{quote_symbol}{quote_quote}_{int(time.time())}.png')
        plt.show()


def main():
    parser = argparse.ArgumentParser(description='Composite Index Chart Generator')
    parser.add_argument('--base', required=True, help='Base asset ticker (e.g., ETH/USDT)')
    parser.add_argument('--quote', required=True, help='Quote asset ticker (e.g., BTC/USDT)')
    parser.add_argument('--interval', default='1h')
    parser.add_argument('--lookback', default=100, type=int)
    args = parser.parse_args()

    CompositeGenerator().generate_chart(
        args.base.upper(),
        args.quote.upper(),
        args.interval,
        args.lookback
    )


if __name__ == '__main__':
    main()
