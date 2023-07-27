import requests 
import json 
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import constants
import secret_keys
import analysis

# global variable that maps builder to searchers
atomic_addrs = defaultdict(lambda: defaultdict(int))
swap_addrs = defaultdict(lambda: defaultdict(int))
blocks = {}

# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known router, dex, etc
def incrementBotCount(builder, addr_to, mev_type):
    global atomic_addrs
    global swap_addrs
    if mev_type == "swap" & addr_to not in constants.COMMON_CONTRACTS:  
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
def get_block_builder(block_number): 
    block = blocks[block_number]
    extra_data = block["extraData"]
    builder = map_extra_data_to_builder(extra_data.lower())
    if builder == "":
        # if no extraData, use feeRecipient addr as builder name
        builder = block["feeRecipient"]
    return builder


# processes addr_tos of all MEV txs in a block
def count_addrs_in_one_block(session, url, block_number):
    try: 
        global atomic_addrs
        builder = get_block_builder(block_number)
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
def count_addrs(start_block, num_blocks):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(count_addrs_in_one_block, session, zeromev_url, b) for b in range(start_block, start_block + num_blocks)]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    atomic_builder_searchers = clean_up(atomic_addrs)
    swap_builder_searchers = clean_up(swap_addrs)

    with open(constants.BUILDER_SEARCHER_MAP_FILE, 'w') as fp: 
        json.dump(atomic_builder_searchers, fp)
    with open(constants.BUILDER_SWAPPER_MAP_FILE, 'w') as fp: 
        json.dump(swap_builder_searchers, fp)


def batch_request(url, batch, retries):
    global blocks
    block_number = 0
    headers = {"Content-Type": "application/json"}
    start = time.time()
    print("getting batch at ", start)
    response = requests.post(url, headers=headers, data=json.dumps(batch))
    print("status code:",response.status_code)

    if response.status_code == 429 and retries < 5:
        print("retrying for the ", retries, " times")
        analysis.dump_dict_to_json(blocks, "blocks_info.json")

        time.sleep(5)
        batch_request(url, batch, retries+1)
    else: 
        try:
            bs = response.json() # [{}, {}]
            for b in bs:
                extraData = bytes.fromhex(b["result"]["extraData"].lstrip("0x")).decode("ISO-8859-1")
                miner = b["result"]["miner"]
                block_number = b["id"]
                blocks[block_number] = {"extraData": extraData, "feeRecipient": miner}
            print("finished getting batch using ", time.time() - start)
        except Exception as e:
            print(b)
            analysis.dump_dict_to_json(blocks, "blocks_info.json")
            print("exception has happened")
            if b["error"]["code"] == 429:
                print("retrying for the ", retries, " times")
                time.sleep(5)
                batch_request(url, batch, retries+1)
            



def get_blocks(start_block, num_blocks):
    batch_size = 1000
    end_block = start_block + num_blocks - 1
    
    start = time.time()
    print("starting to get blocks at ", start)

    for block in range(start_block, end_block + 1, batch_size):
        batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} for i in range(block, min(block + batch_size, end_block + 1))]
        batch_request(secret_keys.ALCHEMY, batch, 0)
    
    print("finished getting blocks in", time.time() - start, " seconds")
    analysis.dump_dict_to_json(blocks, "blocks_info.json")
    


if __name__ == "__main__":
    start_block = 17779790
    num_blocks = 1
    get_blocks(start_block, num_blocks)
    # count_addrs(start_block, num_blocks)



