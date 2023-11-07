# searcherbuilder.pics: an Open-Source Searcher-Builder Relationship Dashboard

# Introduction

Dashboards that investigate the relationships between different layers of the transaction supply chain is vital in observing Ethereum’s decentralisation and censorship-resistance. Different from existing dashboards, [searcherbuilder.pics](http://searcherbuilder.pics) focuses on the MEV transaction flows from searcher to builder to understand the state of vertical integration and searcher dominance. This dashboard solely uses transactions that have landed on-chain, without any mempool or relay bids data. The dashboard focuses on answering these questions:

1. Who are the top atomic & non-atomic MEV searcher addresses? How much market share do they have?
2. Who are the searcher-builders? How much do their searching operations contribute to their builders’ dominance?
3. How do searchers’ MEV strategies differ and how do those differences get reflected in their MEV volume, transaction count, and bribe?

[searcherbuilder.pics](http://searcherbuilder.pics) examines on-chain MEV transaction in both atomic and non-atomic domains. Atomic MEV refers to DEX-DEX arbitrage, sandwiching, and liquidation. Non-atomic MEV refers to mostly CEX-DEX arbitrage. We employ three different metrics to measure the flow from searchers to builders: volume (USD), transaction count, and total bribes (coinbase transfers + priority fees, in ETH). The dashboard separates the atomic and non-atomic MEV searchers due to their immense behavioural differences. We recommend checking out the dashboard on desktop for most information. 

# Methodology

## Identifying Atomic MEV Activities & Searcher Addresses

Using [Zeromev’s API](https://data.zeromev.org/docs/), which employs a slight modification of Flashbots’ [mev-inspect-py](https://github.com/flashbots/mev-inspect-py/tree/main/mev_inspect/models) for MEV detection, we identify atomic MEV transactions in each block. We collect transactions labeled with the `mev_type` of `arb`, `frontrun`, `backrun`, and `liquid`. The smart contract invoked in these transactions, represented by the `address_to` field returned by the Zeromev API, is the potential MEV searcher address.

From these addresses, we filter out labeled non-MEV smart contracts (such as routers, wash trading bots, telegram bots, etc). Only MEV searchers using proprietary contracts will be detected. Although MEV can be extracted through generic contracts, like Uniswap routers and telegram bots, these opportunities represent an insignificant portion of MEV volume. The set of known contract labels is created by aggregating from multiple sources and active manual inspection.

Zeromev captures a reliable lower bound of active atomic MEV searcher addresses with minimal false positives. Our identification of atomic MEV is ultimately limited by Zeromev’s and mev-inspect-py’s capabilities, which have [known issues](https://github.com/flashbots/mev-inspect-py/issues) and miss atomic MEV transactions that fall through their [classification algorithm](https://github.com/flashbots/mev-inspect-py/tree/main/mev_inspect/models).

## Identifying Non-Atomic MEV Activities & Searcher Addresses

In “[A Tale of Two Arbitrages](https://frontier.tech/a-tale-of-two-arbitrages)”, it is estimated that at least “60% of [arbitrage] opportunities (by revenue) are executed via CeFi-DeFi arbitrage”. Capturing such non-atomic MEV activities is the crux of this dashboard.

From all the directional swaps identified by Zeromev, we classify a swap as a CEX-DEX arbitrage if it fulfills one of the following heuristics:

1. It contains an coinbase transfer to the builder (or more generally fee recipient) of the block.
2. It is followed by a separate transaction that is a direct transfer to the builder (a variation of the bribing behavior above).
3. It is within the [top 10% of the block](https://twitter.com/ankitchiplunkar/status/1687806136747966464?s=46&t=NHtVxC1u9l6MoDd95WBeUw). This aims to capture both CEX-DEX arbitrages that are either bribing solely via gas fees or not bribing at all due to of vertical integration. The heuristic is based on [a demonstrated correlation](https://arxiv.org/pdf/2305.19150.pdf) between top-of-block opportunities and CEX-DEX arbitrage, due to the urgency to extract these MEV opportunities.
4. It interacted with only one protocol. Zeromev has often misclassified some atomic arbitrage as directional swaps; and since atomic arbitrages share the above bribing patterns, they get counted as a CEX-DEX arbitrage. To reduce such false positives, we only look at transactions that are one-hop. While this captures most CEX-DEX arbitrages, those with multi-hops DEX-legs are missed.

We collect the `address_to` field of these transactions and filter out known non-MEV contracts. In the future, we intend to incorporate [price volatility data on leading CEXes](https://ethresear.ch/t/the-influence-of-cefi-defi-arbitrage-on-order-flow-auction-bid-profiles/17258) to further improve the accuracies of our results.

We also remove any addresses that have been identified as an atomic searcher to further mitigate Zeromev’s occasional misclassification of atomic MEV as swaps. While this means we won’t capture searcher addresses that pursue both atomic & non-atomic MEV opportunities, these addresses are insignificant in number likely due to the need for specialization.

### Note: Not all non-atomic MEV transactions are CEX-DEX arbitrage

Notably, we observed that a very small portion of the non-atomic MEV transactions identified using the above methodology are cross-chain arbitrage rather than CEX-DEX arbitrage.

For example, this Ethereum [transaction](https://etherscan.io/tx/0x6ade8dd594eaed8abc773dc9566d6353ff20bb8deac38ae5c196bd803994b763) that would’ve been picked up by our methodology is actually an arbitrage between the Uniswap pools on Ethereum and Polygon (this is the [Polygon side](https://polygonscan.com/tx/0x66cb4ce8b367bc84b6ac0fc2df44adb0bc82659e5b8f4a5e80aa21c3c518d905) of the arbitrage). Understanding the size of cross-chain MEV is an interesting open problem space that we may be interested in tackling.

## Metrics for Flow from Searcher to Builder

Flow from searchers to builders can be interpreted with three different metrics: volume (USD), transaction count, and total bribe (coinbase transfer + priority fees, in ETH). Each chart can be viewed in each metric using the upper-right toggle.

We recommend volume (USD) as the metric to analyze non-atomic MEV flow. More transactions does not necessarily indicate more dominance for CEX-DEX arbitrages. Given the state of non-atomic searcher-builder integration, we are skeptical that bribe size is correlated with dominance and trade size. Integrated searchers can be over-bribing builders to lend their builder more leverage in the relay auction or under-bribing since their builder can subsidize their bid directly.

In contrast, we recommend transaction count as the best metric for atomic MEV activities. Due to flash loans, volume loses credibility. We don’t recommend total bribes for similar reasons above. Transaction count speaks to the ability for atomic searchers to land on-chain, which is a good proxy for their dominance.

We decided against showing a combined MEV activities. There isn’t a single metric that can satisfactorily represent and compare both MEV domains. We show the top 25 searcher addresses under each metric for readability. In total, these top 25 addresses typically account of 99% of all MEV volume, transaction count, and bribes.

## Conclusion & Future Directions

1. Who are the top atomic & non-atomic MEV searcher addresses? How much market share do they have?
2. Who are the searcher-builders? How much do their searching operations contribute to their builders’ dominance?
3. How do searchers’ MEV strategies differ and how do those differences get reflected in their MEV volume, transaction count, and bribe?

- Chart that shows how many active searcher addrs do each builder have. How much more private addresses flow does top 4 builders receive? Who receive the most addresses?
- Block subsidization & profit. How much of the bid from searcher to builder actually gets kept by builder vs subsidized by builder?

# Sources

https://www.zeromev.org/

https://www.alchemy.com/

https://frontier.tech/builder-dominance-and-searcher-dependence

https://frontier.tech/a-new-game-in-town

https://frontier.tech/a-tale-of-two-arbitrages

https://ethresear.ch/t/empirical-analysis-of-builders-behavioral-profiles-bbps/16327

https://mevboost.pics/

https://eigenphi.io/

https://www.relayscan.io/