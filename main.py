#!/usr/bin/env python3
import argparse
import time

import pandas as pd
import ccxt
import talib as ta
import mplfinance as mpf
import matplotlib.pyplot as plt

class Binance(ccxt.binance):
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
    def __init__(self, use_evm: bool = False):
        """Create generator.

        Parameters
        ----------
        use_evm: bool
            If True, market data will be fetched from an EVM chain via the
            Moralis API instead of Binance.
        """
        self.use_evm = use_evm
        if not self.use_evm:
            # Only initialize the Binance exchange when needed to avoid
            # requiring ccxt configuration for on-chain usage.
            self.exchange = Binance()

    def fetch_klines(self, symbol: str, interval: str = '1h', lookback: int = 100):
        """Fetch OHLCV data from the configured data source."""
        pd.set_option('future.no_silent_downcasting', True)
        if self.use_evm:
            return self.fetch_evm_klines(symbol, interval, lookback)
        klines = self.exchange.fetch_ohlcv(symbol, interval, limit=lookback)
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

    def fetch_evm_klines(self, ticker: str, interval: str, lookback: int):
        """Retrieve OHLCV data for an on-chain pair using Moralis."""
        # Import lazily to keep Binance-only usage lightweight.
        from moralis_oclh import MoralisApi

        chain, tokens = ticker.split(':', 1)
        token0, token1 = tokens.split('/')

        pair_address = MoralisApi.get_pair_address(token0, token1, chain=chain, time_period=interval)
        klines = MoralisApi.get_klines(chain, interval, lookback, pair_address)

        df = pd.DataFrame(klines)
        # Moralis returns timestamps in milliseconds under the `timestamp` key.
        df['Open Time'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('Open Time', inplace=True)
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume',
        }, inplace=True)
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
            else:
                df[col] = 0.0
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def _extract_symbol_parts(self, ticker: str):
        """Return sanitized symbol and quote components for labeling."""
        if self.use_evm:
            sym = ticker.replace(':', '_').replace('/', '_')
            return sym, ''
        symbol = ticker.split('/')[0]
        quote = ticker.split('/')[1]
        return symbol, quote

    def generate_chart(self, base_ticker, quote_ticker, interval, lookback):
        base_df = self.fetch_klines(base_ticker, interval, lookback)
        quote_df = self.fetch_klines(quote_ticker, interval, lookback)

        base_symbol, base_quote = self._extract_symbol_parts(base_ticker)
        quote_symbol, quote_quote = self._extract_symbol_parts(quote_ticker)

        merged_df = pd.merge(base_df, quote_df, left_index=True, right_index=True,
                             suffixes=(f'_{base_symbol}', f'_{quote_symbol}'))

        ratio_df = pd.DataFrame(index=merged_df.index)
        ratio_df['Open'] = merged_df[f'Open_{base_symbol}'] / merged_df[f'Open_{quote_symbol}']
        ratio_df['High'] = merged_df[[f'High_{base_symbol}', f'High_{quote_symbol}']].apply(lambda row: row.iloc[0] / row.iloc[1], axis=1)
        ratio_df['Low'] = merged_df[[f'Low_{base_symbol}', f'Low_{quote_symbol}']].apply(lambda row: row.iloc[0] / row.iloc[1], axis=1)
        ratio_df['Close'] = merged_df[f'Close_{base_symbol}'] / merged_df[f'Close_{quote_symbol}']
        ratio_df['Volume'] = (merged_df[f'Volume_{base_symbol}'] + merged_df[f'Volume_{quote_symbol}']) / 2

        ratio_df['SAR'] = ta.SAR(ratio_df['High'], ratio_df['Low'])
        macd, macdsignal, macdhist = ta.MACD(merged_df[f'Close_{base_symbol}'], fastperiod=12, slowperiod=26, signalperiod=9)
        ratio_df['MACD'] = macd
        ratio_df['MACD_Signal'] = macdsignal
        ratio_df['MACD_Hist'] = macdhist
        macd_cross = (macd < macdhist)

        ratio_df['EMA'] = ta.EMA(ratio_df['Close'], timeperiod=14)
        ratio_df['EMA_Signal'] = ratio_df['Close'] > ratio_df['EMA']
        ratio_df['SAR_Signal'] = ratio_df['Close'] > ratio_df['SAR']

        ratio_df['Bullish_Signal'] = ratio_df[['SAR_Signal', 'EMA_Signal']].all(axis=1) & macd_cross
        ratio_df['Bearish_Signal'] = ~ratio_df[['SAR_Signal', 'EMA_Signal']].any(axis=1) & ~macd_cross

        ratio_df['Entry'] = ratio_df['Bullish_Signal'] & (~ratio_df['Bullish_Signal'].shift(1).fillna(False).astype(bool))
        ratio_df['Exit'] = ratio_df['Bearish_Signal'] & (~ratio_df['Bearish_Signal'].shift(1).fillna(False).astype(bool))

        entry_plot = ratio_df['Close'].where(ratio_df['Entry'])
        exit_plot = ratio_df['Close'].where(ratio_df['Exit'])

        apdict = [
            mpf.make_addplot(ratio_df['EMA'], color='blue', panel=0, ylabel='Price Ratio'),
            mpf.make_addplot(ratio_df['SAR'], color='white', scatter=True, markersize=10, panel=0),
            mpf.make_addplot(entry_plot, type='scatter', color='green', markersize=100, marker='^', panel=0),
            mpf.make_addplot(exit_plot, type='scatter', color='red', markersize=100, marker='v', panel=0),
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
                plt.Line2D([0], [0], color='white', marker='o', linestyle='None', label='SAR'),
                plt.Line2D([0], [0], color='green', marker='^', linestyle='None', label='Entry'),
                plt.Line2D([0], [0], color='red', marker='v', linestyle='None', label='Exit'),
                plt.Line2D([0], [0], color='yellow', label='MACD'),
                plt.Line2D([0], [0], color='orange', label='MACD Signal'),
                plt.Line2D([0], [0], color='purple', label='MACD Histogram')
            ],
            loc='lower left',
            fontsize='medium',
            frameon=True
        )
        plt.savefig(f'images/{base_symbol}{base_quote}_{quote_symbol}{quote_quote}_{time.time().__str__()}.png')
        plt.show()


def main():
    parser = argparse.ArgumentParser(description='Composite Index Chart Generator')
    parser.add_argument('--base', required=True, help='Base asset ticker (e.g., ETH/USDT)')
    parser.add_argument('--quote', required=True, help='Quote asset ticker (e.g., BTC/USDT)')
    parser.add_argument('--interval', default='1h', help='Interval for candlesticks (default: 1h)')
    parser.add_argument('--lookback', default=100, type=int, help='Number of candles to fetch (default: 100)')
    parser.add_argument('--evm', action='store_true', help='Fetch market data from an EVM chain via Moralis')
    args = parser.parse_args()
    CompositeGenerator(use_evm=args.evm).generate_chart(
        args.base.upper(), args.quote.upper(), args.interval, args.lookback
    )

if __name__ == '__main__':
    main()