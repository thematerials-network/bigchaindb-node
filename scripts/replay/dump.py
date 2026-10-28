"""Dumps one replay side's MongoDB for comparison: every collection as sorted canonical extended JSON lines
(without `_id`), its index definitions, and blocks.tsv (height, app_hash, accepted tx ids in order).

Usage: python dump.py <mongo host> <out dir>
"""
import hashlib
import json
import os
import sys

from bson import json_util
from pymongo import MongoClient

host, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
database = MongoClient(host, 27017)['bigchain']
summary = {}
for name in sorted(database.list_collection_names()):
    collection = database[name]
    lines = sorted(json_util.dumps(document, json_options=json_util.CANONICAL_JSON_OPTIONS, sort_keys=True)
                   for document in collection.find({}, {'_id': False}))
    with open(os.path.join(out, name + '.jsonl'), 'w') as handle:
        for line in lines:
            handle.write(line + '\n')
    indexes = {key: json.loads(json_util.dumps(value, json_options=json_util.CANONICAL_JSON_OPTIONS))
               for key, value in collection.index_information().items()}
    summary[name] = {'documents': len(lines),
                     'sha256': hashlib.sha256(''.join(line + '\n' for line in lines).encode()).hexdigest(),
                     'indexes': indexes}
with open(os.path.join(out, 'blocks.tsv'), 'w') as handle:
    for block in database['blocks'].find({}, {'_id': False}).sort('height', 1):
        handle.write('%d\t%s\t%s\n' % (block['height'], block['app_hash'], ','.join(block['transactions'])))
with open(os.path.join(out, 'summary.json'), 'w') as handle:
    json.dump(summary, handle, indent=1, sort_keys=True)
print(json.dumps({name: [value['documents'], value['sha256'][:16]] for name, value in summary.items()}))
