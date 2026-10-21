#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Cross-venue exact-product control without transporting MRC products.

Hash all comparator header bytes (timestamp-normalized labels), extended header,
payload and per-movie STAR. Input identity and native arm records accompany hashes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('run', type=Path)
p.add_argument('--venue', required=True)
a = p.parse_args()
files = list((a.run / 'Movies').glob('*.mrc'))
stars = list((a.run / 'Movies').glob('*.star'))
assert len(files) == len(stars) == 1, (files, stars)
h = lambda b: hashlib.sha256(b).hexdigest()
with files[0].open('rb') as f:
    head = f.read(1024)
    nx, ny, nz, mode = struct.unpack_from('<4i', head)
    n = struct.unpack_from('<i', head, 92)[0]
    assert n >= 0 and mode == 2
    extended = f.read(n)
    payload = hashlib.sha256()
    size = 0
    for b in iter(lambda: f.read(8 << 20), b''):
        size += len(b)
        payload.update(b)
assert size == nx * ny * nz * 4
labels = bytearray(head[224:1024])
labels[:80] = re.sub(rb'\b\d{2}-[A-Za-z]{3}-\d{2}\s+\d{2}:\d{2}:\d{2}\b',
                     lambda m: b'0' * len(m.group()), bytes(labels[:80]))
run = json.loads((a.run / 'run.json').read_text())
assert run['exit_status'] == 0
json.dump(dict(venue=a.venue, native_run=run, core_header_sha256=h(head[:224]),
               normalized_labels_sha256=h(bytes(labels)), extended_header_sha256=h(extended),
               payload_sha256=payload.hexdigest(), payload_bytes=size,
               star_sha256=h(stars[0].read_bytes()),
               fingerprint_script_sha256=h(Path(__file__).read_bytes())), sys.stdout, indent=2)
print()
