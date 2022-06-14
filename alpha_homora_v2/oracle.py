from os.path import join, abspath, dirname

import pandas as pd
from pycoingecko import CoinGeckoAPI

cg = CoinGeckoAPI()


def GetPriceFunc(Token_Symbol: str):
    """Get the realtime USD price of a token"""
    path = join(abspath((dirname(__file__))), "resources", "coingecko_token_id.csv")
    id_df = pd.read_csv(path, index_col=0)
    token_id = id_df['id'].loc[Token_Symbol]

    pool_token_price = cg.get_price(ids=token_id, vs_currencies='usd')[token_id]['usd']
    return pool_token_price