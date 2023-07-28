import requests, json, time
import analysis, secret_keys

def batch_request(url, batch, retries, prefetched_blocks):
    block_number = 0
    headers = {"Content-Type": "application/json"}
    start = time.time()
    print("getting batch at ", start)
    response = requests.post(url, headers=headers, data=json.dumps(batch))
    print("status code:",response.status_code)

    if response.status_code == 429 and retries < 5:
        print("retrying for the ", retries, " times")
        analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json")
        time.sleep(5)
        batch_request(url, batch, retries+1)
    else: 
        try:
            bs = response.json() # [{}, {}]
            for b in bs:
                extraData = bytes.fromhex(b["result"]["extraData"].lstrip("0x")).decode("ISO-8859-1")
                miner = b["result"]["miner"]
                block_number = b["id"]
                prefetched_blocks[block_number] = {"extraData": extraData, "feeRecipient": miner}
            print("finished getting batch using ", time.time() - start)
        except Exception as e:
            print(b)
            analysis.dump_dict_to_json(prefetched_blocks, "blocks_info.json")
            print("exception has happened")
            if b["error"]["code"] == 429:
                print("retrying for the ", retries, " times")
                time.sleep(5)
                batch_request(url, batch, retries+1)
            

def get_blocks(start_block, num_blocks):
    batch_size = 5
    end_block = start_block + num_blocks - 1
    prefetched_blocks = {}
    
    start = time.time()
    print("starting to get blocks at ", start)

    for block in range(start_block, end_block + 1, batch_size):
        batch = [{"jsonrpc": "2.0", "id": i, "method":"eth_getBlockByNumber", "params":[hex(i), True]} for i in range(block, min(block + batch_size, end_block + 1))]
        batch_request(secret_keys.ALCHEMY, batch, 0, prefetched_blocks)
    
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
    start_block = 17563790
    num_blocks = 100
    prefetched_blocks = get_blocks(start_block, num_blocks)
    # prefetched_blocks = analysis.load_dict_from_json("month_blocks_info.json")
    correct_block_count = count_blocks(prefetched_blocks, start_block)
    # so i can take a quick look 
    analysis.dump_dict_to_json(prefetched_blocks, "prefetch_blocks.json")



