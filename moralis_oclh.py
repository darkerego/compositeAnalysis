import os

import requests
import dotenv
from eth_typing import ChecksumAddress
# from binance.ccxt.static_dependencies.ethereum import ChecksumAddress

class OCLHFailError(Exception):
    pass

dotenv.load_dotenv()
API_KEY = os.environ.get('MORALIS_API_KEY')
assert API_KEY is not None, 'MORALIS_API_KEY environment variable is not set'

class MoralisApi:
    headers = {
        'accept': 'application/json',
        'X-API-Key': API_KEY,
    }

    @classmethod
    def get_klines(cls, chain, time_period, limit, pair):
        params = {
            'chain': chain,
            'timeframe': time_period,
            'currency': 'usd',
            'limit': limit,

        }

        response = requests.get(
            'https://deep-index.moralis.io/api/v2.2/pairs/%s/ohlcv' % pair,
            params=params,
            headers=cls.headers)
        if response.status_code != 200:
            raise OCLHFailError()
        return response.json().get('result')

    @classmethod
    def get_pair_address(cls,
            token0: ChecksumAddress,
            token1: ChecksumAddress,
            chain: str = 'eth',
            exchange: str = 'uniswapv2',
            time_period: str = '1h'
    ):
        if chain == 'ethereum':
            chain = 'eth'
        params = {
            'chain': chain,
            'exchange': exchange,
        }

        response = requests.get(
            'https://deep-index.moralis.io/api/v2.2/%s/%s/pairAddress?chain=%s&timeframe=%s&currency=usd&' % \
            (token0.__str__(), token1.__str__(), chain, time_period),
            params=params,
            headers=cls.headers,
        )
        if response.ok:
            return response.json().get('pairAddress')
        raise OCLHFailError('Failed to get pair address')