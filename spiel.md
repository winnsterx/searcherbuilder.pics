**Non-atomic MEV** refers to primarily CEX-DEX arbitrage.

Using [Zeromev API](data.zeromev.org/docs/), we collect all directional swaps and identify non-atomic MEV transactions using these [heuristics](https://github.com/winnsterx/searcher_database/blob/d334d5f9215ea2d479ac11e79f25be0cb5842aed/nonatomic_mev.py#L19). We filter out transactions sent to known non-MEV smart contracts. Examining the **volume** and **total bribe** that non-atomic searchers sent to builders, we can infer potentially exclusive searcher-builder relationships. 





**Atomic MEV** refers to **DEX-DEX arbitrage, sandwiching, and liquidation.** 

Using [Zeromev API](data.zeromev.org/docs/), we identify atomic MEV transactions. We filter out transactions sent to known non-MEV smart contracts. Examining the **number of transactions** and **total bribe** that atomic searchers sent to builders, we can infer potentially exclusive searcher-builder relationships. 