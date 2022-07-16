from os.path import join, dirname
from os import getenv
import sys

sys.path.insert(0, join(dirname(__file__), '../..'))

from alpha_homora_v2.position import AvalanchePosition
from alpha_homora_v2.receipt import TransactionReceipt


PUBKEY = getenv("PUBLIC_WALLET_ADDRESS")
PRIVKEY = getenv("PRIVATE_WALLET_KEY")
POS_ID = 11347  # Your position ID (in this case WBTC.e/AVAX on Pangolin)
assert PUBKEY is not None and PRIVKEY is not None


def remove(position: AvalanchePosition) -> TransactionReceipt:
    """Remove 25% of LP in position without repaying any debts:"""

    return position.remove(pct_position_size=0.25)  # 0.25 = 25% of position size


def remove_repayA(position: AvalanchePosition) -> TransactionReceipt:
    """Remove 25% of LP in position and repay all tokenA debt"""

    token_a = position.get_pool_tokens()['tokenA']
    token_a_repay_data = token_a, 1.0  # Repay all token A debts (1.0 = 100%)

    return position.remove(pct_position_size=0.25, tokenA_data=token_a_repay_data)


def remove_repayB(position: AvalanchePosition) -> TransactionReceipt:
    """Remove 25% of LP in position and repay all tokenB debt"""

    token_b = position.get_pool_tokens()['tokenB']
    token_b_repay_data = token_b, 1.0  # Repay all token A debts (1.0 = 100%)

    return position.remove(pct_position_size=0.25, tokenB_data=token_b_repay_data)


def remove_repayAB(position: AvalanchePosition) -> TransactionReceipt:
    """Remove 25% of LP in position and repay 50% tokenA and 25% tokenB debts"""
    p_tokens = position.get_pool_tokens()

    token_a_repay_data = p_tokens['tokenA'], 0.50  # Repay 50% of token A debts
    token_b_repay_data = p_tokens['tokenB'], 0.25  # Repay 25% of token B debts

    return position.remove(pct_position_size=0.25, tokenA_data=token_a_repay_data, tokenB_data=token_b_repay_data)


if __name__ == "__main__":
    """Test using simple remove - just position (LP)"""

    pos = AvalanchePosition(POS_ID, PUBKEY, PRIVKEY)
    print(f"Position: {pos.symbol} {pos.dex}")
    print(f"Pool Tokens:", pos.get_pool_tokens(), "\n")

    print("Start Debt Ratio:", pos.get_debt_ratio())
    print("Start Values:", pos.get_position_value(), "\n")

    tx = remove(pos)
    print("Transaction Receipt:", tx, "\n")

    print("End Debt Ratio:", pos.get_debt_ratio())
    print("End Values:", pos.get_position_value(), "\n")
