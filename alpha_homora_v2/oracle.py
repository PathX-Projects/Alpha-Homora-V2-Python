from os.path import join, abspath, dirname

import pandas as pd
from pycoingecko import CoinGeckoAPI

cg = CoinGeckoAPI()


def get_token_price(token_symbol: str):
    """Get the realtime USD price of a token"""
    path = join(abspath((dirname(__file__))), "resources", "token_metadata.csv")
    id_df = pd.read_csv(path, index_col=0)
    token_id = id_df['coingecko_id'].loc[token_symbol]

    return cg.get_price(ids=token_id, vs_currencies='usd')[token_id]['usd']