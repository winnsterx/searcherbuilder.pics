# to get cex/dex searchers 
# iterate thru all blocks and pick out swap txs
    # swap txs that have 1) two unique tokens transfered AND 
    # 2) contains coinbase.transfer OR above avg gas fees AND 3) not a sandwich attack
# sort into two categories 
    # txs that pay via coinbase transfer
    # txs that pay via priority fee

