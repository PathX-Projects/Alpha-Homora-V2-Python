import json
from os.path import join, abspath, dirname
from os import getcwd, pardir
from typing import Optional, Union

from .resources.abi_reference import *
from .util import ContractInstanceFunc, cov_from, get_token_info_from_ref
from .spell import SpellClient, PangolinV2Client, TraderJoeV1Client
from .oracle import get_token_price

import requests
from web3 import Web3
from web3.contract import ContractFunction
from web3.constants import MAX_INT
from web3.exceptions import ContractLogicError


class AlphaHomoraV2Position:
    def __init__(self, web3_provider: Web3, position_id: int, dex: str, owner_wallet_address: str,
                 owner_private_key: str, position_type: str = "Yield Farming"):
        """
        :param web3_provider: The Web3 object used to interact with the Alpha Homora V2 position's chain
                              (ex. Web3(Web3.HTTPProvider(your_network_rpc_url)))
        :param position_id: The Alpha Homora V2 position ID
        :param position_symbol: The symbol for the tokens in the position, exactly as shown on Alpha Homora V2.
                                Used to fetch data about the position.
                                (e.g. AVAX/USDT.e for the Pangolin V2 Yield farming position on Avalanche)
        :param dex: The dex identifier exactly as shown on Alpha Homora (e.g. Pangolin V2)
        :param position_type: The type of position held. Options include: NOT YET IMPLEMENTED
        :param owner_wallet_address: The wallet address of the position owner
        :param owner_private_key: The private key of the position owner's wallet (for transaction signing)
        """
        self.pos_id = position_id
        # self.symbol = position_symbol
        self.dex = dex
        self.w3_provider = web3_provider
        self.homora_bank = ContractInstanceFunc(web3_provider=self.w3_provider,
                                                json_abi_file=HomoraBank_ABI[0],
                                                contract_address=HomoraBank_ABI[1])
        self.platform = self.get_platform(dex)
        self.owner = owner_wallet_address
        self.private_key = owner_private_key
        self.position_type = position_type

    """ ------------------------------------------ PRIMARY ------------------------------------------ """
    def close(self) -> tuple[str, dict]:
        """
        Close the position if it is open

        Returns:
            - transaction hash
            - transaction receipt
        """

        pool_info = self.get_pool_info()

        underlying_tokens = pool_info['tokens']

        try:
            spell_address = Web3.toChecksumAddress(pool_info['spellAddress'])
        except KeyError:
            spell_address = Web3.toChecksumAddress(self.platform.spell_contract.address)

        underlying_tokens_data = list(zip([Web3.toChecksumAddress(address) for address in underlying_tokens],
                                          [self.get_token_borrow_balance(address) for address in underlying_tokens]))

        position_size = self.get_position_info()[-1]

        try:
            lp_balance = self.get_token_borrow_balance(pool_info['lpTokenAddress'])
        except ContractLogicError:
            lp_balance = 0

        encoded_spell_func = self.platform.prepare_close_position(underlying_tokens_data, position_size,
                                                                  amtLPRepay=lp_balance)

        encoded_bank_func = self.homora_bank.functions.execute(self.pos_id, spell_address, encoded_spell_func)

        tx_hash, receipt = self.sign_and_send(
            encoded_bank_func
        )

        return tx_hash, receipt

    def claim_all_rewards(self) -> Union[tuple[str, dict], None]:
        """
        Harvests available position rewards

        Returns:
            if there are rewards to harvest:
                - transaction hash (str)
                - transaction receipt (AttributeDict)
            else None
        """

        try:
            if self.get_rewards_value()[0] == 0:
                return None
        except NotImplementedError:
            pass

        encoded_spell_func = self.platform.prepare_claim_all_rewards()

        pool_info = self.get_pool_info()

        try:
            spell_address = Web3.toChecksumAddress(pool_info['spellAddress'])
        except KeyError:
            spell_address = Web3.toChecksumAddress(self.platform.address)

        encoded_bank_func = self.homora_bank.functions.execute(self.pos_id, spell_address, encoded_spell_func)

        tx_hash, receipt = self.sign_and_send(
            encoded_bank_func
        )

        return tx_hash, receipt

    def get_rewards_value(self) -> tuple[float, float, str, str]:
        """
        Get the amount of outstanding yield farming rewards in the position.

        :return:
            - reward_amount (float) (in the native reward token)
            - reward_value (float) (in USD)
            - reward_token_address (str)
            - reward_token_symbol (str)
        """
        if self.dex != "Pangolin V2":
            raise NotImplementedError("This feature is currently only available for positions on the Pangolin V2 DEX")
        
        owner, coll_token, coll_id, collateral_size = self.get_position_info()

        pool_info = self.platform.get_pool_info(coll_id)
        entryRewardPerShare = pool_info['entryRewardPerShare'] / 1e18
        accRewardPerShare = pool_info['accRewardPerShare'] / 1e18

        if accRewardPerShare >= entryRewardPerShare:
            reward_amount = collateral_size * (accRewardPerShare - entryRewardPerShare) / 1e12
        else:
            reward_amount = 0.0

        reward_token_symbol, reward_token_address = [v for k, v in self.get_pool_info()["exchange"]["reward"].items()]

        reward_value = reward_amount * get_token_price(reward_token_symbol)

        return reward_amount, reward_value, reward_token_address, reward_token_symbol

    def get_debt_ratio(self) -> float:
        """Return the position's debt ratio percentage in decimal form (10% = 0.10)"""

        collateral_credit = self.homora_bank.functions.getCollateralETHValue(self.pos_id).call()
        borrow_credit = self.homora_bank.functions.getBorrowETHValue(self.pos_id).call()

        return borrow_credit / collateral_credit

    def get_position_value(self):
        """
        Get equity, debt, and total position value in AVAX and USD.

        :return: (dict)
            - equity_avax (float)
            - equity_usd (float)
            - debt_avax (float)
            - debt_usd (float)
            - position_avax (float)
            - position_usd (float)
        """
        # Get pool info & underlying token metadata
        pool_info = self.get_pool_info()
        underlying_token_data = [get_token_info_from_ref(token) for token in self.get_pool_info()['tokens']]

        # Get AVAX price once since operation is heavily reliant on this value
        avax_price = get_token_price("AVAX")

        # Get token pair liquidity pool data:
        pool_instance = self.platform.get_lp_contract(pool_info['lpTokenAddress'])
        collateral_size = self.get_position_info()[-1]
        r0, r1, last_block_time = pool_instance.functions.getReserves().call()
        supply = pool_instance.functions.totalSupply().call()

        # Process values by token to get full totals:
        debt_value_usd = 0
        debt_value_avax = 0
        position_value_usd = 0
        position_value_avax = 0
        for i, token_reserve_amt in enumerate([r0, r1]):
            token_price_usd = get_token_price(underlying_token_data[i]["symbol"])
            precision = int(underlying_token_data[i]['precision'])

            owned_reserve_amt = (token_reserve_amt * collateral_size // supply) / 10 ** precision
            owned_reserve_amt_usd = owned_reserve_amt * token_price_usd
            # print(f"{underlying_token_data[i]['symbol']} owned_reserve_amt_usd:", owned_reserve_amt_usd)

            # Get & calculate token debt for underlying token:
            borrow_bal = self.homora_bank.functions.\
                borrowBalanceCurrent(self.pos_id, Web3.toChecksumAddress(underlying_token_data[i]['address'])).call()
            token_debt = borrow_bal / 10 ** precision
            token_debt_usd = token_debt * token_price_usd
            token_debt_avax = token_debt_usd / avax_price

            # Add debt values to total debt valye count
            debt_value_usd += token_debt_usd
            debt_value_avax += token_debt_avax

            # Add owned reserve values to total position value count
            position_value_usd += owned_reserve_amt_usd
            position_value_avax += owned_reserve_amt_usd * (1 / avax_price)

        # Derive equity values from position and debt:
        total_equity_avax = position_value_avax - debt_value_avax
        total_equity_usd = position_value_usd - debt_value_usd

        return {"equity_avax": total_equity_avax, "equity_usd": total_equity_usd,
                "debt_avax": debt_value_avax, "debt_usd": debt_value_usd,
                "position_avax": position_value_avax, "position_usd": position_value_usd}

    # Deprecated but left temporarily for backup and reference:
    # def get_position_value(self):
    #     """
    #     Get equity value, debt value, and total position value in AVAX and USD.
    #
    #     :return: (dict)
    #         - equity_avax (float)
    #         - equity_usd (float)
    #         - debt_avax (float)
    #         - debt_usd (float)
    #         - position_avax (float)
    #         - position_usd (float)
    #     """
    #     pool_info = self.get_pool_info()
    #     underlying_token_data = [get_token_info_from_ref(token) for token in self.get_pool_info()['tokens']]
    #     lp_address = pool_info['lpTokenAddress']
    #     avax_price = get_token_price("AVAX")
    #
    #     pool_instance = self.platform.get_lp_contract(lp_address)
    #
    #     collateral_size = self.get_position_info()[-1]
    #
    #     r0, r1, last_block_time = pool_instance.functions.getReserves().call()
    #     supply = pool_instance.functions.totalSupply().call()
    #
    #     token0_amount = (r0 * collateral_size / supply) / 10 ** int(underlying_token_data[0]['precision'])
    #     token1_amount = (r1 * collateral_size / supply) / 10 ** int(underlying_token_data[1]['precision'])

    #     position_value_usd = token0_amount + (token1_amount * avax_price)
    #     position_value_avax = position_value_usd * (1 / avax_price)
    #
    #     print("Position Value:", position_value_usd)
    #
    #     # Get debts for underlying tokens:
    #     total_debt_usd = 0.0
    #     total_debt_avax = 0.0
    #     for i, token in enumerate(pool_info['tokens']):
    #         borrow_bal = self.homora_bank.functions.borrowBalanceCurrent(self.pos_id,
    #                                                                      Web3.toChecksumAddress(token)).call()
    #         mtd = get_token_info_from_ref(token)
    #         if mtd is None:
    #             raise ValueError(f"Could not locate token metadata for {token}")
    #
    #         token_price_usd = get_token_price(mtd['symbol'])
    #
    #         bbal_in_token = borrow_bal / 10 ** int(mtd['precision'])
    #         bbal_in_usd = bbal_in_token * token_price_usd
    #         bbal_in_avax = bbal_in_token / get_token_price('AVAX')
    #
    #         total_debt_usd += bbal_in_usd
    #         total_debt_avax += bbal_in_avax
    #
    #         print(f"{mtd['symbol']} | "
    #               f"token{i}_amount: {[token0_amount, token1_amount][i]} | "
    #               f"r{i}: {[r0, r1][i]}")
    #
    #     equity_avax = position_value_avax - total_debt_avax
    #     equity_usd = position_value_usd - total_debt_usd
    #
    #     return {"equity_avax": equity_avax, "equity_usd": equity_usd,
    #             "debt_avax": total_debt_avax, "debt_usd": total_debt_usd,
    #             "position_avax": position_value_avax, "position_usd": position_value_usd}
        
    """ ------------------------------------------ UTILITY ------------------------------------------ """
    def get_platform(self, identifier: str) -> SpellClient:
        """Determine what dex the position is on (i.e. Trader Joe, Pangolin V2, Sushiswap, etc)"""
        if identifier == "Pangolin V2":
            return PangolinV2Client(self.w3_provider)
        elif identifier == "Trader Joe":
            return TraderJoeV1Client(self.w3_provider)
        else:
            raise NotImplementedError(f"Spell client not yet implemented for the '{identifier}' DEX. "
                                      f"Please make sure that the dex entered is exactly as shown on your Alpha Homora V2 position.")

    def get_position_info(self) -> list:
        """
        Returns position info from the HomoraBank.getPositionInfo method

        Returns (list):
            owner (address)
            collToken (address)
            collid (int)
            collateralSize (int)
        """
        return self.homora_bank.functions.getPositionInfo(self.pos_id).call()

    # def get_position_debts(self):
    #     return self.homora_bank.functions.getPositionDebts(self.pos_id).call()

    def get_token_borrow_balance(self, token_address: str):
        return self.homora_bank.functions.borrowBalanceCurrent(self.pos_id, Web3.toChecksumAddress(token_address)).call()

    def get_pool_info(self) -> dict:
        """
        If the open position is an LP position, returns the metadata regarding the current pool.
        "https://homora-api.alphafinance.io/v2/43114/pools"

        :return: Dict object containing data about the pool
        """
        r = requests.get("https://homora-api.alphafinance.io/v2/43114/pools")
        if r.status_code != 200:
            raise Exception(f"Could not fetch pools: {r.status_code, r.text}")

        coll_id = self.get_position_info()[2]
        pid = self.platform.decode_collid(coll_id)[0]

        for pool in r.json():
            # Criteria:
            if pool['pid'] == pid and pool['exchange']['name'] == self.dex:
                return pool
        else:
            raise Exception(f"No {self.dex} pool found with PID: {pid}")

    def verify_ownership(self) -> None:
        pass

    def sign_and_send(self, function_call: ContractFunction):
        """
        :param function_call: The uncalled and prepared contract method to sign and send
        """
        txn = function_call.buildTransaction({"nonce": self.w3_provider.eth.get_transaction_count(self.owner),
                                              "from": self.owner})
        signed_txn = self.w3_provider.eth.account.sign_transaction(
            txn, private_key=self.private_key
        )
        tx_hash = self.w3_provider.eth.send_raw_transaction(signed_txn.rawTransaction)

        receipt = dict(self.w3_provider.eth.wait_for_transaction_receipt(tx_hash))

        return tx_hash.hex(), receipt

    def decode_transaction_data(self, transaction_address: Optional) -> tuple:
        """
        Returns the transaction data used to invoke the smart contract function for the underlying contract

        First fetches the transaction data for the HomoraBank.execute() function, then gets the transaction data
        for the underlying smart contract

        :param w3_provider: The Web3.HTTPProvider object for interacting with the network
        :param transaction_address: The transaction address (binary or str)
        :return: (
            decoded bank function (ContractFunction, dict),
            decoded spell function (ContractFunction, dict)
        )
        """
        transaction = self.w3_provider.eth.get_transaction(transaction_address)

        decoded_bank_transaction = self.homora_bank.decode_function_input(transaction.input)

        encoded_contract_data = decoded_bank_transaction[1]['data']

        return decoded_bank_transaction, self.platform.spell_contract.decode_function_input(encoded_contract_data)