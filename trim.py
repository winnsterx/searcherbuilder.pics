import json 
import constants

def trimTopTen():
    jsonfile = "result_50k.json"
    with open(jsonfile) as file:
        og = json.load(file) 
        top_ten = {k: dict(sorted(v.items(), key=lambda item: item[1], reverse=True)[:20]) for k, v in og.items()}

        with open('top_twenty.json', 'w') as fp: 
            json.dump(top_ten, fp)

        return top_ten

def findDisjoint(top_ten):

    beaverbuild = set(top_ten["beaverbuild"].keys())
    builder0x69 = set(top_ten["builder0x69"].keys())
    rsync = set(top_ten["rsync"].keys())
    flashbots = set(top_ten["flashbots"].keys())

    beaver_69 = beaverbuild ^ builder0x69
    beaver_rsync = beaverbuild ^ rsync 
    beaver_fb = beaverbuild ^ flashbots 

    beaver_only = (beaver_69 & beaver_rsync) & beaver_fb & beaverbuild
    print("only in beaver:", beaver_only)

    rsync_69 = rsync ^ builder0x69
    rsync_fb = rsync ^ flashbots
    rsync_only = rsync_69 & rsync_fb & beaver_rsync & rsync
    print("only in rsync:", rsync_only)

    fb_69 = flashbots ^ builder0x69 
    fb_only = fb_69 & rsync_fb & beaver_fb & flashbots
    print("only in flashbots:", fb_only)

    builder69_only = beaver_69 & rsync_69 & fb_69 & builder0x69
    print("only in builder69:", builder69_only)

    preference_by_builder = {
        constants.BEAVERBUILD: list(beaver_only),
        constants.BUILDER_0X69: list(builder69_only),
        constants.RSYNC: list(rsync_only),
        constants.FLASHBOTS: list(fb_only) 
    }
    with open('disjoint.json', 'w') as fp: 
        json.dump(preference_by_builder, fp)

    return preference_by_builder

def countBlocks():
    with open("block_to_builder_50k.json", mode="r") as fp: 
        block_to_builder = json.load(fp)

    counter = {
        constants.BEAVERBUILD: 0,
        constants.BUILDER_0X69: 0,
        constants.RSYNC: 0,
        constants.FLASHBOTS: 0 
    } 
    for b in block_to_builder.values():
        if b in counter.keys():
            counter[b] += 1
    return counter



# block_count_by_builder = countBlocks()
preference_by_builder = findDisjoint(trimTopTen())

