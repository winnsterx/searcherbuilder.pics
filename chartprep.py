import datapane as dp
from datetime import datetime
import analysis 
import visual_analysis

columns = ['sepalLength', 'sepalWidth', 'petalLength', 'petalWidth', 'species']


if __name__ == "__main__":
    map = analysis.load_dict_from_json("atomic/builder_atomic_map.json")
    agg = analysis.load_dict_from_json("atomic/atomic_searchers_agg.json")
    map, agg = analysis.get_map_in_range(map, agg, 0.9)

    fig = visual_analysis.searcher_builder_orderflow(map, agg, "atomic searcher-builder orderflow")
    fig.add_trace(visual_analysis.create_a_flow(map, agg))
    fig.update_layout(title_text="title", font_size=10)
    # fig.show()

    dp.Plot(fig)
