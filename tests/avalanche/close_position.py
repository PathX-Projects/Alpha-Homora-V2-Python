from os.path import join, dirname
from os import getenv
import sys

sys.path.insert(0, join(dirname(__file__), '../..'))

from alpha_homora_v2.position import AvalanchePosition

PUBKEY = getenv("PUBLIC_WALLET_ADDRESS")
PRIVKEY = getenv("PRIVATE_WALLET_KEY")
POS_ID = 11413  # Your position ID (in this case USDC.e/AVAX on Trader Joe)


if __name__ == "__main__":
    assert PUBKEY is not None and PRIVKEY is not None

    position = AvalanchePosition(POS_ID, PUBKEY, PRIVKEY)
    print(f"Position: {position.symbol} {position.dex}\n")

    print(f"Start Values: {position.get_position_value()}\n")

    tx = position.close()

    print(f"Position close transaction: {tx}\n")

    print(f"End Values: {position.get_position_value()}\n")