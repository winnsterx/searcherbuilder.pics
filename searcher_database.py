import requests 
import json 
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from web3 import Web3
import constants
import secret_keys


# to do
# in cases where block.miner/fee_recipient is the proposer, those blocks r ignored 
    # now these blocks' true builders are gotten via extraData field
# do analysis w dataset
    # calculate the likelihood of accepting a specific searcher for a builder 
    # determine metrics for abnormality (50%, 75%) more likely 
    # differentiate between bots preferred by builder vs bots preferring a builder 
        # how to achieve such differentiation? 
# what other interesting conclusions can be drawn with this dataset?
# disjoint is not necessarily the most helpful, bigger builders may obscure the smaller builders who r doing sketchy stuff

# global variable that maps builder to searchers
common_addrs = defaultdict(lambda: defaultdict(int))
swap_addrs = defaultdict(lambda: defaultdict(int))

# loads the block to builder mapping from json-file into block_to_builder dictionary
# returns {block: builder} and [blocks]
def load_block_to_builder():
    with open(constants.BLOCK_BUILDER_MAP_FILE) as file:
        block_to_builder = json.load(file) 
        blocks = block_to_builder.keys()
        return block_to_builder, list(blocks)


# returns fee_recipient of the block, as specified in block_to_builder, 
# if addr is a known builder, return the colloquial name of builder
# otherwise, return "builderUnknown: addr"
def get_block_builder_from_fee_recipient(block_number, block_to_builder):
    builder = block_to_builder[block_number].lower()
    if builder == constants.BUILDER_0X69:
        return "builder0x69"
    elif builder == constants.BEAVERBUILD:
        return "beaverbuild"
    elif builder == constants.RSYNC:
        return "rsync"
    elif builder == constants.FLASHBOTS or builder == constants.FLASHBOTS_SGX:
        return "flashbots"
    elif builder == constants.ETHBUILDER:
        return "ethbuilder"
    elif builder == constants.TITAN:
        return "titan"
    elif builder == constants.BLOXROUTE_MAX_PROFIT or builder == constants.BLOXROUTE_REGULATED:
        return "bloxroute"
    elif builder == constants.BLOCKNATIVE:
        return "blocknative"
    elif builder == constants.F1B:
        return "f1b"
    elif builder == constants.BUILDAI:
        return "buildai"
    elif builder == constants.BOBABUILDER:
        return "boba"
    elif builder == constants.PAYLOAD:
        return "payload"
    elif builder == constants.BEE:
        return "bee"
    elif builder == constants.EDEN:
        return "eden"
    elif builder == constants.LIGHTSPEEDBUILDER_1 or builder == constants.LIGHTSPEEDBUILDER_2:
        return "lightspeedbuilder"
    elif builder == constants.THREETHREES: 
        return "threethrees"
    else:
        return "builderUnknown: " + builder

# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known dapp contract 
def incrementBotCount(builder, addr_to, mev_type, block_number):
    global common_addrs
    global swap_addrs
    if addr_to not in constants.COMMON_CONTRACTS:  
        if mev_type != "swap":
            common_addrs[builder][addr_to] += 1
        else:
            swap_addrs[builder][addr_to] += 1

# maps the extradata to builder 
def map_extra_data_to_builder(extra_data):
    if "beaverbuild.org" in extra_data: 
        return "beaverbuild"
    elif "builder0x69" in extra_data:
        return "builder0x69"
    elif "rsync-builder.xyz" in extra_data:
        return "rsync"
    elif "blocknative" in extra_data:
        return "blocknative"
    elif "titan" in extra_data:
        return "titan"  
    elif "bloxroute" in extra_data:
        return "bloxroute"
    elif "linux" in extra_data or "nethermind" in extra_data:
        return "vanilla_builders"
    else:
        return extra_data
    

# finds the block builder given block number
def get_block_builder(w3, block_number, block_to_builder): 
    # first check if a known builder addr is the fee_recipient 
    builder = get_block_builder_from_fee_recipient(block_number, block_to_builder) 

    # if not fee_recipient is not a known builder, check extradata for further info
    # occassionally, fee_recipient is set as the validator even tho the block is built by an external known builder
    if builder.startswith("builderUnknown"):
        # query for extraData of block using Infura endpoint
        extra_data = str(w3.eth.get_block(int(block_number)).extraData).lower()
        builder = map_extra_data_to_builder(extra_data)

    return builder

# process all the possible searcher addrs in one block by parsing thru the txs
def count_addrs_in_one_block(session, w3, url, block_number, block_to_builder):
    global common_addrs
    builder = get_block_builder(w3, block_number, block_to_builder)

    payload = {
        'block_number': block_number,
        "count": "1"
    }
    res = session.get(url, params=payload)

    if res.status_code == 200:
        data = res.json()
        for tx in data:
            addr_to = tx['address_to'].lower()
            incrementBotCount(builder, addr_to, tx['mev_type'], block_number)
    else: 
        print("error w requesting zeromev:", res.status_code)


# filters out all searchers that have interacted with a builder less than 3 times
# filters out all builders that dont have any searchers that have interacted with the builder more than thrice
# orders the searchers by their number of txs for each builder
def clean_up_builder_searcher():
    global common_addrs
    filter_out_searchers_seen_less_than_thrice = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 4} for outer_k, outer_v in common_addrs.items()}
    filter_out_builders_with_nothing = {builder: searchers for builder, searchers in filter_out_searchers_seen_less_than_thrice.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filter_out_builders_with_nothing.items()}
    return ordered_addrs

def clean_up_swaps():
    global swap_addrs
    filter_out_searchers_seen_less_than_thrice = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 4} for outer_k, outer_v in swap_addrs.items()}
    filter_out_builders_with_nothing = {builder: searchers for builder, searchers in filter_out_searchers_seen_less_than_thrice.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filter_out_builders_with_nothing.items()}
    return ordered_addrs


# iterate through all the blocks to create a frequency mapping between builders and searchers 
# use thread pool to expediate process
def count_addrs(block_to_builder, blocks):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    my_provider = Web3.HTTPProvider(secret_keys.INFURA)
    w3 = Web3(my_provider)

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(count_addrs_in_one_block, session, w3, zeromev_url, b, block_to_builder) for b in blocks]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    builder_searchers = clean_up_builder_searcher()
    swap_searchers = clean_up_swaps()

    with open(constants.BUILDER_SEARCHER_MAP_FILE, 'w') as fp: 
        json.dump(builder_searchers, fp)
    with open(constants.BUILDER_SWAPPER_MAP_FILE, 'w') as fp: 
        json.dump(swap_searchers, fp)


block_to_builder, blocks = load_block_to_builder()
count_addrs(block_to_builder, blocks)


