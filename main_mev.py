import time
import requests
import traceback
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import analysis
from collections import defaultdict
import atomic_mev, nonatomic_mev

def map_extra_data_to_builder(extra_data, feeRecipient):
    builder = re.sub(r'\W+', '', extra_data)
    if builder == "":
        builder = feeRecipient
    elif "geth" in builder or "nethermind" in builder or "linux" in builder:
        builder = "vanilla_builder"
    return builder 


def analyze_tx(builder, fee_recipient, tx, full_tx, full_next_tx, transfer_map, 
               top_of_block_boundary, median_gas, addrs_counted_in_block,
               builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, 
               builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe,
               builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
               builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):

    mev_type = tx['mev_type']
    if mev_type == "swap" or mev_type == "sandwich":
        nonatomic_mev.analyze_tx(builder, fee_recipient, tx, full_tx, full_next_tx, transfer_map, top_of_block_boundary, median_gas, addrs_counted_in_block,
               builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
               builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)
    else:
        atomic_mev.analyze_tx(builder, tx, full_tx, transfer_map, addrs_counted_in_block,
                              builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, 
                              builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe)

# processes addr_tos of all MEV txs in a block
def analyze_block(session, url, block_number, block, fetched_internal_transfers, 
                  builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, 
                  builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe,
                  builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
                  builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe):
    try: 
        total_txs = len(block["transactions"])
        if total_txs < 1:
            # empty block
            return
        
        extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
        # human-readable builder name, derived from extraData 
        builder = atomic_mev.map_extra_data_to_builder(extra_data, block["feeRecipient"]) 
        # hex-string of feeRecipient. can be builder or proposer
        fee_recipient = block["feeRecipient"]
        median_gas = nonatomic_mev.calculate_block_median_gas_price(block["transactions"])
        transfer_map = fetched_internal_transfers[block_number]

        top_of_block_boundary = int(total_txs * 0.1) + ((total_txs * 0.1) % 1 > 0)

        payload = {
            'block_number': block_number,
            "count": "1"
        }
        res = session.get(url, params=payload)

        
        if (int(block_number) - 17595510) % 500 == 0:
            print(block_number)

        builder_atomic_map_block[builder]['total'] += 1
        builder_nonatomic_map_block[builder]['total'] += 1

        addrs_counted_in_block = set()

        if res.status_code == 200:
            data = res.json()
            for tx in data:
                full_tx = block["transactions"][tx["tx_index"]]
                if tx['tx_index'] == total_txs - 1: # tx is at the end of the block
                    full_next_tx = {}
                else: 
                    full_next_tx = block["transactions"][tx['tx_index']+1]
                analyze_tx(builder, fee_recipient, tx, full_tx, full_next_tx, transfer_map, 
                            top_of_block_boundary, median_gas, addrs_counted_in_block,
                            builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, 
                            builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe,
                            builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, 
                            builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)
                                
        else: 
            print("error w requesting zeromev:", res.status_code, block_number, block)
    except Exception as e:
        print("error found in one block", e, block_number)
        print(traceback.format_exc())


def default_block_dic():
    # Create a defaultdict that defaults to 0
    inner = defaultdict(int)
    # But initialize 'total' to 0 explicitly
    inner['total'] = 0
    return inner

def analyze_blocks(fetched_blocks, fetched_internal_transfers):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    builder_atomic_map_block = defaultdict(default_block_dic)
    builder_atomic_map_tx = defaultdict(lambda : defaultdict(atomic_mev.default_searcher_dic))
    builder_atomic_map_profit = defaultdict(lambda : defaultdict(atomic_mev.default_searcher_dic))
    builder_atomic_map_vol = defaultdict(lambda : defaultdict(atomic_mev.default_searcher_dic))
    builder_atomic_map_coin_bribe = defaultdict(lambda: defaultdict(atomic_mev.default_searcher_dic))
    builder_atomic_map_gas_bribe = defaultdict(lambda: defaultdict(atomic_mev.default_searcher_dic))
    
    builder_nonatomic_map_block = defaultdict(default_block_dic)
    builder_nonatomic_map_tx = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_vol = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_coin_bribe = defaultdict(lambda: defaultdict(int))
    builder_nonatomic_map_gas_bribe = defaultdict(lambda: defaultdict(int))

    coinbase_bribe = {}
    after_bribe = {}
    tob_bribe = {}

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=32) as executor:
            # Use the executor to submit the tasks
            futures = [executor.submit(analyze_block, session, zeromev_url, block_number, block, fetched_internal_transfers,
                                       builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe,
                                       builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, 
                                       coinbase_bribe, after_bribe, tob_bribe) for block_number, block in fetched_blocks.items()]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")
    
    return builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe, builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe


if __name__ == "__main__":
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")
    BLOCKS_PATH = "block_data/blocks_50_days.json"
    INTERNAL_TRANSFERS_PATH = "internal_transfers_data/internal_transfers_50_days.json"

    fetched_blocks = analysis.load_dict_from_json(BLOCKS_PATH)
    fetched_internal_transfers = analysis.load_dict_from_json(INTERNAL_TRANSFERS_PATH)

    pre_analysis = time.time()
    print(f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks for atomic.")
    builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe, builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe = analyze_blocks(fetched_blocks, fetched_internal_transfers)
    post_analysis = time.time()
    print(f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data.")

    atomic_mev.compile_atomic_data(builder_atomic_map_block, builder_atomic_map_tx, builder_atomic_map_profit, builder_atomic_map_vol, builder_atomic_map_coin_bribe, builder_atomic_map_gas_bribe)
    nonatomic_mev.compile_cefi_defi_data(builder_nonatomic_map_block, builder_nonatomic_map_tx, builder_nonatomic_map_vol, builder_nonatomic_map_coin_bribe, builder_nonatomic_map_gas_bribe, coinbase_bribe, after_bribe, tob_bribe)