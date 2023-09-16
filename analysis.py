import os
from decimal import Decimal
import pandas as pd
import json
import ijson
import constants
from collections import defaultdict, Counter
from itertools import islice
import statistics
import csv
import re
import atomic_mev, main_mev

# FILE METHODS


def load_dict_from_json(filename):
    with open(filename) as file:
        dict = json.load(file)
        if dict == None:
            dict = {}
        return dict


def dump_dict_to_json(dict, filename):
    with open(filename, "w+") as fp:
        json.dump(dict, fp)


def decimal_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)  # or use str(obj) if you want the exact string representation
    raise TypeError("Type not serializable")


def merge_large_json_files(file_list, output_file):
    with open(output_file, "w") as outfile:
        outfile.write("{")  # start of json

        # flag to keep track if we need to write a comma
        write_comma = False

        for file in file_list:
            with open(file, "rb") as infile:
                # process file
                objects = ijson.kvitems(infile, "")
                for key, value in objects:
                    # if not first object, add a comma
                    if write_comma:
                        outfile.write(",")
                    outfile.write(
                        json.dumps(key)
                        + ":"
                        + json.dumps(value, default=decimal_serializer)
                    )  # add block_number: block_detail pair
                    write_comma = True

        outfile.write("}")  # end of json


def prepare_file_list(dir, keyword="", sort=True):
    # dir = block_data, no /
    files = os.listdir(dir)
    file_list = []
    for file in files:
        if keyword in file:
            file = dir + "/" + file
            file_list.append(file)
    if sort:
        file_list = sorted(file_list)
    return file_list


def replace_upper_non_alnum(s):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s)
    return s.upper()


def covert_csv_to_json(csv_file):
    res = {}
    with open(csv_file, newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            res["key"] = row["property"]
            # address = row["address"]
            # label = replace_upper_non_alnum(row["name"])
            # labeled_contracts[label] = address

    with jsonfile as jsonfile:
        json.dump(res, jsonfile)


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

    return {
        k: v
        for k, v in bots.items()
        if k not in etherscan_bots and k not in coinbase_bots
    }


def return_mev_bots(bots, dir):
    # eliminate known etherscan bots
    etherscan_bots = load_dict_from_json(
        "searcher_databases/etherscan_searchers.json"
    ).keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribe.json").keys()

    return {k: v for k, v in bots.items() if k in etherscan_bots or k in coinbase_bots}


def slice_dict(d, n):
    return dict(islice(d.items(), n))


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


# PRUNE


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


# SORT


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


# COMBINE


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


def get_builder_market_share_percentage(map):
    builder_market_share = {}

    for builder, searchers in map.items():
        builder_market_share[builder] = sum(searchers.values())
    total_count = sum(builder_market_share.values())

    # calculate the percentages
    for builder, count in builder_market_share.items():
        builder_market_share[builder] = count / total_count * 100

    # # adjust the percentages to make sure they sum up to 100
    # adjustment = 100 - sum(builder_market_share.values())
    # builder_with_max_share = max(builder_market_share, key=builder_market_share.get)
    # builder_market_share[builder_with_max_share] += adjustment

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


# if __name__ == "__main__":
