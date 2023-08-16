import json
import collections
import constants
import analysis
from collections import defaultdict, Counter
from itertools import islice
import visual_analysis


def load_dict_from_json(filename):
    with open(filename) as file:
        dict = json.load(file)
        return dict

def dump_dict_to_json(dict, filename):
    with open(filename, 'w+') as fp: 
        json.dump(dict, fp)

def aggregate_searchers(builder_searcher_map):
    searcher_total_interactions = {}
    for builder, interactions in builder_searcher_map.items():
        for searcher, frequency in interactions.items():
            if searcher not in searcher_total_interactions:
                searcher_total_interactions[searcher] = 0
            searcher_total_interactions[searcher] += int(frequency)
    sorted_interactions = {k: v for k, v in sorted(searcher_total_interactions.items(), key=lambda item: item[1], reverse=True)}
    return sorted_interactions

def one_exclusive_relationships(builder_searcher_map, searcher_total_interactions):
    # examine strictly exclusive relationships
    exclusive = collections.defaultdict(dict)
    for builder, interactions in builder_searcher_map.items():
        for searcher, frequency in interactions.items():
            if int(frequency) == searcher_total_interactions[searcher]:
                # found an exclusive relationship
                exclusive[builder][searcher] = frequency
    
    return exclusive
        
def find_joint_between_two_searcher_db(db_one, db_two):
    addr_one = set(db_one.keys())
    addr_two = set(db_two.keys())
    return addr_one & addr_two

def find_only_in_db_one(db_one, db_two):
    return {k: v for k, v in db_one.items() if k not in db_two.keys()}

def remove_common_addrs(searchers):
    return {k: v for k, v in searchers.items() if k not in constants.COMMON_CONTRACTS}

def return_common_addrs(searchers):
    return {k: v for k, v in searchers.items() if k in constants.COMMON_CONTRACTS}

# Checks LIST of bots against Etherscan's MEV Bots, returns lists of known and potential bots
def check_mev_bots(potential_bots):
    mev_bots = analysis.load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    found_known_bots = []
    found_potential_bots = []
    for bot in potential_bots:
        if bot in mev_bots:
            found_known_bots.append(bot)
        else:
            found_potential_bots.append(bot)
    return found_known_bots, found_potential_bots
 

def return_non_mev_bots(bots, dir):
    # eliminate known etherscan bots 
    etherscan_bots = load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribes.json").keys()
    # eliminate bots that i labeled
    mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {k: v for k, v in bots.items() if k not in etherscan_bots 
            and k not in coinbase_bots and k not in mine_bots}

def remove_atomic_bots(bots):
    atomic = load_dict_from_json("atomic/atomic_searchers_agg.json")
    return {k: v for k, v in bots.items() if k not in atomic}

def return_mev_bots(bots, dir):
    # eliminate known etherscan bots 
    etherscan_bots = load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribe.json").keys()
    # eliminate bots that i labeled
    # mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {k: v for k, v in bots.items() if k in etherscan_bots or k in coinbase_bots}



def compare_two_thresholds(lower, higher, lower_dir, higher_dir): 
    # calculate how many bots are known in lower and higher
    bots_only_in_lower = find_only_in_db_one(lower, higher)
    mev_in_lower = return_mev_bots(lower, lower_dir)
    mev_only_in_lower = return_mev_bots(bots_only_in_lower, lower_dir)
    mev_in_higher = return_mev_bots(higher, higher_dir)
    print(f"{len(mev_in_lower)} bots are known MEV bots in lower gas fee range.")
    print(f"{len(mev_in_higher)} bots are known MEV bots in higher gas fee range.")
    # compare number of results, which could increase efficiency
    print(f"{len(lower)} bots are found in a lower threshold, and {len(higher)} bots found in higher threshold")
    print(f"Within these additional {len(bots_only_in_lower)} bots captured by this lower threshold, {len(mev_only_in_lower)} bots are known MEV bots")



def create_agg_from_bribes(dir):
    new_cefi_searcher_agg = defaultdict(int)
    coinbase_bribes = load_dict_from_json(dir + "/coinbase_bribes.json")
    priority_bribes = load_dict_from_json(dir + "/cefi_bots_in_higher_gas.json")

    for searcher, txs in coinbase_bribes.items():
        new_cefi_searcher_agg[searcher] += len(txs)
    for searcher, txs in priority_bribes.items():
        new_cefi_searcher_agg[searcher] += len(txs)
    
    return {k: v for k, v in new_cefi_searcher_agg.items() if v >= 5 or k in coinbase_bribes.keys()}


def analyse_top_x(searchers, x):
    defined_searchers = load_dict_from_json("searcher_databases/mine_searchers.json")
    non_cefidefi = defined_searchers["non-cefidefi"]
    total_tx_count = sum(searchers.values())
    top_x = {k: v for k, v in list(iter(searchers.items()))[:x]}
    total_top_ten_tx_count = sum(top_x.values())
    cefidefi_tx_count = sum(v for k, v in top_x.items() if k not in non_cefidefi)
    print(f"The top {x} addrs created {round(total_top_ten_tx_count / total_tx_count * 100, 2)}% of all txs")
    print(f"Cefi-defi arbs is responsible for {round(cefidefi_tx_count / total_top_ten_tx_count * 100, 2)}% of all txs coming from the top {x} addrs")
    print(f"Cefi-defi arbs is responsible for at least {round(cefidefi_tx_count / total_tx_count * 100, 2)}% of all txs\n") 

    return cefidefi_tx_count / total_top_ten_tx_count

def trim_agg(agg_dir, threshold):
    agg = load_dict_from_json(agg_dir + "/" + agg_dir + "_searchers_agg.json")
    sorted_agg = {k: v for k, v in sorted(agg.items(), key=lambda item: item[1], reverse=True) if v >= threshold}
    dump_dict_to_json(sorted_agg, agg_dir + "/trimmed_agg.json")


def combine_atomic_nonatomic_agg():
    atomic = load_dict_from_json("atomic/atomic_searchers_agg.json")
    non_atomic = load_dict_from_json("non_atomic/above_50_median/cefi_searchers_agg.json")
    result = dict(Counter(atomic) + Counter(non_atomic))
    # sorted_result = {k: v for k, v in sorted(result.items(), key=lambda item: item[1], reverse=True) if v >= 5}
    sorted_result = {k: v for k, v in sorted(result.items(), key=lambda item: item[1], reverse=True)[:20]}
    dump_dict_to_json(sorted_result, "all_searchers.json")
    return sorted_result

def remove_coinbase_bribe_searchers(all_nonatomic):
    coinbase_searchers = load_dict_from_json("non_atomic/all_swaps/coinbase_bribe.json").keys()
    return {k: v for k, v in all_nonatomic.items() if k not in coinbase_searchers}

def slice_dict(d, n):
    return dict(islice(d.items(), n))

def analyse_gas_bribe_searchers():
    all_nonatomic = load_dict_from_json("non_atomic/all_swaps/nonatomic_searchers_agg.json")
    gas_nonatomic = remove_coinbase_bribe_searchers(all_nonatomic)
    unknown_gas_nonatomic = remove_common_addrs(gas_nonatomic)
    # out of all the bots that paid exclusively via gas fees, these are bots 
    # that we havent been able to account for using the list
    visual_analysis.overlap_searcher_frequency_maps(gas_nonatomic, unknown_gas_nonatomic)

    between_100_200_txs = {k: v for k, v in gas_nonatomic.items() if v >= 100 and v <= 200}
    dump_dict_to_json(between_100_200_txs, "between_100_200_nonatomictxs.json")

def rid_map_of_small_addrs(map, agg, ):
    trimmed_agg = {k: v for k, v in agg.items() if v >= 100}
    trimmed_map = defaultdict(lambda: defaultdict(int))
    for builder, searchers in builder_x_map.items():
        for searcher, count in searchers.items():
            if searcher in trimmed_agg.keys():
                trimmed_map[builder][searcher] = count
    return trimmed_map

def rid_known_entities():
    all_swaps = load_dict_from_json("non_atomic/after_and_tob/all_nonatomic_searchers_agg.json")
    rid_labeled = {}
    rid_all = {}

    for addr, count in all_swaps.items():
        if addr not in constants.COMMON_CONTRACTS:
            rid_labeled[addr] = count

    for addr, count in rid_labeled.items():
        if addr not in constants.LABELED_CONTRACTS.values():
            rid_all[addr] = count

    dump_dict_to_json(rid_all, "non_atomic/after_and_tob/nonatomic_searchers_agg.json")


def get_map_in_range(map, agg, threshold):
    total_tx_count = sum(agg.values())
    threshold = total_tx_count * threshold

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
        filtered_map[builder] = {searcher: tx_count for searcher, tx_count in searchers.items() if searcher in top_searchers}

    return filtered_map, top_searchers


if __name__ == "__main__":
    map = analysis.load_dict_from_json("atomic/builder_atomic_map.json")
    agg = analysis.load_dict_from_json("atomic/atomic_searchers_agg.json")
    sorted_map = {builder: dict(sorted(searchers.items(), key=lambda item: item[1], reverse=True)) for builder, searchers in map.items()}

    dump_dict_to_json(rid_map_of_small_addrs(sorted_map, agg), "atomic/smaller_map.json")
