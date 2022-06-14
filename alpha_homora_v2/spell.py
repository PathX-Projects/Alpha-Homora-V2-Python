import json
from os.path import join, abspath, dirname
from os import getcwd, pardir

from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.contract import ContractFunction
from web3.constants import MAX_INT
from web3.exceptions import ContractLogicError

from .util import ContractInstanceFunc
from .resources.abi_reference import *


class SpellClient:
    """Models what each spell client should look like for functionality continuity"""

    def __init__(self, web3_provider: Web3, abi_filename: str, contract_address: str):
        self.contract = ContractInstanceFunc(json_abi_file=abi_filename,
                                             contract_address=contract_address,
                                             web3_provider=web3_provider)
        self.address = Web3.toChecksumAddress(contract_address)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        pass

    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:
        """
        :param underlying_tokens: List of tuples containing (token_address: str, borrow_balance: int)
        :param position_size: The position size (collateral token amt) found with AlphaHomoraV2Position.get_position_info()[-1]
        """
        pass

    def get_and_approve_pair(self, tokens: list):
        """
        Returns the LP token address for the token pair

        :param tokens: List of token addresses in the LP pool
        """
        return self.contract.functions.getAndApprovePair(*[Web3.toChecksumAddress(address) for address in tokens]).call()


class SushiswapSpellsV1Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *SushiswapSpellV1_ABI)


class TraderJoeV1Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *TraderJoeSpellV1_ABI)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.contract.encodeABI(fn_name='harvestWMasterChef')

    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:

        # Closing parameters:
        amtLPTake = position_size  # int(MAX_INT, 16)
        amtLPWithdraw = 0  # int(MAX_INT, 16)
        amtARepay = underlying_tokens[0][1]
        amtBRepay = underlying_tokens[1][1]

        # Slippage controls (Minimum amount allowed after final transaction) 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0

        return self.contract.encodeABI(fn_name='removeLiquidityWMasterChef',
                                       args=[underlying_tokens[0][0], underlying_tokens[1][0],
                                             (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin, amtBMin)])


class PangolinV2Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *PangolinSpellV2_ABI)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.contract.encodeABI(fn_name='harvestWMiniChefRewards')

    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:

        # Closing parameters:
        amtLPTake = position_size  # int(MAX_INT, 16)
        amtLPWithdraw = 0  # int(MAX_INT, 16)
        amtARepay = underlying_tokens[0][1]
        amtBRepay = underlying_tokens[1][1]

        # Slippage controls (Minimum amount allowed after final transaction) 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0

        return self.contract.encodeABI(fn_name='removeLiquidityWMiniChef',
                                       args=[underlying_tokens[0][0], underlying_tokens[1][0],
                                             (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin, amtBMin)])