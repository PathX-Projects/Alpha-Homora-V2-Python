import csv
import os
import sys
sys.path.insert(0, '..')

from alpha_homora_v2.position import get_avax_positions_by_owner, AvalanchePosition

ADDRESS = os.getenv("PUBLIC_WALLET_ADDRESS")
CSV_OUTPUT_FILEPATH = os.path.join(os.path.dirname(__file__), "report.csv")  # File will be generated to tests/report.csv


def build_rows(ahv2_positions: list[AvalanchePosition]):
    for p in ahv2_positions:
        # Meta
        p_id = p.pos_id
        dex = p.dex
        symbol = p.symbol

        print(f"Processing #{p_id} {symbol} {dex}...")

        # Position values
        values = p.get_position_value()
        position_value_usd = values['position_usd']
        equity_value_usd = values['equity_usd']
        debt_value_usd = values['debt_usd']

        # Debt and leverage ratios
        debt_ratio = p.get_debt_ratio()
        leverage_ratio = p.get_leverage_ratio()

        # APYs
        apys = p.get_current_apy()
        farming_apy = apys['farmingAPY']
        trading_fee_apy = apys['tradingFeeAPY']
        borrow_apy = None  # Not yet working
        agg_apy = None

        # Rewards
        rewards = p.get_rewards_value()
        pending_rewards_token = rewards['reward_token']
        pending_rewards_usd = rewards['reward_usd']
        reward_token_symbol = rewards['reward_token_symbol']

        yield [p_id, dex, symbol, position_value_usd, equity_value_usd, debt_value_usd, debt_ratio, leverage_ratio,
               trading_fee_apy, farming_apy, borrow_apy, agg_apy, pending_rewards_token, pending_rewards_usd, reward_token_symbol]


if __name__ == "__main__":
    positions = get_avax_positions_by_owner(ADDRESS)

    assert len(positions) > 0
    assert ADDRESS is not None

    # Generate report CSV
    header = ['position_id', 'dex', 'symbol', 'position_value_usd', 'equity_value_usd', 'debt_value_usd', 'debt_ratio', 'leverage',
              'tradingFeeAPY', 'farmingAPY', 'borrowAPY', 'aggAPY', 'pending_rewards_token', 'pending_rewards_usd', 'reward_token_symbol']

    rows = build_rows(positions)

    with open(CSV_OUTPUT_FILEPATH, 'w') as report:
        writer = csv.writer(report)

        writer.writerow(header)
        for row in rows:
            writer.writerow(row)

    print("Operation complete.")




