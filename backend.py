from flask import Flask, jsonify
from collections import OrderedDict
from analysis import load_dict_from_json

app = Flask(__name__)
app.json.sort_keys = False

SEARCHER_DB_DIR = "searcher_dbs/"

@app.route('/data', methods=['GET'])
def serve_data():
    data = { "key1": "value1", "key2": "value2" }  # Replace with your actual data
    return jsonify(data)

@app.route('/etherscan', methods=['GET'])
def fetch_etherscan_searchers():
    dir = SEARCHER_DB_DIR + "etherscan_searchers.json"
    searchers = load_dict_from_json(dir)
    return jsonify(searchers)

@app.route('/zeromev', methods=['GET'])
def fetch_zeromev_searchers():
    dir = SEARCHER_DB_DIR + "zeromev_searchers.json"
    searchers = load_dict_from_json(dir)
    return jsonify(searchers)

if __name__ == "__main__":
    app.run(debug=True)