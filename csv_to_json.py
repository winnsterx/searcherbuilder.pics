import csv
import json
import re

csvfile = open('./labeled_contracts.csv', 'r')
jsonfile = open('labeled_contracts.json', 'w')

labeled_contracts = {}

def replace_upper_non_alnum(s):
    s = re.sub(r'[^a-zA-Z0-9]+', '_', s)
    return s.upper()

with open('./labeled_contracts.csv', newline='') as file:
    reader = csv.DictReader(file)
    for row in reader:
        address = row['address']
        label = replace_upper_non_alnum(row['name'])
        labeled_contracts[label] = address

with jsonfile as jsonfile: 
    json.dump(labeled_contracts, jsonfile)
        

