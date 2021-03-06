<!-- PROJECT HEADER -->
<div align="center">
  <a href ="https://homora-v2.alphaventuredao.io/"><img src="https://github.com/PathX-Projects/Alpha-Homora-V2-Python/blob/main/img/ahv2_logo.png?raw=true" alt="Alpha Homora V2 Logo" height="200"></a>
  <br/>
  <h2 align="center"><strong>Alpha-Homora-V2-Python</strong></h2>
    <a href="https://homora-v2.alphaventuredao.io/"><img src="https://img.shields.io/website?down_color=red&down_message=Disconnected&label=Alpha%20Homora%20V2&up_color=blue&up_message=Online&url=https%3A%2F%2Fhomora-v2.alphaventuredao.io%2F"/></a>
    <img src="https://img.shields.io/badge/Python-3.9%2B-yellow"/>
    <a href="https://github.com/PathX-Projects/Alpha-Homora-V2-Python/issues"><img src="https://img.shields.io/github/issues/PathX-Projects/Alpha-Homora-V2-Python?color=red"/></a>
    <a href="https://badge.fury.io/py/alpha-homora-v2"><img src="https://badge.fury.io/py/alpha-homora-v2.svg" alt="PyPI version"></a>
    <p align="center">
        A Python3.9+ package that wraps Alpha Homora V2 <b><i>yield farming positions</i></b> to simplify interaction with their smart contracts in your Python projects.
    </p>
    <h3><strong>Current Features</strong></h3>
    <i>Rewards Value | Position Value | Debt & Leverage Ratio | Pool Info | Current APY</i><br>
    <i>Harvest Rewards | Close Position | Add & Remove Liquidity</i><br>
    <h3><strong>Current Supported Networks</strong></h3>
    <i>Avalanche</i><br>
    <i><del>Ethereum</del> (WIP)</i><br>
</div>
<br>

<!-- TABLE OF CONTENTS -->
### Table of Contents
<details>
  <ol>
    <li><a href="#overview">Overview</a></li>
    <li><a href="#installation">Installation</a></li>
    <li><a href="#usage">Usage</a></li>
    <ol>
      <li><a href="#avalanche">Avalanche</a></li>
    </ol>
    <li><a href="#uninstallation">Uninstallation</a></li>
    <li><a href="#features">Roadmap</a></li>
    <li><a href="#contribution">Contribution</a></li>
  </ol>
</details>

## Overview:

This project aims to simplify interaction with Alpha Homora V2's yield farming position smart contracts in your Python projects by packaging all of the necessary functionality and more into a single Python package built on top of [web3.py](https://web3py.readthedocs.io/en/stable/), instead of brownie.

![Positions Image](img/site.png)

Currently, only **yield farming** positions are supported, but we plan to integrate lending positions once the functionality for yield farming positions is available on Avalanche and Ethereum.

### Use cases include:
- Algorithmic liquidity management
- Automated position closing
- Position analytics

## Installation:

This package is set up to be installed using the `pip` package manager.

1. Ensure that you have Python 3.9+ installed. If not, you can download [here](https://www.python.org/downloads/release/python-3912/). The syntax is dependent on features added in this recent version.

2. Install the package using pip:
    ```bash
    pip install --upgrade alpha-homora-v2
    ```

    When updates are made to the package, the version will automatically be incremented so that in order to get the newest version on your end, you can simply use the same installation command and your pip will detect and update to the newest version.

## Usage:

How to use the package:

### Avalanche

1. Import the AvalanchePosition class into your Python script:
    ```python
    from alpha_homora_v2 import AvalanchePosition
    ```

<!-- 2. **(Optional)** Instantiate your custom Web3 provider object to interact with the network:
    ```python
   from alpha_homora_v2.util import get_web3_provider
   
    NETWORK_RPC_URL = "your_rpc_url"
    provider = get_web3_provider(NETWORK_RPC_URL)
    ``` -->
2. Creating an [AvalanchePosition](alpha_homora_v2/position.py) instance requires the following:
    - Your position ID (an integer)
        - This ID should match your position on Alpha Homora, without the "#"
          ![demo](https://github.com/PathX-Projects/Alpha-Homora-V2-Python/blob/main/img/id_highlight.png?raw=true)
      
    <!--- DEPRECATED
    - The token symbol/pair (a string)
        - This parameter should exactly match the token symbol/pair displayed on your Alpha Homora as shown below.
        - ![demo](img/token_highlight.png)
    -->
    <!--- DEPRECATED
    - The DEX identifier (a string)
        - This parameter should exactly match the DEX identifier displayed on your Alpha Homora position as shown below.
        - ![demo](img/dex_highlight.png)
    -->

    - your public wallet key
    - **(Optional)** your private wallet key
        - Your private key is required to sign transactional methods
    <!-- - **(Optional)** A web3 provider object
      - If none is passed, an HTTP provider will be created with the [default Avalanche RPC URL](https://api.avax.network/ext/bc/C/rpc) -->

    Once you've gathered all of these variables, you can create the position instance like this example below:
    ```python
    position = AvalanchePosition(
               position_id=11049,
               owner_wallet_address="0x...",
               owner_private_key="123abc456efg789hij...") # <- Optional - see step 4
    ```
    <!-- web3_provider=provider)  # <- Optional If you'd like to use a custom provider -->
3. Alternatively, get all open positions ([AvalanchePosition](alpha_homora_v2/position.py) objects) by owner wallet address:
   ```python
   from alpha_homora_v2.position import get_avax_positions_by_owner
   
   positions = get_avax_positions_by_owner(owner_address="owner_wallet_address",
                                           owner_private_key="owner_private_key", # <- Optional
                                           )
   
   # NOTE: Passing the private key is optional, but required if you want to use transactional methods on the returned AvalanchePosition object(s).
   ```
4. Use your position instance(s) to interact with the Alpha Homora V2 position smart contracts on the network:
   - Transactional Methods:
     - Return a [TransactionReceipt](alpha_homora_v2/receipt.py) object upon success
     - Private wallet key ***required*** for use to sign transactions
     - See the documentation in the [AvalanchePosition](alpha_homora_v2/position.py) class for function parameters.
     ```python
     # Add liquidity to the LP
     position.add(params)

     # Remove liquidity from the LP
     position.remove(params)

     # Harvest available rewards:
     position.harvest()

     # Close the position:
     position.close()
     ```
   - Informational Methods
     - Return JSON data
     - Private wallet key ***not required*** for use
     - See [`examples/position_info.ipynb`](https://github.com/PathX-Projects/Alpha-Homora-V2-Python/blob/development/examples/avalanche/position_info.ipynb) for output examples.
     ```python
     # Get position value (equity, debt, and position value):
     position.get_position_value()

     # Get value of harvestable rewards:
     position.get_rewards_value()

     # Get current debt ratio:
     position.get_debt_ratio()

     # Get the current leverage ratio:
     position.get_leverage_ratio()

     # Get current pool APY
     position.get_current_apy()

     # Get underlying tokens and LP for the pool:
     position.get_pool_tokens()

     # Get the debt of each token in the position (token, debt_uint256, debt_token, debt_usd):
     position.get_token_debts()
     # Alternatively, get the debt of a single token:
     position.get_token_debts(token_address)

     # Get all token borrow rates from CREAM:
     position.get_cream_borrow_rates()

     # get LP pool info:
     position.pool
     ```

## Uninstallation:

Uninstall the package like any other Python package using the pip uninstall command:
```bash
pip uninstall alpha-homora-v2
```

## Features:

- [x] Avalanche:
    - [x] Get all open positions by owner wallet address
    - [x] Harvest Position Rewards
    - [x] Close Position
    - [x] Get position value of equity and debt
    - [x] Get current debt ratio
    - [x] Get outstanding rewards value in native rewards token and USD
    - [x] Add Liquidity
    - [x] Remove Liquidity
    - [x] Get aggregate pool APY (incl. borrowAPY)
- [ ] Ethereum:
    - [ ] Get all open positions by owner wallet address
    - [ ] Harvest Position Rewards
    - [ ] Close Position
    - [ ] Get position value of equity and debt
    - [ ] Get current debt ratio
    - [ ] Get outstanding rewards value in native rewards token and USD
    - [ ] Add Liquidity
    - [ ] Remove Liquidity
    - [ ] Get aggregate pool APY (incl. borrowAPY)

## Contribution:

Contributions are welcome! Please read the [contribution guidelines](CONTRIBUTING.md) to learn more about how to contribute to this project.

Get in touch: [hschickdevs@gmail.com](mailto:hschickdevs@gmail.com)
