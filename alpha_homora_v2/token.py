from .util import checksum, ContractInstanceFunc
from .provider import avalanche_provider

from web3.contract import ContractFunction


class ARC20Token:
    """Models all of the needed methods by this package to interact with ARC20 tokens"""
    def __init__(self, address: str):
        self.address = checksum(address)
        self.contract = ContractInstanceFunc(avalanche_provider, "ERC20_ABI.json", address)

    def name(self) -> str:
        return self.contract.functions.name().call()

    def symbol(self) -> str:
        return self.contract.functions.symbol().call()

    def decimals(self) -> int:
        return self.contract.functions.decimals().call()

    def balanceOf(self, owner_address: str) -> int:
        return self.contract.functions.balanceOf(checksum(owner_address)).call()

    # Uncalled - should be signed and sent by the position class in position.py
    def prepare_approve(self, spender_address: str, token_amount: int = None) -> ContractFunction:
        if token_amount is None:
            token_amount = 2 ** 256 - 1
        return self.contract.functions.approve(checksum(spender_address), token_amount)
