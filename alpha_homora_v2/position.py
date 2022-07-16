from typing import Optional, Union, TypedDict
from math import floor

from .token import ARC20Token
from .resources.abi_reference import *
from .provider import avalanche_provider
from .receipt import TransactionReceipt, build_receipt
from .oracles import get_token_price_cg, AvalancheSafeOracle
from .util import ContractInstanceFunc, get_token_info_from_ref, checksum
from .spell import SpellClient, PangolinV2Client, TraderJoeClient

import requests
from web3 import Web3
# from web3.constants import MAX_INT
from web3.contract import ContractFunction
from web3.exceptions import ContractLogicError


class AvalanchePosition:
    def __init__(self, position_id: int, owner_wallet_address: str, owner_private_key: str = None):
        """
        :param position_id: The Alpha Homora V2 position ID
        :param owner_wallet_address: The wallet address of the position owner
        :param owner_private_key: The private key of the position owner's wallet (for transaction signing)
        """

        self.pos_id = position_id
        self.owner = owner_wallet_address
        self.private_key = owner_private_key

        self._homora_bank = ContractInstanceFunc(web3_provider=avalanche_provider,
                                                 json_abi_file=HomoraBank_ABI[0],
                                                 contract_address=HomoraBank_ABI[1])

        self.pool_key = self._get_position()['pool']['key']
        self.pool = self._get_pool_info()
        self.symbol = self.pool['name']
        self.dex = self.pool['exchange']['name']

        self._platform = self._get_platform()
        try:
            self.spell_address = checksum(self.pool['spellAddress'])
        except KeyError:
            self.spell_address = checksum(self._platform.spell_contract.address)

        self._oracle = AvalancheSafeOracle()

    """ -------------------- TRANSACTIONAL METHODS: -------------------- """
    
    def add(self,
            tokenA_data: tuple[ARC20Token, float, float] = None,
            tokenB_data: tuple[ARC20Token, float, float] = None,
            tokenLP_data: tuple[ARC20Token, float, float] = None) -> TransactionReceipt:
        """
        Add liquidity to the position

        Fetch underlying and LP token using the self.get_pool_tokens() method.

        :param tokenA_data: The first underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenB_data: The second underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenLP_data: The LP token if supplying, supply amount, and borrow amount (optional)
                             (ARC20Token object, supply_amount, borrow_amount)
                             
        :return: TransactionReceipt object
        """
        self._has_private_key()

        assert not all(v is None for v in [tokenA_data, tokenB_data, tokenLP_data]), "Must provide least one pool token"

        pool_tokens = self.get_pool_tokens()
        if tokenA_data is None:
            tokenA_data = pool_tokens['tokenA'], 0, 0
        else:
            tokenA_data = tokenA_data[0], self.to_wei(tokenA_data[0], tokenA_data[1]), self.to_wei(tokenA_data[0], tokenA_data[2])
        if tokenB_data is None:
            tokenB_data = pool_tokens['tokenB'], 0, 0
        else:
            tokenB_data = tokenB_data[0], self.to_wei(tokenB_data[0], tokenB_data[1]), self.to_wei(tokenB_data[0], tokenB_data[2])
        if tokenLP_data is None:
            tokenLP_data = pool_tokens['tokenLP'], 0, 0
        else:
            tokenLP_data = tokenLP_data[0], self.to_wei(tokenLP_data[0], tokenLP_data[1]), self.to_wei(tokenLP_data[0], tokenLP_data[2])

        pid = self.pool['pid']

        encoded_spell_func = self._platform.prepare_add_liquidity(pid=pid,
                                                                  tokenA_data=tokenA_data,
                                                                  tokenB_data=tokenB_data,
                                                                  tokenLP_data=tokenLP_data)
        encoded_bank_func = self._homora_bank.functions.execute(self.pos_id, self.spell_address, encoded_spell_func)

        # Approve supply amounts
        for data in [tokenA_data, tokenB_data, tokenLP_data]:
            if data[1] > 0:
                # Ensure that the user holds the required amount of tokens, or a SafeERC20 low-level call will fail
                assert data[0].balanceOf(self.owner) >= data[1], \
                    f"Insufficient funds to supply {data[1] / (10 ** data[0].decimals())} {data[0].symbol()}"

                approval_txn = self._sign_and_send(data[0].prepare_approve(HomoraBank_ABI[1]))
                print(f"Approved {data[0].symbol()}: {approval_txn}")

        # Sign and send add liquidity transaction
        return self._sign_and_send(encoded_bank_func)

    def remove(self, pct_position_size: float,
               tokenA_data: tuple[ARC20Token, float] = None,
               tokenB_data: tuple[ARC20Token, float] = None,
               amount_lp_withdraw: int = 0) -> TransactionReceipt:
        """
        Remove liquidity from the pool.
        If both tokenA and tokenB data are left as None, no debt will be repaid.

        :param pct_position_size: The percentage of the position (LP) to remove (0.0 - 1.0) (e.g. 0.25 = 25% of position)
        :param tokenA_data: The first underlying (or native) token in the pool, and the percentage of this token debt to repay (e.g. 0.50 = 50% of USDC debt)
                            (ARC20Token, pct_amount_repay) (optional)
        :param tokenB_data: The second underlying (or native) token in the pool, and the percentage of this token debt to repay (e.g. 0.50 = 50% of USDC debt)
                            (ARC20Token, pct_amount_repay) (optional)
        :param amount_lp_withdraw: (Advanced) The amount of LP token to withdraw
        
        :return: TransactionReceipt object
        """
        self._has_private_key()

        assert 0.0 < pct_position_size <= 1.0, "pct_position_size must be a float (percentage) of 0.0 - 1.0"

        position_amount = floor(self._get_position_info()[-1] * pct_position_size)

        pool_tokens = self.get_pool_tokens()
        if tokenA_data is None:
            tokenA_data = pool_tokens['tokenA'], 0
        else:
            debt = self.get_token_borrow_balance(tokenA_data[0].address)
            tokenA_data = tokenA_data[0], floor(debt * tokenA_data[1])

        if tokenB_data is None:
            tokenB_data = pool_tokens['tokenB'], 0
        else:
            # debt = list(filter(lambda t: t[0].address == tokenB_data[0].address, self.get_token_debts()))[0][1]
            debt = self.get_token_borrow_balance(tokenB_data[0].address)
            tokenB_data = tokenB_data[0], floor(debt * tokenB_data[1])

        encoded_spell_func = self._platform.prepare_remove_liquidity(amt_position_remove=position_amount,
                                                                     tokenA_data=tokenA_data, tokenB_data=tokenB_data,
                                                                     amt_lp_withdraw=amount_lp_withdraw)
        encoded_bank_func = self._homora_bank.functions.execute(self.pos_id, self.spell_address, encoded_spell_func)

        # Sign and send add liquidity transaction
        return self._sign_and_send(encoded_bank_func)

    def close(self) -> TransactionReceipt:
        """
        Close the position if it is open

        :return: TransactionReceipt object
        """
        self._has_private_key()

        underlying_tokens = self.pool['tokens']

        underlying_tokens_data = list(zip([Web3.toChecksumAddress(address) for address in underlying_tokens],
                                          [self.get_token_borrow_balance(address) for address in underlying_tokens]))

        position_size = self._get_position_info()[-1]

        try:
            lp_balance = self.get_token_borrow_balance(self.pool['lpTokenAddress'])
        except ContractLogicError:
            # In the even that there is no LP token owed, a ContractLogicError will be raised
            lp_balance = 0

        encoded_spell_func = self._platform.prepare_close_position(underlying_tokens_data, position_size,
                                                                   amtLPRepay=lp_balance)

        encoded_bank_func = self._homora_bank.functions.execute(self.pos_id, self.spell_address, encoded_spell_func)

        return self._sign_and_send(encoded_bank_func)

    def harvest(self) -> Union[TransactionReceipt, None]:
        """
        Harvests available position rewards

        Returns:
            if there are rewards to harvest:
                - TransactionReceipt object
            else:
                - None
        """
        self._has_private_key()

        # Prevent needless gas spending
        if self.get_rewards_value()['reward_token'] == 0:
            return None

        encoded_spell_func = self._platform.prepare_claim_all_rewards()
        encoded_bank_func = self._homora_bank.functions.execute(self.pos_id, self.spell_address, encoded_spell_func)

        return self._sign_and_send(encoded_bank_func)

    """ -------------------- INFORMATIONAL METHODS: -------------------- """
    
    def get_rewards_value(self) -> dict:  # tuple[float, float, str, str]
        """
        Get the amount of outstanding yield farming rewards in the position.

        :return:
            - reward_token (float) (in the native reward token)
            - reward_usd (float) (in USD)
            - reward_token_address (str)
            - reward_token_symbol (str)
        """
        owner, coll_token, coll_id, collateral_size = self._get_position_info()
        pool_info = self._platform.get_pool_info(coll_id)
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

        reward_token_symbol, reward_token_address = [v for k, v in self._get_pool_info()["exchange"]["reward"].items()]
        reward_usd = reward_amount * get_token_price_cg(reward_token_symbol)

        return {"reward_token": reward_amount, "reward_usd": reward_usd, "reward_token_address": reward_token_address,
                "reward_token_symbol": reward_token_symbol}

    def get_debt_ratio(self) -> float:
        """Return the position's debt ratio percentage in decimal form (10% = 0.10)"""

        collateral_credit = self._homora_bank.functions.getCollateralETHValue(self.pos_id).call()
        borrow_credit = self._homora_bank.functions.getBorrowETHValue(self.pos_id).call()

        try:
            return borrow_credit / collateral_credit
        except ZeroDivisionError:
            return 0.0

    def get_leverage_ratio(self) -> float:
        """Return the position's leverage ratio"""
        position_values = self.get_position_value()

        coll_value = position_values['position_usd']
        debt_value = position_values['debt_usd']

        try:
            return coll_value / (coll_value - debt_value)
        except ZeroDivisionError:
            return 0.0

    def get_current_apy(self) -> dict:
        """
        Return the current APY for the position with APY source breakdowns.

        :return: (dict)
            - APY (float) - The current aggregate APY (farming APY + trading APY - borrow APY)
            - farmingAPY (float)
            - tradingFeeAPY (float)
            - borrowAPY (-float)
        """
        try:
            r = requests.get(f"https://api.homora.alphaventuredao.io/v2/{self._platform.network_chain_id}/apys")
            if r.status_code != 200:
                raise Exception(f"{r.status_code}, {r.text}")
            apy_data = r.json()[self.pool_key]

            leverage = self.get_leverage_ratio()

            # Calculate Borrow APY:
            CREAM_borrow_rates = self.get_cream_borrow_rates()  # Get all CREAM borrow rates
            homora_fee = self._homora_bank.functions.feeBps().call() / 10000  # Get current Homora Fee

            agg_adj_borrow_apy = 0

            token_debts_data = self.get_token_debts()
            total_debt_usd = sum([tok[-1] for tok in token_debts_data])
            for arc20_token, debt_tok_wei, debt_tok, debt_USD in token_debts_data:
                symbol = arc20_token.symbol()
                cream_apy = float(list(filter(lambda t: t['tokenSymbol'] == symbol, CREAM_borrow_rates))[0]['apy']) * 100
                leverage_adjusted_apy = (leverage - 1) * (cream_apy * (1 + homora_fee))
                agg_adj_borrow_apy += leverage_adjusted_apy * (debt_USD / total_debt_usd)  # Adjust for token debt weight of total debt

            # Pull trading and farming APYs from API and adjust for leverage
            adj_tradingFeeAPY = leverage * float(apy_data['tradingFeeAPY'])
            adj_farmingAPY = leverage * float(apy_data['farmingAPY'])

            # Calculate aggregate APY
            aggregate_apy = adj_tradingFeeAPY + adj_farmingAPY + -agg_adj_borrow_apy

            return {"APY": aggregate_apy,
                    "tradingFeeAPY": adj_tradingFeeAPY,
                    "farmingAPY": adj_farmingAPY,
                    "borrowAPY": -agg_adj_borrow_apy}
        except Exception as exc:
            raise Exception(f"Could not get current APY for position: {exc}")

    # Get pool tokens
    class PoolTokens(TypedDict):
        tokenA: ARC20Token
        tokenB: ARC20Token
        tokenLP: ARC20Token
    def get_pool_tokens(self) -> PoolTokens:
        """Returns the underlying and LP tokens from the pool"""
        underlying = [ARC20Token(address) for address in self.pool['tokens']]
        return {"tokenA": underlying[0], "tokenB": underlying[1], "tokenLP": ARC20Token(self.pool['lpTokenAddress'])}

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
        pool_info = self._get_pool_info()
        underlying_token_data = [get_token_info_from_ref(token) for token in self._get_pool_info()['tokens']]

        # Get AVAX price once since operation is heavily reliant on this value
        avax_price = get_token_price_cg("AVAX")

        # Get token pair liquidity pool data:
        pool_instance = self._platform.get_lp_contract(pool_info['lpTokenAddress'])
        collateral_size = self._get_position_info()[-1]
        r0, r1, last_block_time = pool_instance.functions.getReserves().call()
        supply = pool_instance.functions.totalSupply().call()

        # Process values by token to get full totals:
        debt_value_usd = 0
        debt_value_avax = 0
        position_value_usd = 0
        position_value_avax = 0
        for i, token_reserve_amt in enumerate([r0, r1]):
            token_price_usd = get_token_price_cg(underlying_token_data[i]["symbol"])
            precision = int(underlying_token_data[i]['precision'])

            owned_reserve_amt = (token_reserve_amt * collateral_size // supply) / 10 ** precision
            owned_reserve_amt_usd = owned_reserve_amt * token_price_usd
            # print(f"{underlying_token_data[i]['symbol']} owned_reserve_amt_usd:", owned_reserve_amt_usd)

            # Get & calculate token debt for underlying token:
            borrow_bal = self._homora_bank.functions.\
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

    def get_token_debts(self) -> list[tuple[ARC20Token, int, float, float]]:
        """
        Returns the debt amount per token for the position

        :return: list of tuples containing:
            - ARC20Token object
            - debt in integer
            - debt in token
            - debt in USD
        """
        r = self._homora_bank.functions.getPositionDebts(self.pos_id).call()
        if len(r) == 0:
            return r

        debt_output = []
        for token, debt in zip(r[0], r[1]):
            arc20_token = self.get_token(token)
            decimals = arc20_token.decimals()
            debt_token = debt / 10 ** decimals
            try:
                debt_usd = debt_token * self._oracle.get_token_price(token, decimals)[1]
            except Exception as exc:
                print(f"Could not get debt in USD for token {arc20_token.symbol()} - {exc}")
                debt_usd = 0
            debt_output.append((arc20_token, debt, debt_token, debt_usd))

        return debt_output

    """ -------------------- UTILITY METHODS: -------------------- """

    def get_token_borrow_balance(self, token_address: str):
        return self._homora_bank.functions.borrowBalanceCurrent(self.pos_id, Web3.toChecksumAddress(token_address)).call()

    @staticmethod
    def get_cream_borrow_rates() -> list[dict]:
        return requests.get(f"https://api.cream.finance/api/v1/rates?comptroller=avalanche").json()['borrowRates']

    @staticmethod
    def to_wei(token: ARC20Token, amt: float) -> int:
        return int(amt * (10 ** token.decimals()))

    @staticmethod
    def get_token(address: str = None, symbol: str = None) -> ARC20Token:
        assert not all(v is None for v in [address, symbol]), "Address or symbol required to locate token"

        if address is not None:
            return ARC20Token(address)

        r = requests.get("https://api.homora.alphaventuredao.io/v2/43114/tokens")
        assert r.status_code != 200, f"Could not get tokens from AHV2 API: {r.status_code}, {r.text}"
        for token_address, meta in r.json().items():
            if meta['name'] == symbol.upper():
                return ARC20Token(token_address)
        else:
            raise Exception(f"Could not locate token on Alpha Homora V2 with symbol: {symbol}")

    def decode_transaction_data(self, transaction_address: Optional) -> tuple:
        """
        Returns the transaction data used to invoke the smart contract function for the underlying contract

        First fetches the transaction data for the HomoraBank.execute() function, then gets the transaction data
        for the underlying smart contract

        :param transaction_address: The transaction address (binary or str)
        :return: (
            decoded bank function (ContractFunction, dict),
            decoded spell function (ContractFunction, dict)
        )
        """
        transaction = avalanche_provider.eth.get_transaction(transaction_address)

        decoded_bank_transaction = self._homora_bank.decode_function_input(transaction.input)

        encoded_contract_data = decoded_bank_transaction[1]['data']

        return decoded_bank_transaction, self._platform.spell_contract.decode_function_input(encoded_contract_data)

    def _get_position(self) -> dict:
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

    def _get_platform(self) -> SpellClient:
        """Determine what dex the position is on (i.e. Trader Joe, Pangolin V2, Sushiswap, etc)"""
        if self.dex == "Pangolin V2":
            return PangolinV2Client()
        elif self.dex == "Trader Joe":
            try:
                spell_address = self.pool['spellAddress']
            except KeyError:
                spell_address = self.pool['exchange']['spellAddress']
            try:
                staking_address = self.pool['stakingAddress']
            except KeyError:
                staking_address = self.pool['exchange']['stakingAddress']
            return TraderJoeClient(spell_address=spell_address,
                                   w_token_type=self.pool['wTokenType'], w_token_address=self.pool['wTokenAddress'],
                                   staking_address=staking_address)
        else:
            raise NotImplementedError(f"Spell client not yet implemented for the '{self.dex}' DEX. "
                                      f"Please make sure that the dex entered is exactly as shown on your Alpha Homora V2 position.")

    def _get_position_info(self) -> list:
        """
        Returns position info from the HomoraBank.getPositionInfo method

        Returns (list):
            owner (address)
            collToken (address)
            collid (int)
            collateralSize (int)
        """
        return self._homora_bank.functions.getPositionInfo(self.pos_id).call()

    def _get_pool_info(self) -> dict:
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

    def _sign_and_send(self, function_call: ContractFunction) -> TransactionReceipt:
        """
        :param function_call: The uncalled and prepared contract method to sign and send
        """
        self._has_private_key()

        txn = function_call.buildTransaction({"nonce": avalanche_provider.eth.get_transaction_count(self.owner),
                                              "from": self.owner})
        signed_txn = avalanche_provider.eth.account.sign_transaction(
            txn, private_key=self.private_key
        )
        tx_hash = avalanche_provider.eth.send_raw_transaction(signed_txn.rawTransaction)

        receipt = dict(avalanche_provider.eth.wait_for_transaction_receipt(tx_hash))

        return build_receipt(receipt)

    def _has_private_key(self):
        if self.private_key is None:
            raise Exception("This method requires the position holder's private key to sign the transaction.\n"
                            "Please set a value for the 'owner_private_key' class init attribute.")


class EthereumPosition:
    def __int__(self, *a, **kw):
        raise NotImplementedError("Ethereum positions are not yet available.")


class FantomPosition:
    def __int__(self, *a, **kw):
        raise NotImplementedError("Fantom positions are not yet available.")


def get_avax_positions_by_owner(owner_address: str, owner_private_key: str = None) -> list[AvalanchePosition]:
    """
    Get all pool positions on Avalanche held by the provided owner address

    :param owner_address: The owner of the position (address str)
    :param owner_private_key: (optional) The owner's private key for using transactional methods from the AvalanchePosition object(s)
    """
    owned_positions = list(filter(lambda pos: pos["owner"].lower() == owner_address.lower(),
                                  requests.get("https://api.homora.alphaventuredao.io/v2/43114/positions").json()))
    if len(owned_positions) == 0:
        return owned_positions

    return [AvalanchePosition(position_id=position['id'],
                              owner_wallet_address=owner_address,
                              owner_private_key=owner_private_key) for position in owned_positions]
