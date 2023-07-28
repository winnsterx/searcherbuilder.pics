import requests, json, time
import analysis, secret_keys

MAX_RETRIES = 5  # Define a maximum number of retries
INITIAL_BACKOFF = 1  # Define initial backoff time in seconds

def process_response(response, retries, prefetched_blocks, missing_blocks, batch):
    retry_required = False
    try:
        bs = response.json()  # [{}, {}]
        for b in bs:
            if 'result' in b and b['result'] is None:
                print(f"block {b['id']} is missing")
                print(b)
                missing_blocks[b['id']] = b
                retry_required = True
                return retry_required
            elif "error" in b:
                print(f"block {b['id']} is getting error msg of {b['error']}")
                print(b)

                missing_blocks[b['id']] = b
                retry_required = True
                return retry_required
            else:
                extraData = bytes.fromhex(b["result"]["extraData"].lstrip("0x")).decode("ISO-8859-1")
                miner = b["result"]["miner"]
                block_number = b["id"]
                prefetched_blocks[block_number] = {"extraData": extraData, "feeRecipient": miner}
        return retry_required

    except Exception as e:
        print("Exception occurred", e)
        analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json") 

def batch_request(url, batch, retries, prefetched_blocks, missing_blocks):
    headers = {"Content-Type": "application/json"}
    
    while retries < MAX_RETRIES:
        start = time.time()
        print(f"Getting batch at {start}, attempt {retries + 1}")
        response = requests.post(url, headers=headers, data=json.dumps(batch))

        if response.status_code == 200:
            retry_required = process_response(response, retries, prefetched_blocks, missing_blocks, batch)
            if not retry_required: # if retry is not required, process is complete'
                print("batch successfully completed")
                break
            analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json") 

        else: 
            print(f"Non-success status code received: {response.status_code}, retrying for the {retries + 1} time")

        analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json")
        retries += 1
        time.sleep(INITIAL_BACKOFF * (2 ** retries))  # Sleep before next retry with exponential backoff        
        
        if retries == MAX_RETRIES:
            print("Max retries reached. Exiting.")


def get_blocks(start_block, num_blocks, missing_blocks):
    batch_size = 99
    end_block = start_block + num_blocks - 1
    prefetched_blocks = {}
    
    start = time.time()
    print("starting to get blocks at ", start)

    for block in range(start_block, end_block + 1, batch_size):
        batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} for i in range(block, min(block + batch_size, end_block + 1))]
        batch_request(secret_keys.ALCHEMY, batch, 0, prefetched_blocks, missing_blocks)
    
    print("finished getting blocks in", time.time() - start, " seconds")
    analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json")
    return prefetched_blocks
    

# counts that the blocks in block file is in order and present
def count_blocks(blocks, start_block):
    block_num = start_block
    for b, _ in blocks.items():
        if int(b) != block_num:
            print("missing / out of order block number", b, "isnt ", block_num)
            return False
        block_num += 1
    print("all blocks are in order and present, ending at", block_num - 1)
    return True


if __name__ == "__main__":
    # 17563790 to 17779790
    start_block = 17794300
    num_blocks = 7200 * 2
    missing_blocks = {}
    prefetched_blocks = get_blocks(start_block, num_blocks, missing_blocks)
    # prefetched_blocks = analysis.load_dict_from_json("tri_month_blocks.json")
    correct_block_count = count_blocks(prefetched_blocks, start_block)
    # so i can take a quick look 
    analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json")



