import json
import collections
import constants

def load_dict_from_json(filename):
    with open(filename) as file:
        dict = json.load(file)
        return dict

def dump_dict_to_json(dict, filename):
    with open(filename, 'w') as fp: 
        json.dump(dict, fp)

def get_zeromev_searchers(builder_searcher_map):
    searcher_total_interactions = {}
    for builder, interactions in builder_searcher_map.items():
        for searcher, frequency in interactions.items():
            if searcher not in searcher_total_interactions:
                searcher_total_interactions[searcher] = 0
            searcher_total_interactions[searcher] += int(frequency)
    sorted_interactions = {k: v for k, v in sorted(searcher_total_interactions.items(), key=lambda item: item[1], reverse=True)}
    return sorted_interactions
    # return searcher_total_interactions

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
    

zeromev_builder_searcher_map = load_dict_from_json("result.json")
zeromev_searchers = get_zeromev_searchers(zeromev_builder_searcher_map)
etherscan_searchers = load_dict_from_json("searcher_dbs/etherscan_searchers.json")

joint = find_joint_between_two_searcher_db(zeromev_searchers, etherscan_searchers)
dump_dict_to_json(list(joint), "joint.json")


# exclusive_relationships = one_exclusive_relationships(builder_searcher_map, searcher_total_interactions)
# with open('exclusive.json', 'w') as fp: 
#     json.dump(exclusive_relationships, fp)
