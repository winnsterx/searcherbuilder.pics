import requests 
import json 
from collections import defaultdict

# to do
# verify that the data returned is correct 
# trim out the one-time appearances 
# in cases where block.miner/fee_recipient is the proposer, those blocks r ignored 

# table: 
common_addrs = {
    "beaverbuild": {
        # addr: int
    },
    "builder0x69": {},
    "rsync": {},
    "flashbots": {},
    "ethbuilder": {},
    "others": {}
}

block_to_builder = {}

common_contracts = {
    "0xef1c6e67703c7bd7107eed8303fbe6ec2554bf6b": "uniswap_router",
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "uniswap_router_2",
    "0x881d40237659c251811cec9c364ef91dc08d300c": "metamask_router",
    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45": "uniswap_router_3",
    "0xe66B31678d6C16E9ebf358268a790B763C133750": "coinbase_proxy",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "one_inch",
    "0x6131b5fae19ea4f9d964eac0408e4408b66337b5": "kyberswap"
}

common_contract_addrs = set([k.lower() for k in common_contracts.keys()])

def mapBlockToBuilder():
    global block_to_builder
    jsonfile = "block_to_builder_50k.json"
    with open(jsonfile) as file:
        block_to_builder = json.load(file) 
        # print(block_to_builder["17227156"])

def getBlockBuilder(block_number):
    builder = block_to_builder[block_number].lower()
    if builder == "0x690b9a9e9aa1c9db991c7721a92d351db4fac990":
        return "builder0x69"
    elif builder == "0x95222290dd7278aa3ddd389cc1e1d165cc4bafe5":
        return "beaverbuild"
    elif builder == "0x1f9090aae28b8a3dceadf281b0f12828e676c326":
        return "rsync"
    elif builder == "0xdafea492d9c6733ae3d56b7ed1adb60692c98bc5":
        return "flashbots"
    elif builder == "0xfeebabe6b0418ec13b30aadf129f5dcdd4f70cea":
        return "ethbuilder"
    else:
        return "others"


def incrementBotCount(builder, addr_from, addr_to):
    global common_addrs
    if addr_from not in common_addrs[builder] and addr_from not in common_contract_addrs:
        common_addrs[builder][addr_from] = 0 
    
    if addr_from not in common_contract_addrs:
        common_addrs[builder][addr_from] += 1

    if addr_to not in common_addrs[builder] and addr_from not in common_contract_addrs:
        common_addrs[builder][addr_to] = 0 

    if addr_to not in common_contract_addrs:
        common_addrs[builder][addr_to] += 1


def chartOneBlock(block_number):
    global common_addrs
    url = "https://data.zeromev.org/v1/mevBlock"
    payload = {
        'block_number': block_number,
        "count": "1"
    }
    res = requests.get(url, params=payload)

    if res.status_code == 200:
        data = res.json()
        block_number = ""
        builder = ""
        for tx in data:
            if block_number == "":
                block_number = str(tx['block_number'])
                builder = getBlockBuilder(block_number)
                print(block_number, builder)
            addr_from = tx['address_from'].lower()
            addr_to = tx['address_to'].lower()

            incrementBotCount(builder, addr_from, addr_to)


    else: 
        print(res.status_code)


def createFrequencyChart():
    blocks = list(block_to_builder.keys())

    for b in blocks[:1000]:
        chartOneBlock(b)

    filter_one_time = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 1} for outer_k, outer_v in common_addrs.items()}

    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filter_one_time.items()}

    with open('result.json', 'w') as fp: 
        json.dump(ordered_addrs, fp)

mapBlockToBuilder()
createFrequencyChart()
