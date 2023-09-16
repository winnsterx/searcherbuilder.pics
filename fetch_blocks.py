import traceback
import requests, json, time
from urllib3.exceptions import IncompleteRead
import analysis, secret_keys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict


MAX_RETRIES = 5  # Define a maximum number of retries
INITIAL_BACKOFF = 1  # Define initial backoff time in seconds


# BLOCKS


# Simplify a block by keeping only relevant fields
def simplify_block(block):
    simplified = {
        "hash": block["hash"],
        "extraData": block.get("extraData", None),
        "feeRecipient": block["miner"],
        "baseFeePerGas": int(block.get("baseFeePerGas", "0x0"), 16),
        "gasUsed": int(block.get("gasUsed", "0x0"), 16),
        "transactions": [
            {
                "transactionIndex": int(tx["transactionIndex"], 16),
                "hash": tx["hash"],
                "from": tx["from"],
                "to": tx.get("to", "0x0"),
                "value": int(tx["value"], 16),
                "gasPrice": int(tx.get("gasPrice", "0x0"), 16),
            }
            for _, tx in enumerate(block["transactions"])
        ],
    }
    return simplified


# Simplify block fetched and handle errorneous responses
def process_batch_response(response, blocks_fetched):
    success = True
    try:
        blocks = response.json()  # [{}, {}]
        for b in blocks:
            if ("result" in b and b["result"] is None) or "error" in b:
                print(f"block {b['id']} cannot be fetched: {b}")
                success = False
                # immediately stop processing this batch of response bc whole batch may be bad
                return success
            else:
                block_number = str(b["id"])
                full_block = b["result"]
                blocks_fetched[block_number] = simplify_block(full_block)
        return success

    except Exception as e:
        print("Exception occurred", e)
        analysis.dump_dict_to_json(blocks_fetched, "blocks_info.json")


# Sends batch requests of 1000 to node
# Uses exponential retries when errors are encountered


# def batch_request(block, end_block, batch_size, retries, blocks_fetched):
# def batch_request(first_block_of_batch, end_block, batch_size, retries, blocks_fetched):
def batch_request(batch, retries, blocks_fetched):
    headers = {"Content-Type": "application/json"}
    # batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} for i in range(first_block_of_batch, min(first_block_of_batch + batch_size, end_block + 1))]

    while retries < MAX_RETRIES:
        try:
            start = time.time()
            print(f"Fetching batch at {start}, attempt {retries + 1}")
            response = requests.post(
                secret_keys.ALCHEMY, headers=headers, data=json.dumps(batch)
            )

            if response.status_code == 200:
                success = process_batch_response(response, blocks_fetched)
                if success:  # if retry is not required, process is complete'
                    print("Batch successfully fetched & processed")
                    break
            else:
                print(
                    f"Non-success status code received: {response.status_code}, retrying for the {retries + 1} time"
                )

            retries += 1
            time.sleep(
                INITIAL_BACKOFF * (2**retries)
            )  # Sleep before next retry with exponential backoff

            if retries == MAX_RETRIES:
                analysis.dump_dict_to_json(blocks_fetched, "blocks_info.json")
                print("Max retries reached. Exiting.")
        except IncompleteRead as e:
            print(
                f"IncompleteRead error occurred: {e}, retrying for the {retries + 1} time"
            )
            retries += 1
            time.sleep(
                INITIAL_BACKOFF * (2**retries)
            )  # Sleep before next retry with exponential backof


# Get all blocks in batch requests of 1000
def get_blocks_by_list(block_nums):
    batch_size = 1000
    blocks_fetched = {}

    start = time.time()
    print("Fetching blocks at", start)

    for i in range(0, len(block_nums), batch_size):
        batch = [
            {
                "jsonrpc": "2.0",
                "id": block,
                "method": "eth_getBlockByNumber",
                "params": [hex(block), True],
            }
            for block in block_nums[i : i + batch_size]
        ]

        batch_request(batch, 0, blocks_fetched)

    print(
        "Finished fetching initial blocks in",
        time.time() - start,
        " seconds. Now adding gasUsed to block txs.",
    )

    blocks_fetched = add_gas_used_to_blocks(blocks_fetched)
    print("Finished adding gasUsed to block txs.")
    return blocks_fetched


# Attach gasUsed to each tx of blocks using receipt API
def add_gas_used_to_blocks(blocks):
    with requests.Session() as session:
        for block_num, block in blocks.items():
            receipts = return_one_block_receipts(session, block_num)
            block_txs_num = len(block["transactions"])
            for r in receipts:
                gas_used = r["gas_used"]
                tx_index = r["tx_index"]

                if tx_index > block_txs_num:
                    continue

                block["transactions"][tx_index]["gasUsed"] = gas_used

    return blocks


# Get all blocks in batch requests of 1000
def get_blocks(start_block, num_blocks):
    batch_size = 1000
    end_block = start_block + num_blocks - 1
    blocks_fetched = {}

    start = time.time()
    print("Fetching blocks at", start)

    for block in range(start_block, end_block + 1, batch_size):
        batch = [
            {
                "jsonrpc": "2.0",
                "id": i,
                "method": "eth_getBlockByNumber",
                "params": [hex(i), True],
            }
            for i in range(block, min(block + batch_size, end_block + 1))
        ]
        batch_request(batch, 0, blocks_fetched)

    print(
        "Finished fetching blocks in",
        time.time() - start,
        "seconds. Now adding gasUsed to block txs.",
    )
    blocks_fetched = add_gas_used_to_blocks(blocks_fetched)
    print("Finished adding gas used to txs.")
    return blocks_fetched


# Counts that the blocks in block file is in order and present
# Counts anything that is basically in structure of {block_num: {}}
def count_blocks(blocks, start_block):
    missing = []
    block_num = start_block

    # for b, _ in blocks.items():
    #     if block_num != int(b):
    #         print("out of order")
    #     block_num += 1

    for b, _ in blocks.items():
        # b > block_number
        while int(b) > block_num:
            print("missing / out of order block number", b, "isnt ", block_num)
            missing.append(block_num)
            block_num += 1

        block_num += 1
    print(
        f"all {len(blocks)} blocks are in order and present, ending at", block_num - 1
    )
    return missing


# INTERNAL TRANSFERS


def default_internal_transfer_dic():
    return {"from": "", "to": "", "value": ""}


def get_internal_transfers_to_fee_recipient_in_block(
    block_number, builder, all_internal_transfers
):
    try:
        headers = {"accept": "application/json", "content-type": "application/json"}
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "category": ["internal"],
                    "toAddress": builder,
                    "fromBlock": hex(int(block_number)),
                    "toBlock": hex(int(block_number)),
                }
            ],
        }

        response = requests.post(secret_keys.ALCHEMY, json=payload, headers=headers)
        print(block_number)
        transfers = response.json()["result"]["transfers"]
        transfer_map = {
            tr["hash"]: {"from": tr["from"], "to": tr["to"], "value": tr["value"]}
            for tr in transfers
        }
        all_internal_transfers[block_number] = transfer_map
    except Exception as e:
        print("error found in one block", e, block_number)
        print(traceback.format_exc())


def get_internal_transfers_to_fee_recipients_in_blocks(blocks):
    all_internal_transfers = defaultdict(
        lambda: defaultdict(default_internal_transfer_dic)
    )
    with ThreadPoolExecutor(max_workers=64) as executor:
        # Use the executor to submit the tasks
        futures = [
            executor.submit(
                get_internal_transfers_to_fee_recipient_in_block,
                block_number,
                block["feeRecipient"],
                all_internal_transfers,
            )
            for block_number, block in blocks.items()
        ]
        for future in as_completed(futures):
            pass

    return all_internal_transfers


# RECEIPTS


def simplify_receipts(receipts):
    simplified = [
        {
            "tx_index": int(receipt.get("transactionIndex", "0x0"), 16),
            "block_num": int(receipt.get("blockNumber", "0x0"), 16),
            "effective_gas_price": int(receipt.get("effectiveGasPrice", "0x0"), 16),
            "gas_used": int(receipt.get("gasUsed", "0x0"), 16),
        }
        for _, receipt in enumerate(receipts)
    ]
    return simplified


def get_block_receipts(session, block_num, all_receipts):
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTransactionReceipts",
        "params": [{"blockNumber": hex(int(block_num))}],
    }
    headers = {"accept": "application/json", "content-type": "application/json"}
    response = session.post(secret_keys.ALCHEMY, json=payload, headers=headers)
    response = response.json()["result"]["receipts"]
    print(block_num)
    response = simplify_receipts(response)
    all_receipts[str(block_num)] = response


def return_one_block_receipts(session, block_num):
    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "alchemy_getTransactionReceipts",
        "params": [{"blockNumber": hex(int(block_num))}],
    }
    headers = {"accept": "application/json", "content-type": "application/json"}
    response = session.post(secret_keys.ALCHEMY, json=payload, headers=headers)
    response = response.json()["result"]["receipts"]
    print(block_num)
    response = simplify_receipts(response)
    return response


def get_blocks_receipts_by_list(blocks_nums):
    all_receipts = defaultdict(lambda: defaultdict)
    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("Fetch receipts for blocks")
        with ThreadPoolExecutor(max_workers=64) as executor:
            # Use the executor to submit the tasks
            futures = [
                executor.submit(get_block_receipts, session, block_number, all_receipts)
                for block_number in blocks_nums
            ]
            for future in as_completed(futures):
                pass
        print("Finished fetching receipts in", time.time() - start, " seconds")

    return all_receipts


def get_blocks_receipts(start_block, num_blocks):
    end_block = start_block + num_blocks
    all_receipts = defaultdict(lambda: defaultdict)
    with requests.Session() as session:
        # Create a ThreadPoolExecutor
        start = time.time()
        print("Fetch receipts for blocks")
        with ThreadPoolExecutor(max_workers=64) as executor:
            # Use the executor to submit the tasks
            futures = [
                executor.submit(get_block_receipts, session, block_number, all_receipts)
                for block_number in range(start_block, end_block)
            ]
            for future in as_completed(futures):
                pass
        print("Finished fetching receipts in", time.time() - start, " seconds")

    return all_receipts


def get_new_start_and_end_block_nums():
    # Current block number
    payload = {"id": 1, "jsonrpc": "2.0", "method": "eth_blockNumber"}
    headers = {"accept": "application/json", "content-type": "application/json"}
    current_block_number = int(
        requests.post(secret_keys.ALCHEMY, json=payload, headers=headers).json()[
            "result"
        ],
        16,
    )

    # Ethereum block time is roughly 15 seconds
    # 14 days = 14 * 24 * 60 * 60 seconds
    blocks_in_14_days = (14 * 24 * 60 * 60) / 12
    return current_block_number - int(blocks_in_14_days), current_block_number


# if __name__ == "__main__":
