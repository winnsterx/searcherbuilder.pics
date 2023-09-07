import pandas as pd
import os
import json
import secret_keys


def transform_transactions(transactions_str):
    # Replace single quotes with double quotes for valid JSON.
    data = transactions_str.replace("'", '"')

    # Replace Python None with JSON null
    data = data.replace(": None", ": null")

    # Convert Python Decimal to a string representation for valid JSON
    # The regex identifies the Decimal structure, captures the number inside, and replaces it with that number wrapped in quotes
    import re

    data = re.sub(r'Decimal\((["\'])([^"\']+)\1\)', r'"\2"', data)

    # Insert commas to separate the dictionaries within the list
    data = data.replace("}\n {", "},\n {")

    return data


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = secret_keys.GBQ_SERVICE_ACCT_PATH
sql = """
WITH
  TxAndTraces AS (
  SELECT
    t.block_number,
    t.`hash` AS tx_hash,
    t.to_address AS tx_to_address,
    t.from_address AS tx_from_address,
    t.gas_price AS tx_gas_price,
    t.receipt_gas_used AS tx_gas_used,
    t.transaction_index AS tx_index,
    tr.to_address AS tr_to_address,
    tr.value AS tr_value,
    b.`hash` AS block_hash,
    b.miner AS fee_recipient,
    b.extra_data AS block_extra_data,
    b.gas_used AS block_gas_used,
    b.base_fee_per_gas AS block_base_fee,
    b.timestamp AS block_timestamp
  FROM
    `bigquery-public-data.crypto_ethereum.blocks` AS b
  JOIN
    `bigquery-public-data.crypto_ethereum.transactions` AS t
  ON
    t.block_number = b.number
  LEFT JOIN
    `bigquery-public-data.crypto_ethereum.traces` AS tr
  ON
    t.`hash` = tr.transaction_hash
    AND (tr.to_address = b.miner OR tr.from_address = b.miner)
  WHERE
    b.number = 18074466
),
  AggregatedTransfers AS (
  SELECT
    block_number,
    tx_hash,
    ARRAY_AGG(STRUCT(tr_to_address, tr_value) ORDER BY tr_value DESC LIMIT 1)[OFFSET(0)] AS internal_transfer
  FROM
    TxAndTraces
  GROUP BY
    block_number,
    tx_hash
)
SELECT
  t.block_number,
  t.block_hash,
  t.fee_recipient,
  t.block_extra_data,
  t.block_base_fee,
  t.block_timestamp,
  t.block_gas_used,
  ARRAY_AGG(STRUCT(t.tx_hash, t.tx_to_address, t.tx_from_address, t.tx_gas_price, t.tx_gas_used, t.tx_index, a.internal_transfer)) AS transactions
FROM
  TxAndTraces t
JOIN
  AggregatedTransfers a
ON
  t.tx_hash = a.tx_hash
GROUP BY
  t.block_number,
  t.block_hash,
  t.fee_recipient,
  t.block_extra_data,
  t.block_base_fee,
  t.block_timestamp,
  t.block_gas_used
ORDER BY
  t.block_number;
"""

# df = pd.read_gbq(sql, project_id=secret_keys.PROJECT_ID, dialect="standard")
# df.to_csv("filename.csv", index=False)
# txs = json.loads(df)

df = pd.read_csv("filename.csv")
data = transform_transactions(df.at[0, "transactions"])
txs = json.loads(data)
tx = txs[3]
print(tx["internal_transfer"]["tr_value"])
print(tx)
# print(json.loads(df.at[0, "transactions"].replace("'", '"')))
