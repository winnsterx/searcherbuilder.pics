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

START_BLOCK = 17616021
END_BLOCK = 17666420

PRICE_DIFFERENTIAL_THRESHOLD = 1.2

# use this api to get internal tx https://docs.alchemy.com/reference/alchemy-getassettransfers

# swap_txs = [{}]
# def analyze_block(block_number, swap_txs):
#     cex_dex_arbs = [] 
#     for tx in swap_txs:
#         token_a, token_b = tx.token_pai()
#         price_diff = cex_dex_price_delta_on_token(tokena, tokenb, block_number)
#         if price_diff > PRICE_DIFFERENTIAL_THRESHOLD:
#             cex_dex_arbs += tx
#     return cex_dex_arbs

# zeromev: returns block, tx index, addrs 
    # need gas fee, coinbase transfer, number of swaps, base fee of blocks 
    # get all blocks info, get gas fees, avg/median fee, 
    # collect swap txs later 
    # 

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


def get_above_median_txs_in_block(block_number, block, builder_swapper_map):
    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    builder = searcher_db.map_extra_data_to_builder(extra_data)
    swap_txs = get_swaps(block_number)
    median_gas_price = calculate_block_median_gas_price(block["transactions"])
    print(median_gas_price)
    for swap in swap_txs:
        tx = block["transactions"][swap['tx_index']]
        if tx["gasPrice"] > median_gas_price:
            builder_swapper_map[builder][tx["to"]] += 1
        

def analyze_blocks(blocks):
    builder_swapper_map = defaultdict(lambda: defaultdict(int))
    for block_number, block in blocks.items():
        get_above_median_txs_in_block(block_number, block, builder_swapper_map)
    return builder_swapper_map


if __name__ == "__main__":
    start_block = 17563790
    num_blocks = 30
    blocks_fetched = fetch_blocks.get_blocks(start_block, num_blocks) 
    analysis.dump_dict_to_json(blocks_fetched, "all_blocks.json")
    # blocks_fetched = analysis.load_dict_from_json("blocks_info.json")

    builder_swapper_map = analyze_blocks(blocks_fetched)
    ordered = searcher_db.clean_up(builder_swapper_map, 2)
    analysis.dump_dict_to_json(ordered, "builder_cex_map.json")