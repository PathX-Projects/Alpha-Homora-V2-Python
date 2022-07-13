from dataclasses import dataclass
from hexbytes import HexBytes

@dataclass
class TransactionReceipt:
    """
    Dataclass to model the important receipt return parameters from the Web3.eth.wait_for_transaction_receipt()
    https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.wait_for_transaction_receipt
    """
    blockHash: HexBytes  # Access the string by using blockHash.hex()
    blockNumber: int
    contractAddress: str
    cumulativeGasUsed: int
    effectiveGasPrice: int
    fromAddress: str
    gasUsed: str
    logs: list
    status: int
    toAddress: str
    transactionHash: HexBytes  # Access the string by using transactionHash.hex()
    transactionIndex: int
    type: str


def build_receipt(d: dict) -> TransactionReceipt:
    """
    :param d: Transaction receipt JSON data as returned by Web3.eth.wait_for_transaction_receipt():
              https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.wait_for_transaction_receipt
    :return: TransactionReceipt class to model the transaction
    """

    return TransactionReceipt(*[v for k, v in d.items()])