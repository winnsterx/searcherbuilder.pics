import json
import collections
import constants
import analysis
from collections import defaultdict
from itertools import islice


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

def remove_known_addrs_from_list(searchers):
    return {k: v for k, v in searchers.items() if k not in constants.COMMON_CONTRACTS}

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
 

def return_unknown_bots(bots, dir):
    # eliminate known etherscan bots 
    etherscan_bots = load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribes.json").keys()
    # eliminate bots that i labeled
    mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {k: v for k, v in bots.items() if k not in etherscan_bots 
            and k not in coinbase_bots and k not in mine_bots}


def return_known_bots(bots, dir):
    # eliminate known etherscan bots 
    etherscan_bots = load_dict_from_json("searcher_databases/etherscan_searchers.json").keys()
    # eliminate bots did coinbase transfers
    coinbase_bots = load_dict_from_json(dir + "coinbase_bribes.json").keys()
    # eliminate bots that i labeled
    mine_bots = load_dict_from_json("searcher_databases/mine_searchers.json").keys()
    return {k: v for k, v in bots.items() if k in etherscan_bots 
            or k in coinbase_bots or k in mine_bots}



def compare_two_thresholds(lower, higher, lower_dir, higher_dir): 
    # calculate how many bots are known in lower and higher
    bots_only_in_lower = find_only_in_db_one(lower, higher)
    known_in_lower = return_known_bots(lower, lower_dir)
    known_only_in_lower = return_known_bots(bots_only_in_lower, lower_dir)
    known_in_higher = return_known_bots(higher, higher_dir)
    print(f"{len(known_in_lower)} bots are known MEV bots in lower gas fee range.")
    print(f"{len(known_in_higher)} bots are known MEV bots in higher gas fee range.")
    # compare number of results, which could increase efficiency
    print(f"{len(lower)} bots are found in a lower threshold, and {len(higher)} bots found in higher threshold")
    print(f"Within these additional {len(bots_only_in_lower)} bots captured by this lower threshold, {len(known_only_in_lower)} bots are known MEV bots")



def create_agg_from_bribes(dir):
    new_cefi_searcher_agg = defaultdict(int)
    coinbase_bribes = load_dict_from_json(dir + "/coinbase_bribes.json")
    priority_bribes = load_dict_from_json(dir + "/cefi_bots_in_higher_gas.json")

    for searcher, txs in coinbase_bribes.items():
        new_cefi_searcher_agg[searcher] += len(txs)
    for searcher, txs in priority_bribes.items():
        new_cefi_searcher_agg[searcher] += len(txs)
    
    return {k: v for k, v in new_cefi_searcher_agg.items() if v >= 5 or k in coinbase_bribes.keys()}


def analyse_top_ten(searchers):
    defined_searchers = load_dict_from_json("searcher_databases/mine_searchers.json")
    non_cefidefi = defined_searchers["non-cefidefi"]
    total_tx_count = sum(searchers.values())
    top_ten = {k: v for k, v in list(iter(searchers.items()))[:10]}
    total_top_ten_tx_count = sum(top_ten.values())
    cefidefi_tx_count = sum(v for k, v in top_ten.items() if k not in non_cefidefi)
    print(f"the top ten addrs occupy {total_top_ten_tx_count / total_tx_count * 100}% of all txs")
    print(f"cefi-defi arb addrs occupy {cefidefi_tx_count / total_top_ten_tx_count * 100}% of all top ten addrs")
    print(f"cefi-defi arb addrs occupy {cefidefi_tx_count / total_tx_count * 100}% of all tx")

    return cefidefi_tx_count / total_top_ten_tx_count
    

if __name__ == "__main__":
    # cleaned = remove_known_addrs_from_list(load_dict_from_json("bot_data/above_50_median/cefi_searchers_agg.json"))
    # dump_dict_to_json(cleaned, "bot_data/above_50_median/new_cefi_searchers_agg.json")

    all_bots = load_dict_from_json("bot_data/above_50_median/cefi_searchers_agg.json")
    print(analyse_top_ten(all_bots))
    # unknown_bots = return_unknown_bots(all_bots, "bot_data/above_50_median/")

    # dump_dict_to_json(unknown_bots, "bot_data/above_50_median/unknown_bots.json")

    # agg_1 = create_agg_from_bribes("bot_data/above_median")
    # agg_1 = {k: v for k, v in sorted(agg_1.items(), key=lambda item: item[1], reverse=True)}
    # dump_dict_to_json(agg_1, "bot_data/above_median/new_cefi_searchers_agg.json")

    # # print("comparing median * 1.25 and median * 1.5")
    # # lower = "bot_data/above_125_median/"
    # # higher = "bot_data/above_15_median/"
    # # lower_bots = load_dict_from_json(lower + "cefi_searchers_agg.json")
    # # higher_bots = load_dict_from_json(higher + "cefi_searchers_agg.json")
    # # compare_two_thresholds(lower_bots, higher_bots, lower, higher)

    # print("comparing median * 1 and median * 1.25")
    # lower = "bot_data/above_median/"
    # higher = "bot_data/above_125_median/"
    # lower_bots = load_dict_from_json(lower + "new_cefi_searchers_agg.json")
    # higher_bots = load_dict_from_json(higher + "cefi_searchers_agg.json")
    # compare_two_thresholds(lower_bots, higher_bots, lower, higher)
