import json
from os.path import join, abspath, dirname
from os import getcwd, pardir
from typing import Optional

from .resources.abi_reference import *
from .util import ContractInstanceFunc
from .spell import SpellClient, PangolinV2Client, TraderJoeV1Client

import requests
from web3 import Web3
from web3.contract import ContractFunction
from web3.constants import MAX_INT
from web3.exceptions import ContractLogicError


class AlphaHomoraV2Position:
    def __init__(self, web3_provider: Web3, position_id: int, position_symbol: str, dex: str, owner_wallet_address: str,
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
        self.symbol = position_symbol
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
            spell_address = Web3.toChecksumAddress(self.platform.contract.address)

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

    def claim_all_rewards(self) -> tuple[str, dict]:
        """
        Harvests available position rewards

        Returns:
            - transaction hash
            - transaction receipt
        """

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

    def repay_debt(self, amount: float):
        raise NotImplementedError

    def deposit_collateral(self, amount: float):
        raise NotImplementedError

    def withdraw_collateral(self, amount: float):
        raise NotImplementedError

    """ ------------------------------------------ UTILITY ------------------------------------------ """
    def get_platform(self, identifier: str) -> SpellClient:
        """Determine what dex the position is on (i.e. Uniswap, Sushiswap, etc)"""
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

        w_token_address = self.get_position_info()[1].lower()
        for pool in r.json():
            # Criteria:
            if pool['wTokenAddress'].lower() == w_token_address and pool['name'] == self.symbol:
                # issue with the Trader Joe client due to mismatch
                return pool
        else:
            raise Exception(f"No {self.symbol} pool found with the wToken address: {w_token_address}")

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

        return decoded_bank_transaction, self.platform.contract.decode_function_input(encoded_contract_data)