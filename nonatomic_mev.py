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
    if len(gas_prices) > 0:
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



def followed_by_transfer_to_builder(fee_recipient, cur_tx, next_tx):
    if next_tx == {}:
        return False
    if next_tx["from"] == cur_tx["from"] and next_tx["to"] == fee_recipient:
        return True
    return False 


# analyze_tx(builder, fee_recipient, swap, full_tx, full_next_tx, transfer_map, top_of_block_boundary, median_gas)
def analyze_tx(builder, fee_recipient, swap, full_tx, full_next_tx, transfer_map, top_of_block_boundary, median_gas, addrs_counted_in_block,
               builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
               builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    tx_index = swap['tx_index']
    tx_volume = swap.get('user_swap_volume_usd', 0) or 0
    addr_to = swap['address_to'].lower()
    addr_from = swap['address_from'].lower()

    if full_tx["hash"] in transfer_map.keys(): 
        builder_nonatomic_map_tx[builder][transfer_map[full_tx['hash']]["from"]] += 1
        builder_nonatomic_map_vol[builder][transfer_map[full_tx['hash']]["from"]] += tx_volume
        builder_nonatomic_map_coin_bribe[builder][transfer_map[full_tx['hash']]["from"]] += transfer_map[full_tx['hash']]["value"]

        coinbase_bribe.setdefault(transfer_map[full_tx['hash']]["from"], []).append({
            "hash": full_tx["hash"],
            "builder": builder,
            "bribe": transfer_map[full_tx['hash']]["value"]
        })
        if addr_to not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)

    # if followed by a direct transfer to builder
    elif followed_by_transfer_to_builder(fee_recipient, full_tx, full_next_tx) == True:
        # mev bot collected here will be an EOA
        builder_nonatomic_map_tx[builder][addr_from] += 1
        builder_nonatomic_map_vol[builder][addr_from] += tx_volume
        builder_nonatomic_map_coin_bribe[builder][addr_from] += full_next_tx["value"]
        
        after_bribe.setdefault(addr_from, []).append({
            "hash": full_tx["hash"],
            "builder": builder,
            "bribe": full_next_tx["value"]
        })
        if addr_from not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_from] += 1
            addrs_counted_in_block.add(addr_from)

    # if within top of block (first 10%):
    elif tx_index <= top_of_block_boundary:
        builder_nonatomic_map_tx[builder][addr_to] += 1
        builder_nonatomic_map_vol[builder][addr_to] += tx_volume
        builder_nonatomic_map_gas_bribe[builder][addr_to] += full_tx["gas"] * full_tx["gasPrice"]

        tob_bribe.setdefault(addr_to, []).append({
            "hash": full_tx['hash'],
            "builder": builder,
            "index": tx_index,
            "gas_price": full_tx['gasPrice'],
            "gas": full_tx['gas'],
            "block_median_gas": median_gas,
        })
        if addr_to not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)


# Given a block and its txs, get all the valid swap txs in that block, check that the swap txs 
# EITHER contains an internal transfer to builder OR pays in top of block. 
def analyze_block(block_number, block, fetched_internal_transfers, builder_nonatomic_map_tx, builder_nonatomic_map_vol, 
                  builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
    # human-readable builder name, derived from extraData 
    builder = atomic_mev.map_extra_data_to_builder(extra_data, block["feeRecipient"]) 
    # hex-string of feeRecipient. can be builder or proposer
    fee_recipient = block["feeRecipient"]
    median_gas = calculate_block_median_gas_price(block["transactions"])
    transfer_map = fetched_internal_transfers[block_number]

    all_swaps = get_swaps(block_number)

    total_txs = len(block["transactions"])
    top_of_block_boundary = int(total_txs * 0.1) + ((total_txs * 0.1) % 1 > 0)
    print(block_number, len(all_swaps))


    # only consider txs labeled as swap by zeromev
    for swap in all_swaps:
        print("hi")
        # if bribe via coinbase transfer
#         def analyze_tx(builder, tx, full_tx, transfer_map, full_next_tx):
        full_tx = block["transactions"][swap["tx_index"]]
        full_next_tx = block.get("transactions", [])[swap['tx_index']+1] if 0 <= swap['tx_index']+1 < len(block.get("transactions", [])) else None

        analyze_tx(builder, fee_recipient, swap, full_tx, full_next_tx, transfer_map, top_of_block_boundary, median_gas,
                   builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
                   builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)
        

def analyze_blocks(fetched_blocks, fetched_internal_transfers):
    builder_nonatomic_map_tx = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_vol = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_coin_bribe = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_gas_bribe = defaultdict(lambda: defaultdict(int))

    coinbase_bribe = {}
    after_bribe = {}
    tob_bribe = {}
    with ThreadPoolExecutor(max_workers=64) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(analyze_block, block_number, block, fetched_internal_transfers, builder_nonatomic_map_tx, 
                                   builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, 
                                   coinbase_bribe, after_bribe, tob_bribe) for block_number, block in fetched_blocks.items()]
        for future in as_completed(futures):
            pass
    return builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe
    

# end result: 1) builder nonatomic map that shows builder: searcher where searchers have submitted more than 5 times
# 2) aggregate, frequency map of searchers: # of txs 
# 3) show bots that come when u have a lower threshold, for checking if bot 
    # lower threshold nets mev bots without adding false positives. 
    # will we include swaps that are actually not MEV, if we lower the threshold? 

def compile_cefi_defi_data(builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    # trimmed_map = searcher_db.clean_up(builder_nonatomic_map, 5)
    analysis.dump_dict_to_json(builder_nonatomic_map_block, "nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_block.json")
    analysis.dump_dict_to_json(builder_nonatomic_map_tx, "nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_tx.json")
    analysis.dump_dict_to_json(builder_nonatomic_map_vol, "nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_vol.json")
    analysis.dump_dict_to_json(builder_nonatomic_map_coin_bribe, "nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_coin_bribe.json")
    analysis.dump_dict_to_json(builder_nonatomic_map_gas_bribe, "nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_gas_bribe.json")

    agg_block = analysis.aggregate_block_count(builder_nonatomic_map_block)
    agg_tx = analysis.create_sorted_agg_from_map(builder_nonatomic_map_tx)
    agg_vol = analysis.create_sorted_agg_from_map(builder_nonatomic_map_vol)
    agg_coin = analysis.create_sorted_agg_from_map(builder_nonatomic_map_coin_bribe)
    agg_gas = analysis.create_sorted_agg_from_map(builder_nonatomic_map_gas_bribe)
    analysis.dump_dict_to_json(agg_block, "nonatomic/fifty/agg/agg_block.json")
    analysis.dump_dict_to_json(agg_tx, "nonatomic/fifty/agg/agg_tx.json")
    analysis.dump_dict_to_json(agg_vol, "nonatomic/fifty/agg/agg_vol.json")
    analysis.dump_dict_to_json(agg_coin, "nonatomic/fifty/agg/agg_coin.json")
    analysis.dump_dict_to_json(agg_gas, "nonatomic/fifty/agg/agg_gas.json")

    # bots that are only included when threshold is lower, 
    analysis.dump_dict_to_json(coinbase_bribe, "nonatomic/fifty/bribe_specs/coinbase_bribe.json")
    analysis.dump_dict_to_json(after_bribe, "nonatomic/fifty/bribe_specs/after_bribe.json")
    analysis.dump_dict_to_json(tob_bribe, "nonatomic/fifty/bribe_specs/tob_bribe.json")


if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")
    fetched_blocks = analysis.load_dict_from_json("block_data/blocks_3.json")
    fetched_internal_transfers = analysis.load_dict_from_json("internal_transfers_data/internal_transfers_50_days.json")

    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")
    builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe = analyze_blocks(fetched_blocks, fetched_internal_transfers)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_cefi_defi_data(builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)