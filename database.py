import requests 
import json 
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import constants

# to do
# in cases where block.miner/fee_recipient is the proposer, those blocks r ignored 
# do analysis w dataset
    # calculate the likelihood of accepting a specific searcher for a builder 
    # determine metrics for abnormality (50%, 75%) more likely 
    # differentiate between bots preferred by builder vs bots preferring a builder 
        # how to achieve such differentiation? 
# what other interesting conclusions can be drawn with this dataset?
# disjoint is not necessarily the most helpful, bigger builders may obscure the smaller builders who r doing sketchy stuff

common_addrs = defaultdict(lambda: defaultdict(int))


def load_block_to_builder():
    jsonfile = "block_to_builder_50k.json"
    with open(jsonfile) as file:
        block_to_builder = json.load(file) 
        blocks = block_to_builder.keys()
        return block_to_builder, list(blocks)


# block_number: string
def get_block_builder(block_number, block_to_builder):
    builder = block_to_builder[block_number].lower()
    if builder == constants.BUILDER_0X69:
        return "builder0x69"
    elif builder == constants.BEAVERBUILD:
        return "beaverbuild"
    elif builder == constants.RSYNC:
        return "rsync"
    elif builder == constants.FLASHBOTS:
        return "flashbots"
    elif builder == constants.ETHBUILDER:
        return "ethbuilder"
    else:
        return "others"


def incrementBotCount(builder, addr_from, addr_to):
    global common_addrs

    if addr_from not in constants.COMMON_CONTRACTS:
        common_addrs[builder][addr_from] += 1

    if addr_to not in constants.COMMON_CONTRACTS:
        common_addrs[builder][addr_to] += 1



def count_addrs_in_one_block(url, block_number, block_to_builder):

    global common_addrs
    payload = {
        'block_number': block_number,
        "count": "1"
    }
    res = requests.get(url, params=payload)

    if res.status_code == 200:
        data = res.json()
        builder = get_block_builder(block_number, block_to_builder) 
        print(builder, block_number)
        for tx in data:
            addr_from = tx['address_from'].lower()
            addr_to = tx['address_to'].lower()
            incrementBotCount(builder, addr_from, addr_to)

    else: 
        print("error w requesting zeromev:", res.status_code)


def count_addrs(block_to_builder, blocks):
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"

        # Create a ThreadPoolExecutor
    start = time.time()
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(count_addrs_in_one_block, zeromev_url, b, block_to_builder) for b in blocks]
        for future in as_completed(futures):
            pass
    print("finished counting in", time.time() - start)


    # start = time.time()
    # print("start counting all blocks", start)
    # for b in blocks[:20]:
    #     count_addrs_in_one_block(zeromev_url, b, block_to_builder)

    # print("finish counting all blocks take", time.time()-start)

    filter_out_one_time = {outer_k: {inner_k: v for inner_k, v in outer_v.items() if v > 3} for outer_k, outer_v in common_addrs.items()}
    ordered_addrs = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)) for k, v in filter_out_one_time.items()}

    with open('result.json', 'w') as fp: 
        json.dump(ordered_addrs, fp)


block_to_builder, blocks = load_block_to_builder()
count_addrs(block_to_builder, blocks)


