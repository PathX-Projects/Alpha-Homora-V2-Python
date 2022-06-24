from os.path import join, abspath, dirname
from os import getcwd, pardir
import json

import requests
from web3 import Web3
from web3.eth import Contract
from web3.middleware import geth_poa_middleware


def cov_from(amount):
    return float(Web3.fromWei(amount, 'ether'))


def get_web3_provider(network_rpc_url: str) -> Web3:
    """Returns a Web3 connection provider object"""
    provider = Web3(Web3.HTTPProvider(network_rpc_url))

    provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    return provider


def ContractInstanceFunc(web3_provider: Web3, json_abi_file, contract_address):
    """
    Set up the contract instance with the provided ABI and address

    :param web3_provider: The Web3 object used to interact with the chain
                          (ex. Web3(Web3.HTTPProvider(your_network_rpc_url)))
    :param json_abi_file: The filename for the contract's local JSON ABI file
    :param contract_address: The on-chain address for the smart contract
    """
    abi_storage_path = join(abspath(dirname(__file__)), "abi")
    with open(join(abi_storage_path, json_abi_file)) as json_file:
        contract_abi = json.load(json_file)

    contract_address = Web3.toChecksumAddress(contract_address)

    return web3_provider.eth.contract(address=contract_address, abi=contract_abi)


def store_abi(abi_url: str, abi_filename: str, abi_path: str = None) -> None:
    """
    Format and store a smart contract ABI in JSON locally

    :param abi_url: ETHERSCAN -> Export ABI -> RAW/Text Format -> Get the URL
                    (ex. "http://api.etherscan.io/api?module=contract&action=getabi&address=0xc4a59cfed3fe06bdb5c21de75a70b20db280d8fe&format=raw")
    :param abi_filename: The desired filename for local storage
    :param abi_path: The local path for the abi if one already exists and is being refactored
    """
    contract_abi = requests.get(abi_url).json()

    path = join(abspath(join(dirname(__file__), pardir)), "abi", abi_filename) if abi_path is None else abi_path
    with open(path, "w") as json_file:
        json_file.write(json.dumps(contract_abi, indent=2))
