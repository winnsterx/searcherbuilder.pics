import requests 
import re, string
import json 
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import constants
import analysis
import nonatomic_mev

# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known router, dex, etc
def analyze_tx(builder, tx, full_tx, transfer_map, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe):
    mev_type = tx['mev_type']

    addr_to = tx['address_to'].lower()
    addr_from = tx['address_from'].lower()
    profit = tx.get('extractor_profit_usd', 0) or 0 
    volume = tx.get('extractor_swap_volume_usd', 0) or 0

    # collect info on bribes
    if full_tx["hash"] in transfer_map.keys():
        builder_atomic_map_coin_bribe[builder][addr_to][mev_type] += transfer_map[full_tx["hash"]]["value"]
        builder_atomic_map_coin_bribe[builder][addr_to]["total"] += transfer_map[full_tx["hash"]]["value"]

    else:
        builder_atomic_map_gas_bribe[builder][addr_to][mev_type] += full_tx["gas"] * full_tx["gasPrice"]
        builder_atomic_map_gas_bribe[builder][addr_to]["total"] += full_tx["gas"] * full_tx["gasPrice"]


    # handle info collection depending on mev_type
    if mev_type == "arb" or mev_type == "frontrun": 
        builder_atomic_map_tx[builder][addr_to][mev_type] += 1
        builder_atomic_map_profit[builder][addr_to][mev_type] += profit
        builder_atomic_map_vol[builder][addr_to][mev_type] += volume 

        builder_atomic_map_tx[builder][addr_to]["total"] += 1
        builder_atomic_map_profit[builder][addr_to]["total"] += profit
        builder_atomic_map_vol[builder][addr_to]["total"] += volume

    elif mev_type == "backrun":
        # counting both txs in a sandwich
        builder_atomic_map_tx[builder][addr_to][mev_type] += 1
        # revenut (not profit) will be zero for one of the legs. if even, then in front 
        builder_atomic_map_profit[builder][addr_to][mev_type] += profit
        builder_atomic_map_vol[builder][addr_to][mev_type] += volume 
        # only count volume from frontrun in the total (can count it separate for later purpose)
        builder_atomic_map_tx[builder][addr_to]["total"] += 1
        builder_atomic_map_profit[builder][addr_to]["total"] += profit

    elif mev_type == "liquid":
        # addr_from here, bc liquidation doesnt use special contracts but EOA 
        builder_atomic_map_tx[builder][addr_from][mev_type] += 1
        builder_atomic_map_vol[builder][addr_from][mev_type] += volume

        builder_atomic_map_tx[builder][addr_from]["total"] += 1
        builder_atomic_map_profit[builder][addr_from]["total"] += profit
        builder_atomic_map_vol[builder][addr_from]["total"] += volume



# maps the extradata to builder 
def map_extra_data_to_builder(extra_data, feeRecipient):
    builder = re.sub(r'\W+', '', extra_data)
    if builder == "":
        builder = feeRecipient
    elif "geth" in builder or "nethermind" in builder or "linux" in builder:
        builder = "vanilla_builder"
    return builder 
    # builder = ""
    # for key in constants.extraData_mapping:
    #     if key in extra_data.lower():
    #         builder = constants.extraData_mapping[key]
    # # If no matches, return the original data
    # if builder == "":
    #     # if no extraData, use feeRecipient addr as builder name
    #     builder = feeRecipient
    # return builder

    
# filters out all bots that have interacted with a builder less than five times
# filters out all builders w no bots after first filter
# orders bots by their number of txs in each builder
def clean_up(data, threshold):
    filtered_searchers = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v >= threshold} for outer_k, outer_v in data.items()}
    filtered_builders = {builder: searchers for builder, searchers in filtered_searchers.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filtered_builders.items()}
    return ordered_addrs


# # finds the block builder given block number using extraData
# def get_block_builder(block_number, fetched_blocks): 
#     block = fetched_blocks[str(block_number)]
#     extra_data = block["extraData"]
#     builder = map_extra_data_to_builder(extra_data, block["feeRecipient"])
#     return builder


# processes addr_tos of all MEV txs in a block
def analyze_block(session, url, block_number, block, fetched_internal_transfers, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe):
    try: 
        extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
        builder = map_extra_data_to_builder(extra_data, block["feeRecipient"])
        fee_recipient = block["feeRecipient"]
        transfer_map = fetched_internal_transfers[block_number]
        # transfer_map = nonatomic_mev.get_internal_transfers_to_fee_recipient_in_block(block_number, fee_recipient)
        payload = {
            'block_number': block_number,
            "count": "1"
        }
        res = session.get(url, params=payload)

        print(block_number)
        if res.status_code == 200:
            data = res.json()
            for tx in data:
                full_tx = block["transactions"][tx["tx_index"]]
                analyze_tx(builder, tx, full_tx, transfer_map, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe)
                                
        else: 
            print("error w requesting zeromev:", res.status_code)
    except Exception as e:
        print("error found in one block", e)



def default_searcher_dic():
    return {
        "total": 0,
        "arb": 0,
        "frontrun": 0,
        "backrun": 0,
        "liquid": 0
    }

# iterate through all the blocks to create a frequency mapping between builders and searchers 
# use thread pool to expediate process
def analyze_blocks(fetched_blocks, fetched_internal_transfers):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    builder_atomic_map_tx = defaultdict(lambda : defaultdict(default_searcher_dic))
    builder_atomic_map_profit = defaultdict(lambda : defaultdict(default_searcher_dic))
    builder_atomic_map_vol = defaultdict(lambda : defaultdict(default_searcher_dic))
    builder_atomic_map_coin_bribe = defaultdict(lambda: defaultdict(default_searcher_dic))
    builder_atomic_map_gas_bribe = defaultdict(lambda: defaultdict(default_searcher_dic))
    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=64) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(analyze_block, session, zeromev_url, block_number, block, fetched_internal_transfers,
                                       builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe) for block_number, block in fetched_blocks.items()]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    return builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe


def compile_atomic_data(builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe):
    analysis.dump_dict_to_json(builder_atomic_map_tx, "atomic/fifty/builder_atomic_maps/builder_atomic_map_tx.json")
    analysis.dump_dict_to_json(builder_atomic_map_profit, "atomic/fifty/builder_atomic_maps/builder_atomic_map_profit.json")
    analysis.dump_dict_to_json(builder_atomic_map_vol, "atomic/fifty/builder_atomic_maps/builder_atomic_map_vol.json")
    analysis.dump_dict_to_json(builder_atomic_map_coin_bribe, "atomic/fifty/builder_atomic_maps/builder_atomic_map_coin_bribe.json")
    analysis.dump_dict_to_json(builder_atomic_map_gas_bribe, "atomic/fifty/builder_atomic_maps/builder_atomic_map_gas_bribe.json")

    agg_tx = analysis.aggregate_atomic_searchers(builder_atomic_map_tx)
    agg_profit = analysis.aggregate_atomic_searchers(builder_atomic_map_profit)
    agg_vol = analysis.aggregate_atomic_searchers(builder_atomic_map_vol)
    agg_coin = analysis.aggregate_atomic_searchers(builder_atomic_map_coin_bribe)
    agg_gas = analysis.aggregate_atomic_searchers(builder_atomic_map_gas_bribe)
    analysis.dump_dict_to_json(agg_tx, "atomic/fifty/agg/agg_tx.json")
    analysis.dump_dict_to_json(agg_profit, "atomic/fifty/agg/agg_profit.json")
    analysis.dump_dict_to_json(agg_vol, "atomic/fifty/agg/agg_vol.json")
    analysis.dump_dict_to_json(agg_coin, "atomic/fifty/agg/agg_coin.json")
    analysis.dump_dict_to_json(agg_gas, "atomic/fifty/agg/agg_gas.json")


if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")

    fetched_blocks = analysis.load_dict_from_json("block_data/two_blocks.json")
    fetched_internal_transfers = analysis.load_dict_from_json("internal_transfer_data/internal_transfers_50_days.json")
    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")
    builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe = analyze_blocks(fetched_blocks, fetched_internal_transfers)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_atomic_data(builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe)




