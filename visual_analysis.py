import matplotlib.pyplot as plt
import plotly.graph_objects as go
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


def order_flow():
    atomic_builder_searcher_map = analysis.load_dict_from_json("atomic/builder_atomic_map.json")
    atomic_searcher_agg = analysis.load_dict_from_json("atomic/atomic_searchers_agg.json")
