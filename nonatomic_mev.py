import statistics
import helpers


def calculate_block_median_gas_price(transactions):
    gas_prices = [tx["gasPrice"] for tx in transactions]
    if len(gas_prices) > 0:
        return statistics.median(gas_prices)


def followed_by_transfer_to_builder(fee_recipient, cur_tx, next_tx):
    if next_tx == {}:
        return False
    if next_tx["from"] == cur_tx["from"] and next_tx["to"] == fee_recipient:
        return True
    return False


def analyze_tx(
    block_number,
    builder,
    fee_recipient,
    swap,
    full_tx,
    full_next_tx,
    transfer_map,
    top_of_block_boundary,
    block_base_fee,
    addrs_counted_in_block,
    builder_nonatomic_map_block,
    builder_nonatomic_map_tx,
    builder_nonatomic_map_vol,
    builder_nonatomic_map_coin_bribe,
    builder_nonatomic_map_gas_bribe,
    builder_nonatomic_map_vol_list,
    coinbase_bribe,
    after_bribe,
    tob_bribe,
):
    """
    For any uni-directional swaps detected by zeromev, we classify it as a CEX-DEX arbitrage if it meets one of the following criteria:
    1. swap contains a coinbase transfer to the builder/fee recipient of the block
    2. swap is followed by a direct transfer to the builder/fee recipient of the block
    3. swap is within the top 10% of the block
    """

    if swap == None:
        return
    tx_index = swap["tx_index"]
    tx_volume = swap.get("user_swap_volume_usd", 0) or 0

    addr_to = (swap.get("address_to") or "").lower()
    addr_from = (swap.get("address_from") or "").lower()  # Corrected to "address_from"
    if addr_to == "" or addr_from == "":
        return

    if full_tx["hash"] in transfer_map.keys():
        builder_nonatomic_map_tx[builder][addr_to] += 1
        builder_nonatomic_map_vol[builder][addr_to] += tx_volume
        builder_nonatomic_map_vol_list[builder][addr_to].append(tx_volume)

        builder_nonatomic_map_coin_bribe[builder][addr_to] += transfer_map[
            full_tx["hash"]
        ]["value"]

        tx_priority_fee = (
            full_tx["gasUsed"] * full_tx["gasPrice"]
            - full_tx["gasUsed"] * block_base_fee
        )

        builder_nonatomic_map_gas_bribe[builder][addr_to] += tx_priority_fee

        coinbase_bribe[addr_to][builder].append(transfer_map[full_tx["hash"]]["value"])

        if addr_to not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)

    elif followed_by_transfer_to_builder(fee_recipient, full_tx, full_next_tx) == True:
        # mev bot collected here will be an EOA
        builder_nonatomic_map_tx[builder][addr_from] += 1
        builder_nonatomic_map_vol[builder][addr_from] += tx_volume
        builder_nonatomic_map_vol_list[builder][addr_from].append(tx_volume)
        builder_nonatomic_map_coin_bribe[builder][addr_from] += helpers.wei_to_eth(
            full_next_tx["value"]
        )

        after_bribe[addr_from][builder].append(
            helpers.wei_to_eth(full_next_tx["value"])
        )

        if addr_from not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_from] += 1
            addrs_counted_in_block.add(addr_from)

    # if within top of block (first 10%):
    elif tx_index <= top_of_block_boundary:
        builder_nonatomic_map_tx[builder][addr_to] += 1
        builder_nonatomic_map_vol[builder][addr_to] += tx_volume
        builder_nonatomic_map_vol_list[builder][addr_to].append(tx_volume)
        builder_nonatomic_map_gas_bribe[builder][addr_to] += (
            full_tx["gasUsed"] * full_tx["gasPrice"]
        )
        tx_priority_fee = (
            full_tx["gasUsed"] * full_tx["gasPrice"]
            - full_tx["gasUsed"] * block_base_fee
        )

        builder_nonatomic_map_gas_bribe[builder][addr_to] += tx_priority_fee

        tob_bribe.setdefault(addr_to, []).append(
            {
                "builder": builder,
                "block_number": block_number,
                "index": tx_index,
                "gas_price": full_tx["gasPrice"],
            }
        )
        if addr_to not in addrs_counted_in_block:
            builder_nonatomic_map_block[builder][addr_to] += 1
            addrs_counted_in_block.add(addr_to)


def compile_cefi_defi_data(
    builder_nonatomic_map_block,
    builder_nonatomic_map_tx,
    builder_nonatomic_map_vol,
    builder_nonatomic_map_coin_bribe,
    builder_nonatomic_map_gas_bribe,
    builder_nonatomic_map_vol_list,
    coinbase_bribe,
    after_bribe,
    tob_bribe,
):
    # trimmed_map = searcher_db.clean_up(builder_nonatomic_map, 5)
    helpers.dump_dict_to_json(
        builder_nonatomic_map_block,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_block.json",
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_tx,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_tx.json",
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_vol,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_vol.json",
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_coin_bribe,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_coin_bribe.json",
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_gas_bribe,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_gas_bribe.json",
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_vol_list,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_vol_list.json",
    )

    agg_block = helpers.aggregate_block_count(builder_nonatomic_map_block)
    agg_tx = helpers.create_sorted_agg_from_map(builder_nonatomic_map_tx)
    agg_vol = helpers.create_sorted_agg_from_map(builder_nonatomic_map_vol)
    agg_coin = helpers.create_sorted_agg_from_map(builder_nonatomic_map_coin_bribe)
    agg_gas = helpers.create_sorted_agg_from_map(builder_nonatomic_map_gas_bribe)
    helpers.dump_dict_to_json(agg_block, "nonatomic/fourteen/agg/agg_block.json")
    helpers.dump_dict_to_json(agg_tx, "nonatomic/fourteen/agg/agg_tx.json")
    helpers.dump_dict_to_json(agg_vol, "nonatomic/fourteen/agg/agg_vol.json")
    helpers.dump_dict_to_json(agg_coin, "nonatomic/fourteen/agg/agg_coin.json")
    helpers.dump_dict_to_json(agg_gas, "nonatomic/fourteen/agg/agg_gas.json")
    (
        builder_nonatomic_map_bribe,
        agg_bribe,
    ) = helpers.combine_gas_and_coin_bribes_in_eth(
        builder_nonatomic_map_gas_bribe, builder_nonatomic_map_coin_bribe, False
    )
    helpers.dump_dict_to_json(
        builder_nonatomic_map_bribe,
        "nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_bribe.json",
    )
    helpers.dump_dict_to_json(agg_bribe, "nonatomic/fourteen/agg/agg_bribe.json")

    # bots that are only included when threshold is lower,
    helpers.dump_dict_to_json(
        coinbase_bribe, "nonatomic/fourteen/bribe_specs/coinbase_bribe.json"
    )
    helpers.dump_dict_to_json(
        after_bribe, "nonatomic/fourteen/bribe_specs/after_bribe.json"
    )
    helpers.dump_dict_to_json(
        tob_bribe, "nonatomic/fourteen/bribe_specs/tob_bribe.json"
    )
