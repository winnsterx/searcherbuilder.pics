import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import analysis

def abbreviate_address(address):
    # For simplicity, this example takes the first 5 characters. Adjust as needed.
    return address[:5] + '...'

# bottom and top are dicts = {"addr": tx_count}
def overlap_searcher_frequency_maps(bottom, top):
    df_A = pd.DataFrame(list(bottom.items()), columns=['Address', 'Tx_count_A'])
    df_B = pd.DataFrame(list(top.items()), columns=['Address', 'Tx_count_B'])

    # Merge on Address
    merged = df_A.merge(df_B, on="Address", how="left").fillna(0)

    merged['Short_Address'] = merged['Address'].apply(abbreviate_address)

    # Plot
    fig, ax = plt.subplots()

    merged.plot(x="Short_Address", y="Tx_count_A", kind="bar", ax=ax, color="blue", position=1, width=0.4)
    merged.plot(x="Short_Address", y="Tx_count_B", kind="bar", ax=ax, color="red", position=0, width=0.4)

    ax.set_ylabel("Tx_count")
    ax.set_title("Overlapping Datasets")
    plt.xticks(rotation=45)  # Rotating x-axis labels for better visualization
    plt.tight_layout()

    plt.show(block=False)


def create_a_flow(map, agg, searcher=None):
    if searcher is None:
        nodes = list(agg.keys()) + list(map.keys())
    else: 
        nodes = list(searcher) + list(map.keys())

    source_indices = []
    target_indices = []
    values = []

    for builder, searchers in map.items():
        for s, tx_count in searchers.items():
            if searcher is None or s == searcher:
                if s not in nodes: 
                    continue
                source_indices.append(nodes.index(s))
                target_indices.append(nodes.index(builder))
                values.append(tx_count)

    return go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=nodes),
        link=dict(source=source_indices, target=target_indices, value=values)
    )


def searcher_builder_orderflow(map, agg, title):
    # Create a figure with a dropdown menu
    fig = make_subplots(specs=[[{'type': 'sankey'}]])
    fig.add_trace(create_a_flow(map, agg))
    fig.update_layout(title_text=title, font_size=10)
    fig.show()


    # Create a dropdown menu with all the searchers and an option for all searchers
    # menu_buttons = [dict(args=[{"data": [create_a_flow(map, agg)]}], label='All searchers', method='update')]
    # for searcher in agg:
    #     menu_buttons.append(
    #         dict(
    #             args=[{"data": [create_a_flow(map, agg, searcher)]}],
    #             label=searcher,
    #             method='update'
    #         )
    #     )

    # # Update the layout to add the dropdown menu
    # fig.update_layout(
    #     updatemenus=[
    #         dict(
    #             buttons=menu_buttons,
    #             direction="down",
    #             pad={"r": 10, "t": 10},
    #             showactive=True,
    #             x=0.1,
    #             xanchor="left",
    #             y=1.15,
    #             yanchor="top"
    #         ),
    #     ],
    #     annotations=[
    #         dict(text="Select searcher:", showarrow=False, x=0, y=1.085, yref="paper", align="left")
    #     ]
    # )



if __name__ == "__main__":
    map = analysis.load_dict_from_json("atomic/builder_atomic_map.json")
    agg = analysis.load_dict_from_json("atomic/atomic_searchers_agg.json")
    map, agg = analysis.get_map_in_range(map, agg, 0.9)

    searcher_builder_orderflow(map, agg, "atomic searcher-builder orderflow")

    nonatomic_dir = "non_atomic/after_and_tob/"
    map = analysis.load_dict_from_json(nonatomic_dir + "no_atomic_overlap_map.json")
    agg = analysis.load_dict_from_json(nonatomic_dir + "no_atomic_overlap_agg.json")
    map, agg = analysis.get_map_in_range(map, agg, 0.9)

    searcher_builder_orderflow(map, agg, "nonatomic searcher-builder orderflow")


