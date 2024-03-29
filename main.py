import time
import subprocess
import fetch_blocks
import helpers
import main_mev
import chartprep
import secret_keys

BLOCK_DIR = "blockchain_data/block_data/"
TR_DIR = "blockchain_data/transfer_data/"

BLOCK_FILE = "blockchain_data/block_data/fourteen_day_blocks.json"
TR_FILE = "blockchain_data/transfer_data/fourteen_day_transfers.json"
BLOCK_FILE_SANS_GASUSED = (
    "blockchain_data/block_data/fourteen_day_blocks_sans_gasUsed.json"
)
ZEROMEV_FILE = "blockchain_data/zeromev_data/fourteen_day_zeromev.json"

SMALL_BLOCK_FILE = "blockchain_data/block_data/small_block.json"
SMALL_TR_FILE = "blockchain_data/transfer_data/small_transfer.json"
SMALL_BLOCK_FILE_SANS_GASUSED = (
    "blockchain_data/block_data/small_blocks_sans_gasUsed.json"
)
SMALL_ZEROMEV_FILE = "blockchain_data/zeromev_data/small_zeromev.json"


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
    return blocks, to_fetch


def update_tr_file(new_start, new_end, blocks):
    print("Loading old tr file")
    old_trs = helpers.load_dict_from_json(TR_FILE)
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
        if len(missing) > 1000:
            return

    return updated_trs


def update_zeromev_file(new_start, new_end):
    print("Loading old zeromev file")
    old_zeromev = helpers.load_dict_from_json(ZEROMEV_FILE)
    to_fetch = find_to_fetch(old_zeromev, new_start, new_end)

    new_zeromev = main_mev.fetch_zeromev_blocks(to_fetch)
    missing, updated_zeromev = combine_blocks(
        new_start, new_end, old_zeromev, new_zeromev
    )
    if len(missing) > 0:
        print("Missing some ZEROMEV blocks. Failed to combine fully.")
        print(missing)
        if len(missing) > 1000:
            return

    return updated_zeromev


def update_block_files(new_start, new_end):
    # new_start = 18035586
    # new_end = new_start + 1000
    print("New start and end block num", new_start, new_end)
    old_blocks = helpers.load_dict_from_json(BLOCK_FILE)
    new_blocks, to_fetch = fetch_new_blocks(old_blocks, new_start, new_end)

    missing, updated_blocks = combine_blocks(new_start, new_end, old_blocks, new_blocks)

    if len(missing) > 0:
        print("Missing some BLOCKS. Failed to combine fully.")
        print(missing)
        if len(missing) > 1000:
            return

    helpers.dump_dict_to_json(updated_blocks, BLOCK_FILE_SANS_GASUSED)

    updated_receipts = fetch_blocks.get_blocks_receipts_by_list(to_fetch)
    updated_blocks = fetch_blocks.add_gas_used_to_blocks(
        updated_blocks, updated_receipts
    )

    helpers.dump_dict_to_json(updated_blocks, BLOCK_FILE)

    updated_trs = update_tr_file(new_start, new_end, updated_blocks)
    helpers.dump_dict_to_json(updated_trs, TR_FILE)

    updated_zeromev_blocks = update_zeromev_file(new_start, new_end)
    helpers.dump_dict_to_json(updated_zeromev_blocks, ZEROMEV_FILE)

    return updated_blocks, updated_trs, updated_zeromev_blocks


def check_blocks_all_present(blocks, new_start, new_end):
    missing = []
    for i in range(new_start, new_end + 1):
        b = blocks.get(str(i), None)
        if b == None:
            missing.append(i)
        # for tx in b["transactions"]:
        #     if tx.get("gasUsed", None) == None:

    full = True if len(missing) == 0 else False
    return full, missing


def update_worker():
    new_start, new_end = fetch_blocks.get_new_start_and_end_block_nums()

    fetched_blocks, fetched_trs, fetched_zeromev_blocks = update_block_files(
        new_start, new_end
    )

    full_blocks, missing_blocks = check_blocks_all_present(
        fetched_blocks, new_start, new_end
    )
    print("All blocks are present:", full_blocks)

    full_trs, missing_trs = check_blocks_all_present(fetched_trs, new_start, new_end)
    print("All trs are present:", full_trs)

    full_zeromev, missing_zeromev = check_blocks_all_present(
        fetched_zeromev_blocks, new_start, new_end
    )
    print("All zeromev blocks are present:", full_zeromev)

    # create maps and aggs used in chartprep
    main_mev.create_mev_analysis(fetched_blocks, fetched_trs, fetched_zeromev_blocks)

    # update the charts
    chartprep.create_html_page()


if __name__ == "__main__":
    # Generate the static site
    start_time = time.time()
    update_worker()
    print(f"--- Updating page took total of {time.time() - start_time} seconds ---")

    # Push changes to github
    subprocess.run(
        f"cd {secret_keys.HTML_PATH} && git add . && git commit -m 'Update static site' && git push",
        shell=True,
    )
