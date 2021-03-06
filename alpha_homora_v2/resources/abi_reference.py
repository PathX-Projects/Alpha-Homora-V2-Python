"""
Config file contains tuples:
    (ABI filename, contract address)
For each required ABI.

These pairs can be passed into the ContractInstanceFunc class using unpacking e.g. ContractInstanceFunc(*HomoraBank_ABI)
"""

# Alpha Homora
HomoraBank_ABI = 'HomoraBankABI.json', '0x376d16C7dE138B01455a51dA79AD65806E9cd694'
AggregatorOracle_ABI = 'AggregatorOracle_ABI.json','0xc842CC25FE89F0A60Fe9C1fd6483B6971020Eb3A'
ISafeOracle_ABI = 'ISafeOracle_ABI.json', '0xdB90a1A31ff72976b6F2f009e77131673404180b'
WERC20_ABI = 'WERC20ABI.json', '0x496Aa991Cf3952264f284355371cD190ddcc8588'

# Avalanche - Trader Joe:
WMasterchefJoeV2_ABI = "WMasterchefJoeV2_ABI.json", '0xB41DE9c1f50697cC3Fd63F24EdE2B40f6269CBcb'
MasterChefJoeV2_ABI = "MasterChefJoeV2_ABI.json", "0xd6a4F121CA35509aF06A0Be99093d08462f53052"
TraderJoeLP_ABI = 'TraderJoeLP_ABI.json', None
TRADERJOE_ABI_REF = {"WMasterChef":
                         {"wrapper": WMasterchefJoeV2_ABI[0], "staking": MasterChefJoeV2_ABI[0]},
                     "WMasterChefJoeV3":
                         {"wrapper": "WMasterChefJoeV3_ABI.json", "staking": "MasterChefJoeV3_ABI.json"},
                     "WBoostedMasterChefJoe":
                         {"wrapper": "WBoostedMasterChefJoe_ABI.json", "staking": "BoostedMasterChefJoe_custom_ABI.json"}}

# Avalanche - Pangolin
TraderJoeSpellV1_ABI = 'TraderJoeSpellV1ABI.json', '0xdBc2Aa11Aa01bAa22892dE745C661Db9f204b2cd'
PangolinSpellV2_ABI = 'PangolinSpellV2.json', '0x966bbec3ac35452133B5c236b4139C07b1e2c9b1'
WMiniChefPNG_ABI = 'WMiniChefPNG.json', '0xa67CF61b0b9BC39c6df04095A118e53BFb9303c7'
USDCe_ABI = 'USDC.e_ABI.json', '0xA7D7079b0FEaD91F3e65f86E8915Cb59c1a4C664'
MiniChefV2_ABI = 'Minichef_v2ABI.json', '0x1f806f7C8dED893fd3caE279191ad7Aa3798E928'
PangolinLiquidity_ABI = 'PangolinLiquidityABI.json', None

