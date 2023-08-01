# To estimate amount of CEX-DEX Arbs during a historical period
# we utilise cefi and defi price oracles to determine price differences
# if the price differences of CEX and DEX right before block N > threshold 
# any relevant trade in block is considered a CEX-DEX arb

# running thru txs between block 17616021 and 17666420
# subject to further changes
import requests
import json
from collections import defaultdict
import searcher_db
import fetch_blocks
import analysis
import constants
import secret_keys

START_BLOCK = 17616021
END_BLOCK = 17666420

GAS_PRICE_MULTIPLIER = 1.20

# use this api to get internal tx https://docs.alchemy.com/reference/alchemy-getassettransfers

# zeromev: returns block, tx index, addrs 
    # need gas fee, coinbase transfer, number of swaps, base fee of blocks 
    # get all blocks info, get gas fees, avg/median fee, 
    # collect swap txs later 

# return sth similar to builder: searcher frequency map 
def get_swaps(block_number):
    swaps = []
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    payload = {
        'block_number': block_number,
        "count": "1"
    }
    res = requests.get(zeromev_url, params=payload)
    if res.status_code == 200:
        data = res.json()
        for tx in data:
            if tx['mev_type'] == "swap" and tx["address_to"] not in constants.COMMON_CONTRACTS:
                swaps.append(tx) 
        return swaps                        
    else: 
        print("error w requesting zeromev:", res.status_code)


def calculate_block_median_gas_price(transactions):
    gas_prices = sorted(tx['gasPrice'] for tx in transactions)
    mid = len(gas_prices) // 2
    if len (gas_prices) % 2 == 0:
        return (gas_prices[mid - 1] + gas_prices[mid]) / 2
    else:
        return gas_prices[mid]

        

def simplify_transfers(transfers):
    simplified = [
        {
            "hash": tr["hash"],
            "from": tr["from"],
            "to": tr["to"],
            "value": tr["value"]
        }
        for _, tr in enumerate(transfers)
    ]
    return simplified


def get_internal_transfers_in_block(block_number, builder):
    headers = { "accept": "application/json", "content-type": "application/json" }
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getAssetTransfers",
        "params": [
            {
                "category": ["internal"],
                "toAddress": builder, 
                "fromBlock": hex(block_number),
                "toBlock": hex(block_number)
            }
        ]
    }
    response = requests.post(secret_keys.ALCHEMY, json=payload, headers=headers)
    transfers = response.json()["result"]["transfers"]
    simplified_transfers = simplify_transfers(transfers)

    transfer_set = set(tr['hash'] for tr in simplified_transfers)
    return simplified_transfers, transfer_set


def analyze_block(block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe):

    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    builder = searcher_db.map_extra_data_to_builder(extra_data, block["feeRecipient"])
    
    fee_recipient = block["feeRecipient"]
    transfer_list, transfer_set = get_internal_transfers_in_block(block_number, fee_recipient)

    swap_txs = get_swaps(block_number)
    median_gas_price = calculate_block_median_gas_price(block["transactions"])
    print(median_gas_price)

    # only consider txs labeled as swap by zeromev
    for swap in swap_txs:
        tx = block["transactions"][swap['tx_index']] 
        if tx["hash"] in transfer_set:
            builder_swapper_map[builder][tx["to"]] += 1
            coinbase_bribe.add(tx["hash"])
        elif tx["gasPrice"] > median_gas_price * GAS_PRICE_MULTIPLIER:
            print(tx["hash"], tx["gasPrice"])
            builder_swapper_map[builder][tx["to"]] += 1
            gas_fee_bribe.add(tx["hash"])
    
    return coinbase_bribe, gas_fee_bribe


def analyze_blocks(blocks):
    builder_swapper_map = defaultdict(lambda: defaultdict(int))
    coinbase_bribe = set()
    gas_fee_bribe = set()

    for block_number, block in blocks.items():
        analyze_block(block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe)

    return builder_swapper_map, coinbase_bribe, gas_fee_bribe


if __name__ == "__main__":
    start_block = 17563790
    num_blocks = 100

    # transfers = get_internal_transfers_in_block(15933685, "0x690B9A9E9aa1C9dB991C7721a92d351Db4FaC990")

    blocks_fetched = fetch_blocks.get_blocks(start_block, num_blocks) 
    analysis.dump_dict_to_json(blocks_fetched, "test_blocks.json")
    # blocks_fetched = analysis.load_dict_from_json("blocks_info.json")

    builder_swapper_map, coinbase_bribe, gas_fee_bribe = analyze_blocks(blocks_fetched)

    # ordered = searcher_db.clean_up(builder_swapper_map, 2)
    analysis.dump_dict_to_json(builder_swapper_map, "builder_cex_map.json")
    print("coinbase bribes hashes:", coinbase_bribe)
    print("gas fee bribes:", gas_fee_bribe)
