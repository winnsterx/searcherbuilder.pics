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
def incrementBotCount(builder, addr_to, mev_type):
    global atomic_addrs
    global swap_addrs
    if mev_type == "swap" and addr_to not in constants.COMMON_CONTRACTS:  

        swap_addrs[builder][addr_to] += 1
    elif mev_type == "sandwich":
        return
    elif addr_to not in constants.COMMON_CONTRACTS: 
        # if tx is neither swap nor sandwich, it must be frontrun, backrun, liquidation, arb 
        atomic_addrs[builder][addr_to] += 1


# maps the extradata to builder 
def map_extra_data_to_builder(extra_data):
    for key in constants.extraData_mapping:
        if key in extra_data:
            return constants.extraData_mapping[key]
    # If no matches, return the original data
    return extra_data

    

# finds the block builder given block number using extraData
def get_block_builder(block_number, prefetched_blocks): 
    block = prefetched_blocks[str(block_number)]
    extra_data = block["extraData"]
    builder = map_extra_data_to_builder(extra_data.lower())
    if builder == "":
        # if no extraData, use feeRecipient addr as builder name
        builder = block["feeRecipient"]
    return builder

# def is_cex_dex_arb(tx):
#     # a swap tx
#     return True

# processes addr_tos of all MEV txs in a block
def count_addrs_in_one_block(session, url, prefetched_blocks, block_number):
    try: 
        global atomic_addrs
        builder = get_block_builder(block_number, prefetched_blocks)
        payload = {
            'block_number': block_number,
            "count": "1"
        }
        res = session.get(url, params=payload)
        if res.status_code == 200:
            data = res.json()
            for tx in data:
                addr_to = tx['address_to'].lower()
                incrementBotCount(builder, addr_to, tx['mev_type'])
            
                # if tx['mev_type'] == "swap":
                #     is_cex_dex = is_cex_dex_arb(tx)
                    
        else: 
            print("error w requesting zeromev:", res.status_code)
    except Exception as e:
        print("error found in one block", e)


# filters out all bots that have interacted with a builder less than five times
# filters out all builders w no bots after first filter
# orders bots by their number of txs in each builder
def clean_up(data):
    filtered_searchers = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 4} for outer_k, outer_v in data.items()}
    filtered_builders = {builder: searchers for builder, searchers in filtered_searchers.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filtered_builders.items()}
    return ordered_addrs


# iterate through all the blocks to create a frequency mapping between builders and searchers 
# use thread pool to expediate process
def count_addrs(start_block, num_blocks, prefetched_blocks):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(count_addrs_in_one_block, session, zeromev_url, prefetched_blocks, b) for b in range(start_block, start_block + num_blocks)]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    atomic_builder_searchers = clean_up(atomic_addrs)
    swap_builder_searchers = clean_up(swap_addrs)

    with open(constants.BUILDER_SEARCHER_MAP_FILE, 'w') as fp: 
        json.dump(atomic_builder_searchers, fp)
    with open(constants.BUILDER_SWAPPER_MAP_FILE, 'w') as fp: 
        json.dump(swap_builder_searchers, fp)

if __name__ == "__main__":
    # 17563790 to 17779790
    start_block = 17788280
    num_blocks = 7200 
    prefetched_blocks = analysis.load_dict_from_json("month_blocks_info.json")
    count_addrs(start_block, num_blocks, prefetched_blocks)



