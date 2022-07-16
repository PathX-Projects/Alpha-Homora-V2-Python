from os.path import join, dirname
from os import getenv
import sys

sys.path.insert(0, join(dirname(__file__), '../..'))

from alpha_homora_v2.position import AvalanchePosition


PUBKEY = getenv("PUBLIC_WALLET_ADDRESS")
PRIVKEY = getenv("PRIVATE_WALLET_KEY")
POS_ID = 11575  # Your position ID (in this case USDT.e/DAI.e on Trader Joe)

if __name__ == "__main__":
    assert PUBKEY is not None and PRIVKEY is not None

    position = AvalanchePosition(POS_ID, PUBKEY, PRIVKEY)
    print(f"Position: {position.symbol} {position.dex}\n")

    pool_toks = position.get_pool_tokens()
    print("Pool Tokens:", *[(k, v.symbol()) for k, v in pool_toks.items()], "\n")

    print("Beginning Position Values:", position.get_position_value(), "\n")

    # Token data structure: ARC20Token, supply_token, borrow_token
    # Supply 0.90 of tokenA (USDT.e) and borrow 0.45 of tokenB (DAI.e)
    token_a_data = pool_toks['tokenA'], 0.90, 0
    token_b_data = pool_toks['tokenB'], 0, 0.45  # Borrow 50% of deposited tokenA (USDT.e)

    tx = position.add(tokenA_data=token_a_data, tokenB_data=token_b_data)
    print(f"\nAdded liquidity transaction receipt: {tx}\n")

    print(f"Ending Position Values:", position.get_position_value())

