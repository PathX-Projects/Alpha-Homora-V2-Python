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

    def __init__(self, web3_provider: Web3, abi_filename: str, contract_address: str,
                 coll_contract_abi_filename: str, coll_contract_address: str,
                 staking_contract_abi_filename: str, staking_contract_address: str):
        self.spell_contract = ContractInstanceFunc(web3_provider,
                                             abi_filename, contract_address)
        self.address = Web3.toChecksumAddress(contract_address)
        self.coll_contract = ContractInstanceFunc(web3_provider,
                                                  coll_contract_abi_filename, coll_contract_address)
        self.staking_contract = ContractInstanceFunc(web3_provider,
                                                     staking_contract_abi_filename, staking_contract_address)

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
        return self.spell_contract.functions.getAndApprovePair(*[Web3.toChecksumAddress(address) for address in tokens]).call()

    def decode_collid(self, coll_id: int) -> list:
        """
        Get the PID for the given token id used as collateral (collid)
        Position must be on the same platform as the spell.

        :return: PID, entryRewardPerShare
        """
        return self.coll_contract.functions.decodeId(coll_id).call()

    def get_pool_info(self, coll_id) -> dict:
        """
        SEE SPELL CLIENTS FOR RETURN VALUES

        Returns a dict with key value pairs since the output is variable depending on the platform.
        """


class SushiswapSpellsV1Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *SushiswapSpellV1_ABI)


class TraderJoeV1Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *TraderJoeSpellV1_ABI, *WMasterchefJoeV2_ABI, *MasterChefJoeV2_ABI)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.spell_contract.encodeABI(fn_name='harvestWMasterChef')

    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:

        # Closing parameters:
        amtLPTake = position_size  # int(MAX_INT, 16)
        amtLPWithdraw = 0  # int(MAX_INT, 16)
        amtARepay = underlying_tokens[0][1]
        if amtARepay > 0:
            amtARepay = int(MAX_INT, 16)
        amtBRepay = underlying_tokens[1][1]
        if amtBRepay > 0:
            amtBRepay = int(MAX_INT, 16)

        # Slippage controls (Minimum amount allowed after final transaction); 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0
        
        print("Attempting to close position with following parameters:\n"
              "removeLiquidityWMasterChef\n"
              f"Underlying Tokens: {underlying_tokens}\n"
              f"amtLPTake: {amtLPTake}\n"
              f"amtLPWithdraw: {amtLPWithdraw}\n"
              f"amtARepay: {amtARepay}\n"
              f"amtBRepay: {amtBRepay}\n"
              f"amtAMin: {amtAMin}\n"
              f"amtBMin: {amtBMin}")

        return self.spell_contract.encodeABI(fn_name='removeLiquidityWMasterChef',
                                             args=[underlying_tokens[0][0], underlying_tokens[1][0],
                                             (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin, amtBMin)])

    def get_pool_info(self, coll_id) -> dict:
        """
        :param coll_id: The coded collId as returned by HomoraBank.getPositionInfo()

        :return: (dict)
            pid - The decoded position ID (int)
            entryRewardPerShare - entry reward per share in JOE (int)
            lpTokenAddress - liquidity pool token address (str)
            allocPoint - alloc point
            lastRewardTimestamp - last reward timestamp (int)
            accRewardPerShare - acc reward (JOE) per share (str)
            rewarderAddress - rewarder address (str)
        """
        pid, entryRewardPerShare = self.decode_collid(coll_id)
        pool_info = self.staking_contract.functions.poolInfo(pid).call()
        # return pid, entryRewardPerShare, *pool_info
        return {"pid": pid, "entryRewardPerShare": entryRewardPerShare, "lpTokenAddress": pool_info[0],
                "allocPoint": pool_info[1], "lastRewardTimestamp": pool_info[2], "accRewardPerShare": pool_info[3],
                "rewarderAddress": pool_info[4]}


class PangolinV2Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, *PangolinSpellV2_ABI, *WMiniChefPNG_ABI, *MiniChefV2_ABI)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.spell_contract.encodeABI(fn_name='harvestWMiniChefRewards')

    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:

        # Closing parameters:
        amtLPTake = position_size  # int(MAX_INT, 16)
        amtLPWithdraw = 0  # int(MAX_INT, 16)
        amtARepay = underlying_tokens[0][1]
        if amtARepay > 0:
            amtARepay = int(MAX_INT, 16)
        amtBRepay = underlying_tokens[1][1]
        if amtBRepay > 0:
            amtBRepay = int(MAX_INT, 16)

        # Slippage controls (Minimum amount allowed after final transaction); 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0

        print("Attempting to close position with following parameters:\n"
              "removeLiquidityWMiniChef\n"
              f"Underlying Tokens: {underlying_tokens}\n"
              f"amtLPTake: {amtLPTake}\n"
              f"amtLPWithdraw: {amtLPWithdraw}\n"
              f"amtARepay: {amtARepay}\n"
              f"amtBRepay: {amtBRepay}\n"
              f"amtAMin: {amtAMin}\n"
              f"amtBMin: {amtBMin}")

        return self.spell_contract.encodeABI(fn_name='removeLiquidityWMiniChef',
                                             args=[underlying_tokens[0][0], underlying_tokens[1][0],
                                             (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin, amtBMin)])

    def get_pool_info(self, coll_id) -> dict:
        """
        :param coll_id: The coded collId as returned by HomoraBank.getPositionInfo()

        :return: (dict)
            pid - The decoded position ID (int)
            entryRewardPerShare - entry reward per share in PNG (int)
            accRewardPerShare - acc reward per share in PNG (str)
            lastRewardTimestamp - last reward timestamp (int)
            allocPoint - alloc point
        """
        pid, entryRewardPerShare = self.decode_collid(coll_id)
        pool_info = self.staking_contract.functions.poolInfo(pid).call()
        # return pid, entryRewardPerShare, *pool_info
        return {"pid": pid, "entryRewardPerShare": entryRewardPerShare, "accRewardPerShare": pool_info[0],
                "lastRewardTimestamp": pool_info[1], "allocPoint": pool_info[2]}
