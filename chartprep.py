import datapane as dp
import statistics
import random
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import math
import analysis

from collections import defaultdict
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import colorcet as cc
import secret_keys
import searcher_addr_map, builder_addr_map


def abbreviate_label(label, short=False):
    res = ""
    if label.startswith("0x"):
        if label in searcher_addr_map.SEARCHER_ADDR_LABEL_MAP:
            res = searcher_addr_map.SEARCHER_ADDR_LABEL_MAP[label]
            if short == False:
                res += " (" + label[:9] + ")"
            return res
        elif label in builder_addr_map.BUILDER_ADDR_MAP:
            res = builder_addr_map.BUILDER_ADDR_MAP[label]
            if short == False:
                res += " (" + label[:9] + ")"
            return res
        else:
            return label[:15] + "..."
    else:
        return label


def convert_metric_for_title(metric):
    if metric == "tx":
        return "Transaction Count"
    elif metric == "vol":
        return "Volume (ETH)"
    elif metric == "bribe":
        return "Bribes (Coinbase Transfers + Priority Fees, in ETH)"
    elif metric == "block":
        return "Block Count"


def get_builder_colors_map(list_of_builders):
    colors = sns.color_palette(cc.glasbey_hv, len(list_of_builders))
    # random.shuffle(colors)
    builder_color_map = {
        builder: "rgb" + str(color) for builder, color in zip(list_of_builders, colors)
    }
    return builder_color_map


def create_searcher_builder_sankey(map, agg, builder_color_map, title, unit, date):
    # nodes is index of searcher + builder, each unique
    # an entity will now be recognized as the index from this list now
    span = '<span style="font-size: 20px;font-weight:bold; margin-bottom: 10px;">{}<br /><span style="font-size: 15px">({} from {} to {})</span></span>'

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

    fig = go.Figure(
        data=go.Sankey(
            arrangement="snap",
            textfont=go.sankey.Textfont(size=16, color="black", family="Courier New"),
            node=dict(
                x=x_coors,
                y=y_coors,
                pad=20,
                thickness=20,
                line=dict(color="black", width=0.5),
                label=abbreviated_nodes,
                hovertemplate="<b>%{label}<b><br />%{value} " + unit,
            ),
            link=dict(
                source=source_indices,
                target=target_indices,
                value=values,
                hovertemplate="<b>total: %{source.value:,.0f} <br /><b>" + unit,
            ),
        )
    )

    tx_mev_types = "arbitrage, sandwich, and liquidation txs"
    if "non-atomic" in title.lower():
        tx_mev_types = "cefi-defi arbitrage txs"
    elif "combined" in title.lower():
        tx_mev_types = "all atomic and non-atomic MEV txs"

    fig.update_layout(
        title_text=span.format(title, tx_mev_types, date[0], date[1]),
        font_size=16,
        #   paper_bgcolor='#eee',
        font=dict(
            family="Courier New, monospace",
            # size=20,  # Set the font size here
            color="black",
        ),
        autosize=True,
        width=800,
        height=1200,
        margin=dict(t=100, b=100, l=50, r=50),
    )
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


def create_notable_searcher_builder_percentage_bar_chart(
    map, metric, mev_domain, builder_color_map
):
    fig = go.Figure()
    (
        notable,
        builder_market_share,
        highlight_relationship,
    ) = analysis.find_notable_searcher_builder_relationships(map)

    # builder_num = len(builder_market_share.keys())
    # for builder, share in builder_market_share.items():
    #     builder_market_share[builder] = 100 / builder_num

    span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">Disproportionate Orderflow Relationships<br /><span style="font-size: 15px;">Filtering out relationships in which a searcher sent a disproportionate<br /> amount of orderflow to a builder, ranked by {}</span></span>'

    for builder, searchers in map.items():
        # Separate data for highlighted and non-highlighted bars
        x_highlighted = []
        y_highlighted = []
        x_regular = []
        y_regular = []
        customdata_highlighted = []
        customdata_regular = []
        unit = "ETH" if metric != "tx" else "txs"

        for searcher, builders_percent in notable.items():
            if (
                searcher,
                builder,
            ) in highlight_relationship:
                y_highlighted.append(searcher)
                x_highlighted.append(builders_percent.get(builder, 0))
                customdata_highlighted.append(
                    (
                        builder,
                        analysis.humanize_number(searchers.get(searcher, 0)),
                        metric,
                    )
                )
            else:
                y_regular.append(searcher)
                x_regular.append(builders_percent.get(builder, 0))
                customdata_regular.append(
                    (
                        builder,
                        analysis.humanize_number(searchers.get(searcher, 0)),
                        metric,
                    )
                )

        y_highlighted.insert(0, "All Searchers")
        x_highlighted.insert(0, builder_market_share[builder])
        customdata_highlighted.insert(
            0,
            (builder, analysis.humanize_number(sum(searchers.values())), metric),
        )
        # Trace for non-highlighted bars
        fig.add_trace(
            go.Bar(
                y=[abbreviate_label(s, True) for s in y_regular[::-1]],
                x=x_regular[::-1],
                name=abbreviate_label(builder, True),
                orientation="h",
                customdata=customdata_regular[::-1],  # Your additional hover info
                hovertemplate=(
                    "<b>Searcher:</b> %{y}<br>"
                    "<b>Builder:</b> %{customdata[0]}<br>"
                    "<b>Total %{customdata[2]} sent to builder:</b> %{customdata[1]} ETH<br>"
                    "<b>Percentage:</b> %{x:.2r}%<extra></extra>"
                ),
                marker=dict(color="lightgray", line=dict(width=1)),
                showlegend=False,  # Don't show this in legend
                legendgroup=builder,  # Use same legendgroup identifier as before
            )
        )

        # Trace for highlighted bars
        fig.add_trace(
            go.Bar(
                y=[abbreviate_label(s, True) for s in y_highlighted[::-1]],
                x=x_highlighted[::-1],
                text=[
                    str(data[1]) + " " + unit for data in customdata_highlighted[::-1]
                ],
                textposition="auto",
                customdata=customdata_highlighted[::-1],  # Your additional hover info
                hovertemplate=(
                    "<b>Searcher:</b> %{y}<br>"
                    "<b>Builder:</b> %{customdata[0]}<br>"
                    "<b>Total %{customdata[2]} sent to builder:</b> %{customdata[1]} ETH<br>"
                    "<b>Percentage:</b> %{x:.2r}%<extra></extra>"
                ),
                name=abbreviate_label(builder, True),
                orientation="h",
                marker=dict(color=builder_color_map[builder], line=dict(width=1)),
                legendgroup=builder,
            )
        )

    title_layout = {
        "text": span.format(convert_metric_for_title(metric).lower()),
        "y": 0.9,
        "x": 0.5,
        "xanchor": "center",
        "yanchor": "top",
    }

    fig.update_layout(
        title=title_layout,
        xaxis_title=generate_xaxis_title(metric),
        yaxis_title="",
        xaxis_range=[0, 100],
        barmode="stack",
        legend={"traceorder": "normal"},
        margin={"t": 150},  # what gives the spacing between title and plot
        font=dict(family="Courier New, monospace", color="black"),
        autosize=False,
        height=700,
    )

    return fig


def create_searcher_builder_percentage_bar_chart(
    map, agg, builder_color_map, mev_domain, metric
):
    fig = go.Figure()
    top_searchers = analysis.slice_dict(agg, 20)
    builder_market_share = {}

    span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{} Searchers Orderflow Breakdown by Builder<br /><span style="font-size: 15px;">Ranked by {}</span></span>'

    for builder, searchers in map.items():
        builder_market_share[builder] = sum(searchers.values())

    total_count = sum(builder_market_share.values())
    unit = "ETH" if metric != "tx" else "txs"
    for builder, searchers in map.items():
        x = []
        y = [abbreviate_label(s, True) for s in list(top_searchers.keys())]
        customdata = []
        # adding total market share as comparison
        y.insert(0, "All Searchers")
        x.insert(0, builder_market_share[builder] / total_count * 100)
        customdata.insert(
            0,
            (builder, analysis.humanize_number(builder_market_share[builder]), metric),
        )

        for searcher, _ in top_searchers.items():
            percent = searchers.get(searcher, 0) / agg[searcher] * 100
            x.append(percent)
            customdata.append(
                (builder, analysis.humanize_number(searchers.get(searcher, 0)), metric)
            )

        fig.add_trace(
            go.Bar(
                y=y[::-1],
                x=x[::-1],
                name=abbreviate_label(builder, True),
                text=[str(data[1]) + " " + unit for data in customdata[::-1]],
                textposition="auto",
                orientation="h",
                customdata=customdata[::-1],  # Your additional hover info
                hovertemplate=(
                    "<b>Searcher:</b> %{y}<br>"
                    "<b>Builder:</b> %{customdata[0]}<br>"
                    "<b>Total %{customdata[2]} sent to builder:</b> %{customdata[1]} ETH<br>"
                    "<b>Percentage:</b> %{x:.2r}%<extra></extra>"
                ),
                marker=dict(color=builder_color_map[builder], line=dict(width=1)),
            )
        )

    title_layout = {
        "text": span.format(
            mev_domain,
            convert_metric_for_title(metric)
            if metric != "bribe"
            else "Bribes (Coinbase Transfers + Priority Fees, in ETH)",
        ),
        "y": 0.9,
        "x": 0.05,
        "xanchor": "left",
        "yanchor": "top",
    }

    fig.update_layout(
        title=title_layout,
        xaxis_title=generate_xaxis_title(metric),
        yaxis_title="",
        xaxis_range=[0, 100],
        barmode="stack",
        legend={"traceorder": "normal"},
        margin={"t": 120},  # what gives the spacing between title and plot
        font=dict(family="Courier New, monospace", color="black"),
        height=700,
    )

    return fig


def create_searcher_pie_chart(
    agg, searcher_color_map, title_1, title_2, metric, legend=False
):
    if len(title_2) > 1:  # if not combined
        span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{}<br />{}<br /><span style="font-size: 15px;">By {}</span></span>'
        title_layout = {
            "text": span.format(title_1, title_2, convert_metric_for_title(metric)),
            "y": 0.9,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        }
    else:
        span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{}<br /><span style="font-size: 15px;">By {}</span></span>'
        title_layout = {
            "text": span.format(title_1, convert_metric_for_title(metric)),
            "y": 0.9,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        }
        legend = True

    small_searchers = {k: agg[k] for k in list(agg.keys())[25:]}
    agg = {k: agg[k] for k in list(agg)[:25]}
    agg.update({"Others": sum(small_searchers.values())})

    searchers = [abbreviate_label(s) for s in list(agg.keys())]
    counts = list(agg.values())
    unit = "ETH" if metric != "tx" else "txs"
    fig = go.Figure(
        data=go.Pie(
            labels=searchers,
            values=counts,
            hole=0.3,  # Optional: to create a donut-like chart
            hovertemplate=(
                f"<b>Searcher:</b> %{{label}}<br>"
                f"<b>Value:</b> %{{value}} {unit}<br>"
                "<b>Percentage:</b> %{percent}<extra></extra>"
            ),
            textposition="inside",
            textinfo="percent",
        )
    )

    # Setting layout details
    fig.update_layout(
        title=title_layout,
        showlegend=legend,
        font=dict(family="Courier New, monospace", color="black"),
        height=550,
    )
    return fig


def return_map_vol_list_pruned_of_known_entities_and_atomic(metric, atomic_agg):
    atomic_map = analysis.load_dict_from_json(
        f"atomic/fourteen/builder_atomic_maps/builder_atomic_map_{metric}.json"
    )
    nonatomic_map = analysis.load_dict_from_json(
        f"nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_{metric}.json"
    )
    atomic_map = analysis.prune_known_entities_from_simple_map(atomic_map)
    # atomic_searchers = list(
    #     set(searcher for builder in atomic_map.values() for searcher in builder.keys())
    # )
    nonatomic_map = analysis.prune_known_entities_from_simple_map(nonatomic_map)
    nonatomic_map = analysis.remove_atomic_from_map(nonatomic_map, atomic_agg)

    return [atomic_map, {}, nonatomic_map, {}]


def return_sorted_map_and_agg_pruned_of_known_entities_and_atomc(metric):
    """
    Returns atomic, nonatomic, and combined maps and aggs that are
    sorted, pruned of known entities, (for nonatomic, remove atomic addrs),
    and trimmed of only addrs responsible for 99% of {metric}
    """
    atomic_map = analysis.load_dict_from_json(
        f"atomic/fourteen/builder_atomic_maps/builder_atomic_map_{metric}.json"
    )

    atomic_agg = analysis.load_dict_from_json(f"atomic/fourteen/agg/agg_{metric}.json")

    nonatomic_map = analysis.load_dict_from_json(
        f"nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_{metric}.json"
    )
    nonatomic_agg = analysis.load_dict_from_json(
        f"nonatomic/fourteen/agg/agg_{metric}.json"
    )

    # before, atomic_map is {total, arb,...}. after this, atomic is simple
    atomic_map = analysis.return_atomic_maps_with_only_type(atomic_map, "total")

    atomic_map, atomic_agg = analysis.prune_known_entities_from_map_and_agg(
        atomic_map, atomic_agg
    )

    atomic_map, atomic_agg = analysis.get_map_and_agg_in_range(
        atomic_map, atomic_agg, 0.99
    )
    # sort after pruning the known entities
    atomic_agg = analysis.sort_agg(atomic_agg)
    atomic_map = analysis.sort_map(atomic_map)

    nonatomic_map, nonatomic_agg = analysis.prune_known_entities_from_map_and_agg(
        nonatomic_map, nonatomic_agg
    )
    nonatomic_map, nonatomic_agg = analysis.remove_atomic_from_map_and_agg(
        nonatomic_map, nonatomic_agg, atomic_agg
    )
    nonatomic_map, nonatomic_agg = analysis.get_map_and_agg_in_range(
        nonatomic_map, nonatomic_agg, 0.99
    )

    nonatomic_agg = analysis.sort_agg(nonatomic_agg)
    nonatomic_map = analysis.sort_map(nonatomic_map)

    return [
        atomic_map,
        atomic_agg,
        nonatomic_map,
        nonatomic_agg,
    ]


def return_sorted_block_map_and_agg_pruned(metric="block"):
    # {builder: {total: x, searcher: x}}
    atomic_map = analysis.load_dict_from_json(
        f"atomic/fourteen/builder_atomic_maps/builder_atomic_map_{metric}.json"
    )
    atomic_agg = analysis.load_dict_from_json(f"atomic/fourteen/agg/agg_{metric}.json")
    nonatomic_map = analysis.load_dict_from_json(
        f"nonatomic/fourteen/builder_nonatomic_maps/builder_nonatomic_map_{metric}.json"
    )
    nonatomic_agg = analysis.load_dict_from_json(
        f"nonatomic/fourteen/agg/agg_{metric}.json"
    )

    atomic_map, atomic_agg = analysis.prune_known_entities_from_map_and_agg(
        atomic_map, atomic_agg
    )
    nonatomic_map, nonatomic_agg = analysis.prune_known_entities_from_map_and_agg(
        nonatomic_map, nonatomic_agg
    )

    atomic_agg = analysis.sort_agg(atomic_agg)
    atomic_map = analysis.sort_map(atomic_map)
    nonatomic_agg = analysis.sort_agg(nonatomic_agg)
    nonatomic_map = analysis.sort_map(nonatomic_map)

    # combined_map, combined_agg = analysis.combine_atomic_nonatomic_block_map_and_agg(
    #     atomic_map, atomic_agg, nonatomic_map, nonatomic_agg
    # )
    # combined_agg = analysis.sort_agg(combined_agg)
    # combined_map = analysis.sort_map(combined_map)

    return [
        atomic_map,
        atomic_agg,
        nonatomic_map,
        nonatomic_agg,
        # combined_map,
        # combined_agg,
    ]


def dump_data_used(all):
    # [block, tx, vol, bribe, vol_list]
    for i in range(0, len(all)):
        if i == 0:
            type = "block"
        elif i == 1:
            type = "tx"
        elif i == 2:
            type = "vol"
        elif i == 3:
            type = "bribe"
        elif i == 4:
            type = "vol_list"
        all_maps_and_aggs = all[i]

        # [atomic_map, atomic_agg, nonatomic_map, nonatomic_agg, combined_map, combined_agg]
        for j in range(0, len(all_maps_and_aggs), 2):
            map = all_maps_and_aggs[j]
            agg = all_maps_and_aggs[j + 1]
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

    atomic_agg = analysis.load_dict_from_json(path + f"atomic_agg_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(path + f"nonatomic_agg_{metric}.json")

    return [
        atomic_map,
        atomic_agg,
        nonatomic_map,
        nonatomic_agg,
    ]


def add_dummy_traces_to_match(fig, target_num_traces):
    """Add dummy invisible traces to fig to match target_num_traces."""
    while len(fig.data) < target_num_traces:
        fig.add_trace(go.Bar(x=[], y=[], visible=False))
    return fig


def generate_title(metric, mev_domain):
    span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{} Searchers Orderflow Breakdown by Builder<br /><span style="font-size: 15px;">Ranked by {}</span></span>'
    title = span.format(mev_domain, convert_metric_for_title(metric))
    return title


def generate_xaxis_title(metric):
    if metric == "vol":
        return "Percentage of Volume"
    elif metric == "bribe":
        return "Percentage of Total Bribes"
    elif metric == "tx":
        return "Percentage of Transactions"


def create_toggle(fig_prime, fig_bribe, metric, mev_domain):
    # Combine the figures. Set the second one as invisible initially.
    # Determine the max number of traces
    max_traces = max(len(fig_prime.data), len(fig_bribe.data))

    span = '<span style="font-size: 1.4rem;font-weight:bold; margin-bottom: 10px;">{} Searchers Orderflow Breakdown by Builder<br /><span style="font-size: 15px;">Ranked by {}</span></span>'

    # Add dummy traces as necessary to match the number of traces
    fig_prime = add_dummy_traces_to_match(fig_prime, max_traces)
    fig_bribe = add_dummy_traces_to_match(fig_bribe, max_traces)

    # Combine and set the toggle logic
    combined_fig = fig_prime
    for trace in fig_bribe.data:
        trace.visible = False
        combined_fig.add_trace(trace)

    combined_fig.update_layout(
        updatemenus=[
            {
                "type": "dropdown",
                "direction": "down",
                "active": 0,
                "showactive": True,
                "x": 1.48,
                "y": 1.08,
                "xanchor": "right",
                "yanchor": "bottom",
                "buttons": [
                    {
                        "label": convert_metric_for_title(metric),
                        "method": "update",
                        "args": [
                            {"visible": [True] * max_traces + [False] * max_traces},
                            {
                                "title": {
                                    "text": generate_title(metric, mev_domain),
                                    "y": 0.9,
                                    "x": 0.05,
                                    "xanchor": "left",
                                    "yanchor": "top",
                                },
                                "xaxis.title.text": generate_xaxis_title(metric),
                            },
                        ],
                    },
                    {
                        "label": "Bribes (ETH)",
                        "method": "update",
                        "args": [
                            {"visible": [False] * max_traces + [True] * max_traces},
                            {
                                "title": {
                                    "text": generate_title(
                                        "bribe", mev_domain
                                    )  # Assuming a different metric name for bribes
                                },
                                "xaxis.title.text": generate_xaxis_title("bribe"),
                            },
                        ],
                    },
                ],
            }
        ]
    )
    return combined_fig


def create_html_page():
    all_builders_keys = list(
        analysis.load_dict_from_json(
            "atomic/fourteen/builder_atomic_maps/builder_atomic_map_block.json"
        ).keys()
    )
    builder_color_map = get_builder_colors_map(all_builders_keys)

    all_maps_and_aggs_block = return_sorted_block_map_and_agg_pruned()
    all_maps_and_aggs_tx = return_sorted_map_and_agg_pruned_of_known_entities_and_atomc(
        "tx"
    )
    all_maps_and_aggs_vol = (
        return_sorted_map_and_agg_pruned_of_known_entities_and_atomc("vol")
    )

    all_maps_and_aggs_bribe = (
        return_sorted_map_and_agg_pruned_of_known_entities_and_atomc("bribe")
    )
    all_maps_and_aggs_vol_list = (
        return_map_vol_list_pruned_of_known_entities_and_atomic(
            "vol_list", all_maps_and_aggs_vol[1]
        )
    )

    dump_data_used(
        [
            all_maps_and_aggs_block,
            all_maps_and_aggs_tx,
            all_maps_and_aggs_vol,
            all_maps_and_aggs_bribe,
            all_maps_and_aggs_vol_list,
        ]
    )

    # all_maps_and_aggs_tx = load_maps_and_aggs_from_dir("tx")
    # all_maps_and_aggs_vol = load_maps_and_aggs_from_dir("vol")
    # all_maps_and_aggs_bribe = load_maps_and_aggs_from_dir("bribe")
    # all_maps_and_aggs_vol_list = load_maps_and_aggs_from_dir("vol_list")

    nonatomic_notable_bar = create_notable_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_vol[2], "vol", "Non-atomic", builder_color_map
    )

    atomic_notable_bar = create_notable_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_tx[0], "tx", "Atomic", builder_color_map
    )

    nonatomic_vol_bar = create_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_vol[2],
        all_maps_and_aggs_vol[3],
        builder_color_map,
        "Non-atomic",
        "vol",
    )

    nonatomic_bribe_bar = create_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_bribe[2],
        all_maps_and_aggs_bribe[3],
        builder_color_map,
        "Non-atomic",
        "bribe",
    )

    nonatomic_bar = create_toggle(
        nonatomic_vol_bar, nonatomic_bribe_bar, "vol", "Non-atomic"
    )

    atomic_tx_bar = create_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_tx[0],
        all_maps_and_aggs_tx[1],
        builder_color_map,
        "Atomic",
        "tx",
    )

    atomic_bribe_bar = create_searcher_builder_percentage_bar_chart(
        all_maps_and_aggs_bribe[0],
        all_maps_and_aggs_bribe[1],
        builder_color_map,
        "Atomic",
        "bribe",
    )
    atomic_bar = create_toggle(atomic_tx_bar, atomic_bribe_bar, "tx", "Atomic")

    atomic_searcher_pie_tx = create_searcher_pie_chart(
        all_maps_and_aggs_tx[1],
        builder_color_map,
        "Atomic Searchers Market Shares",
        "",
        "tx",
    )

    nonatomic_searcher_pie_vol = create_searcher_pie_chart(
        all_maps_and_aggs_vol[3],
        builder_color_map,
        "Non-atomic Searchers Market Shares",
        "",
        "vol",
    )

    title = "# <p style='text-align: center;margin:0px;'> Searcher-Builder Relationship Dashboard </p>"
    head = (
        "<div><div><div style ='float:left;color:#0F1419;font-size:18px'>Based on transactions from last 14 days. Last updated {}.</div>"
        + '<div style ="float:right;font-size:18px;color:#0F1419">View <a href="https://github.com/winnsterx/searcher_database/tree/main/data">raw data</a> </div></div>'
        + '<div><div style ="float:left;font-size:18px;color:#0F1419;clear: left">Built by '
        + '<a href="https://twitter.com/winnsterx">winnsterx</a> at <a href="https://twitter.com/BitwiseInvest">Bitwise</a>. Inspired by '
        + '<a href="https://mevboost.pics">mevboost.pics</a>.</div>'
        + '<div style ="float:right;font-size:18px;color:#0F1419">View Source on <a href="https://github.com/winnsterx/searcher_database">Github</a></div></div></div>'
        + "\n"
    )
    head = head.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    view = dp.Blocks(
        dp.Page(
            title="Non-atomic MEV",
            blocks=[
                title,
                head,
                nonatomic_bar,
                nonatomic_notable_bar,
                nonatomic_searcher_pie_vol,
            ],
        ),
        dp.Page(
            title="Atomic MEV",
            blocks=[
                title,
                head,
                atomic_bar,
                atomic_notable_bar,
                atomic_searcher_pie_tx,
            ],
        ),
    )
    dp.save_report(view, path=secret_keys.HTML_PATH + "/index.html")

    fixedposi = (
        "<style>nav.min-h-screen {position: -webkit-sticky;position: sticky;}</style>"
    )

    more_css = """
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
    """

    with open(secret_keys.HTML_PATH + "/index.html", "r") as file:
        f = file.read()
    OG_STUFF = ' <title>searcherbuilder.pics | Searcher Builder Dashboard</title>\n<meta charset="UTF-8" />\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:site" content="@winnsterx">\n<meta name="twitter:title" content="Searcher Builder Dashboard">\n<meta name="twitter:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum.">\n<meta name="twitter:image" content="https://www.searcherbuilder.pics/">\n<meta property="og:title" content=Searcher Builder Dashboard>\n<meta property="og:site_name" content=searcherbuilder.pics>\n<meta property="og:url" content=searcherbuilder.pics>\n<meta property="og:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum." >\n<meta property="og:type" content=website>\n<link rel="shortcut icon" href="https://mevboost.toniwahrstaetter.com/ethlogo.png" />\n<meta property="og:image" content=https://mevboost.toniwahrstaetter.com/pv.png>\n<meta name="description" content="Up-to-date comparative visualizations on MEV-Boost and Proposer Builder Separation on Ethereum.">\n<meta name="keywords" content="Ethereum, MEV-Boost, PBS, Dashboard">\n <meta name="author" content="Toni Wahrstätter">'
    f = f.replace('<meta charset="UTF-8" />\n', fixedposi + OG_STUFF + more_css)  # + GA
    with open(secret_keys.HTML_PATH + "/index.html", "w") as file:
        file.write(f)


if __name__ == "__main__":
    create_html_page()
