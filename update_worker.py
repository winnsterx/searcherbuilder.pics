import fetch_blocks
import analysis
import main_mev
import chartprep

BLOCK_DIR = "blockchain_data/block_data/"
TR_DIR = "blockchain_data/transfer_data/"
RECEIPT_DIR = "blockchain_data/receipt_data/"

BLOCK_FILE = "blockchain_data/block_data/fourteen_day_blocks.json"
TR_FILE = "blockchain_data/transfer_data/fourteen_day_transfers.json"
RECEIPT_FILE = "blockchain_data/receipt_data/fourteen_day_receipts.json"

SMALL_BLOCK_FILE = "blockchain_data/block_data/small_block.json"
SMALL_TR_FILE = "blockchain_data/transfer_data/small_transfer.json"
SMALL_RECEIPT_FILE = "blockchain_data/receipt_data/small_receipt.json"


def combine_blocks(new_start, new_end, old_blocks, new_blocks):
    # take 14 days of blocks and append 1 days of blocks to it and remove the first 1
    # num_blocks_flush = 7200  # 24*60*60/12
    combined = {}
    missing = []

    for i in range(new_start, new_end + 1):
        block_num = str(i)

        if block_num in old_blocks:
            combined[block_num] = old_blocks[block_num]
        elif block_num in new_blocks:
            combined[block_num] = new_blocks[block_num]
        else:
            missing.append(block_num)
    return missing, combined


# returns list of block num (int) of data that needs to be fetched
def find_to_fetch(old_data, new_start, new_end):
    to_fetch = []
    for i in range(new_start, new_end + 1):
        if str(i) in old_data:  # not in the old_blocks
            continue
        to_fetch.append(i)

    print("There are", len(to_fetch), "blocks of data needed to be fetched")
    return to_fetch


def fetch_new_blocks(old_blocks, new_start, new_end):
    # find blocks that go from new start to new end, but using old_blocks if it already has it
    # old_end = max(old_blocks, key=int)
    to_fetch = find_to_fetch(old_blocks, new_start, new_end)
    blocks = fetch_blocks.get_blocks_by_list(to_fetch)
    return to_fetch, blocks


def update_tr_files(new_start, new_end, blocks):
    print("Loading old tr file")
    old_trs = analysis.load_dict_from_json(TR_FILE)
    to_fetch = find_to_fetch(old_trs, new_start, new_end)

    to_fetch_blocks = {}
    for block_num in to_fetch:
        to_fetch_blocks[str(block_num)] = blocks[str(block_num)]

    new_trs = fetch_blocks.get_internal_transfers_to_fee_recipients_in_blocks(
        to_fetch_blocks
    )

    missing, updated_trs = combine_blocks(new_start, new_end, old_trs, new_trs)
    if len(missing) > 0:
        print("Missing some TRANSFERS. Failed to combine fully.")
        print(missing)
        return

    return updated_trs


def update_receipt_files(new_start, new_end):
    old_receipts = analysis.load_dict_from_json(RECEIPT_FILE)
    to_fetch = find_to_fetch(old_receipts, new_start, new_end)

    new_receipts = fetch_blocks.get_blocks_receipts_by_list(to_fetch)

    missing, updated_receipts = combine_blocks(
        new_start, new_end, old_receipts, new_receipts
    )
    if len(missing) > 0:
        print("Missing some RECEIPTS. Failed to combine fully.")
        print(missing)
        # return

    return updated_receipts


def add_gas_used_to_block_files(blocks, receipts):
    for block_num, block in blocks.items():
        block_receipts = receipts.get(block_num, {})
        block_txs = block["transactions"]
        for receipt in block_receipts:
            gas_used = receipt["gas_used"]
            tx_index = receipt["tx_index"]

            if tx_index > len(block_txs):
                continue

            block_txs[tx_index]["gasUsed"] = gas_used

    return blocks


def update_block_files(new_start, new_end):
    # new_start = 18035586
    # # new_start = 18035731
    # new_end = 18035588
    # # new_end = 18136386
    RECEIPTS_SYNC_BLOCKS = False
    print("New start and end block num", new_start, new_end)
    old_blocks = analysis.load_dict_from_json(BLOCK_FILE)
    to_fetch, new_blocks = fetch_new_blocks(old_blocks, new_start, new_end)

    missing, updated_blocks = combine_blocks(new_start, new_end, old_blocks, new_blocks)

    if len(missing) > 0:
        print("Missing some BLOCKS. Failed to combine fully.")
        print(missing)
        return

    analysis.dump_dict_to_json(updated_blocks, BLOCK_FILE)
    updated_receipts = {}
    # if RECEIPTS_SYNC_BLOCKS:
    #     updated_receipts = update_receipt_files(min(to_fetch), max(to_fetch))
    # else:
    #     updated_receipts = update_receipt_files(new_start, new_end)

    # updated_blocks = add_gas_used_to_block_files(updated_blocks, updated_receipts)

    updated_trs = update_tr_files(new_start, new_end, updated_blocks)
    analysis.dump_dict_to_json(updated_trs, TR_FILE)

    return updated_blocks, updated_trs, updated_receipts


if __name__ == "__main__":
    new_start, new_end = fetch_blocks.get_new_start_and_end_block_nums()
    fetched_blocks, fetched_trs, fetched_receipts = update_block_files(
        new_start, new_end
    )

    main_mev.create_mev_analysis(fetched_blocks, fetched_trs)

    # update the charts
    chartprep.create_html_page()

    # new_start = 18030230
    # new_end = 18131030
    # start + 14_days = end
    # print("new_start and end", new_start, new_end)

    # old_blocks = analysis.load_dict_from_json("block_data/fourteen_blocks.json")
    # new_blocks = analysis.load_dict_from_json("new_blocks.json")
    # missing, updated_blocks = combine_blocks(new_start, new_end, old_blocks, new_blocks)

    # fetch_blocks.count_blocks(
    #     analysis.load_dict_from_json("fourteen_blocks.json"), 18030230
    # )

    # # update the website everyday, but always only show 14 days of results
    # # get the last 14 days of data
    # two_weeks_blocks = 100800  # 14 * 24 * 60 * 60 / 12
    # # start_block = 18088050
    # start_block = fetch_blocks.block_number_14_days_ago()
    # # print(start_block)

    # # fetched_blocks = fetch_blocks.get_blocks(start_block, two_weeks_blocks)
    # # analysis.dump_dict_to_json(fetched_blocks, "fourteen_blocks.json")

    # # fetched_internal_transfers = (
    # #     fetch_blocks.get_internal_transfers_to_fee_recipients_in_blocks(fetched_blocks)
    # # )
    # # analysis.dump_dict_to_json(fetched_internal_transfers, "fourteen_transfers.json")

    # # fetched_receipts = fetch_blocks.get_blocks_receipts(start_block, two_weeks_blocks)
    # # analysis.dump_dict_to_json(fetched_receipts, "fourteen_receipts.json")

    # fetched_blocks = analysis.load_dict_from_json("fourteen_blocks.json")
    # fetched_internal_transfers = analysis.load_dict_from_json("fourteen_transfers.json")

    # main_mev.create_mev_analysis(fetched_blocks, fetched_internal_transfers)

    # # update the charts
    # chartprep.create_html_page()
