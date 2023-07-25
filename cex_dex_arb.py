# To estimate amount of CEX-DEX Arbs during a historical period
# we utilise cefi and defi price oracles to determine price differences
# if the price differences of CEX and DEX right before block N > threshold 
# any relevant trade in block is considered a CEX-DEX arb

# running thru txs between block 17616021 and 17666420
# subject to further changes
import requests
import json

START_BLOCK = 17616021
END_BLOCK = 17666420

PRICE_DIFFERENTIAL_THRESHOLD = 1.2

def calculate_cex_dex_delta(token_a, token_b, block_number):


# swap_txs = [{}]
# def analyze_block(block_number, swap_txs):
#     cex_dex_arbs = [] 
#     for tx in swap_txs:
#         token_a, token_b = tx.token_pai()
#         price_diff = cex_dex_price_delta_on_token(tokena, tokenb, block_number)
#         if price_diff > PRICE_DIFFERENTIAL_THRESHOLD:
#             cex_dex_arbs += tx
#     return cex_dex_arbs

