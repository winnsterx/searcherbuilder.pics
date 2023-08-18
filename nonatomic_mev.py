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
import atomic_mev
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
            if tx['mev_type'] == "swap" or tx['mev_type'] == "sandwich":
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
def get_internal_transfers_to_fee_recipient_in_block(block_number, builder):
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
    transfer_map = {tr['hash']: {'from': tr["from"], 'to': tr['to'], 'value': tr["value"]} for tr in transfers}
    return transfer_map


def followed_by_transfer_to_builder(fee_recipient, cur_tx, next_tx):
    if next_tx["from"] == cur_tx["from"] and next_tx["to"] == fee_recipient:
        return True
    return False 

# Given a block and its txs, get all the valid swap txs in that block, check that the swap txs 
# EITHER contains an internal transfer to builder OR pays in top of block. 
def analyze_block(block_number, block, builder_swapper_map_tx, builder_swapper_map_vol, 
                  builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    # human-readable builder name, derived from extraData 
    builder = atomic_mev.map_extra_data_to_builder(extra_data, block["feeRecipient"]) 
    # hex-string of feeRecipient. can be builder or proposer
    fee_recipient = block["feeRecipient"]
    median_gas = calculate_block_median_gas_price(block["transactions"])
    transfer_map = get_internal_transfers_to_fee_recipient_in_block(block_number, fee_recipient)

    all_swaps = get_swaps(block_number)

    total_txs = len(block["transactions"])
    top_of_block_boundary = int(total_txs * 0.1) + ((total_txs * 0.1) % 1 > 0)
    print(block_number, total_txs)


    # only consider txs labeled as swap by zeromev
    for swap in all_swaps:
        tx_index = swap['tx_index']
        tx = block["transactions"][tx_index] 
        tx_volume = swap['user_swap_volume_usd']
        # if bribe via coinbase transfer
        if tx["hash"] in transfer_map.keys(): 
            builder_swapper_map_tx[builder][transfer_map[tx['hash']]["from"]] += 1
            builder_swapper_map_vol[builder][transfer_map[tx['hash']]["from"]] += tx_volume
            builder_swapper_map_coin_bribe[builder][transfer_map[tx['hash']]["from"]] += transfer_map[tx['hash']]["value"]

            coinbase_bribe.setdefault(transfer_map[tx['hash']]["from"], []).append({
                "hash": tx["hash"],
                "builder": builder,
                "bribe": transfer_map[tx['hash']]["value"]
            })
        # if followed by a direct transfer to builder
        elif followed_by_transfer_to_builder(fee_recipient, tx, block["transactions"][tx_index + 1]) == True:
            # mev bot collected here will be an EOA
            builder_swapper_map_tx[builder][tx["from"]] += 1
            builder_swapper_map_vol[builder][tx["from"]] += tx_volume
            builder_swapper_map_coin_bribe[builder][tx["from"]] += block["transactions"][tx_index + 1]["value"]
            
            after_bribe.setdefault(tx["from"], []).append({
                "hash": tx["hash"],
                "builder": builder,
                "bribe": block["transactions"][tx_index + 1]["value"]
            })
        # if within top of block (first 10%):
        elif swap['tx_index'] <= top_of_block_boundary:
            builder_swapper_map_tx[builder][tx["to"]] += 1
            builder_swapper_map_vol[builder][tx["to"]] += tx_volume
            builder_swapper_map_gas_bribe[builder][tx["to"]] += tx["gas"] * tx["gasPrice"]

            tob_bribe.setdefault(tx["to"], []).append({
                "hash": tx['hash'],
                "builder": builder,
                "index": tx_index,
                "gas_price": tx['gasPrice'],
                "gas": tx['gas'],
                "block_median_gas": median_gas,
            })
        

def analyze_blocks(blocks):
    builder_swapper_map_tx = defaultdict(lambda: defaultdict(int))
    builder_swapper_map_vol = defaultdict(lambda: defaultdict(int))
    builder_swapper_map_coin_bribe = defaultdict(lambda: defaultdict(int))
    builder_swapper_map_gas_bribe = defaultdict(lambda: defaultdict(int))

    coinbase_bribe = {}
    after_bribe = {}
    tob_bribe = {}
    with ThreadPoolExecutor(max_workers=64) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(analyze_block, block_number, block, builder_swapper_map_tx, 
                                   builder_swapper_map_vol, builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, 
                                   coinbase_bribe, after_bribe, tob_bribe) for block_number, block in blocks.items()]
        for future in as_completed(futures):
            pass
    return builder_swapper_map_tx, builder_swapper_map_vol, builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe
    

# end result: 1) builder swapper map that shows builder: searcher where searchers have submitted more than 5 times
# 2) aggregate, frequency map of searchers: # of txs 
# 3) show bots that come when u have a lower threshold, for checking if bot 
    # lower threshold nets mev bots without adding false positives. 
    # will we include swaps that are actually not MEV, if we lower the threshold? 

def compile_cefi_defi_data(builder_swapper_map_tx, builder_swapper_map_vol, builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    # trimmed_map = searcher_db.clean_up(builder_swapper_map, 5)
    analysis.dump_dict_to_json(builder_swapper_map_tx, "non_atomic/vol_after_tob/builder_swapper_maps/builder_swapper_map_tx.json")
    analysis.dump_dict_to_json(builder_swapper_map_vol, "non_atomic/vol_after_tob/builder_swapper_maps/builder_swapper_map_vol.json")
    analysis.dump_dict_to_json(builder_swapper_map_coin_bribe, "non_atomic/vol_after_tob/builder_swapper_maps/builder_swapper_map_coin_bribe.json")
    analysis.dump_dict_to_json(builder_swapper_map_gas_bribe, "non_atomic/vol_after_tob/builder_swapper_maps/builder_swapper_map_gas_bribe.json")

    agg_tx = analysis.aggregate_searchers(builder_swapper_map_tx)
    agg_vol = analysis.aggregate_searchers(builder_swapper_map_vol)
    agg_coin = analysis.aggregate_searchers(builder_swapper_map_coin_bribe)
    agg_gas = analysis.aggregate_searchers(builder_swapper_map_gas_bribe)
    analysis.dump_dict_to_json(agg_tx, "non_atomic/vol_after_tob/agg/agg_tx.json")
    analysis.dump_dict_to_json(agg_vol, "non_atomic/vol_after_tob/agg/agg_vol.json")
    analysis.dump_dict_to_json(agg_coin, "non_atomic/vol_after_tob/agg/agg_coin.json")
    analysis.dump_dict_to_json(agg_gas, "non_atomic/vol_after_tob/agg/agg_gas.json")

    # bots that are only included when threshold is lower, 
    analysis.dump_dict_to_json(coinbase_bribe, "non_atomic/vol_after_tob/bribe_specs/coinbase_bribe.json")
    analysis.dump_dict_to_json(after_bribe, "non_atomic/vol_after_tob/bribe_specs/after_bribe.json")
    analysis.dump_dict_to_json(tob_bribe, "non_atomic/vol_after_tob/bribe_specs/tob_bribe.json")


if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")
    blocks_fetched = analysis.load_dict_from_json("block_data/blocks_30_days.json")

    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")
    builder_swapper_map_tx, builder_swapper_map_vol, builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe = analyze_blocks(blocks_fetched)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_cefi_defi_data(builder_swapper_map_tx, builder_swapper_map_vol, builder_swapper_map_coin_bribe, builder_swapper_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)