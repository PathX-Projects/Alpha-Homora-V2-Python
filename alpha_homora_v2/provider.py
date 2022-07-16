from .util import get_web3_provider
from ._config import AVAX_RPC_URL

from web3 import Web3
from web3.middleware import geth_poa_middleware

# Avalanche Provider
try:
    avalanche_provider = Web3(Web3.HTTPProvider(AVAX_RPC_URL))
    avalanche_provider.middleware_onion.inject(geth_poa_middleware, layer=0)
except Exception as e:
    raise ConnectionError(f"Could not create Web3 provider to interact with the Avalanche Network - {e}")

# Ethereum Provider:


# Fantom Provider