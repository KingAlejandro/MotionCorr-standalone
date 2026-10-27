#!/usr/bin/env python3
"""Reproduction of the single FAILED input preflight; no native arm invocation.

Run only for a separately authorized attempt in a fresh scratch root containing
source/ from git archive 326f03a073aec0d26c9cd585ce4f701d1c808245.
This script records mismatch; it does not repair or accept a changed input.
"""
import json
import sys
import time
from pathlib import Path

scratch, index_path = map(Path, sys.argv[1:3])
sys.path.insert(0, str(scratch / 'source/test-data'))
import generate_realistic_motion as gen

r = gen.recipe('dose1', 0)
p = scratch / 'expectations'
p.mkdir(exist_ok=False)
e = p / 'inmodel.npy'
start = time.time()
proof = gen.expected(r, e)
e.with_suffix('.json').write_text(json.dumps(dict(recipe=r, proof=proof), indent=2) + '\n')
print('expectation', proof, 'seconds', time.time() - start, flush=True)
receipt = gen.generate(r, e, scratch / 'first-movie')
index = json.loads(index_path.read_text())
pin = next(x for x in index if x['name'] == 'dose1-s00')
result = dict(name=pin['name'], expected=pin, generated=receipt,
              movie_matches=pin['movie_sha256'] == receipt['files']['movie.mrcs'],
              expectation_matches=pin['expectation_sha256'] == proof['expectation_sha256'])
(scratch / 'first-input-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2), flush=True)
