# To estimate amount of CEX-DEX Arbs during a historical period
# we utilise cefi and defi price oracles to determine price differences
# if the price differences of CEX and DEX right before block N > threshold 
# any relevant trade in block is considered a CEX-DEX arb

# running thru txs between block 17616021 and 17666420
# subject to further changes
import requests
from collections import defaultdict
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import searcher_db
import analysis
import constants
import secret_keys
import time

START_BLOCK = 17616021
END_BLOCK = 17666420

GAS_PRICE_MULTIPLIER = 1.5

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
    gas_prices = [tx['gasPrice'] for tx in transactions]
    return statistics.median(gas_prices)

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
    transfer_map = {tr['hash']: {'from': tr["from"], 'to': tr['to']} for tr in transfers}
    transfer_set = set(tr['hash'] for tr in transfers)
    return transfer_set, transfer_map


           

# Given a block and its txs, get all the valid swap txs in that block, check that the swap txs 
# EITHER contains an internal transfer to builder OR pays "high" gas price. 
def analyze_block(block_number, block, builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher):
    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    builder = searcher_db.map_extra_data_to_builder(extra_data, block["feeRecipient"])
    
    fee_recipient = block["feeRecipient"]
    transfer_set, transfer_map = get_internal_transfers_in_block(block_number, fee_recipient)

    swap_txs = get_swaps(block_number)
    median_gas_price = calculate_block_median_gas_price(block["transactions"])

    print(block_number)

    # only consider txs labeled as swap by zeromev
    for swap in swap_txs:
        tx = block["transactions"][swap['tx_index']] 
        if tx["hash"] in transfer_map.keys(): 
            # bribing with coinbase transfers
            builder_swapper_map[builder][transfer_map[tx['hash']]["from"]] += 1
            if tx["to"] in coinbase_bribe:
                coinbase_bribe[transfer_map[tx['hash']]["from"]].append(tx['hash'])
            else: 
                coinbase_bribe[transfer_map[tx['hash']]["from"]] = [tx["hash"]]
        elif tx["gasPrice"] >= median_gas_price * GAS_PRICE_MULTIPLIER:
            # bribing w gas_fee at least 50% above median
            builder_swapper_map[builder][tx["to"]] += 1
            if tx["to"] in gas_fee_bribe_higher:
                gas_fee_bribe_higher[tx["to"]].append(tx['hash'])
            else: 
                gas_fee_bribe_higher[tx["to"]] = [tx["hash"]]
        # elif (tx["gasPrice"] >= median_gas_price * GAS_PRICE_MULTIPLIER_1) and (tx["gasPrice"] < median_gas_price * GAS_PRICE_MULTIPLIER_2):
        #     # bribing with gas_fee that is above median, but below median * 1.2 
        #     if tx["to"] in gas_fee_bribe_lower:
        #         gas_fee_bribe_lower[tx["to"]].append(tx['hash'])
        #     else: 
        #         gas_fee_bribe_lower[tx["to"]] = [tx["hash"]]


def analyze_blocks(blocks):
    builder_swapper_map = defaultdict(lambda: defaultdict(int))
    coinbase_bribe = {}
    gas_fee_bribe_lower = {}
    gas_fee_bribe_higher = {}
    with ThreadPoolExecutor(max_workers=64) as executor:
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

def compile_cefi_defi_data(builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher):
    trimmed_map = searcher_db.clean_up(builder_swapper_map, 5)
    analysis.dump_dict_to_json(trimmed_map, "non_atomic/builder_cefi_map.json")

    agg = analysis.aggregate_searchers(builder_swapper_map)
    trimmed_agg = {k: v for k, v in agg.items() if v >= 5 or k in coinbase_bribe.keys()}
    analysis.dump_dict_to_json(trimmed_agg, "non_atomic/cefi_searchers_agg.json")

    # bots that are only included when threshold is lower, 
    # trimmed_in_lower_only = {k: v for k, v in gas_fee_bribe_lower.items() if k not in gas_fee_bribe_higher and len(v) >= 5}
    # analysis.dump_dict_to_json((trimmed_in_lower_only), "non_atomic/cefi_bots_only_in_lower_gas.json")
    analysis.dump_dict_to_json(gas_fee_bribe_lower, "non_atomic/cefi_bots_only_in_lower_gas.json")
    analysis.dump_dict_to_json(gas_fee_bribe_higher, "non_atomic/cefi_bots_in_higher_gas.json")
    analysis.dump_dict_to_json(coinbase_bribe, "non_atomic/coinbase_bribes.json")

    # known, potential = check_mev_bots(list(in_lower_only))
    # analysis.dump_dict_to_json(list(known), "non_atomic/only_lower_gas_known.json")
    # analysis.dump_dict_to_json(list(potential), "non_atomic/only_lower_gas_potential.json")



if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")
    blocks_fetched = analysis.load_dict_from_json("block_data/all_blocks_30_days.json")

    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")
    builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher = analyze_blocks(blocks_fetched)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_cefi_defi_data(builder_swapper_map, coinbase_bribe, gas_fee_bribe_lower, gas_fee_bribe_higher)