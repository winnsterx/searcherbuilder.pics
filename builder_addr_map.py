"""
IMPORTANT THAT ALL THESE ADDRESSES ARE IN LOWERCASE
Create PR to add a known builder: fee_recipient_addr
BUILDER_ADDR_MAP is used to check whether the builder is the fee recipient. 
Note: imposter can copy the fee recipient addr and extra data of a real builder, and we dont
have a method to check that atm. However, since its a relatively small phenonmenon that is financially
pointless, we r not prioritizing adding this check.
"""


# Builder: FEE RECIPIENT ADDRESS
BUILDER_0X69 = "0x690b9a9e9aa1c9db991c7721a92d351db4fac990"
BEAVERBUILD = "0x95222290dd7278aa3ddd389cc1e1d165cc4bafe5"
RSYNC = "0x1f9090aae28b8a3dceadf281b0f12828e676c326"
FLASHBOTS = "0xdafea492d9c6733ae3d56b7ed1adb60692c98bc5"
FLASHBOTS_SGX = "0xc83dad6e38bf7f2d79f2a51dd3c4be3f530965d6"
TITAN = "0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97"
BLOXROUTE_MAX_PROFIT = "0xf2f5c73fa04406b1995e397b55c24ab1f3ea726c"
BLOXROUTE_REGULATED = "0x199d5ed7f45f4ee35960cf22eade2076e95b253f"
BLOCKNATIVE = "0xbaf6dc2e647aeb6f510f9e318856a1bcd66c5e19"
F1B = "0x5124fcc2b3f99f571ad67d075643c743f38f1c34"
BUILDAI = "0xbd3afb0bb76683ecb4225f9dbc91f998713c3b01"
ETHBUILDER = "0xfeebabe6b0418ec13b30aadf129f5dcdd4f70cea"
BOBABUILDER = "0x3b64216ad1a58f61538b4fa1b27327675ab7ed67"
PAYLOAD = "0xce0babc8398144aa98d9210d595e3a9714910748"
BEE = "0x3bee5122e2a2fbe11287aafb0cb918e22abb5436"
EDEN = "0xaab27b150451726ec7738aa1d0a94505c8729bd1"
LIGHTSPEEDBUILDER_2 = "0xd2090025857b9c7b24387741f120538e928a3a59"
LIGHTSPEEDBUILDER_1 = "0x7316b4e0f0d4b19b4ac13895224cd522d785e51d"
ANTBUILDER = "0xc9d945721ed37c6451e457b3c7f1e0cec42417fb"
THREETHREES = "0x333333f332a06ecb5d20d35da44ba07986d6e203"
UWUBUILDER = "0xd0d0ce5c067eeea7487ca11153247905364eeb12"
GAMBIT = "0x0aa8ebb6ad5a8e499e550ae2c461197624c6e667"
NFACTORIAL = "0x3b7faec3181114a99c243608bc822c5436441fff"

LIDO = "0x388c818ca8b9251b393131c08a736a67ccb19297"
STAKEFISH = "0xffee087852cb4898e6c3532e776e68bc68b1143b"

BUILDER_ADDR_MAP = {
    """
    Builder extra data field: fee recipient addr
    ALL MUST BE IN LOWER CASE
    Key: extraData field of a block. Must be in minimally unique pattern. (i.e. uwu for uwubuilders and matches to no other builder)
        If a situation where some kind of variation exists for the same builder, add them both pointing to the same addr (like eth-builder and ethbuilder)
    Value: known fee recipient addr of builder. 
        If >1 addrs exist for a builder, add it to a list
    """
    "beaverbuild": [BEAVERBUILD],
    "builder0x69": [BUILDER_0X69],
    "rsync": [RSYNC],
    "blocknative": [BLOCKNATIVE],
    "titan": [TITAN],
    "bloxroute": [BLOXROUTE_MAX_PROFIT],
    "bloxr": [BLOXROUTE_REGULATED],
    "illuminate": [FLASHBOTS],
    "buildai": [BUILDAI],
    "f1b": [F1B],
    "eden": [EDEN],
    "eth-builder": [ETHBUILDER],
    "ethbuilder": [ETHBUILDER],
    "boba": [BOBABUILDER],
    "lightspeed": [LIGHTSPEEDBUILDER_1, LIGHTSPEEDBUILDER_2],
    "payload": [PAYLOAD],
    "gambit": [GAMBIT],
    "bob": [BOBABUILDER],
    "nfactorial": [NFACTORIAL],
    "antbuilder": [ANTBUILDER],
    "uwu": [UWUBUILDER],
}
