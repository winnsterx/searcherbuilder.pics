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

common_addrs = defaultdict(lambda: defaultdict(int))

# returns {block: builder} and [blocks]
def load_block_to_builder():
    jsonfile = "block_to_builder.json"
    with open(jsonfile) as file:
        block_to_builder = json.load(file) 
        blocks = block_to_builder.keys()
        return block_to_builder, list(blocks)


# block_number: string, block_to_builder: {block_number/string: addr/string}
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
    elif builder == constants.LIDO or builder == constants.STAKEFISH: 
        return "pools"
    else:
        return "builderUnknown: " + builder


def incrementBotCount(builder, addr_from, addr_to):
    global common_addrs

    if addr_from not in constants.COMMON_CONTRACTS:
        common_addrs[builder][addr_from] += 1

    if addr_to not in constants.COMMON_CONTRACTS:
        common_addrs[builder][addr_to] += 1


def map_extra_data_to_builder(extra_data):
    print(extra_data)
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
    elif "linux" or "nethermind" in extra_data:
        return "vanilla_builders"
    else:
        return extra_data
    

def get_block_builder(w3, block_number, block_to_builder): 
    # extra_data = w3.eth.get_block(int(block_number)).extraData
    # # builder = map_extra_data_to_builder(extra_data)
    # return str(extra_data)

    builder = get_block_builder_from_fee_recipient(block_number, block_to_builder) 
    if builder == "pools" or builder.startswith("builderUnknown"):
        # need to find block builder via extraData field 
        extra_data = str(w3.eth.get_block(int(block_number)).extraData).lower()
        builder = map_extra_data_to_builder(extra_data)
    return builder


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
        
        print(builder, block_number)
        for tx in data:
            addr_from = tx['address_from'].lower()
            addr_to = tx['address_to'].lower()
            incrementBotCount(builder, addr_from, addr_to)

    else: 
        print("error w requesting zeromev:", res.status_code)


def clean_up_builder_searcher():
    global common_addrs
    filter_out_searchers_seen_less_than_thrice = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 3} for outer_k, outer_v in common_addrs.items()}
    filter_out_builders_with_nothing = {builder: searchers for builder, searchers in filter_out_searchers_seen_less_than_thrice.items() if searchers}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filter_out_builders_with_nothing.items()}
    return ordered_addrs



def count_addrs(block_to_builder, blocks):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    my_provider = Web3.HTTPProvider(secret_keys.INFURA)
    w3 = Web3(my_provider)

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        with ThreadPoolExecutor(max_workers=10) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(count_addrs_in_one_block, session, w3, zeromev_url, b, block_to_builder) for b in blocks]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    builder_searchers = clean_up_builder_searcher()

    with open('result.json', 'w') as fp: 
        json.dump(builder_searchers, fp)


block_to_builder, blocks = load_block_to_builder()
count_addrs(block_to_builder, blocks[:500])


