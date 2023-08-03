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
import time

START_BLOCK = 17616021
END_BLOCK = 17666420

GAS_PRICE_MULTIPLIER_1 = 0.8
GAS_PRICE_MULTIPLIER_2 = 1

# use this api to get internal tx https://docs.alchemy.com/reference/alchemy-getassettransfers

# zeromev: returns block, tx index, addrs 
    # need gas fee, coinbase transfer, number of swaps, base fee of blocks 
    # get all blocks info, get gas fees, avg/median fee, 
    # collect swap txs later 

# return sth similar to builder: searcher frequency map 

# Gets all swap txs in a block of given number by querying Zeromev
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


# Calculates median gas price given a list of transactions 
def calculate_block_median_gas_price(transactions):
    gas_prices = sorted(tx['gasPrice'] for tx in transactions)
    mid = len(gas_prices) // 2
    if len (gas_prices) % 2 == 0:
        return (gas_prices[mid - 1] + gas_prices[mid]) / 2
    else:
        return gas_prices[mid]


# Simplifies transfers returned by Alchemy's getInternalTransfers function
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


# block_number: string, builder: string
# Gets set of internal transfers to the builder in a block using Alchemy's API
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
                "fromBlock": hex(int(block_number)),
                "toBlock": hex(int(block_number))
            }
        ]
    }
    response = requests.post(secret_keys.ALCHEMY, json=payload, headers=headers)
    transfers = response.json()["result"]["transfers"]
    simplified_transfers = simplify_transfers(transfers)

    transfer_set = set(tr['hash'] for tr in simplified_transfers)
    return simplified_transfers, transfer_set


# Checks LIST of bots against Etherscan's MEV Bots, returns lists of known and potential bots
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
            

# Given a block and its txs, get all the valid swap txs in that block, check that the swap txs 
# EITHER contains an internal transfer to builder OR pays "high" gas price. 
def analyze_block(block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher):
    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    builder = searcher_db.map_extra_data_to_builder(extra_data, block["feeRecipient"])
    
    fee_recipient = block["feeRecipient"]
    transfer_list, transfer_set = get_internal_transfers_in_block(block_number, fee_recipient)

    swap_txs = get_swaps(block_number)

    median_gas_price = calculate_block_median_gas_price(block["transactions"])

    print(block_number)

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
            if tx["to"] in gas_fee_bribe_lower:
                gas_fee_bribe_lower[tx["to"]].append(tx['hash'])
            else: 
                gas_fee_bribe_lower[tx["to"]] = [tx["hash"]]
        elif tx["gasPrice"] >= median_gas_price * GAS_PRICE_MULTIPLIER_2:
            # bribing w gas_fee 25% above median
            builder_swapper_map[builder][tx["to"]] += 1
            if tx["to"] in gas_fee_bribe_higher:
                gas_fee_bribe_higher[tx["to"]].append(tx['hash'])
            else: 
                gas_fee_bribe_higher[tx["to"]] = [tx["hash"]]

    return coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher



def analyze_blocks(blocks):
    builder_swapper_map = defaultdict(lambda: defaultdict(int))
    coinbase_bribe = {}
    gas_fee_bribe_lower = {}
    gas_fee_bribe_higher = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(analyze_block, block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher) for block_number, block in blocks.items()]
        for future in as_completed(futures):
            pass
    return builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher
    

# end result: 1) builder swapper map that shows builder: searcher where searchers have submitted more than 5 times
# 2) aggregate, frequency map of searchers: # of txs 
# 3) show bots that come when u have a lower threshold, for checking if bot 
    # lower threshold nets mev bots without adding false positives. 
    # will we include swaps that are actually not MEV, if we lower the threshold? 

def compile_cefi_defi_data(builder_swapper_map, gas_fee_bribe_lower, gas_fee_bribe_higher):
    trimmed_map = searcher_db.clean_up(builder_swapper_map, 5)
    analysis.dump_dict_to_json(trimmed_map, "builder_cefi_map.json")

    agg = analysis.aggregate_searchers(builder_swapper_map)
    trimmed_agg = {k: v for k, v in agg.items() if v >= 5}
    analysis.dump_dict_to_json(trimmed_agg, "bot_data/cefi_searchers_agg.json")

    # bots that are only included when threshold is lower, 
    trimmed_in_lower_only = {k: v for k, v in gas_fee_bribe_lower.items() if k not in gas_fee_bribe_higher and len(v) >= 2}
    analysis.dump_dict_to_json((trimmed_in_lower_only), "bot_data/cefi_bots_only_in_lower_gas.json")

    # known, potential = check_mev_bots(list(in_lower_only))
    # analysis.dump_dict_to_json(list(known), "bot_data/only_lower_gas_known.json")
    # analysis.dump_dict_to_json(list(potential), "bot_data/only_lower_gas_potential.json")



if __name__ == "__main__":
    # start_block = 17563790
    # num_blocks = 10
    # blocks_fetched = fetch_blocks.get_blocks(start_block, num_blocks)
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")
    blocks_fetched = analysis.load_dict_from_json("block_data/test_blocks.json")

    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")
    builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher = analyze_blocks(blocks_fetched)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_cefi_defi_data(builder_swapper_map, gas_fee_bribe_lower, gas_fee_bribe_higher)