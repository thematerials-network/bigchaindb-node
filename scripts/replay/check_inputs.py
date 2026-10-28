"""Checks one replay side against the recovered data: every rebuilt transaction (JSONL `tx`) must read back
identically through BigchainDB.get_transaction, and every tx must sit in the block the membership CSV records.

Usage: python check_inputs.py <rebuilt-transactions.jsonl> <block-membership.csv> <blocks.tsv> <out.json>
Env: BIGCHAINDB_DATABASE_HOST (the side's MongoDB).
"""
import csv
import json
import sys

from bigchaindb import config_utils

config_utils.autoconfigure(force=True)
from bigchaindb import BigchainDB  # noqa: E402

jsonl_path, csv_path, blocks_path, out_path = sys.argv[1:5]
bigchain = BigchainDB()

replayed_height = {}
for line in open(blocks_path):
    height, _, ids = line.rstrip('\n').split('\t')
    for txid in filter(None, ids.split(',')):
        replayed_height[txid] = int(height)

recorded_height = {row[0]: int(row[1]) for row in csv.reader(open(csv_path)) if row and row[0] != 'tx_id'}
result = {'jsonl': 0, 'read_back_equal': 0, 'read_back_missing': [], 'read_back_different': [],
          'csv_rows': len(recorded_height), 'height_equal': 0, 'height_different': [],
          'replayed_not_in_csv': sorted(set(replayed_height) - set(recorded_height)),
          'csv_not_replayed': sorted(set(recorded_height) - set(replayed_height))}
for line in open(jsonl_path):
    record = json.loads(line)
    result['jsonl'] += 1
    transaction = bigchain.get_transaction(record['id'])
    if transaction is None:
        result['read_back_missing'].append(record['id'])
    elif transaction.to_dict() == record['tx']:
        result['read_back_equal'] += 1
    else:
        result['read_back_different'].append(record['id'])
for txid, height in recorded_height.items():
    if replayed_height.get(txid) == height:
        result['height_equal'] += 1
    elif txid in replayed_height:
        result['height_different'].append([txid, height, replayed_height[txid]])
json.dump(result, open(out_path, 'w'), indent=1)
print(json.dumps({key: value if isinstance(value, int) else len(value) for key, value in result.items()}))
