import requests 
import json 
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import constants
import analysis

# global variable that maps builder to searchers
atomic_addrs = defaultdict(lambda: defaultdict(int))
swap_addrs = defaultdict(lambda: defaultdict(int))

# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known router, dex, etc
def incrementBotCount(builder, addr_from, addr_to, mev_type):
    global atomic_addrs
    if mev_type == "swap" or mev_type == "sandwich":
        return
    if mev_type == "liquid":
        atomic_addrs[builder][addr_from] += 1
    elif addr_to not in constants.COMMON_CONTRACTS: 
        # if tx is neither swap nor sandwich, it must be frontrun, backrun, liquidation, arb 
        atomic_addrs[builder][addr_to] += 1


# maps the extradata to builder 
def map_extra_data_to_builder(extra_data, feeRecipient):
    builder = ""
    for key in constants.extraData_mapping:
        if key in extra_data.lower():
            builder = constants.extraData_mapping[key]
    # If no matches, return the original data
    if builder == "":
        # if no extraData, use feeRecipient addr as builder name
        builder = feeRecipient
    return builder

    

# finds the block builder given block number using extraData
def get_block_builder(block_number, prefetched_blocks): 
    block = prefetched_blocks[str(block_number)]
    extra_data = block["extraData"]
    builder = map_extra_data_to_builder(extra_data, block["feeRecipient"])
    return builder


# processes addr_tos of all MEV txs in a block
def count_addrs_in_one_block(session, url, block_number, block):
    try: 
        global atomic_addrs
        extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
        builder = map_extra_data_to_builder(extra_data, block["feeRecipient"])
        payload = {
            'block_number': block_number,
            "count": "1"
        }
        res = session.get(url, params=payload)
        print(block_number)
        if res.status_code == 200:
            data = res.json()
            for tx in data:
                addr_to = tx['address_to'].lower()
                addr_from = tx['address_from'].lower()
                incrementBotCount(builder, addr_from, addr_to, tx['mev_type'])
                                
        else: 
            print("error w requesting zeromev:", res.status_code)
    except Exception as e:
        print("error found in one block", e)


# filters out all bots that have interacted with a builder less than five times
# filters out all builders w no bots after first filter
# orders bots by their number of txs in each builder
def clean_up(data, threshold):
    filtered_searchers = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v >= threshold} for outer_k, outer_v in data.items()}
    filtered_builders = {builder: searchers for builder, searchers in filtered_searchers.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filtered_builders.items()}
    return ordered_addrs


# iterate through all the blocks to create a frequency mapping between builders and searchers 
# use thread pool to expediate process
def count_addrs(prefetched_blocks):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    builder_atomic_map = defaultdict(lambda: defaultdict(int))
    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=64) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(count_addrs_in_one_block, session, zeromev_url, block_number, block) for block_number, block in prefetched_blocks.items()]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    return atomic_addrs


def compile_atomic_data(builder_atomic_map):
    # not trimming anything, will do processing later
    analysis.dump_dict_to_json(builder_atomic_map, "atomic/builder_atomic_map.json")
    agg = analysis.aggregate_searchers(builder_atomic_map)
    analysis.dump_dict_to_json(agg, "atomic/atomic_searchers_agg.json")



if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")

    prefetched_blocks = analysis.load_dict_from_json("block_data/blocks_30_days.json")
    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks.")

    builder_atomic_map = count_addrs(prefetched_blocks)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    compile_atomic_data(builder_atomic_map)




