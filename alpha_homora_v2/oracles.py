from os.path import join, abspath, dirname

from .util import ContractInstanceFunc, checksum
from .resources.abi_reference import AggregatorOracle_ABI, ISafeOracle_ABI
from .provider import avalanche_provider

import pandas as pd
from pycoingecko import CoinGeckoAPI
from web3 import Web3

cg = CoinGeckoAPI()


def get_token_price_cg(token_symbol: str):
    """Get the realtime USD price of a token"""
    path = join(abspath((dirname(__file__))), "resources", "token_metadata.csv")
    id_df = pd.read_csv(path, index_col=0)
    token_id = id_df['coingecko_id'].loc[token_symbol]

    return cg.get_price(ids=token_id, vs_currencies='usd')[token_id]['usd']


class AvalancheAggOracle:
    def __init__(self):
        self.contract = ContractInstanceFunc(avalanche_provider, AggregatorOracle_ABI[0], AggregatorOracle_ABI[1])

    def get_token_price(self, token_address: str, token_decimals: int) -> tuple[float, float]:
        """
        :return: tuple
            - price in AVAX
            - price in USD

        @dev-note
        The token price will always be returned from the contract in the network native token (AVAX in this case)
        """
        price_u112 = self.contract.functions.getETHPx(checksum(token_address)).call()
        price_avax = price_u112 / 2 ** 112 / 10 ** (18 - token_decimals)
        price_usd = price_avax * get_token_price_cg("WAVAX")
        return price_avax, price_usd


class AvalancheSafeOracle:
    def __init__(self):
        self.contract = ContractInstanceFunc(avalanche_provider, ISafeOracle_ABI[0], ISafeOracle_ABI[1])
        self.agg_oracle = AvalancheAggOracle()

    def get_token_price(self, token_address: str, token_decimals: int) -> tuple[float, float]:
        """
        :return: tuple
            - price in AVAX
            - price in USD

        @dev-note
        The token price will always be returned from the contract in the network native token (AVAX in this case)
        """
        try:
            price_u112 = self.contract.functions.getSafeETHPx(checksum(token_address)).call()[0]
            price_avax = price_u112 / 2 ** 112 / 10 ** (18 - token_decimals)
            price_usd = price_avax * get_token_price_cg("WAVAX")
            return price_avax, price_usd
        except:
            # Revert to aggregate
            return self.agg_oracle.get_token_price(token_address, token_decimals)


