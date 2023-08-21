import datapane as dp
import plotly.graph_objects as go
from datetime import datetime
import analysis 
import visual_analysis

def abbreviate_label(label):
    if label.startswith("0x"):
        return label[:9] + '...' if len(label) > 10 else label
    else: 
        return label


def create_searcher_builder_sankey(map, agg, title, unit):
    # nodes is index of searcher + builder, each unique
    # an entity will now be recognized as the index from this list now
    span = '<span style="font-size: 24px;font-weight:bold;">{}</span>'     
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
        node = dict(
            x = x_coors,
            y = y_coors,
            pad = 20,
            thickness = 20,
            line = dict(color = "black", width = 0.5),      
            label = abbreviated_nodes,  
            hovertemplate='<b>%{label}<b><br />%{value}'+unit,
        ),
        link = dict(
            source = source_indices,
            target = target_indices,
            value = values,            
            hovertemplate='<b>%{source.value:,.0f} <br /><b>'+unit,  
        )
    ))

    fig.update_layout(title_text=span.format(title),
                      font_size=16,
                      paper_bgcolor='#eee',
                      font=dict(
                                family="Courier New, monospace",
                                size=20,  # Set the font size here
                                color="black"
                               ), autosize=False, width=800, height=1500)
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
    return map, agg


def create_three_sankeys_by_metric(metric, unit, percentile, min_count):
    nonatomic_map = analysis.load_dict_from_json(f"nonatomic/new/builder_swapper_maps/builder_swapper_map_{metric}.json")
    nonatomic_agg = analysis.load_dict_from_json(f"nonatomic/new/agg/agg_{metric}.json")
    atomic_map = analysis.load_dict_from_json(f"atomic/new/builder_atomic_maps/builder_atomic_map_{metric}.json")
    atomic_agg = analysis.load_dict_from_json(f"atomic/new/agg/agg_{metric}.json")
    combined_map, combined_agg = analysis.combine_atomic_nonatomic_map_and_agg(atomic_map, atomic_agg, nonatomic_map, nonatomic_agg)
    analysis.dump_dict_to_json(combined_map, "combined_bribe_map.json")
    analysis.dump_dict_to_json(combined_agg, "combined_bribe_agg.json")
    atomic_map, atomic_agg = prune_map_and_agg_for_sankey(atomic_map, atomic_agg, metric, percentile, min_count, "atomic")
    atomic_map = analysis.sort_map(atomic_map)
    atomic_fig = create_searcher_builder_sankey(atomic_map, atomic_agg, f"Atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit}, last month)", unit)

    nonatomic_map, nonatomic_agg = prune_map_and_agg_for_sankey(nonatomic_map, nonatomic_agg, metric, percentile, min_count, "nonatomic")
    nonatomic_map = analysis.sort_map(nonatomic_map)
    nonatomic_fig = create_searcher_builder_sankey(nonatomic_map, nonatomic_agg, f"Non-atomic Searcher-Builder Orderflow by {metric.capitalize()} ({unit}, last month)", unit)

    combined_map, combined_agg = prune_map_and_agg_for_sankey(combined_map, combined_agg, metric, 0.9, 5, "combined")
    combined_map = analysis.sort_map(combined_map)
    combined_fig = create_searcher_builder_sankey(combined_map, combined_agg, f"Combined Searcher-Builder Orderflow by {metric.capitalize()} ({unit}, last month)", unit)

    return atomic_fig, nonatomic_fig, combined_fig

if __name__ == "__main__":
    atomic_fig_vol, nonatomic_fig_vol, combined_fig_vol = create_three_sankeys_by_metric("vol", "USD", 0.9, 1000)
    atomic_fig_tx, nonatomic_fig_tx, combined_fig_tx = create_three_sankeys_by_metric("tx", "tx count", 0.9, 5)
    atomic_fig_bribe, nonatomic_fig_bribe, combined_fig_bribe = create_three_sankeys_by_metric("bribe", "ETH", 0.9, 5)

    title = "# <p style='text-align: center;margin:0px;'> __Searcher Builder Activity Dashboard__ </p>"
    head =  '<div><div style ="float:left;font-size:18px;color:#0F1419;clear: left">Built by '\
            +'<a href="https://twitter.com/winnsterx">winnsterx</a></div>'\
            +'<div style ="float:right;font-size:18px;color:#0F1419">View Source on Github'\
            +'<a href="https://github.com/winnsterx/searcher_database>Github</a></div></div>'
    
    # atomic_fig.show()
    view = dp.Blocks(
        dp.Page(title="Highlights", blocks=[
            title, 
            head, 
        ]),
        dp.Page(title="Volume", blocks=[
            title, 
            head, 
            atomic_fig_vol,
            nonatomic_fig_vol, 
            combined_fig_vol
        ]),
        dp.Page(title="Number of Txs", blocks=[
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

        nav {
            position: sticky;
            top: 0;
            z-index: 99999;
            background-color: white;
            display: flex;
            margin-bottom: 1.5rem;
        }
                
        </style>
    '''

    with open("/Users/winniex/Documents/GitHub/winnsterx.github.io/index.html", "r") as file:
        f = file.read()
    OG_STUFF = ' <title>searcherbuilder.pics | Searcher Builder Dashboard</title>\n<meta charset="UTF-8" />\n<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:site" content="@winnsterx">\n<meta name="twitter:title" content="Searcher Builder Dashboard">\n<meta name="twitter:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum.">\n<meta name="twitter:image" content="https://www.searcherbuilder.pics/">\n<meta property="og:title" content=Searcher Builder Dashboard>\n<meta property="og:site_name" content=searcherbuilder.pics>\n<meta property="og:url" content=searcherbuilder.pics>\n<meta property="og:description" content="Selected comparative visualizations on searcher-builder relationship on Ethereum." >\n<meta property="og:type" content=website>\n<link rel="shortcut icon" href="https://mevboost.toniwahrstaetter.com/ethlogo.png" />\n<meta property="og:image" content=https://mevboost.toniwahrstaetter.com/pv.png>\n<meta name="description" content="Up-to-date comparative visualizations on MEV-Boost and Proposer Builder Separation on Ethereum.">\n<meta name="keywords" content="Ethereum, MEV-Boost, PBS, Dashboard">\n <meta name="author" content="Toni Wahrstätter">'
    f = f.replace('<meta charset="UTF-8" />\n', fixedposi+ OG_STUFF+more_css) # + GA
    with open("/Users/winniex/Documents/GitHub/winnsterx.github.io/index.html", "w") as file:
        file.write(f)