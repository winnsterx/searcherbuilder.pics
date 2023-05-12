import csv
import json

csvfile = open('./block_to_builder_50k.csv', 'r')
jsonfile = open('file.json', 'w')

block_to_builder = {}

with open('./block_to_builder_50k.csv', newline='') as file:
    reader = csv.DictReader(file)
    for row in reader:
        block_number = row['number']
        builder = row['miner']
        block_to_builder[block_number] = builder

with jsonfile as jsonfile: 
    json.dump(block_to_builder, jsonfile)
        