from os.path import join, abspath, dirname
from os import getcwd, pardir
import json
from typing import Union
import csv

import requests
from web3 import Web3
from web3.middleware import geth_poa_middleware
import web3.eth


def cov_from(amount):
    return float(Web3.fromWei(amount, 'ether'))


def checksum(address: str) -> str:
    return Web3.toChecksumAddress(address)


def get_web3_provider(network_rpc_url: str) -> Web3:
    """Returns a Web3 connection provider object"""
    provider = Web3(Web3.HTTPProvider(network_rpc_url))

    provider.middleware_onion.inject(geth_poa_middleware, layer=0)

    return provider


def ContractInstanceFunc(web3_provider: Web3, json_abi_file, contract_address) -> web3.eth.Contract:
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

    path = join(join(dirname(__file__)), "abi", abi_filename) if abi_path is None else abi_path
    with open(path, "w") as json_file:
        json_file.write(json.dumps(contract_abi, indent=2))


def get_token_info_from_ref(identifier: str) -> Union[dict, None]:
    """
    Get the token info row (dict) from the reference file (resources/token_metadata.csv)
    
    :param identifier: Either the token symbol or the token address
    :return: The token info as a dict:
        {'symbol (str)', 'coingecko_id (str)', 'precision (str need to convert to int)', 'address (str)'}
    """
    path = join(abspath((dirname(__file__))), "resources", "token_metadata.csv")
    with open(path) as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            if row["symbol"].upper() == identifier.upper() or row['address'] == identifier.lower():
                return row
    return None


def get_all_pool_underlying_token_addresses() -> dict:
    """Did not use exchange identifier because this was used to aggregate all supported tokens for the reference in resources"""
    r = requests.get("https://homora-api.alphafinance.io/v2/43114/pools").json()
    return {pool['name']: [(pool['name'].split('/')[i], token) for i, token in enumerate(pool['tokens'])] for pool in r}


def get_avalanche_pool_wtoken_types(dex: str):
    return list(set(pool['wTokenType'] for pool in requests.get("https://homora-api.alphafinance.io/v2/43114/pools").json() if pool['exchange']['name'] == dex))
