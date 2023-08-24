import requests, json, time, ijson, os
from urllib3.exceptions import IncompleteRead
import analysis, secret_keys
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

MAX_RETRIES = 5  # Define a maximum number of retries
INITIAL_BACKOFF = 1  # Define initial backoff time in seconds

# Simplify a block by keeping only relevant fields
def simplify_block(block):
    simplified = {
        "hash": block["hash"],
        "extraData": block.get("extraData", None),
        "feeRecipient": block["miner"],
        "transactions": [
            {
                "transactionIndex": int(tx["transactionIndex"], 16),
                "hash": tx["hash"],
                "from": tx["from"],
                "to": tx.get("to", "0x0"),
                "gas": int(tx["gas"], 16),
                "gasPrice": int(tx.get("gasPrice", "0x0"), 16),
                "maxFeePerGas": int(tx.get("maxFeePerGas", "0x0"), 16),
                "maxPriorityFeePerGas": int(tx.get("maxPriorityFeePerGas", "0x0"), 16),
                "value": int(tx["value"], 16)
            }
            for _, tx in enumerate(block["transactions"])
        ]
    }
    return simplified 


# Simplify block fetched and handle errorneous responses 
def process_batch_response(response, blocks_fetched):
    success = True
    try:
        blocks = response.json()  # [{}, {}]
        for b in blocks:
            if ('result' in b and b['result'] is None) or "error" in b:
                print(f"block {b['id']} cannot be fetched: {b}")
                success = False
                # immediately stop processing this batch of response bc whole batch may be bad
                return success
            else:
                block_number = b["id"]
                full_block = b["result"]
                blocks_fetched[block_number] = simplify_block(full_block)
        return success

    except Exception as e:
        print("Exception occurred", e)
        analysis.dump_dict_to_json(blocks_fetched, "blocks_info.json") 


# Sends batch requests of 1000 to node 
# Uses exponential retries when errors are encountered 
        
# def batch_request(block, end_block, batch_size, retries, blocks_fetched):
def batch_request(batch, retries, blocks_fetched):
    headers = {"Content-Type": "application/json"}
    # batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} 
    #          for i in range(block, min(block + batch_size, end_block + 1))]

    while retries < MAX_RETRIES:
        try: 
            start = time.time()
            print(f"Getting batch at {start}, attempt {retries + 1}")
            response = requests.post(secret_keys.ALCHEMY, headers=headers, data=json.dumps(batch))

            if response.status_code == 200:
                success = process_batch_response(response, blocks_fetched)
                if success: # if retry is not required, process is complete'
                    print("Batch successfully fetched & processed")
                    break
            else: 
                print(f"Non-success status code received: {response.status_code}, retrying for the {retries + 1} time")

            retries += 1
            time.sleep(INITIAL_BACKOFF * (2 ** retries))  # Sleep before next retry with exponential backoff        
            
            if retries == MAX_RETRIES:
                analysis.dump_dict_to_json(blocks_fetched, "blocks_info.json") 
                print("Max retries reached. Exiting.")
        except IncompleteRead as e:
            print(f"IncompleteRead error occurred: {e}, retrying for the {retries + 1} time")
            retries += 1
            time.sleep(INITIAL_BACKOFF * (2 ** retries))  # Sleep before next retry with exponential backof


# Get all blocks in batch requests of 1000 
def get_blocks(start_block, num_blocks):
    batch_size = 1000
    end_block = start_block + num_blocks - 1
    blocks_fetched = {}
    
    start = time.time()
    print("starting to get blocks at ", start)

    # with ThreadPoolExecutor(max_workers=64) as executor:
    #     # Use the executor to submit the tasks
    #     futures = [executor.submit(batch_request, first_block_of_batch, 
    #                                end_block, batch_size, 0, blocks_fetched) for first_block_of_batch in range(start_block, end_block + 1, batch_size)]
    #     for future in as_completed(futures):
    #         pass

    for block in range(start_block, end_block + 1, batch_size):
        batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} 
                 for i in range(block, min(block + batch_size, end_block + 1))]
        batch_request(batch, 0, blocks_fetched)
    
    print("finished getting blocks in", time.time() - start, " seconds")
    return blocks_fetched
    

# Counts that the blocks in block file is in order and present
def count_blocks(blocks, start_block):
    block_num = start_block
    
    for b, _ in blocks.items():
        if int(b) != block_num:
            print("missing / out of order block number", b, "isnt ", block_num)
            return False
        block_num += 1
    print(f"all {len(blocks)} blocks are in order and present, ending at", block_num - 1)
    return True

def prepare_file_list(dir, keyword="", sort=True):
    # dir = block_data, no /
    files = os.listdir(dir)
    file_list = []
    for file in files:
        if keyword in file:
            file = dir+"/"+file
            file_list.append(file)
    if sort: 
        file_list = sorted(file_list)
    return file_list

def merge_large_json_files(file_list, output_file):
    with open(output_file, 'w') as outfile:
        outfile.write('{')  # start of json

        # flag to keep track if we need to write a comma
        write_comma = False

        for file in file_list:
            with open(file, 'rb') as infile:
                # process file
                objects = ijson.kvitems(infile, '')
                for key, value in objects:
                    # if not first object, add a comma
                    if write_comma:  
                        outfile.write(',')
                    outfile.write(json.dumps(key) + ':' + json.dumps(value))  # add block_number: block_detail pair
                    write_comma = True

        outfile.write('}')  # end of json


def get_internal_transfers_to_fee_recipient_in_block(block_number, builder, all_internal_transfers):
    try:
        headers = { "accept": "application/json", "content-type": "application/json" }
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "category": ["internal"],
                    "toAddress": builder, 
                    "fromBlock": hex(int(block_number)),
                    "toBlock": hex(int(block_number))
                }
            ]
        }
        response = requests.post(secret_keys.ALCHEMY, json=payload, headers=headers)
        print(block_number, response.status_code)
        transfers = response.json()["result"]["transfers"]
        transfer_map = {tr['hash']: {'from': tr["from"], 'to': tr['to'], 'value': tr["value"]} for tr in transfers}
        all_internal_transfers[block_number] = transfer_map
    except Exception as e:
        print("error found in one block", e)


def default_internal_transfer_dic():
    return {
        "from": "",
        "to": "",
        "value": ""
    }

def get_internal_transfers_to_fee_recipients_in_blocks(blocks):
    all_internal_transfers = defaultdict(lambda: defaultdict(default_internal_transfer_dic))
    with ThreadPoolExecutor(max_workers=64) as executor:
        # Use the executor to submit the tasks
        futures = [executor.submit(get_internal_transfers_to_fee_recipient_in_block, block_number, block["feeRecipient"], all_internal_transfers) for block_number, block in blocks.items()]
        for future in as_completed(futures):
            pass
    
    return all_internal_transfers
    


if __name__ == "__main__":
    start_block = 17595510 #  Jul-01-2023 12:00:11 AM +UTC
    num_blocks = 360000 # 50 * 24 * 60 * 60 / 12
    end_block = 17955510 # Aug-20-2023 10:58:47 AM +UTC

    blocks = analysis.load_dict_from_json("block_data/blocks_50_days.json")
    all_internal_transfers = get_internal_transfers_to_fee_recipients_in_blocks(blocks)
    analysis.dump_dict_to_json(all_internal_transfers,"internal_transfers_50_days.json")

    # blocks = get_blocks(start_block, num_blocks)
    # analysis.dump_dict_to_json(blocks, "block_data/now_aug_blocks.json")

    # merge_large_json_files(["block_data/blocks_30_days.json", "block_data/aug_blocks.json"], "blocks_50_days.json")
    # blocks = analysis.load_dict_from_json("blocks_50_days.json")
    # count_blocks(blocks, 17595510)







