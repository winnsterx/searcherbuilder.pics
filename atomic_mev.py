import helpers


# increments the frequency counter of searcher, which can be addr_from/to, for the builder
# contract is ignored if it is a known router, dex, etc
def analyze_tx(
    builder,
    tx,
    full_tx,
    transfer_map,
    block_base_fee,
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

    if mev_type == "swap" and tx["protocol"] == "multiple":
        print("found a tx that is swap w multiple protocols")
        mev_type = "uncertain"
    elif mev_type == "sandwich" or mev_type == "swap":
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

    tx_priority_fee = (
        full_tx["gasUsed"] * full_tx["gasPrice"] - full_tx["gasUsed"] * block_base_fee
    )

    builder_atomic_map_gas_bribe[builder][addr_to][mev_type] += tx_priority_fee
    builder_atomic_map_gas_bribe[builder][addr_to]["total"] += tx_priority_fee

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
    # for swaps that are likely atomic MEV due to their multiple hop nature
    elif mev_type == "uncertain":
        builder_atomic_map_tx[builder][addr_to][mev_type] += 1
        user_volume = tx.get("user_swap_volume_usd", 0) or 0
        builder_atomic_map_vol[builder][addr_to][mev_type] += user_volume
        builder_atomic_map_vol_list[builder][addr_to].append(user_volume)
        builder_atomic_map_tx[builder][addr_to]["total"] += 1
        builder_atomic_map_vol[builder][addr_to]["total"] += user_volume

        if addr_to not in addrs_counted_in_block:
            builder_atomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)


def default_searcher_dic():
    return {
        "total": 0,
        "arb": 0,
        "frontrun": 0,
        "backrun": 0,
        "liquid": 0,
        "uncertain": 0,
    }


def compile_atomic_data(
    builder_atomic_map_block,
    builder_atomic_map_tx,
    builder_atomic_map_profit,
    builder_atomic_map_vol,
    builder_atomic_map_coin_bribe,
    builder_atomic_map_gas_bribe,
    builder_atomic_map_vol_list,
):
    helpers.dump_dict_to_json(
        builder_atomic_map_block,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_block.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_tx,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_tx.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_profit,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_profit.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_vol,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_vol.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_coin_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_coin_bribe.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_gas_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_gas_bribe.json",
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_vol_list,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_vol_list.json",
    )

    agg_block = helpers.aggregate_block_count(builder_atomic_map_block)
    agg_tx = helpers.create_sorted_agg_from_atomic_map(builder_atomic_map_tx)
    agg_profit = helpers.create_sorted_agg_from_atomic_map(builder_atomic_map_profit)
    agg_vol = helpers.create_sorted_agg_from_atomic_map(builder_atomic_map_vol)
    agg_coin = helpers.create_sorted_agg_from_atomic_map(builder_atomic_map_coin_bribe)
    agg_gas = helpers.create_sorted_agg_from_atomic_map(builder_atomic_map_gas_bribe)
    helpers.dump_dict_to_json(agg_block, "atomic/fourteen/agg/agg_block.json")
    helpers.dump_dict_to_json(agg_tx, "atomic/fourteen/agg/agg_tx.json")
    helpers.dump_dict_to_json(agg_profit, "atomic/fourteen/agg/agg_profit.json")
    helpers.dump_dict_to_json(agg_vol, "atomic/fourteen/agg/agg_vol.json")
    helpers.dump_dict_to_json(agg_coin, "atomic/fourteen/agg/agg_coin.json")
    helpers.dump_dict_to_json(agg_gas, "atomic/fourteen/agg/agg_gas.json")

    builder_atomic_map_bribe, agg_bribe = helpers.combine_gas_and_coin_bribes_in_eth(
        builder_atomic_map_gas_bribe, builder_atomic_map_coin_bribe, True
    )
    helpers.dump_dict_to_json(
        builder_atomic_map_bribe,
        "atomic/fourteen/builder_atomic_maps/builder_atomic_map_bribe.json",
    )
    helpers.dump_dict_to_json(agg_bribe, "atomic/fourteen/agg/agg_bribe.json")


# if __name__ == "__main__":
#     block = helpers.load_dict_from_json("blockchain_data/block_data/small_block.json")
