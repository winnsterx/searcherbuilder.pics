import datapane as dp
import random
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import math
import analysis 
import visual_analysis
import constants
from collections import defaultdict
import seaborn as sns
import colorcet as cc
import secret_keys


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


def get_builder_colors_map(list_of_builders):
    colors = sns.color_palette(cc.glasbey_hv, len(list_of_builders))
    # random.shuffle(colors)
    builder_color_map = {builder: color for builder, color in zip(list_of_builders, colors)}
    return builder_color_map



def create_searcher_builder_sankey(map, agg, builder_color_map, title, unit, date):
    # nodes is index of searcher + builder, each unique
    # an entity will now be recognized as the index from this list now
    span = '<span style="font-size: 20px;font-weight:bold; margin-bottom: 10px;">{}<br /><span style="font-size: 14px;font-weight:normal">({} from {} to {})</span></span>'     
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


def prune_map_and_agg_for_sankey(map, agg, metric, percentile, min_count):
    # map, agg are all sorted and pruned of known entities and atomic (if nonatomic)
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


def create_three_sankeys_by_metric(all_maps_and_agg, builder_color_map, metric, unit, percentile, min_count):
    for i in range(0, len(all_maps_and_agg), 2):
        map = all_maps_and_agg[i]
        agg = all_maps_and_agg[i+1]
        map, agg = prune_map_and_agg_for_sankey(map, agg, metric, percentile, min_count)
        all_maps_and_agg[i] = map
        all_maps_and_agg[i+1] = agg

    atomic_fig = create_searcher_builder_sankey(all_maps_and_agg[0], all_maps_and_agg[1], builder_color_map, f"Atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit, ("7/1", "8/1"))
    nonatomic_fig = create_searcher_builder_sankey(all_maps_and_agg[2], all_maps_and_agg[3], builder_color_map, f"Non-atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit, ("7/1", "8/1"))
    # combined_fig = create_searcher_builder_sankey(all_maps_and_agg[4], all_maps_and_agg[5], f"Combined Searcher-Builder Orderflow by {metric.capitalize()} ({unit})", unit,  ("7/1", "8/1"))

    return atomic_fig, nonatomic_fig, nonatomic_fig


def calculate_highlight_figures():
    atomic_agg = analysis.load_dict_from_json("atomic/fifty/agg/agg_vol.json")
    atomic_agg = analysis.remove_known_entities_from_agg(atomic_agg)

    nonatomic_agg = analysis.load_dict_from_json("nonatomic/fifty/agg/agg_vol.json")
    nonatomic_agg = analysis.remove_known_entities_from_agg(nonatomic_agg)
    # since atomic is needed, dont get atomic by range until after this
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)

    nonatomic_agg = analysis.get_agg_in_range(nonatomic_agg, 0.99)
    atomic_agg = analysis.get_agg_in_range(atomic_agg, 0.99)
    
    num_atomic = len(atomic_agg)
    num_nonatomic = len(nonatomic_agg)

    atomic_tot_vol = analysis.humanize_number(int(sum(atomic_agg.values())))
    nonatomic_tot_vol = analysis.humanize_number(sum(nonatomic_agg.values()))

    atomic_agg = analysis.load_dict_from_json("atomic/fifty/agg/agg_tx.json")
    atomic_agg = analysis.remove_known_entities_from_agg(atomic_agg)

    nonatomic_agg = analysis.load_dict_from_json("nonatomic/fifty/agg/agg_tx.json")
    nonatomic_agg = analysis.remove_known_entities_from_agg(nonatomic_agg)
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)

    atomic_agg = analysis.get_agg_in_range(atomic_agg, 0.95)
    nonatomic_agg = analysis.get_agg_in_range(nonatomic_agg, 0.95)

    atomic_tot_tx = analysis.humanize_number(sum(atomic_agg.values()))
    nonatomic_tot_tx = analysis.humanize_number(sum(nonatomic_agg.values()))

    return num_atomic, num_nonatomic, atomic_tot_vol, nonatomic_tot_vol, atomic_tot_tx, nonatomic_tot_tx


def create_notable_searcher_builder_percentage_bar_chart(map, metric, mev_domain, builder_color_map, threshold=50):
    fig = go.Figure()
    notable, builder_market_share, highlight_relationship = analysis.find_notable_searcher_builder_relationships(map, threshold)
    span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">Notable {} Searcher-Builder Relationships<br /><span style="font-size: 13px;">(Highlighting relationships where a searcher is captured in<br />a builder\'s blocks at rates > 2x their overall market share)</span></span>'     

    for builder, searchers in map.items():
        # Separate data for highlighted and non-highlighted bars
        x_highlighted = []
        y_highlighted = []
        x_regular = []
        y_regular = []

        y_highlighted.insert(0, "Total Market Shares")
        x_highlighted.insert(0, builder_market_share[builder])

        for searcher, builders_percent in notable.items():
            if (searcher, builder) in highlight_relationship or searcher == "Total Market Shares":
                y_highlighted.append(searcher)
                x_highlighted.append(builders_percent.get(builder, ""))
            else:
                y_regular.append(searcher)
                x_regular.append(builders_percent.get(builder, ""))


        # Trace for non-highlighted bars
        fig.add_trace(go.Bar(
            y=[abbreviate_label(s,True) for s in y_regular[::-1]],
            x=x_regular[::-1],
            name=abbreviate_label(builder, True),
            orientation="h",
            hovertemplate='<b>%{x:.2r}%<b> ',
            marker=dict(
                color='lightgray',
                line=dict(width=1)
            ),
            showlegend=False,   # Don't show this in legend
            legendgroup=builder  # Use same legendgroup identifier as before
        ))

        # Trace for highlighted bars
        fig.add_trace(go.Bar(
            y=[abbreviate_label(s, True) for s in y_highlighted[::-1]],
            x=x_highlighted[::-1],
            name=abbreviate_label(builder, True),
            orientation="h",
            hovertemplate='<b>%{x:.2r}%<b> ',
            marker=dict(
                color=f"rgb{builder_color_map[builder]}",
                line=dict(width=1)
            ),
            legendgroup=builder  # Use builder as legendgroup identifier
        ))

    title_layout = {
        'text': span.format(mev_domain),
        'y':0.9,
        'x':0.5,
        'xanchor': 'center',
        'yanchor': 'top'
    }

    fig.update_layout(
        title=title_layout,
        xaxis_title=f"Percentage of {metric.capitalize()}",
        yaxis_title="",
        xaxis_range=[0, 100],
        barmode="stack",
        legend={'traceorder':'normal'},
        margin={"t":150}, # what gives the spacing between title and plot
        font=dict(
            family="Courier New, monospace",
            color="black"
        ),       
        autosize=False,
        height=600,
    )

    return fig
            





def create_searcher_builder_percentage_bar_chart(map, agg, builder_color_map, title, metric):
    fig = go.Figure()
    top_searchers = analysis.slice_dict(agg, 20)
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
            marker=dict(
                color=f"rgb{builder_color_map[builder]}",
                line=dict(width=1)
            ),
        ))


    fig.update_layout(
        title=title,
        xaxis_title="Percentage of {unit}".format(unit="Transactions" if metric=="tx" else metric.capitalize()+"s"),
        yaxis_title="",
        xaxis_range=[0, 100],
        barmode="stack",
        legend={'traceorder':'normal'},
        # margin={"l":20, "t":20},
        font=dict(
            family="Courier New, monospace",
            color="black"
        ),        
        autosize=False,
        height=600,
    )

    return fig


def create_three_bar_charts_by_metric(all_maps_and_agg, builder_color_map, metric, unit):
    atomic_fig = create_searcher_builder_percentage_bar_chart(all_maps_and_agg[0], all_maps_and_agg[1], builder_color_map, f"Atomic Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)
    nonatomic_fig = create_searcher_builder_percentage_bar_chart(all_maps_and_agg[2], all_maps_and_agg[3], builder_color_map, f"Nonatomic Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)
    combined_fig = create_searcher_builder_percentage_bar_chart(all_maps_and_agg[4], all_maps_and_agg[5], builder_color_map, f"Combined Searcher Orderflow Breakdown by Builder in {metric.capitalize()} ({unit})", metric)

    return atomic_fig, nonatomic_fig, combined_fig


def create_searcher_bar_chart(agg, title, metric):
    agg = analysis.slice_dict(agg, 15)
    searchers = [abbreviate_label(s) for s in list(agg.keys())]
    counts = list(agg.values())

    fig = go.Figure(data=go.Bar(
        x=searchers, y=counts
    ))
    fig.update_layout(
        title="Searcher Counts",
        xaxis_title="Searcher",
        yaxis_title="Count"
    )   

    return fig


def create_searcher_pie_chart(agg, title_1, title_2, metric, unit, legend=False):
    if len(title_2) > 1: # if not combined
        span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{}<br />{}<br /><span style="font-size: 16px;"> by top 10 searchers (in {})</span></span>'     
        title_layout = {
            'text': span.format(title_1, title_2, unit),
            'y':0.9,
            'x':0.5,
            'xanchor': 'center',
            'yanchor': 'top'
        }
    else: 
        span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{}<br /><span style="font-size: 16px;"> by top 10 searchers (in {})</span></span>'     
        title_layout = {'text': span.format(title_1, unit)}


    agg = analysis.slice_dict(agg, 10)
    searchers = [abbreviate_label(s) for s in list(agg.keys())]
    counts = list(agg.values())

    fig = go.Figure(data=go.Pie(
        labels=searchers,
        values=counts,
        hole=0.3,  # Optional: to create a donut-like chart
        hoverinfo='label+percent+value'
    ))

    # Setting layout details
    fig.update_layout(
        title=title_layout,
        showlegend=legend,
        font=dict(
            family="Courier New, monospace",
            color="black"
        )
    )
    return fig


def return_sorted_map_and_agg_pruned_of_known_entities_and_atomc(metric):
    atomic_map = analysis.load_dict_from_json(f"atomic/fifty/builder_atomic_maps/builder_atomic_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(f"atomic/fifty/agg/agg_{metric}.json")
    nonatomic_map = analysis.load_dict_from_json(f"nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(f"nonatomic/fifty/agg/agg_{metric}.json")

    # before, atomic_map is {total, arb,...}. after this, atomic is simple
    atomic_agg = analysis.sort_agg(atomic_agg)
    atomic_map = analysis.sort_map(analysis.return_atomic_maps_with_only_type(atomic_map, "total"))
    atomic_map, atomic_agg = analysis.prune_known_entities_from_map_and_agg(atomic_map, atomic_agg)

    nonatomic_agg = analysis.sort_agg(nonatomic_agg)
    nonatomic_map = analysis.sort_map(nonatomic_map)
    nonatomic_map, nonatomic_agg = analysis.prune_known_entities_from_map_and_agg(nonatomic_map, nonatomic_agg)
    nonatomic_agg = analysis.remove_atomic_from_agg(nonatomic_agg, atomic_agg)

    combined_map, combined_agg = analysis.combine_atomic_nonatomic_map_and_agg(atomic_map, atomic_agg, nonatomic_map, nonatomic_agg)
    combined_agg = analysis.sort_agg(combined_agg)
    combined_map = analysis.sort_map(combined_map)
    combined_map, combined_agg = analysis.prune_known_entities_from_map_and_agg(combined_map, combined_agg)

    atomic_map, atomic_agg = analysis.get_map_and_agg_in_range(atomic_map, atomic_agg, 0.99)
    nonatomic_map, nonatomic_agg = analysis.get_map_and_agg_in_range(nonatomic_map, nonatomic_agg, 0.99)
    combined_map, combined_agg = analysis.get_map_and_agg_in_range(combined_map, combined_agg, 0.99)
    return [atomic_map, atomic_agg, nonatomic_map, nonatomic_agg, combined_map, combined_agg]


def return_sorted_block_map_and_agg_pruned(metric="block"):
    # {builder: {total: x, searcher: x}}
    atomic_map = analysis.load_dict_from_json(f"atomic/fifty/builder_atomic_maps/builder_atomic_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(f"atomic/fifty/agg/agg_{metric}.json")
    nonatomic_map = analysis.load_dict_from_json(f"nonatomic/fifty/builder_nonatomic_maps/builder_nonatomic_map_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(f"nonatomic/fifty/agg/agg_{metric}.json")
    
    atomic_map, atomic_agg = analysis.prune_known_entities_from_map_and_agg(atomic_map, atomic_agg)
    nonatomic_map, nonatomic_agg = analysis.prune_known_entities_from_map_and_agg(nonatomic_map, nonatomic_agg)
    
    atomic_agg = analysis.sort_agg(atomic_agg)
    atomic_map = analysis.sort_map(atomic_map)
    nonatomic_agg = analysis.sort_agg(nonatomic_agg)
    nonatomic_map = analysis.sort_map(nonatomic_map)

    combined_map, combined_agg = analysis.combine_atomic_nonatomic_block_map_and_agg(atomic_map, atomic_agg, nonatomic_map, nonatomic_agg)
    combined_agg = analysis.sort_agg(combined_agg)
    combined_map = analysis.sort_map(combined_map)

    return [atomic_map, atomic_agg, nonatomic_map, nonatomic_agg, combined_map, combined_agg]
    
def dump_data_used(all):
    # [block, tx, vol, bribe]
    for i in range(0, len(all)):
        if i == 0:
            type = "block"
        elif i == 1:
            type = "tx"
        elif i == 1:
            type = "vol"
        elif i == 2:
            type = "bribe"
        all_maps_and_aggs = all[i]

        # [atomic_map, atomic_agg, nonatomic_map, nonatomic_agg, combined_map, combined_agg]
        for j in range(0, len(all_maps_and_aggs), 2):
            map = all_maps_and_aggs[j]
            agg = all_maps_and_aggs[j+1]
            if j == 0:
                mev_domain = "atomic"
            elif j == 2:
                mev_domain = "nonatomic"
            elif j == 4:
                mev_domain = "combined"

            analysis.dump_dict_to_json(map, f"data/{type}/{mev_domain}_map_{type}.json")
            analysis.dump_dict_to_json(agg, f"data/{type}/{mev_domain}_agg_{type}.json")


def load_maps_and_aggs_from_dir(metric):
    path = f"data/{metric}/"
    atomic_map = analysis.load_dict_from_json(path + f"atomic_map_{metric}.json")
    nonatomic_map = analysis.load_dict_from_json(path + f"nonatomic_map_{metric}.json")
    combined_map = analysis.load_dict_from_json(path + f"combined_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(path + f"atomic_agg_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(path + f"nonatomic_agg_{metric}.json")
    combined_agg = analysis.load_dict_from_json(path + f"combined_agg_{metric}.json")

    return [atomic_map, atomic_agg, nonatomic_map, nonatomic_agg, combined_map, combined_agg]


if __name__ == "__main__":
    all_builders = list(analysis.load_dict_from_json("atomic/fifty/builder_atomic_maps/builder_atomic_map_block.json").keys())
    # all_maps_and_aggs_block = return_sorted_block_map_and_agg_pruned()    
    # all_maps_and_aggs_tx = return_sorted_map_and_agg_pruned_of_known_entities_and_atomc("tx")
    # all_maps_and_aggs_vol = return_sorted_map_and_agg_pruned_of_known_entities_and_atomc("vol")
    # all_maps_and_aggs_bribe = return_sorted_map_and_agg_pruned_of_known_entities_and_atomc("bribe")
    # dump_data_used([all_maps_and_aggs_block, all_maps_and_aggs_tx, all_maps_and_aggs_vol, all_maps_and_aggs_bribe])
    
    all_maps_and_aggs_block = load_maps_and_aggs_from_dir("block")    
    all_maps_and_aggs_tx = load_maps_and_aggs_from_dir("tx")
    all_maps_and_aggs_vol = load_maps_and_aggs_from_dir("vol")
    all_maps_and_aggs_bribe = load_maps_and_aggs_from_dir("bribe")

    builder_color_map = get_builder_colors_map(all_builders)

    atomic_notable_bar = create_notable_searcher_builder_percentage_bar_chart(all_maps_and_aggs_block[0], "block", "Atomic", builder_color_map)
    nonatomic_notable_bar = create_notable_searcher_builder_percentage_bar_chart(all_maps_and_aggs_block[2], "block", "Non-atomic", builder_color_map)

    atomic_bar_vol, nonatomic_bar_vol, combined_bar_vol = create_three_bar_charts_by_metric(all_maps_and_aggs_vol, builder_color_map, "vol", "USD")
    atomic_bar_tx, nonatomic_bar_tx, combined_bar_tx = create_three_bar_charts_by_metric(all_maps_and_aggs_tx, builder_color_map, "tx", "Transaction Count")
    atomic_bar_bribe, nonatomic_bar_bribe, combined_bar_bribe = create_three_bar_charts_by_metric(all_maps_and_aggs_bribe, builder_color_map,"bribe", "ETH")
        
    atomic_fig_vol, nonatomic_fig_vol, combined_fig_vol = create_three_sankeys_by_metric(all_maps_and_aggs_vol, builder_color_map, "vol", "USD", 0.95, 5000)
    atomic_fig_tx, nonatomic_fig_tx, combined_fig_tx = create_three_sankeys_by_metric(all_maps_and_aggs_tx, builder_color_map, "tx", "number of transactions", 0.95, 5)
    atomic_fig_bribe, nonatomic_fig_bribe, combined_fig_bribe = create_three_sankeys_by_metric(all_maps_and_aggs_bribe, builder_color_map, "bribe", "ETH", 0.95, 5)

    atomic_searcher_pie_tx = create_searcher_pie_chart(all_maps_and_aggs_tx[1], "Atomic Searchers", "Market Shares", "tx", "tx count")
    nonatomic_searcher_pie_tx = create_searcher_pie_chart(all_maps_and_aggs_tx[3], "Noatomic Searchers", "Market Shares", "tx", "tx count")
    combined_searcher_pie_tx = create_searcher_pie_chart(all_maps_and_aggs_tx[5], "Combined Searchers Market Shares", "", "tx", "tx count", True)
    
    title = "# <p style='text-align: center;margin:0px;'> Searcher Builder Activity Dashboard </p>"
    head = ("<div><div><div style ='float:left;color:#0F1419;font-size:18px'>Analysis based on txs from 7/1 to 8/20</div>" 
                +'<div style ="float:right;font-size:18px;color:#0F1419">View <a href="https://github.com/winnsterx/searcher_database/tree/main/data">raw data</a> </div></div>'
                +'<div><div style ="float:left;font-size:18px;color:#0F1419;clear: left">Built by '
                +'<a href="https://twitter.com/winnsterx">winnsterx</a> & inspired by '
                +'<a href="https://mevboost.pics">mevboost.pics</a> by <a href="https://twitter.com/nero_eth">Toni Wahrstätter</a></div>'
                +'<div style ="float:right;font-size:18px;color:#0F1419">View Source on <a href="https://github.com/winnsterx/searcher_database">Github</a></div></div></div>'
                +"\n")

    view = dp.Blocks(
        dp.Page(title="Highlights", blocks=[
            title, 
            head, 
            atomic_notable_bar,
            nonatomic_notable_bar, 
            atomic_bar_tx, nonatomic_bar_tx, combined_bar_tx,
            dp.Group(
                atomic_searcher_pie_tx,
                nonatomic_searcher_pie_tx,
                columns=2
            ),
            combined_searcher_pie_tx,
            atomic_fig_tx,
            # nonatomic_fig_vol,
            # combined_fig_bribe
        ]),
        dp.Page(title="Volume", blocks=[
            title, 
            head, 
            atomic_bar_vol, nonatomic_bar_vol, combined_bar_vol,
            # atomic_fig_vol,
            nonatomic_fig_vol, 
            # combined_fig_vol,
        ]),
        dp.Page(title="Transaction Count", blocks=[
            title, 
            head, 
            atomic_bar_tx, nonatomic_bar_tx, combined_bar_tx,
            atomic_fig_tx,
            # nonatomic_fig_tx,
            # combined_fig_tx
        ]),
        dp.Page(title="Bribes", blocks=[
            title, 
            head, 
            atomic_bar_bribe, nonatomic_bar_bribe, combined_bar_bribe,
            # atomic_fig_bribe,
            # nonatomic_fig_bribe,
            combined_fig_bribe,
        ])
    )
    dp.save_report(view, path=secret_keys.HTML_PATH+"/index.html")

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

    with open(secret_keys.HTML_PATH+"/index.html", "r") as file:
        f = file.read()
    OG_STUFF = ' <title>searcherbuilder.pics | Searcher Builder Dashboard</title>\n<meta charset="UTF-8" />\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:site" content="@winnsterx">\n<meta name="twitter:title" content="Searcher Builder Dashboard">\n<meta name="twitter:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum.">\n<meta name="twitter:image" content="https://www.searcherbuilder.pics/">\n<meta property="og:title" content=Searcher Builder Dashboard>\n<meta property="og:site_name" content=searcherbuilder.pics>\n<meta property="og:url" content=searcherbuilder.pics>\n<meta property="og:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum." >\n<meta property="og:type" content=website>\n<link rel="shortcut icon" href="https://mevboost.toniwahrstaetter.com/ethlogo.png" />\n<meta property="og:image" content=https://mevboost.toniwahrstaetter.com/pv.png>\n<meta name="description" content="Up-to-date comparative visualizations on MEV-Boost and Proposer Builder Separation on Ethereum.">\n<meta name="keywords" content="Ethereum, MEV-Boost, PBS, Dashboard">\n <meta name="author" content="Toni Wahrstätter">'
    f = f.replace('<meta charset="UTF-8" />\n', fixedposi+ OG_STUFF+more_css) # + GA
    with open(secret_keys.HTML_PATH+"/index.html", "w") as file:
        file.write(f)