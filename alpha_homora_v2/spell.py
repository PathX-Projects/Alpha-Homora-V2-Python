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
from .provider import avalanche_provider
from .token import ARC20Token


class SpellClient(ABC):
    """Models what each spell client should look like for functionality continuity"""

    @abstractmethod
    def __init__(self, network_chain_id: int, abi_filename: str, contract_address: str,
                 wrapper_contract_abi: str, wrapper_contract_address: str,
                 staking_contract_filename: str, staking_contract_address: str):
        self.network_chain_id = network_chain_id
        self.spell_contract = ContractInstanceFunc(avalanche_provider, abi_filename, contract_address)
        self.address = Web3.toChecksumAddress(contract_address)
        self.wrapper_contract = ContractInstanceFunc(avalanche_provider,
                                                     wrapper_contract_abi, wrapper_contract_address)
        self.staking_contract = ContractInstanceFunc(avalanche_provider,
                                                     staking_contract_filename, staking_contract_address)

    @abstractmethod
    def prepare_claim_all_rewards(self) -> ContractFunction:
        pass

    @abstractmethod
    def prepare_add_liquidity(self, pid: int,
                              tokenA_data: tuple[ARC20Token, int, int],
                              tokenB_data: tuple[ARC20Token, int, int],
                              tokenLP_data: tuple[ARC20Token, int, int] = None) -> ContractFunction:
        """
        Adds liquidity to the specified pool

        :param pid: The pool id (not position ID)
        :param tokenA_data: The first underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenB_data: The second underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenLP_data: The LP token if supplying, supply amount, and borrow amount (optional)
                             (ARC20Token object, supply_amount, borrow_amount)

        @dev-note
        The Homora docs state that borrowing LP is not supported, and that amtLPBorrow should always be 0
        """
        pass

    @abstractmethod
    def prepare_remove_liquidity(self, amt_position_remove: int,
                                 tokenA_data: tuple[ARC20Token, int],
                                 tokenB_data: tuple[ARC20Token, int],
                                 amt_lp_withdraw: int) -> ContractFunction:
        """
        Remove liquidity from specified pool

        :param amt_position_remove: The amount of the LP (position) to remove from Homora (position.get_position_info()[-1] returns the current size)
        :param tokenA_data: The first underlying token in the pool, and the amount of this token debt to repay
                            (ARC20Token, amount_repay)
        :param tokenB_data: The second underlying token in the pool, and the amount of this token debt to repay
                            (ARC20Token, amount_repay)
        :param amt_lp_withdraw: The amount of LP to withdraw
        """
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
    def __init__(self, spell_address: str, w_token_type: str, w_token_address: str,
                 staking_address: str):
        spell_contract = (TraderJoeSpellV1_ABI[0], spell_address)
        wrapper_contract = (TRADERJOE_ABI_REF[w_token_type]['wrapper'], w_token_address)
        staking_contract = (TRADERJOE_ABI_REF[w_token_type]['staking'], staking_address)

        self.w_token_type = w_token_type
        self.w_token_address = w_token_address

        super().__init__(43114, *spell_contract, *wrapper_contract, *staking_contract)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.spell_contract.encodeABI(fn_name='harvestWMasterChef')

    def prepare_add_liquidity(self, pid: int,
                              tokenA_data: tuple[ARC20Token, int, int] = None,
                              tokenB_data: tuple[ARC20Token, int, int] = None,
                              tokenLP_data: tuple[ARC20Token, int, int] = None) -> ContractFunction:
        """
        Adds liquidity to the specified pool

        :param pid: Minichef pool id (not position ID)
        :param tokenA_data: The first underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenB_data: The second underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenLP_data: The LP token if supplying, supply amount, and borrow amount (optional)
                             (ARC20Token object, supply_amount, borrow_amount)
        """

        amtAUser = tokenA_data[1]  # TokenA amount to supply
        amtABorrow = tokenA_data[2]  # Amount of tokenA to borrow

        amtBUser = tokenB_data[1]  # TokenB amount to supply
        amtBBorrow = tokenB_data[2]  # Amount of tokenB to borrow

        amtLPUser = tokenLP_data[1]  # LP token to supply
        amtLPBorrow = tokenLP_data[2]  # Amount of LP token to borrow, should always be 0

        amtAMin = 0  # Desired tokenA amount (slippage control)
        amtBMin = 0  # Desired tokenB amount (slippage control)

        # print("Attempting to add liquidity with following parameters:\n"
        #       "addLiquidityWMiniChef\n"
        #       f"tokenA Address: {tokenA_data[0].address}\n"
        #       f"tokenB Address: {tokenB_data[0].address}\n"
        #       f"amtAUser: {amtAUser, type(amtAUser)}\n"
        #       f"amtABorrow: {amtABorrow, type(amtABorrow)}\n"
        #       f"amtBUser: {amtBUser, type(amtBUser)}\n"
        #       f"amtBBorrow: {amtBBorrow, type(amtBBorrow)}\n"
        #       f"amtLPUser: {amtLPUser, type(amtLPUser)}\n"
        #       f"amtLPBorrow: {amtLPBorrow, type(amtLPBorrow)}\n"
        #       f"amtAMin: {amtAMin, type(amtAMin)}\n"
        #       f"amtBMin: {amtBMin, type(amtBMin)}\n",
        #       f"PID: {pid, type(pid)}")

        return self.spell_contract.encodeABI(fn_name='addLiquidityWMasterChef',
                                             args=[checksum(tokenA_data[0].address), checksum(tokenB_data[0].address),
                                                   (amtAUser, amtBUser, amtLPUser, amtABorrow, amtBBorrow, amtLPBorrow,
                                                    amtAMin, amtBMin), pid])

    def prepare_remove_liquidity(self, amt_position_remove: int,
                                 tokenA_data: tuple[ARC20Token, int],
                                 tokenB_data: tuple[ARC20Token, int],
                                 amt_lp_withdraw: int = 0) -> ContractFunction:
        # Closing parameters:
        amtLPTake = amt_position_remove  # Amount of position to remove from Homora
        amtLPWithdraw = amt_lp_withdraw
        amtLPRepay = 0  # Should be 0

        amtARepay = tokenA_data[1]  # Amount of token A to repay while removing liquidity
        amtBRepay = tokenB_data[1]  # Amount of token B to repay while removing liquidity

        # Slippage controls (Minimum amount allowed after final transaction); 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0

        print("Attempting to remove liquidity with following parameters:\n"
              "removeLiquidityWMasterChef\n"
              f"amtLPTake: {amtLPTake, type(amtLPTake)}\n"
              f"amtLPWithdraw: {amtLPWithdraw, type(amtLPWithdraw)}\n"
              f"amtARepay: {amtARepay, type(amtARepay)}\n"
              f"amtBRepay: {amtBRepay, type(amtBRepay)}\n"
              f"amtAMin: {amtAMin, type(amtAMin)}\n"
              f"amtBMin: {amtBMin, type(amtBMin)}")

        return self.spell_contract.encodeABI(fn_name='removeLiquidityWMasterChef',
                                             args=[checksum(tokenA_data[0].address), checksum(tokenB_data[0].address),
                                                   (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin,
                                                    amtBMin)])

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

        # print("Attempting to close position with following parameters:\n"
        #       "removeLiquidityWMasterChef\n"
        #       f"Underlying Tokens: {underlying_tokens}\n"
        #       f"amtLPTake: {amtLPTake}\n"
        #       f"amtLPWithdraw: {amtLPWithdraw}\n"
        #       f"amtARepay: {amtARepay}\n"
        #       f"amtBRepay: {amtBRepay}\n"
        #       f"amtAMin: {amtAMin}\n"
        #       f"amtBMin: {amtBMin}")

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
        return ContractInstanceFunc(avalanche_provider, TraderJoeLP_ABI[0], lp_token_address)


class PangolinV2Client(SpellClient):
    def __init__(self):
        super().__init__(43114, *PangolinSpellV2_ABI, *WMiniChefPNG_ABI, *MiniChefV2_ABI)

    def prepare_claim_all_rewards(self) -> ContractFunction:
        return self.spell_contract.encodeABI(fn_name='harvestWMiniChefRewards')

    def prepare_add_liquidity(self, pid: int,
                              tokenA_data: tuple[ARC20Token, int, int] = None,
                              tokenB_data: tuple[ARC20Token, int, int] = None,
                              tokenLP_data: tuple[ARC20Token, int, int] = None) -> ContractFunction:
        """
        Adds liquidity to the specified pool

        :param pid: Minichef pool id (not position ID)
        :param tokenA_data: The first underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenB_data: The second underlying token in the pool, supply amount, and borrow amount
                            (ARC20Token, supply_amount, borrow_amount)
        :param tokenLP_data: The LP token if supplying, supply amount, and borrow amount (optional)
                             (ARC20Token object, supply_amount, borrow_amount)
        """

        amtAUser = tokenA_data[1]  # TokenA amount to supply
        amtABorrow = tokenA_data[2]  # Amount of tokenA to borrow

        amtBUser = tokenB_data[1]  # TokenB amount to supply
        amtBBorrow = tokenB_data[2]  # Amount of tokenB to borrow

        amtLPUser = tokenLP_data[1]  # LP token to supply
        amtLPBorrow = tokenLP_data[2]  # Amount of LP token to borrow, should always be 0

        amtAMin = 0  # Desired tokenA amount (slippage control)
        amtBMin = 0  # Desired tokenB amount (slippage control)

        # print("Attempting to add liquidity with following parameters:\n"
        #       "addLiquidityWMiniChef\n"
        #       f"tokenA Address: {tokenA_data[0].address}\n"
        #       f"tokenB Address: {tokenB_data[0].address}\n"
        #       f"amtAUser: {amtAUser, type(amtAUser)}\n"
        #       f"amtABorrow: {amtABorrow, type(amtABorrow)}\n"
        #       f"amtBUser: {amtBUser, type(amtBUser)}\n"
        #       f"amtBBorrow: {amtBBorrow, type(amtBBorrow)}\n"
        #       f"amtLPUser: {amtLPUser, type(amtLPUser)}\n"
        #       f"amtLPBorrow: {amtLPBorrow, type(amtLPBorrow)}\n"
        #       f"amtAMin: {amtAMin, type(amtAMin)}\n"
        #       f"amtBMin: {amtBMin, type(amtBMin)}\n",
        #       f"PID: {pid, type(pid)}")

        return self.spell_contract.encodeABI(fn_name='addLiquidityWMiniChef',
                                             args=[checksum(tokenA_data[0].address), checksum(tokenB_data[0].address),
                                                   (amtAUser, amtBUser, amtLPUser, amtABorrow, amtBBorrow, amtLPBorrow,
                                                    amtAMin, amtBMin), pid])

    def prepare_remove_liquidity(self, amt_position_remove: int,
                                 tokenA_data: tuple[ARC20Token, int],
                                 tokenB_data: tuple[ARC20Token, int],
                                 amt_lp_withdraw: int = 0) -> ContractFunction:
        # Closing parameters:
        amtLPTake = amt_position_remove  # Amount of position to remove from Homora
        amtLPWithdraw = amt_lp_withdraw
        amtLPRepay = 0  # Should be 0

        amtARepay = tokenA_data[1]  # Amount of token A to repay while removing liquidity
        amtBRepay = tokenB_data[1]  # Amount of token B to repay while removing liquidity

        # Slippage controls (Minimum amount allowed after final transaction); 0 = No slippage controls
        amtAMin = 0
        amtBMin = 0

        print("Attempting to remove liquidity with following parameters:\n"
              "removeLiquidityWMiniChef\n"
              f"amtLPTake: {amtLPTake, type(amtLPTake)}\n"
              f"amtLPWithdraw: {amtLPWithdraw, type(amtLPWithdraw)}\n"
              f"amtARepay: {amtARepay, type(amtARepay)}\n"
              f"amtBRepay: {amtBRepay, type(amtBRepay)}\n"
              f"amtAMin: {amtAMin, type(amtAMin)}\n"
              f"amtBMin: {amtBMin, type(amtBMin)}")

        return self.spell_contract.encodeABI(fn_name='removeLiquidityWMiniChef',
                                             args=[checksum(tokenA_data[0].address), checksum(tokenB_data[0].address),
                                                   (amtLPTake, amtLPWithdraw, amtARepay, amtBRepay, amtLPRepay, amtAMin,
                                                    amtBMin)])

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
        return ContractInstanceFunc(avalanche_provider, PangolinLiquidity_ABI[0], lp_token_address)
