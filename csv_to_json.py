import csv
import json

csvfile = open('./block_to_builder_50k_from_17666420.csv', 'r')
jsonfile = open('block_to_builder.json', 'w')

block_to_builder = {}

with open('./block_to_builder_50k_from_17666420.csv', newline='') as file:
    reader = csv.DictReader(file)
    for row in reader:
        block_number = row['block_number']
        builder = row['builder']
        block_to_builder[block_number] = builder

with jsonfile as jsonfile: 
    json.dump(block_to_builder, jsonfile)
        