from bs4 import BeautifulSoup
import os
import json

# parsing downloaded HTML of this URL bc scraper cannot circumvent Cloudflare
url = "https://etherscan.io/accounts/label/mev-bot?subcatid=undefined&size=100&start=0&col=3&order=desc"
mev_bots = {}

pages = os.listdir("etherscan/pages")

for page in pages: 
    if "bot_" not in page: 
        continue
    page = "etherscan/pages/" + page
    print(page)
    with open(page, "r", errors='ignore') as f: 
        contents = f.read()

    soup = BeautifulSoup(contents, 'html.parser')
    table = soup.find('tbody')
    for row in table.find_all("tr"):
        addr = row.find("a", class_="me-1")["data-bs-title"]
        txn_count = int(row.find_all("td")[-1].string.replace(",", ""))
        mev_bots[addr] = txn_count

sorted_mev_bots = dict(sorted(mev_bots.items(), key=lambda item: item[1], reverse=True))

with open("searcher_databases/etherscan_searchers.json", "w") as fp:
    json.dump(sorted_mev_bots, fp)

