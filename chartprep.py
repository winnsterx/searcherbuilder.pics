import datapane as dp
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import math, humanize
import analysis 
import visual_analysis
import constants
from collections import defaultdict


def abbreviate_label(label, short=False):
    res = ""
    if label.startswith("0x"):
        if label in constants.KNOWN_SEARCHERS_MAPPING:
            res = constants.KNOWN_SEARCHERS_MAPPING[label]
            if short == False:
                res += " (" + label[:9] + ")"
            return res
        elif label in constants.KNOWN_BUILDER_MAPPING:
            res = constants.KNOWN_BUILDER_MAPPING[label] 
            if short == False:
                res += " (" + label[:9] + ")"
            return res
        else: 
            return label[:15] + "..."
    else:
        return label

def create_searcher_builder_sankey(map, agg, title, unit, date):
    # nodes is index of searcher + builder, each unique
    # an entity will now be recognized as the index from this list now
    span = '<span style="font-size: 20px;font-weight:bold; margin-bottom: 10px;">{}<br /><span style="font-size: 14px;">({} from {} to {})</span></span>'     
    # span = "<span style=&quot;font-size: 24px;font-weight:bold;&quot;>MEV-Boost Block Flow<br /><span style='font-size:14px;'>(last 30 days)</span></span>"
    searcher_builder_map = analysis.create_searcher_builder_map(map)
    # nodes = sorted_searchers + list(map.keys())
    nodes = list(agg.keys()) + list(map.keys())
    abbreviated_nodes = [abbreviate_label(node) for node in nodes]
    source_indices = []
    target_indices = [] 
    values = []

    for searcher, builders in searcher_builder_map.items():
        for builder, count in builders.items():
            source_indices.append(nodes.index(searcher))
            target_indices.append(nodes.index(builder))
            values.append(count)

    x_coors = [0.001] * len(agg) + [0.999] * len(map)
    y_coors = [0.01] * len(agg) + [0.01] * len(map)

    fig = go.Figure(data=go.Sankey(
        arrangement='snap',
        textfont=go.sankey.Textfont(size=16, color="black", family="Courier New"),
        node = dict(
            x = x_coors,
            y = y_coors,
            pad = 20,
            thickness = 20,
            line = dict(color = "black", width = 0.5),      
            label = abbreviated_nodes,  
            hovertemplate='<b>%{label}<b><br />%{value} '+unit,
        ),
        link = dict(
            source = source_indices,
            target = target_indices,
            value = values,            
            hovertemplate='<b>total: %{source.value:,.0f} <br /><b>'+unit,  
        )
    ))

    tx_mev_types = "arbitrage, sandwich, and liquidation txs"
    if "non-atomic" in title.lower():
        tx_mev_types = "cefi-defi arbitrage txs"
    elif "combined" in title.lower():
        tx_mev_types = "all atomic and non-atomic MEV txs"

    fig.update_layout(title_text=span.format(title, tx_mev_types, date[0], date[1]),
                      font_size=16,
                    #   paper_bgcolor='#eee',
                      font=dict(
                                family="Courier New, monospace",
                                # size=20,  # Set the font size here
                                color="black"
                               ), autosize=True, width=800, height=1200, margin=dict(t=100, b=100, l=50, r=50))
    return fig 


def prune_map_and_agg_for_sankey(map, agg, metric, percentile, min_count, mev_domain):
    # map, agg are non sorted, native maps from atomic or nonatomic
    if mev_domain == "atomic":
        map = analysis.return_atomic_maps_with_only_type(map, "total")
    elif mev_domain == "nonatomic":
        atomic = analysis.load_dict_from_json(f"atomic/new/agg/agg_{metric}.json")
        agg = analysis.remove_atomic_from_agg(agg, atomic)
        map = analysis.remove_atomic_from_map(map, atomic)
    # get searchers that are responsible for x% of all {metric} produced 
    map, agg = analysis.get_map_and_agg_in_range(map, agg, percentile)
    # eliminate smaller builders who account for little of a tx to show better correlation
    map, agg = analysis.remove_small_builders(map, agg, min_count)

    # if x percentile of searchers is more than 30, we trim for better visuals
    if len(agg) > 30:
        agg = analysis.slice_dict(agg, 30)
        res = defaultdict(lambda: defaultdict(int))
        for builder, searchers in map.items():
            for searcher, count in searchers.items():
                if searcher in agg: 
                    res[builder][searcher] += count 
        map = res
        
    return map, agg


def create_three_sankeys_by_metric(metric, unit, percentile, min_count):
    nonatomic_map = analysis.load_dict_from_json(f"nonatomic/new/builder_swapper_maps/builder_swapper_map_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(f"nonatomic/new/agg/agg_{metric}.json")
    atomic_map = analysis.load_dict_from_json(f"atomic/new/builder_atomic_maps/builder_atomic_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(f"atomic/new/agg/agg_{metric}.json")
    combined_map, combined_agg = analysis.combine_atomic_nonatomic_map_and_agg(atomic_map, atomic_agg, nonatomic_map, nonatomic_agg)

    atomic_map, atomic_agg = prune_map_and_agg_for_sankey(atomic_map, atomic_agg, metric, percentile, min_count, "atomic")
    atomic_map = analysis.sort_map(atomic_map)
    atomic_fig = create_searcher_builder_sankey(atomic_map, atomic_agg, f"Atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit, ("7/1", "8/1"))

    nonatomic_map, nonatomic_agg = prune_map_and_agg_for_sankey(nonatomic_map, nonatomic_agg, metric, percentile, min_count, "nonatomic")
    nonatomic_map = analysis.sort_map(nonatomic_map)
    nonatomic_fig = create_searcher_builder_sankey(nonatomic_map, nonatomic_agg, f"Non-atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit, ("7/1", "8/1"))

    combined_map, combined_agg = prune_map_and_agg_for_sankey(combined_map, combined_agg, metric, percentile, min_count, "combined")
    combined_map = analysis.sort_map(combined_map)
    combined_fig = create_searcher_builder_sankey(combined_map, combined_agg, f"Combined Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit,  ("7/1", "8/1"))

    return atomic_fig, nonatomic_fig, combined_fig


def calculate_highlight_figures():
    atomic_agg = analysis.load_dict_from_json("atomic/new/agg/agg_vol.json")
    atomic_agg = analysis.remove_known_entities_from_agg(atomic_agg)

    nonatomic_agg = analysis.load_dict_from_json("nonatomic/new/agg/agg_vol.json")
    nonatomic_agg = analysis.remove_known_entities_from_agg(nonatomic_agg)
    # since atomic is needed, dont get atomic by range until after this
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)

    nonatomic_agg = analysis.get_agg_in_range(nonatomic_agg, 0.99)
    atomic_agg = analysis.get_agg_in_range(atomic_agg, 0.99)
    
    num_atomic = len(atomic_agg)
    num_nonatomic = len(nonatomic_agg)

    atomic_tot_vol = analysis.humanize_number(int(sum(atomic_agg.values())))
    nonatomic_tot_vol = analysis.humanize_number(sum(nonatomic_agg.values()))

    atomic_agg = analysis.load_dict_from_json("atomic/new/agg/agg_tx.json")
    atomic_agg = analysis.remove_known_entities_from_agg(atomic_agg)

    nonatomic_agg = analysis.load_dict_from_json("nonatomic/new/agg/agg_tx.json")
    nonatomic_agg = analysis.remove_known_entities_from_agg(nonatomic_agg)
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)

    atomic_agg = analysis.get_agg_in_range(atomic_agg, 0.95)
    nonatomic_agg = analysis.get_agg_in_range(nonatomic_agg, 0.95)

    atomic_tot_tx = analysis.humanize_number(sum(atomic_agg.values()))
    nonatomic_tot_tx = analysis.humanize_number(sum(nonatomic_agg.values()))

    return num_atomic, num_nonatomic, atomic_tot_vol, nonatomic_tot_vol, atomic_tot_tx, nonatomic_tot_tx


def create_searcher_builder_percentage_bar_chart(map, agg, title, metric):
    fig = go.Figure()
    top_searchers = analysis.slice_dict(agg, 10)
    builder_market_share = {}

    for builder, searchers in map.items():
        builder_market_share[builder] = sum(searchers.values())
    
    total_count = sum(builder_market_share.values())

    for builder, searchers in map.items():
        x = []
        y = [abbreviate_label(s, True) for s in list(top_searchers.keys())]

        # adding total market share as comparison
        y.insert(0, "Total Market Shares")
        x.insert(0, builder_market_share[builder] / total_count * 100)

        for searcher, _ in top_searchers.items():
            percent = searchers.get(searcher, 0) / agg[searcher] * 100
            x.append(percent)
        
        fig.add_trace(go.Bar(
            y=y[::-1],
            x=x[::-1],
            name=abbreviate_label(builder, True),
            orientation="h",
            hovertemplate='<b>%{x:.2r}%<b> ',
        ))


    fig.update_layout(
        title=title,
        xaxis_title="Percentage of {unit}".format(unit="Volume" if metric=="vol" else metric.capitalize()),
        yaxis_title="",
        xaxis_range=[0, 100],
        barmode="stack",
        legend={'traceorder':'normal'},
        # margin={"l":20, "t":20},
        font=dict(
            family="Courier New, monospace",
            color="black"
        ),        
    )

    return fig


def create_three_bar_charts_by_metric(metric, unit):
    nonatomic_map = analysis.load_dict_from_json(f"nonatomic/new/builder_swapper_maps/builder_swapper_map_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(f"nonatomic/new/agg/agg_{metric}.json")
    atomic_map = analysis.load_dict_from_json(f"atomic/new/builder_atomic_maps/builder_atomic_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(f"atomic/new/agg/agg_{metric}.json")
    combined_map, combined_agg = analysis.combine_atomic_nonatomic_map_and_agg(atomic_map, atomic_agg, nonatomic_map, nonatomic_agg)

    atomic_agg = analysis.sort_agg(atomic_agg)
    atomic_map = analysis.sort_map(analysis.return_atomic_maps_with_only_type(atomic_map, "total"))
    atomic_map, atomic_agg = analysis.prune_known_entities_from_map_and_agg(atomic_map, atomic_agg)
    atomic_fig = create_searcher_builder_percentage_bar_chart(atomic_map, atomic_agg, f"Atomic Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)

    nonatomic_agg = analysis.sort_agg(nonatomic_agg)
    nonatomic_map = analysis.sort_map(nonatomic_map)
    nonatomic_map, nonatomic_agg = analysis.prune_known_entities_from_map_and_agg(nonatomic_map, nonatomic_agg)
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)
    nonatomic_fig = create_searcher_builder_percentage_bar_chart(nonatomic_map, nonatomic_agg, f"Nonatomic Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)

    combined_agg = analysis.sort_agg(combined_agg)
    combined_map = analysis.sort_map(combined_map)
    combined_fig = create_searcher_builder_percentage_bar_chart(combined_map, combined_agg, f"Combined Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)

    return atomic_fig, nonatomic_fig, combined_fig



if __name__ == "__main__":
    atomic_fig_vol, nonatomic_fig_vol, combined_fig_vol = create_three_sankeys_by_metric("vol", "USD", 0.95, 5000)
    atomic_fig_tx, nonatomic_fig_tx, combined_fig_tx = create_three_sankeys_by_metric("tx", "number of transactions", 0.95, 5)
    atomic_fig_bribe, nonatomic_fig_bribe, combined_fig_bribe = create_three_sankeys_by_metric("bribe", "ETH", 0.95, 5)

    atomic_bar_vol, nonatomic_bar_vol, combined_bar_vol = create_three_bar_charts_by_metric("vol", "USD")


    title = "# <p style='text-align: center;margin:0px;'> Searcher Builder Activity Dashboard </p>"
    head = ("<div><div><div style ='float:left;color:#0F1419;font-size:18px'>Analysis based on txs from 7/1 to 8/1</div>" 
                +'<div style ="float:right;font-size:18px;color:#0F1419">View <a href="./data.html">raw data</a> </div></div>'
                +'<div><div style ="float:left;font-size:18px;color:#0F1419;clear: left">Built by '
                +'<a href="https://twitter.com/nero_eth">winnsterx</a> & inspired by '
                +'<a href="https://mevboost.pics">mevboost.pics</a> by <a href="https://twitter.com/nero_eth">Toni Wahrstätter</a></div>'
                +'<div style ="float:right;font-size:18px;color:#0F1419">View Source on <a href="https://github.com/winnsterx/searcher_database">Github</a></div></div></div>'
                +"\n")

    num_atomic, num_nonatomic, atomic_tot_vol, nonatomic_tot_vol, atomic_tot_tx, nonatomic_tot_tx = calculate_highlight_figures()
    # atomic_fig.show()
    view = dp.Blocks(
        dp.Page(title="Highlights", blocks=[
            title, 
            head, 
            dp.Group(
              dp.BigNumber(heading="Number of Atomic Searchers", value=num_atomic),
              dp.BigNumber(heading="Number of Atomic MEV Transactions", value=atomic_tot_tx),
              dp.BigNumber(heading="Total Volume from Atomic MEV (USD)", value=atomic_tot_vol),
              dp.BigNumber(heading="Number of Cefi-Defi Arb Searchers", value=num_nonatomic),
              dp.BigNumber(heading="Number of Cefi-Defi Arb Transactions", value=nonatomic_tot_tx),
              dp.BigNumber(heading="Total Volume of Cefi-Defi Arb (USD)", value=nonatomic_tot_vol),
              columns=3
            ),
            combined_bar_vol,
            atomic_bar_vol,
            nonatomic_bar_vol,
            atomic_fig_tx,
            nonatomic_fig_vol,
            combined_fig_bribe,
        ]),
        dp.Page(title="Volume", blocks=[
            title, 
            head, 
            atomic_fig_vol,
            nonatomic_fig_vol, 
        ]),
        dp.Page(title="Transaction Count", blocks=[
            title, 
            head, 
            atomic_fig_tx,
            nonatomic_fig_tx,
        ]),
        dp.Page(title="Bribes", blocks=[
            title, 
            head, 
            atomic_fig_bribe,
            nonatomic_fig_bribe,
            combined_fig_bribe,
        ])
    )
    dp.save_report(view, path="/Users/winniex/Documents/GitHub/winnsterx.github.io/index.html")

    fixedposi = "<style>nav.min-h-screen {position: -webkit-sticky;position: sticky;}</style>"

    more_css = '''
        <style>
        
        body {
            max-width: 900px;
            margin-left: auto !important;
            margin-right: auto !important;
            background: #eee;
        }
        @media screen and (min-width: 700px) {
            body {
                max-width: 1000px;
            }
        }

        a.pt-1 {
            position: sticky;
            top:0%;
            font-size: 1.4rem;
            padding-top: 1.2rem !important;
            padding-bottom: 1.2rem !important;
        }

        nav div, nav div.hidden {
            margin: 0 0 0 0;
            width: 100%;
            justify-content: space-evenly;
        }
        .py-5.px-4 {
            background: white;
        }
        main div.px-4 {
            background: #eee;
        }


        .flex {
            width: 100%; 
            justify-content: space-evenly;
        }

        nav {
            position: sticky;
            top: 0;
            z-index: 99999;
            background-color: white;
            display: flex;
            margin-bottom: 1.5rem;
        }

        div.justify-start {
            margin-top: 1rem;
            margin-bottom: 1rem;
        }
                
        </style>
    '''

    with open("/Users/winniex/Documents/GitHub/winnsterx.github.io/index.html", "r") as file:
        f = file.read()
    OG_STUFF = ' <title>searcherbuilder.pics | Searcher Builder Dashboard</title>\n<meta charset="UTF-8" />\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:site" content="@winnsterx">\n<meta name="twitter:title" content="Searcher Builder Dashboard">\n<meta name="twitter:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum.">\n<meta name="twitter:image" content="https://www.searcherbuilder.pics/">\n<meta property="og:title" content=Searcher Builder Dashboard>\n<meta property="og:site_name" content=searcherbuilder.pics>\n<meta property="og:url" content=searcherbuilder.pics>\n<meta property="og:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum." >\n<meta property="og:type" content=website>\n<link rel="shortcut icon" href="https://mevboost.toniwahrstaetter.com/ethlogo.png" />\n<meta property="og:image" content=https://mevboost.toniwahrstaetter.com/pv.png>\n<meta name="description" content="Up-to-date comparative visualizations on MEV-Boost and Proposer Builder Separation on Ethereum.">\n<meta name="keywords" content="Ethereum, MEV-Boost, PBS, Dashboard">\n <meta name="author" content="Toni Wahrstätter">'
    f = f.replace('<meta charset="UTF-8" />\n', fixedposi+ OG_STUFF+more_css) # + GA
    with open("/Users/winniex/Documents/GitHub/winnsterx.github.io/index.html", "w") as file:
        file.write(f)