import requests, json, time, ijson
import analysis, secret_keys

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
def batch_request(url, batch, retries, blocks_fetched):
    headers = {"Content-Type": "application/json"}

    while retries < MAX_RETRIES:
        start = time.time()
        print(f"Getting batch at {start}, attempt {retries + 1}")
        response = requests.post(url, headers=headers, data=json.dumps(batch))

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


# Get all blocks in batch requests of 1000 
def get_blocks(start_block, num_blocks):
    batch_size = 1000
    end_block = start_block + num_blocks - 1
    blocks_fetched = {}
    
    start = time.time()
    print("starting to get blocks at ", start)

    for block in range(start_block, end_block + 1, batch_size):
        batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} 
                 for i in range(block, min(block + batch_size, end_block + 1))]
        batch_request(secret_keys.ALCHEMY, batch, 0, blocks_fetched)
    
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
    print("all blocks are in order and present, ending at", block_num - 1)
    return True


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


if __name__ == "__main__":
    start_block = 17765390
    num_blocks = 1

    start = time.time()
    print("Loading blocks")
    blocks = analysis.load_dict_from_json("test_blocks.json")
    done_loading = time.time()
    print("Blocks took x seconds to load", done_loading - start)
    count_blocks(blocks, start_block=17563790)
    done_counting = time.time()
    print("Block took x to count", done_counting - done_loading)
    print(blocks["17563790"])
    print("block to x to retrieve after loading:", time.time() - done_counting)
    





