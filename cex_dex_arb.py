# To estimate amount of CEX-DEX Arbs during a historical period
# we utilise cefi and defi price oracles to determine price differences
# if the price differences of CEX and DEX right before block N > threshold 
# any relevant trade in block is considered a CEX-DEX arb

# running thru txs between block 17616021 and 17666420
# subject to further changes
import requests
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import searcher_db
import fetch_blocks
import analysis
import constants
import secret_keys

START_BLOCK = 17616021
END_BLOCK = 17666420

GAS_PRICE_MULTIPLIER_1 = 1
GAS_PRICE_MULTIPLIER_2 = 1.10

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

# takes in a LIST of bots and checks them against the existing db
def check_mev_bots(potential_bots):
    mev_bots = analysis.load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    found_known_bots = []
    found_potential_bots = []
    for bot in potential_bots:
        if bot in mev_bots:
            found_known_bots.append(bot)
        else:
            found_potential_bots.append(bot)
    return found_known_bots, found_potential_bots
            

def analyze_block(block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe_1, gas_fee_bribe_10):
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
            # bribing with coinbase transfers
            builder_swapper_map[builder][tx["to"]] += 1
            coinbase_bribe[tx["hash"]] = tx["to"]
        elif (tx["gasPrice"] >= median_gas_price * GAS_PRICE_MULTIPLIER_1) and (tx["gasPrice"] < median_gas_price * GAS_PRICE_MULTIPLIER_2):
            # bribing with gas_fee that is 10% above median, but below 25% above median 
            builder_swapper_map[builder][tx["to"]] += 1
            if tx["to"] in gas_fee_bribe_1:
                gas_fee_bribe_1[tx["to"]].append(tx['hash'])
            else: 
                gas_fee_bribe_1[tx["to"]] = [tx["hash"]]
        elif tx["gasPrice"] >= median_gas_price * GAS_PRICE_MULTIPLIER_2:
            # bribing w gas_fee 25% above median
            builder_swapper_map[builder][tx["to"]] += 1
            if tx["to"] in gas_fee_bribe_10:
                gas_fee_bribe_10[tx["to"]].append(tx['hash'])
            else: 
                gas_fee_bribe_10[tx["to"]] = [tx["hash"]]

    return coinbase_bribe, gas_fee_bribe_1, gas_fee_bribe_10


def analyze_blocks(blocks):
    builder_swapper_map = defaultdict(lambda: defaultdict(int))
    coinbase_bribe = {}
    gas_fee_bribe_1 = {}
    gas_fee_bribe_10 = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(analyze_block, block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe_1, gas_fee_bribe_10) for block_number, block in blocks.items()]
        for future in as_completed(futures):
            pass

    return builder_swapper_map, coinbase_bribe, gas_fee_bribe_1, gas_fee_bribe_10
    


if __name__ == "__main__":
    # start_block = 17563790
    # num_blocks = 10
    # blocks_fetched = fetch_blocks.get_blocks(start_block, num_blocks)

    blocks_fetched = analysis.load_dict_from_json("block_data/blocks_1.json")
    
    builder_swapper_map, coinbase_bribe, gas_fee_bribe_1, gas_fee_bribe_10 = analyze_blocks(blocks_fetched)
    analysis.dump_dict_to_json(builder_swapper_map, "builder_cex_map.json")

    agg = analysis.aggregate_searchers(builder_swapper_map)
    analysis.dump_dict_to_json(agg, "bot_data/cex_searchers_agg.json")

    # bots & txs that are caught when the threshold is median vs median * 1.1
    analysis.dump_dict_to_json(gas_fee_bribe_1, "gas_fee_bribe_1.json")
    analysis.dump_dict_to_json(gas_fee_bribe_10, "gas_fee_bribe_10.json")

    # bots that are only included when threshold is lower, 
    in_lower_only, _ = analysis.find_disjoint_between_two_searcher_db(gas_fee_bribe_1, gas_fee_bribe_10)
    analysis.dump_dict_to_json(list(in_lower_only), "gas_fee_1_only.json")

    known, potential = check_mev_bots(list(in_lower_only))
    analysis.dump_dict_to_json(list(known), "bot_data/known_in_gas_1.json")
    analysis.dump_dict_to_json(list(potential), "bot_data/potential_in_gas_1.json")

    known_2, potential_2 = check_mev_bots(agg.keys())
    analysis.dump_dict_to_json(list(known_2), "bot_data/known_in_all.json")
    analysis.dump_dict_to_json(list(potential_2), "bot_data/potential_in_all.json")
