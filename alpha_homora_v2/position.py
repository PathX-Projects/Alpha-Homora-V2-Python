from typing import Optional, Union

from .resources.abi_reference import *
from .util import ContractInstanceFunc, cov_from, get_token_info_from_ref, get_web3_provider
from .spell import SpellClient, PangolinV2Client, TraderJoeClient
from .oracle import get_token_price
from .receipt import TransactionReceipt, build_receipt

import requests
from web3 import Web3
from web3.contract import ContractFunction
from web3.constants import MAX_INT
from web3.exceptions import ContractLogicError


class AvalanchePosition:
    def __init__(self, position_id: int, owner_wallet_address: str, owner_private_key: str = None,
                 web3_provider: Web3 = None):
        """
        :param web3_provider: The Web3 object used to interact with the Alpha Homora V2 position's chain
                              (ex. Web3(Web3.HTTPProvider(your_network_rpc_url)))
        :param position_id: The Alpha Homora V2 position ID
        :param position_type: The type of position held. Options include: NOT YET IMPLEMENTED
        :param owner_wallet_address: The wallet address of the position owner
        :param owner_private_key: The private key of the position owner's wallet (for transaction signing)
        """

        self.pos_id = position_id
        self.owner = owner_wallet_address
        self.private_key = owner_private_key

        self.w3_provider = web3_provider if web3_provider is not None else \
            get_web3_provider("https://api.avax.network/ext/bc/C/rpc")

        self.homora_bank = ContractInstanceFunc(web3_provider=self.w3_provider,
                                                json_abi_file=HomoraBank_ABI[0],
                                                contract_address=HomoraBank_ABI[1])

        self.pool_key = self.get_position()['pool']['key']
        self.pool = self.get_pool_info()
        self.symbol = self.pool['name']
        self.dex = self.pool['exchange']['name']

        self.platform = self.get_platform()

    """ ------------------------------------------ PRIMARY ------------------------------------------ """
    def close(self) -> TransactionReceipt:
        """
        Close the position if it is open

        Returns:
            - transaction hash
            - transaction receipt
        """
        self.has_private_key()

        underlying_tokens = self.pool['tokens']

        try:
            spell_address = Web3.toChecksumAddress(self.pool['spellAddress'])
        except KeyError:
            spell_address = Web3.toChecksumAddress(self.platform.spell_contract.address)

        underlying_tokens_data = list(zip([Web3.toChecksumAddress(address) for address in underlying_tokens],
                                          [self.get_token_borrow_balance(address) for address in underlying_tokens]))

        position_size = self.get_position_info()[-1]

        try:
            lp_balance = self.get_token_borrow_balance(self.pool['lpTokenAddress'])
        except ContractLogicError:
            lp_balance = 0

        encoded_spell_func = self.platform.prepare_close_position(underlying_tokens_data, position_size,
                                                                  amtLPRepay=lp_balance)

        encoded_bank_func = self.homora_bank.functions.execute(self.pos_id, spell_address, encoded_spell_func)

        return self.sign_and_send(encoded_bank_func)

    def claim_all_rewards(self) -> Union[TransactionReceipt, None]:
        """
        Harvests available position rewards

        Returns:
            if there are rewards to harvest:
                - transaction hash (str)
                - transaction receipt (AttributeDict)
            else None
        """
        self.has_private_key()

        try:
            # Prevent needless gas spending
            if self.get_rewards_value()['reward_token'] == 0:
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

        return self.sign_and_send(encoded_bank_func)

    def get_rewards_value(self) -> dict:  # tuple[float, float, str, str]
        """
        Get the amount of outstanding yield farming rewards in the position.

        :return:
            - reward_token (float) (in the native reward token)
            - reward_usd (float) (in USD)
            - reward_token_address (str)
            - reward_token_symbol (str)
        """
        owner, coll_token, coll_id, collateral_size = self.get_position_info()
        pool_info = self.platform.get_pool_info(coll_id)
        start_reward_per_share = pool_info['entryRewardPerShare']
        end_reward_per_share = pool_info['accRewardPerShare']

        if self.dex == "Trader Joe":
            if self.pool['wTokenType'].startswith("WMasterChef"):
                precision = 10 ** 12
                reward_amount = collateral_size * (end_reward_per_share - start_reward_per_share) // precision
            else:  # Accounts for BoostedMasterChef positions
                wrapper_token_per_share = pool_info['wrapper_token_per_share']
                lp_amt = pool_info['lpAmt']
                reward_debt = pool_info['rewardDebt']
                precision = 10 ** 18

                extra_reward_per_share = end_reward_per_share - (reward_debt * precision // lp_amt)
                end_token_per_share = wrapper_token_per_share + extra_reward_per_share
                reward_amount = (collateral_size * (end_token_per_share - start_reward_per_share) // precision) / precision
        else:
            # entryRewardPerShare = pool_info['entryRewardPerShare'] / 1e18
            # accRewardPerShare = pool_info['accRewardPerShare'] / 1e18
            reward_amount = collateral_size * ((end_reward_per_share / 1e18) - (start_reward_per_share / 1e18)) / 1e12

        reward_token_symbol, reward_token_address = [v for k, v in self.get_pool_info()["exchange"]["reward"].items()]
        reward_usd = reward_amount * get_token_price(reward_token_symbol)

        return {"reward_token": reward_amount, "reward_usd": reward_usd, "reward_token_address": reward_token_address,
                "reward_token_symbol": reward_token_symbol}

    def get_debt_ratio(self) -> float:
        """Return the position's debt ratio percentage in decimal form (10% = 0.10)"""

        collateral_credit = self.homora_bank.functions.getCollateralETHValue(self.pos_id).call()
        borrow_credit = self.homora_bank.functions.getBorrowETHValue(self.pos_id).call()

        try:
            return borrow_credit / collateral_credit
        except ZeroDivisionError:
            return 0.0

    def get_leverage_ratio(self) -> float:
        """Return the position's leverage ratio"""
        position_values = self.get_position_value()

        coll_value = position_values['position_usd']
        debt_value = position_values['debt_usd']
        # print(f"Coll: {coll_value} | Debt: {debt_value}")
        try:
            return coll_value / (coll_value - debt_value)
        except ZeroDivisionError:
            return 0.0

    def get_current_apy(self) -> dict:
        """
        Return the current APY for the LP from the official Alpha Homora V2 /apys API endpoint

        :return: (dict)
            - APY (float) - The current net APY (farming APY + trading APY - borrow fees)
            - breakdown (dict) - Each individual component of the net APY
                - farmingAPY (float)
                - tradingFeeAPY (float)
                - borrowAPY (-float)
        """
        try:
            r = requests.get(f"https://api.homora.alphaventuredao.io/v2/{self.platform.network_chain_id}/apys")
            if r.status_code != 200:
                raise Exception(f"{r.status_code}, {r.text}")

            pool_key = self.get_pool_info()['key']
            apy_data = r.json()[pool_key]

            leverage = self.get_leverage_ratio()
            # print("Leverage:", leverage)

            return {"totalAPY": leverage * float(apy_data['totalAPY']),
                    "tradingFeeAPY": leverage * float(apy_data['tradingFeeAPY']),
                    "farmingAPY": leverage * float(apy_data['farmingAPY'])}
        except Exception as exc:
            raise Exception(f"Could not get current APY for position: {exc}")

    def get_position_value(self) -> dict:
        """
        Get equity, debt, and total position value in AVAX and USD.

        :return: (tuple)
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

        # return total_equity_avax, total_equity_usd, debt_value_avax, debt_value_usd, position_value_avax, position_value_usd
        return {"equity_avax": total_equity_avax, "equity_usd": total_equity_usd,
                "debt_avax": debt_value_avax, "debt_usd": debt_value_usd,
                "position_avax": position_value_avax, "position_usd": position_value_usd}

    """ ------------------------------------------ UTILITY ------------------------------------------ """
    def get_position(self) -> dict:
        """
        Returns the position matching the owner wallet address and position ID on Avalanche

        {id: int
        owner: str
        collateralSize: str (int)
        pool: {key: str}
        collateralCredit: str (int)
        borrowCredit: str (int)
        debtRatio: str (float)}
        """
        r = requests.get("https://api.homora.alphaventuredao.io/v2/43114/positions")
        if r.status_code != 200:
            raise Exception(f"Could not fetch position: {r.status_code, r.text}")

        try:
            return list(filter(lambda p: int(p['id']) == self.pos_id and p['owner'].lower() == self.owner.lower(),
                               r.json()))[0]
        except IndexError:
            raise IndexError(f"Could not fetch pool for position_id {self.pos_id} owned by {self.owner} "
                             f"(If you just opened the position, please retry in a few minutes)")

    def get_platform(self) -> SpellClient:
        """Determine what dex the position is on (i.e. Trader Joe, Pangolin V2, Sushiswap, etc)"""
        if self.dex == "Pangolin V2":
            return PangolinV2Client(self.w3_provider)
        elif self.dex == "Trader Joe":
            try:
                spell_address = self.pool['spellAddress']
            except KeyError:
                spell_address = self.pool['exchange']['spellAddress']
            try:
                staking_address = self.pool['stakingAddress']
            except KeyError:
                staking_address = self.pool['exchange']['stakingAddress']
            return TraderJoeClient(self.w3_provider,
                                   spell_address=spell_address,
                                   w_token_type=self.pool['wTokenType'], w_token_address=self.pool['wTokenAddress'],
                                   staking_address=staking_address)
        else:
            raise NotImplementedError(f"Spell client not yet implemented for the '{self.dex}' DEX. "
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

        pool = list(filter(lambda p: p['key'] == self.pool_key, r.json()))
        if len(pool) == 0:
            raise IndexError(f"Could not find pool matching key: {self.pool_key}")
        if len(pool) > 1:
            raise IndexError(f"Found multiple pools matching key: {self.pool_key}")

        return pool[0]

    def verify_ownership(self) -> None:
        pass

    def sign_and_send(self, function_call: ContractFunction) -> TransactionReceipt:
        """
        :param function_call: The uncalled and prepared contract method to sign and send
        """
        self.has_private_key()

        txn = function_call.buildTransaction({"nonce": self.w3_provider.eth.get_transaction_count(self.owner),
                                              "from": self.owner})
        signed_txn = self.w3_provider.eth.account.sign_transaction(
            txn, private_key=self.private_key
        )
        tx_hash = self.w3_provider.eth.send_raw_transaction(signed_txn.rawTransaction)

        receipt = dict(self.w3_provider.eth.wait_for_transaction_receipt(tx_hash))

        return build_receipt(receipt)

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

    @staticmethod
    def get_cream_borrow_rates(network: str) -> list[dict]:
        assert network in ['eth', 'avalanche', 'fantom', 'ironbank']

        return requests.get(f"https://api.cream.finance/api/v1/rates?comptroller={network}").json()['borrowRates']

    def has_private_key(self):
        if self.private_key is None:
            raise Exception("This method requires the position holder's private key to sign the transaction.\n"
                            "Please set a value for the 'owner_private_key' class init attribute.")


class EthereumPosition:
    def __int__(self, *a, **kw):
        raise NotImplementedError("Ethereum positions are not yet available.")


class FantomPosition:
    def __int__(self, *a, **kw):
        raise NotImplementedError("Fantom positions are not yet available.")


def get_avax_positions_by_owner(owner_address: str, owner_private_key: str = None, web3_provider: Web3 = None
                                          ) -> list[AvalanchePosition]:
    """
    Get all pool positions on Avalanche held by the provided owner address

    :param owner_address: The owner of the position (address str)
    :param web3_provider: Your Web3 provider object to interact with the network
    :param owner_private_key: (optional) The owner's private key for using transactional methods from the AvalanchePosition object(s)
    """
    owned_positions = list(filter(lambda pos: pos["owner"].lower() == owner_address.lower(),
                                  requests.get("https://api.homora.alphaventuredao.io/v2/43114/positions").json()))
    if len(owned_positions) == 0:
        return owned_positions

    pools = requests.get("https://api.homora.alphaventuredao.io/v2/43114/pools").json()

    obj = []
    for position in owned_positions:
        pos_key = position['pool']['key']
        pool_data = list(filter(lambda pool: pool['key'] == pos_key, pools))[0]
        obj.append(AvalanchePosition(web3_provider=web3_provider, position_id=position['id'],
                                     owner_wallet_address=owner_address, owner_private_key=owner_private_key))

    return obj
