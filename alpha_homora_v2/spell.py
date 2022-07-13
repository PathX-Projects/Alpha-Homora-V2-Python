import json
from os.path import join, abspath, dirname
from os import getcwd, pardir
from abc import ABC, abstractmethod

import web3.eth
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.contract import ContractFunction
from web3.constants import MAX_INT
from web3.exceptions import ContractLogicError

from .util import ContractInstanceFunc, checksum
from .resources.abi_reference import *


class SpellClient(ABC):
    """Models what each spell client should look like for functionality continuity"""

    @abstractmethod
    def __init__(self, web3_provider: Web3, network_chain_id: int, abi_filename: str, contract_address: str,
                 wrapper_contract_abi: str, wrapper_contract_address: str,
                 staking_contract_filename: str, staking_contract_address: str):
        self.w3_provider = web3_provider
        self.network_chain_id = network_chain_id
        self.spell_contract = ContractInstanceFunc(web3_provider, abi_filename, contract_address)
        self.address = Web3.toChecksumAddress(contract_address)
        self.wrapper_contract = ContractInstanceFunc(web3_provider,
                                                     wrapper_contract_abi, wrapper_contract_address)
        self.staking_contract = ContractInstanceFunc(web3_provider,
                                                     staking_contract_filename, staking_contract_address)

    @abstractmethod
    def prepare_claim_all_rewards(self) -> ContractFunction:
        pass

    @abstractmethod
    def prepare_close_position(self, underlying_tokens: list[tuple], position_size: int,
                               amtLPRepay: int = 0) -> ContractFunction:
        """
        :param underlying_tokens: List of tuples containing (token_address: str, borrow_balance: int)
        :param position_size: The position size (collateral token amt) found with AvalanchePosition.get_position_info()[-1]
        """
        pass

    def get_and_approve_pair(self, tokens: list):
        """
        Returns the LP token address for the token pair

        :param tokens: List of token addresses in the LP pool
        """
        return self.spell_contract.functions.getAndApprovePair(
            *[Web3.toChecksumAddress(address) for address in tokens]).call()

    def decode_collid(self, coll_id: int) -> list:
        """
        Get the PID for the given token id used as collateral (collid)
        Position must be on the same platform as the spell.

        :return: PID, entryRewardPerShare
        """
        return self.wrapper_contract.functions.decodeId(coll_id).call()

    @abstractmethod
    def get_pool_info(self, coll_id) -> dict:
        """
        SEE SPELL CLIENTS FOR RETURN VALUES

        Returns a dict with key value pairs since the output is variable depending on the platform.
        """
        pass

    @abstractmethod
    def get_lp_contract(self, lp_token_address: str) -> web3.eth.Contract:
        """
        Returns a contract instance for the liquidity pool matching the given address.
        This address can be found using the get_pool_info() class method in the positions.AvalanchePosition.

        :param lp_token_address: The contract address for the liquidity pool token on the Spell's network.
        :return: Contract instance for using the LP pool methods.
        """
        pass


class TraderJoeClient(SpellClient):
    def __init__(self, web3_provider: Web3, spell_address: str, w_token_type: str, w_token_address: str,
                 staking_address: str):
        spell_contract = (TraderJoeSpellV1_ABI[0], spell_address)
        wrapper_contract = (TRADERJOE_ABI_REF[w_token_type]['wrapper'], w_token_address)
        staking_contract = (TRADERJOE_ABI_REF[w_token_type]['staking'], staking_address)

        self.w_token_type = w_token_type
        self.w_token_address = w_token_address

        super().__init__(web3_provider, 43114, *spell_contract, *wrapper_contract, *staking_contract)

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
        # print(self.w_token_type, pool_info)
        if self.w_token_type in ["WMasterChef", "WMasterChefJoeV3"]:
            lpTokenAddress = pool_info[0]
            allocPoint = pool_info[1]
            lastRewardTimestamp = pool_info[2]
            accRewardPerShare = pool_info[3]
            lpAmt = None
            rewardDebt = None
            wrapper_token_per_share = None
        elif self.w_token_type == "WBoostedMasterChefJoe":
            lpTokenAddress = pool_info[0]
            allocPoint = pool_info[1]
            lastRewardTimestamp = pool_info[4]
            accRewardPerShare = pool_info[2]
            wrapper_token_per_share = self.wrapper_contract.functions.accJoePerShare().call()
            lpAmt, rewardDebt, _ = self.staking_contract.functions.userInfo(pid, checksum(self.w_token_address)).call()
        else:
            raise NotImplementedError(f"Wrapper contract for the wrapper token type '{self.w_token_type}' is not implemented.")

        return {"pid": pid, "entryRewardPerShare": entryRewardPerShare, "lpTokenAddress": lpTokenAddress,
                "allocPoint": allocPoint, "lastRewardTimestamp": lastRewardTimestamp,
                "accRewardPerShare": accRewardPerShare,
                "lpAmt": lpAmt, "rewardDebt": rewardDebt, "wrapper_token_per_share": wrapper_token_per_share}

    def get_lp_contract(self, lp_token_address: str) -> web3.eth.Contract:
        return ContractInstanceFunc(self.w3_provider, TraderJoeLP_ABI[0], lp_token_address)


class PangolinV2Client(SpellClient):
    def __init__(self, web3_provider: Web3):
        super().__init__(web3_provider, 43114, *PangolinSpellV2_ABI, *WMiniChefPNG_ABI, *MiniChefV2_ABI)

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
                                                   (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin,
                                                    amtBMin)])

    def get_pool_info(self, coll_id) -> dict:
        """
        :param coll_id: The coded collId as returned by HomoraBank.getPositionInfo()

        :return: (dict)
            pid - The decoded position ID (int)
            entryRewardPerShare - entry reward per share in PNG (int)
            accRewardPerShare - acc reward per share in PNG (int)
            lastRewardTimestamp - last reward timestamp (int)
            allocPoint - alloc point
        """
        pid, entryRewardPerShare = self.decode_collid(coll_id)
        pool_info = self.staking_contract.functions.poolInfo(pid).call()
        return {"pid": pid, "entryRewardPerShare": entryRewardPerShare, "accRewardPerShare": int(pool_info[0]),
                "lastRewardTimestamp": pool_info[1], "allocPoint": pool_info[2]}

    def get_lp_contract(self, lp_token_address: str) -> web3.eth.Contract:
        return ContractInstanceFunc(self.w3_provider, PangolinLiquidity_ABI[0], lp_token_address)
