import requests
import traceback
import re, string
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed, wait
import constants
import analysis
import nonatomic_mev, main_mev


# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known router, dex, etc
def analyze_tx(
    builder,
    tx,
    full_tx,
    transfer_map,
    addrs_counted_in_block,
    builder_atomic_map_block,
    builder_atomic_map_tx,
    builder_atomic_map_profit,
    builder_atomic_map_vol,
    builder_atomic_map_coin_bribe,
    builder_atomic_map_gas_bribe,
    builder_atomic_map_vol_list,
):
    mev_type = tx["mev_type"]
    if mev_type == "sandwich" or mev_type == "swap":
        return

    addr_to = tx["address_to"].lower()
    addr_from = tx["address_from"].lower()
    profit = tx.get("extractor_profit_usd", 0) or 0
    volume = tx.get("extractor_swap_volume_usd", 0) or 0

    # collect info on bribes
    if full_tx["hash"] in transfer_map.keys():
        builder_atomic_map_coin_bribe[builder][addr_to][mev_type] += transfer_map[
            full_tx["hash"]
        ]["value"]
        builder_atomic_map_coin_bribe[builder][addr_to]["total"] += transfer_map[
            full_tx["hash"]
        ]["value"]

    else:
        builder_atomic_map_gas_bribe[builder][addr_to][mev_type] += (
            full_tx["gas"] * full_tx["gasPrice"]
        )
        builder_atomic_map_gas_bribe[builder][addr_to]["total"] += (
            full_tx["gas"] * full_tx["gasPrice"]
        )

    # handle info collection depending on mev_type
    if mev_type == "arb" or mev_type == "frontrun":
        builder_atomic_map_tx[builder][addr_to][mev_type] += 1
        builder_atomic_map_profit[builder][addr_to][mev_type] += profit
        builder_atomic_map_vol[builder][addr_to][mev_type] += volume
        builder_atomic_map_vol_list[builder][addr_to].append(volume)
        builder_atomic_map_tx[builder][addr_to]["total"] += 1
        builder_atomic_map_profit[builder][addr_to]["total"] += profit
        builder_atomic_map_vol[builder][addr_to]["total"] += volume

        if addr_to not in addrs_counted_in_block:
            builder_atomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)

    elif mev_type == "backrun":
        # counting both txs in a sandwich
        builder_atomic_map_tx[builder][addr_to][mev_type] += 1
        # revenut (not profit) will be zero for one of the legs. if even, then in front
        builder_atomic_map_profit[builder][addr_to][mev_type] += profit
        builder_atomic_map_vol[builder][addr_to][mev_type] += volume
        builder_atomic_map_vol_list[builder][addr_to].append(volume)

        # only count volume from frontrun in the total (can count it separate for later purpose)
        builder_atomic_map_tx[builder][addr_to]["total"] += 1
        builder_atomic_map_profit[builder][addr_to]["total"] += profit

        if addr_to not in addrs_counted_in_block:
            builder_atomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)

    elif mev_type == "liquid":
        # addr_from here, bc liquidation doesnt use special contracts but EOA
        builder_atomic_map_tx[builder][addr_from][mev_type] += 1
        builder_atomic_map_vol[builder][addr_from][mev_type] += volume
        builder_atomic_map_vol_list[builder][addr_from].append(volume)

        builder_atomic_map_tx[builder][addr_from]["total"] += 1
        builder_atomic_map_profit[builder][addr_from]["total"] += profit
        builder_atomic_map_vol[builder][addr_from]["total"] += volume

        if addr_from not in addrs_counted_in_block:
            builder_atomic_map_block[builder][addr_from] += 1
            addrs_counted_in_block.add(addr_from)


# maps the extradata to builder
def map_extra_data_to_builder(extra_data, feeRecipient):
    builder = re.sub(r"\W+", "", extra_data)
    if builder == "":
        builder = feeRecipient
    elif "geth" in builder or "nethermind" in builder or "linux" in builder:
        builder = "vanilla_builder"
    return builder


# processes addr_tos of all MEV txs in a block
def analyze_block(
    session,
    url,
    block_number,
    block,
    fetched_internal_transfers,
    builder_atomic_map_block,
    builder_atomic_map_tx,
    builder_atomic_map_profit,
    builder_atomic_map_vol,
    builder_atomic_map_coin_bribe,
    builder_atomic_map_gas_bribe,
    builder_atomic_map_vol_list,
):
    try:
        extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
        builder = map_extra_data_to_builder(extra_data, block["feeRecipient"])
        fee_recipient = block["feeRecipient"]
        transfer_map = fetched_internal_transfers[block_number]
        payload = {"block_number": block_number, "count": "1"}
        res = session.get(url, params=payload)

        if (int(block_number) - 17595510) % 100 == 0:
            print(block_number)

        builder_atomic_map_block[builder]["total"] += 1
        addrs_counted_in_block = set()

        if res.status_code == 200:
            data = res.json()
            for tx in data:
                full_tx = block["transactions"][tx["tx_index"]]
                analyze_tx(
                    builder,
                    tx,
                    full_tx,
                    transfer_map,
                    addrs_counted_in_block,
                    builder_atomic_map_block,
                    builder_atomic_map_tx,
                    builder_atomic_map_profit,
                    builder_atomic_map_vol,
                    builder_atomic_map_coin_bribe,
                    builder_atomic_map_gas_bribe,
                )

        else:
            print("error w requesting zeromev:", res.status_code)
    except Exception as e:
        print("error found in one block", e, block_number)
        print(traceback.format_exc())


def default_searcher_dic():
    return {"total": 0, "arb": 0, "frontrun": 0, "backrun": 0, "liquid": 0}


# iterate through all the blocks to create a frequency mapping between builders and searchers
# use thread pool to expediate process
def analyze_blocks(fetched_blocks, fetched_internal_transfers):
    # returns all the MEV txs in that block (are there false negatives?)
    zeromev_url = "https://data.zeromev.org/v1/mevBlock"
    builder_atomic_map_block = defaultdict(main_mev.default_block_dic)
    builder_atomic_map_tx = defaultdict(lambda: defaultdict(default_searcher_dic))
    builder_atomic_map_profit = defaultdict(lambda: defaultdict(default_searcher_dic))
    builder_atomic_map_vol = defaultdict(lambda: defaultdict(default_searcher_dic))
    builder_atomic_map_coin_bribe = defaultdict(
        lambda: defaultdict(default_searcher_dic)
    )
    builder_atomic_map_gas_bribe = defaultdict(
        lambda: defaultdict(default_searcher_dic)
    )

    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("starting to go thru blocks")
        with ThreadPoolExecutor(max_workers=64) as executor:
            # Use the executor to submit the tasks
            futures = [
                executor.submit(
                    analyze_block,
                    session,
                    zeromev_url,
                    block_number,
                    block,
                    fetched_internal_transfers,
                    builder_atomic_map_block,
                    builder_atomic_map_tx,
                    builder_atomic_map_profit,
                    builder_atomic_map_vol,
                    builder_atomic_map_coin_bribe,
                    builder_atomic_map_gas_bribe,
                )
                for block_number, block in fetched_blocks.items()
            ]
            for future in as_completed(futures):
                pass
        print("finished counting in", time.time() - start, " seconds")

    return (
        builder_atomic_map_block,
        builder_atomic_map_tx,
        builder_atomic_map_profit,
        builder_atomic_map_vol,
        builder_atomic_map_coin_bribe,
        builder_atomic_map_gas_bribe,
    )


def compile_atomic_data(
    builder_atomic_map_block,
    builder_atomic_map_tx,
    builder_atomic_map_profit,
    builder_atomic_map_vol,
    builder_atomic_map_coin_bribe,
    builder_atomic_map_gas_bribe,
    builder_atomic_map_vol_list,
):
    analysis.dump_dict_to_json(
        builder_atomic_map_block,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_block.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_tx,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_tx.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_profit,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_profit.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_vol,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_vol.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_coin_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_coin_bribe.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_gas_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_gas_bribe.json",
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_vol_list,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_vol_list.json",
    )

    agg_block = analysis.aggregate_block_count(builder_atomic_map_block)
    agg_tx = analysis.create_sorted_agg_from_atomic_map(builder_atomic_map_tx)
    agg_profit = analysis.create_sorted_agg_from_atomic_map(builder_atomic_map_profit)
    agg_vol = analysis.create_sorted_agg_from_atomic_map(builder_atomic_map_vol)
    agg_coin = analysis.create_sorted_agg_from_atomic_map(builder_atomic_map_coin_bribe)
    agg_gas = analysis.create_sorted_agg_from_atomic_map(builder_atomic_map_gas_bribe)
    analysis.dump_dict_to_json(agg_block, "atomic/fourteen/agg/agg_block.json")
    analysis.dump_dict_to_json(agg_tx, "atomic/fourteen/agg/agg_tx.json")
    analysis.dump_dict_to_json(agg_profit, "atomic/fourteen/agg/agg_profit.json")
    analysis.dump_dict_to_json(agg_vol, "atomic/fourteen/agg/agg_vol.json")
    analysis.dump_dict_to_json(agg_coin, "atomic/fourteen/agg/agg_coin.json")
    analysis.dump_dict_to_json(agg_gas, "atomic/fourteen/agg/agg_gas.json")

    builder_atomic_map_bribe, agg_bribe = analysis.combine_gas_and_coin_bribes_in_eth(
        builder_atomic_map_gas_bribe, builder_atomic_map_coin_bribe, True
    )
    analysis.dump_dict_to_json(
        builder_atomic_map_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_bribe.json",
    )
    analysis.dump_dict_to_json(agg_bribe, "atomic/fourteen/agg/agg_bribe.json")


if __name__ == "__main__":
    # 17563790 to 17779790
    start = time.time()
    print(f"Starting to load block from json at {start / 1000}")

    fetched_blocks = analysis.load_dict_from_json("block_data/blocks_50_days.json")
    fetched_internal_transfers = analysis.load_dict_from_json(
        "internal_transfers_data/internal_transfers_50_days.json"
    )
    pre_analysis = time.time()
    print(
        f"Finished loading blocks in {pre_analysis - start} seconds. Now analyzing blocks."
    )
    (
        builder_atomic_map_block,
        builder_atomic_map_tx,
        builder_atomic_map_profit,
        builder_atomic_map_vol,
        builder_atomic_map_coin_bribe,
        builder_atomic_map_gas_bribe,
    ) = analyze_blocks(fetched_blocks, fetched_internal_transfers)
    post_analysis = time.time()
    print(
        f"Finished analysis in {post_analysis - pre_analysis} seconds. Now compiling data."
    )

    compile_atomic_data(
        builder_atomic_map_block,
        builder_atomic_map_tx,
        builder_atomic_map_profit,
        builder_atomic_map_vol,
        builder_atomic_map_coin_bribe,
        builder_atomic_map_gas_bribe,
    )
