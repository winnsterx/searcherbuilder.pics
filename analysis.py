import os, time, math
import pandas as pd
import json
import collections
import constants
import analysis
from collections import defaultdict, Counter
from itertools import islice
import statistics
import requests
import secret_keys
import functools
import visual_analysis
import fetch_blocks, chartprep, atomic_mev, main_mev


def load_dict_from_json(filename):
    with open(filename) as file:
        dict = json.load(file)
        return dict


def load_nested_dict_from_json(filename, lamb):
    with open(filename) as file:
        dict = json.load(file, object_hook=functools.partial(defaultdict, lambda: lamb))
        return dict


def dump_dict_to_json(dict, filename):
    with open(filename, "w+") as fp:
        json.dump(dict, fp)


def find_joint_between_two_aggs(db_one, db_two):
    addr_one = set(db_one.keys())
    addr_two = set(db_two.keys())
    return addr_one & addr_two


def find_only_in_agg_one(agg_one, agg_two):
    return {k: v for k, v in agg_one.items() if k not in agg_two.keys()}


def return_non_mev_bots(bots, dir):
    # eliminate known etherscan bots
    etherscan_bots = load_dict_from_json(
        "searcher_databases/etherscan_searchers.json"
    ).keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribes.json").keys()
    # eliminate bots that i labeled
    mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {
        k: v
        for k, v in bots.items()
        if k not in etherscan_bots and k not in coinbase_bots and k not in mine_bots
    }


def return_mev_bots(bots, dir):
    # eliminate known etherscan bots
    etherscan_bots = load_dict_from_json(
        "searcher_databases/etherscan_searchers.json"
    ).keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribe.json").keys()
    # eliminate bots that i labeled
    # mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {k: v for k, v in bots.items() if k in etherscan_bots or k in coinbase_bots}


def trim_agg(agg, threshold):
    sorted_agg = {
        k: v
        for k, v in sorted(agg.items(), key=lambda item: item[1], reverse=True)
        if v >= threshold
    }
    dump_dict_to_json(sorted_agg, agg_dir + "/trimmed_agg.json")


def combine_atomic_nonatomic_agg():
    atomic = load_dict_from_json("atomic/atomic_searchers_agg.json")
    non_atomic = load_dict_from_json(
        "non_atomic/above_50_median/cefi_searchers_agg.json"
    )
    result = dict(Counter(atomic) + Counter(non_atomic))
    # sorted_result = {k: v for k, v in sorted(result.items(), key=lambda item: item[1], reverse=True) if v >= 5}
    sorted_result = {
        k: v
        for k, v in sorted(result.items(), key=lambda item: item[1], reverse=True)[:20]
    }
    dump_dict_to_json(sorted_result, "all_searchers.json")
    return sorted_result


def remove_coinbase_bribe_searchers(all_nonatomic):
    coinbase_searchers = load_dict_from_json(
        "non_atomic/all_swaps/coinbase_bribe.json"
    ).keys()
    return {k: v for k, v in all_nonatomic.items() if k not in coinbase_searchers}


def slice_dict(d, n):
    return dict(islice(d.items(), n))


def rid_map_of_small_addrs(
    map,
    agg,
):
    trimmed_agg = {k: v for k, v in agg.items() if v >= 100}
    trimmed_map = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for searcher, count in searchers.items():
            if searcher in trimmed_agg.keys():
                trimmed_map[builder][searcher] = count
    return trimmed_map


def remove_known_entities_from_agg(agg):
    res = {}
    for addr, count in agg.items():
        if (
            addr not in constants.COMMON_CONTRACTS
            and addr not in constants.LABELED_CONTRACTS.values()
        ):
            res[addr] = count
    return res


def return_atomic_maps_with_only_type(map, type):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for searcher, stats in searchers.items():
            res[builder][searcher] = stats[type]
    return res


def remove_small_builders(map, agg, min_count):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        builder_total_count = sum(searchers.values())
        if builder_total_count > min_count:
            res[builder] = searchers
        else:
            for searcher, count in searchers.items():
                if searcher in agg:
                    agg[searcher] -= count

    return res, agg


# agg is all the searchers, sans known entities
# map is all the fields
def get_map_and_agg_in_range(map, agg, threshold):
    # must sort agg first to get accurate top searchers
    agg = sort_agg(agg)

    total_count = sum(agg.values())
    threshold = total_count * threshold

    # Find the top searchers with a collective transaction count >50%
    running_total = 0
    top_searchers = {}
    for searcher, count in agg.items():
        running_total += agg[searcher]
        top_searchers[searcher] = count
        if running_total > threshold:
            break

    # Filter the data based on the top searchers
    filtered_map = {}
    for builder, searchers in map.items():
        filtered_map[builder] = {
            searcher: tx_count
            for searcher, tx_count in searchers.items()
            if searcher in top_searchers
        }
    return filtered_map, top_searchers


def get_agg_in_range(agg, threshold):
    agg = sort_agg(agg)

    total_count = sum(agg.values())
    threshold = total_count * threshold

    # Find the top searchers with a collective transaction count >50%
    running_total = 0
    top_searchers = {}
    for searcher, count in agg.items():
        running_total += agg[searcher]
        top_searchers[searcher] = count
        if running_total > threshold:
            break
    return top_searchers


def remove_atomic_from_map_and_agg(map, agg, atomic):
    map = remove_atomic_from_map(map, atomic)
    agg = remove_atomic_from_agg(agg, atomic)
    return map, agg


def remove_atomic_from_agg(agg, atomic):
    res = {}
    for addr, count in agg.items():
        if addr not in atomic:
            res[addr] = count
    return res


def remove_atomic_from_map(map, atomic):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for searcher, count in searchers.items():
            if searcher not in atomic:
                res[builder][searcher] = count
    return res


def prune(dir, is_atomic):
    # prune from agg
    agg_list = fetch_blocks.prepare_file_list(dir + "/agg")
    for a in agg_list:
        agg = load_dict_from_json(a)
        res = remove_known_entities_from_agg(agg)
        if is_atomic == False:
            res = remove_atomic_from_agg(
                res, load_dict_from_json("atomic/new/agg/agg_vol.json")
            )
        dump_dict_to_json(res, dir + "/pruned/agg/" + os.path.basename(a))


def create_sorted_agg_from_atomic_map(builder_atomic_map):
    # {builder: {searcher: {"total": x, "arb": x, "frontrun": x, "backrun": x, "liquid": x}}}
    # aggregate means adding up the total for each searcher
    agg = defaultdict(int)
    for _, searchers in builder_atomic_map.items():
        for searcher, counts in searchers.items():
            agg[searcher] += counts["total"]
    agg = sort_agg(agg)
    return agg


def aggregate_block_count(builder_searcher_map_block):
    agg = defaultdict(int)
    for _, searchers in builder_searcher_map_block.items():
        for searcher, count in searchers.items():
            if searcher == "total":
                continue
            else:
                agg[searcher] += count
    agg = sort_agg(agg)
    return agg


def prune_known_entities_from_map_and_agg(map, agg):
    agg = prune_known_entities_from_agg(agg)
    map = prune_known_entities_from_simple_map(map)
    return map, agg


def prune_known_entities_from_agg(agg):
    res = {}
    for addr, count in agg.items():
        if (
            addr not in constants.COMMON_CONTRACTS
            and addr not in constants.LABELED_CONTRACTS.values()
        ):
            res[addr] = count
    return res


def prune_known_entities_from_simple_map(map):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for addr, count in searchers.items():
            if (
                addr not in constants.COMMON_CONTRACTS
                and addr not in constants.LABELED_CONTRACTS.values()
            ):
                res[builder][addr] = count
    return res


def prune_known_entities_from_atomic_map(map):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for addr, stats in searchers.items():
            if (
                addr not in constants.COMMON_CONTRACTS
                and addr not in constants.LABELED_CONTRACTS.values()
            ):
                res[builder][addr] = stats["total"]
    return res


def prune_known_entities_from_searcher_builder_map(map):
    res = defaultdict(lambda: defaultdict(int))
    for searcher, builders in map.items():
        if (
            searcher not in constants.COMMON_CONTRACTS
            and searcher not in constants.LABELED_CONTRACTS.values()
        ):
            res[searcher] = builders

    return res


def sort_agg(agg):
    return {
        k: v for k, v in sorted(agg.items(), key=lambda item: item[1], reverse=True)
    }


def sort_map(map):
    map = {
        outer_key: {
            inner_key: count
            for inner_key, count in sorted(
                inner_dict.items(), key=lambda item: item[1], reverse=True
            )
        }
        for outer_key, inner_dict in map.items()
    }
    builder_totals = {
        builder: sum(searchers.values()) for builder, searchers in map.items()
    }
    builder_totals = sorted(
        builder_totals.keys(), key=lambda builder: builder_totals[builder], reverse=True
    )
    sorted_map = {builder: map[builder] for builder in builder_totals}
    return sorted_map


def sort_atomic_map_by_total(map):
    for outer_key, inner_dict in map.items():
        sorted_inner_dict = {
            k: v
            for k, v in sorted(
                inner_dict.items(), key=lambda item: item[1]["total"], reverse=True
            )
        }
        map[outer_key] = sorted_inner_dict
    sorted_map = {
        k: v
        for k, v in sorted(
            map.items(),
            key=lambda item: sum(
                inner_dict["total"] for inner_dict in item[1].values()
            ),
            reverse=True,
        )
    }
    return sorted_map


# maps and aggs are pruned of known entities
def combine_atomic_nonatomic_map_and_agg(
    atomic_map, atomic_agg, nonatomic_map, nonatomic_agg
):
    total_map = defaultdict(lambda: defaultdict(int))
    for builder, searchers in atomic_map.items():
        for searcher, stat in searchers.items():
            total_map[builder][searcher] += stat

    for builder, searchers in nonatomic_map.items():
        for searcher, stat in searchers.items():
            total_map[builder][searcher] += stat

    total_agg = defaultdict(int)
    for searcher, count in atomic_agg.items():
        total_agg[searcher] += count
    for searcher, count in nonatomic_agg.items():
        total_agg[searcher] += count

    return total_map, total_agg


def combine_atomic_nonatomic_block_map_and_agg(
    atomic_map, atomic_agg, nonatomic_map, nonatomic_agg
):
    total_map = defaultdict(lambda: defaultdict(int))
    for builder, searchers in atomic_map.items():
        for searcher, stat in searchers.items():
            if searcher == "total":
                total_map[builder]["total"] = stat
            else:
                total_map[builder][searcher] += stat

    for builder, searchers in nonatomic_map.items():
        for searcher, stat in searchers.items():
            if searcher == "total":
                total_map[builder]["total"] = stat
            else:
                total_map[builder][searcher] += stat

    total_agg = defaultdict(int)
    for searcher, count in atomic_agg.items():
        total_agg[searcher] += count
    for searcher, count in nonatomic_agg.items():
        total_agg[searcher] += count

    return total_map, total_agg


def create_searcher_builder_map(map):
    res = defaultdict(lambda: defaultdict(int))
    for builder, searchers in map.items():
        for searcher, count in searchers.items():
            res[searcher][builder] += count
    res = sort_map(res)
    return res


def create_sorted_agg_from_map(map):
    res = defaultdict(int)
    for _, searchers in map.items():
        for searcher, count in searchers.items():
            res[searcher] += count
    res = sort_agg(res)
    return res


def wei_to_eth(wei_val):
    wei_per_eth = 10**18
    return wei_val / wei_per_eth


def combine_gas_and_coin_bribes_in_eth(gas_map, coin_map, is_atomic):
    wei_per_eth = 10**18

    if is_atomic:
        res = defaultdict(lambda: defaultdict(atomic_mev.default_searcher_dic))
        for builder, searchers in gas_map.items():
            for searcher, stats in searchers.items():
                res[builder][searcher]["total"] += stats["total"] / wei_per_eth
                res[builder][searcher]["arb"] += stats["arb"] / wei_per_eth
                res[builder][searcher]["frontrun"] += stats["frontrun"] / wei_per_eth
                res[builder][searcher]["backrun"] += stats["backrun"] / wei_per_eth
                res[builder][searcher]["liquid"] += stats["liquid"] / wei_per_eth

        for builder, searchers in coin_map.items():
            for searcher, stats in searchers.items():
                res[builder][searcher]["total"] += stats["total"]
                res[builder][searcher]["arb"] += stats["arb"]
                res[builder][searcher]["frontrun"] += stats["frontrun"]
                res[builder][searcher]["backrun"] += stats["backrun"]
                res[builder][searcher]["liquid"] += stats["liquid"]

        res = sort_atomic_map_by_total(res)
        # res = prune_known_entities_from_atomic_map(res)
        agg = create_sorted_agg_from_atomic_map(res)
    else:
        res = defaultdict(lambda: defaultdict(int))
        for builder, searchers in gas_map.items():
            for searcher, gas in searchers.items():
                res[builder][searcher] += gas / wei_per_eth

        for builder, searchers in gas_map.items():
            for searcher, coin in searchers.items():
                res[builder][searcher] += coin
        res = sort_map(res)
        # res = prune_known_entities_from_simple_map(res)
        agg = create_sorted_agg_from_map(res)

    return res, agg


def humanize_number(value, fraction_point=1):
    powers = [10**x for x in (12, 9, 6, 3, 0)]
    human_powers = ("T", "B", "M", "K", "")
    is_negative = False
    if not isinstance(value, float):
        value = float(value)
    if value < 0:
        is_negative = True
        value = abs(value)
    for i, p in enumerate(powers):
        if value >= p:
            return_value = (
                str(
                    round(value / (p / (10.0**fraction_point)))
                    / (10**fraction_point)
                )
                + human_powers[i]
            )
            break
    if is_negative:
        return_value = "-" + return_value

    return return_value


# def get_builder_market_share_percentage(map):
#     builder_market_share = {}

#     for builder, searchers in map.items():
#         builder_market_share[builder] = sum(searchers.values())
#     total_count = sum(builder_market_share.values())
#     for builder, count in builder_market_share.items():
#         builder_market_share[builder] = count / total_count * 100

#     return builder_market_share


def get_builder_market_share_percentage(map):
    builder_market_share = {}

    for builder, searchers in map.items():
        builder_market_share[builder] = sum(searchers.values())
    total_count = sum(builder_market_share.values())

    # calculate the percentages
    for builder, count in builder_market_share.items():
        builder_market_share[builder] = count / total_count * 100

    # adjust the percentages to make sure they sum up to 100
    adjustment = 100 - sum(builder_market_share.values())
    builder_with_max_share = max(builder_market_share, key=builder_market_share.get)
    builder_market_share[builder_with_max_share] += adjustment

    return builder_market_share


def get_big_builders(builder_market_share):
    big_builders = set()
    for builder, share in builder_market_share.items():
        if share > 25:
            big_builders.add(builder)
    return big_builders


def find_notable_searcher_builder_relationships(map):
    """
    Finds searchers who submitted either >2x to big 4 or >10 to other builders
    Only looking at searchers that in the 99th percentile AND only return
    at most top 20 searchers.
    """

    tolerance_big_builder = 2
    tolerance_small_builder = 10
    notable = defaultdict(lambda: defaultdict(int))
    highlight_relationship = set()

    searcher_builder_map = sort_map(create_searcher_builder_map(map))

    cutoff = 20  # only look at the top 20 interesting relationships
    i = 0
    builder_market_share = get_builder_market_share_percentage(map)  # by the metric
    dump_dict_to_json(searcher_builder_map, "searcher_b_nap.json")

    for searcher, builders in searcher_builder_map.items():
        if i >= cutoff:
            break
        total_count = sum(builders.values())
        for builder, count in builders.items():
            percent = count / total_count * 100
            builder_usual_percent = builder_market_share[builder]

            if builder_usual_percent > 40:
                # for an ultra big builder, it would have to be towards 100% to be interesting
                if percent > 80:
                    i += 1
                    highlight_relationship.add((searcher, builder))
                    # print(searcher, builder, percent, builder_usual_percent)
                    notable[searcher] = {
                        builder: (count / total_count) * 100
                        for builder, count in builders.items()
                    }
                    break
            elif builder_usual_percent > 25:
                # for a big builder, 2x is sufficiently preferential
                if percent > builder_usual_percent * tolerance_big_builder:
                    i += 1
                    highlight_relationship.add((searcher, builder))
                    # print(searcher, builder, percent, builder_usual_percent)
                    notable[searcher] = {
                        builder: (count / total_count) * 100
                        for builder, count in builders.items()
                    }
                    break
            elif builder_usual_percent > 3:
                if percent > builder_usual_percent * 3:
                    i += 1
                    highlight_relationship.add((searcher, builder))
                    # print(searcher, builder, percent, builder_usual_percent)
                    notable[searcher] = {
                        builder: (count / total_count) * 100
                        for builder, count in builders.items()
                    }
                    break
            elif (
                percent > builder_usual_percent * tolerance_small_builder
                and percent > 10
            ):
                # for a small builder, 10x is meaningful
                i += 1
                highlight_relationship.add((searcher, builder))
                # print(searcher, builder, percent, builder_usual_percent)
                notable[searcher] = {
                    builder: (count / total_count) * 100
                    for builder, count in builders.items()
                }
                break

    return notable, builder_market_share, highlight_relationship


def is_builder_fee_recipient(builder, fee_recipient):
    for b, addr in constants.BUILDER_ADDR_MAP.items():
        if b in builder:
            return addr == fee_recipient
    return False


def calculate_builder_profitability(blocks, receipts, internal_transfers):
    # for each block
    # builder_profit = total priority fee + total transfers to builders (internal and external) - total transfers from builders (to anyone within the block)
    builder_profit_map = defaultdict(int)
    builder_subsidy_map = defaultdict(int)

    for block_num, block in blocks.items():
        extra_data = bytes.fromhex(block["extraData"].lstrip("0x")).decode("ISO-8859-1")
        builder = main_mev.map_extra_data_to_builder(extra_data, block["feeRecipient"])
        if "flashbots" in extra_data:
            print(extra_data, block_num)
        receipt = receipts[block_num]

        total_priority_fees = 0
        total_coinbase_transfers = 0  # eth
        total_builder_rebates = 0  # wei

        builder_is_fee_recipient = is_builder_fee_recipient(
            builder, block["feeRecipient"]
        )

        # if builder_is_fee_recipient == False:
        #     print()
        #     continue

        for tx in block["transactions"]:
            # only know gas used in receipt (after the tx has happened)
            gas_used = receipt[tx["transactionIndex"]]["gas_used"]
            all_gas_fees = gas_used * tx["gasPrice"]

            base_fees = gas_used * block["baseFeePerGas"]
            priority_fees = all_gas_fees - base_fees

            total_priority_fees += priority_fees

            if tx["from"] == block["feeRecipient"]:
                # a rebate from builder
                total_builder_rebates += tx["value"]

        trs = internal_transfers[block_num]
        for tr_hash, tr in trs.items():
            total_coinbase_transfers += tr["value"]

        total_priority_fees = wei_to_eth(total_priority_fees)
        total_builder_rebates = wei_to_eth(total_builder_rebates)

        builder_block_profit = (
            total_priority_fees + total_coinbase_transfers - total_builder_rebates
        )

        print(builder_block_profit)

        if builder_block_profit < 0:
            builder_subsidy_map[builder] += abs(builder_block_profit)

        builder_profit_map[builder] += builder_block_profit

    return builder_profit_map, builder_subsidy_map


def create_searcher_builder_average_vol_map(map_tx, map_vol):
    # Initialize the result dictionary
    searcher_builder_map_avg = {}

    # Iterate through the builder_searcher_map_vol dictionary and compute the average volume per transaction
    for builder, searchers in map_vol.items():
        for searcher, volume in searchers.items():
            tx_count = map_tx[builder][searcher]
            avg_vol_per_tx = volume / tx_count
            searcher_builder_map_avg.setdefault(searcher, {})[builder] = avg_vol_per_tx

    return searcher_builder_map_avg


def create_searcher_builder_median_vol_map(map_vol_list):
    searcher_builder_map_med = {}
    for builder, searchers in map_vol_list.items():
        for searcher, vols in searchers.items():
            searcher_builder_map_med.setdefault(searcher, {})[
                builder
            ] = statistics.median(vols)

    return searcher_builder_map_med


def create_searcher_builder_vol_list_map(map_vol_list):
    searcher_builder_map = {}
    for builder, searchers in map_vol_list.items():
        for searcher, vols in searchers.items():
            searcher_builder_map.setdefault(searcher, {})[builder] = vols

    return searcher_builder_map


if __name__ == "__main__":
    start = 17969910
    num_blocks = 50400
    end = 18020309

    map_tx = load_dict_from_json(
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_tx.json"
    )
    map_vol = load_dict_from_json(
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_vol.json"
    )

    dump_dict_to_json(
        create_searcher_builder_average_vol_map(map_tx, map_vol),
        "searcher_builder_avg.json",
    )

    # beaconchain = load_dict_from_json("response_1693950298679.json")
    # block_numbers = [item["blockNumber"] for item in beaconchain["data"]]

    # blocks = fetch_blocks.get_blocks_by_list(block_numbers)
    # internal_transfers = (
    #     fetch_blocks.get_internal_transfers_to_fee_recipients_in_blocks(blocks)
    # )
    # receipts = fetch_blocks.get_blocks_receipts_by_list(block_numbers)

    # blocks = load_dict_from_json("block_18071077.json")
    # internal_transfers = load_dict_from_json("internal_transfers_18071077.json")
    # receipts = load_dict_from_json("receipt_18071077.json")

    # seven_day_blocks = {
    #     block_number: block
    #     for block_number, block in blocks.items()
    #     if int(block_number) > start and int(block_number) <= end
    # }
    # seven_day_receipts = {
    #     block_number: receipt
    #     for block_number, receipt in receipts.items()
    #     if int(block_number) > start and int(block_number) <= end
    # }

    # builder_profit_map, builder_subsidy_map = calculate_builder_profitability(
    #     blocks, receipts, internal_transfers
    # )

    # dump_dict_to_json(sort_agg(builder_profit_map), "builder_profit_map.json")
    # dump_dict_to_json(sort_agg(builder_subsidy_map), "builder_subsidy_map.json")

    # atomic_gas_map = load_dict_from_json("nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_gas_bribe.json")
    # atomic_coin_map = load_dict_from_json("nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_coin_bribe.json")
    # combine_gas_and_coin_bribes_in_eth(atomic_gas_map, atomic_coin_map, False, "fifty")

    # nonatomic_map = sort_map(load_dict_from_json("nonatomic/new/builder_nonatomic_maps/builder_nonatomic_map_vol.json"))
    # nonatomic_agg = load_dict_from_json("nonatomic/new/agg/agg_vol.json")
    # nonatomic_map, nonatomic_agg = get_map_and_agg_in_range(nonatomic_map, nonatomic_agg, 0.95)
    # nonatomic_map, nonatomic_agg = analysis.remove_small_builders(nonatomic_map, nonatomic_agg, 1000)
    # nonatomic_fig = chartprep.create_searcher_builder_sankey(nonatomic_map, nonatomic_agg, "Non-atomic Searcher-Builder Orderflow by Volume (USD, last month)", "USD")

    # nonatomic_fig.show()
    # blocks_agg = load_dict_from_json("atomic/fifty/builder_atomic_maps/builder_atomic_map_block.json")
    # tally = 0
    # for builder, searchers in blocks_agg.items():
    #     tally += searchers['total']

    # right_tally = 17955510-17595510
    # print(tally, right_tally)

    # searcher_flow = {}
    # for builder, searchers in nonatomic_map.items():
    #     for searcher, count in searchers.items():
    #         searcher_flow[searcher] = searcher_flow.get(searcher, 0) + count

    # for searcher, count in nonatomic_agg.items():
    #     if searcher_flow[searcher] != count:
    #         print("not the same!", searcher, count, searcher_flow[searcher])

    # nonatomic_fig = chartprep.create_searcher_builder_sankey(nonatomic_map, nonatomic_agg, "Non-atomic Searcher-Builder Orderflow by Volume (USD, last month)", "USD")
