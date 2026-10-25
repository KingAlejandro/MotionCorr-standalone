#!/usr/bin/env python3
"""Controls: verify_tree must reject a flipped byte, an extra file, a missing file, a symlink and a wrong RUN identity."""
import hashlib, json, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tierc_stage_eval import verify_tree

SRC = '3eee0a4b4e367f9b57f950c440c89679a5ec9c93'


def build(root):
    runs = Path(root) / 'runs'; (runs / 'C-x-p3-cpu-none' / 'Movies').mkdir(parents=True)
    d = runs / 'C-x-p3-cpu-none'
    run = json.dumps(dict(id='C-x-p3-cpu-none', tier='C', exit=0, source_sha=SRC)).encode()
    blobs = {'RUN.json': run, 'runtime.json': b'{}', 'witness.txt': b'w', 'Movies/a.mrc': b'M' * 100, 'Movies/a.star': b's', 'Movies/a.log': b'l'}
    files = []
    for rel, b in blobs.items():
        (d / rel).write_bytes(b); files.append(dict(rel=rel, bytes=len(b), sha256=hashlib.sha256(b).hexdigest()))
    return runs, [dict(id='C-x-p3-cpu-none', files=files)]


def expect_fail(mutate, label):
    with tempfile.TemporaryDirectory() as t:
        runs, recs = build(t); mutate(runs, recs)
        try: verify_tree(runs, recs)
        except ValueError: return
        raise SystemExit(f'control did not fail: {label}')


with tempfile.TemporaryDirectory() as t:
    runs, recs = build(t); assert verify_tree(runs, recs) == 6
expect_fail(lambda r, _: (r / 'C-x-p3-cpu-none/Movies/a.mrc').write_bytes(b'N' + b'M' * 99), 'flipped byte')
expect_fail(lambda r, _: (r / 'C-x-p3-cpu-none/extra.txt').write_text('x'), 'extra file')
expect_fail(lambda r, _: (r / 'C-x-p3-cpu-none/witness.txt').unlink(), 'missing file')
expect_fail(lambda r, _: (r / 'C-x-p3-cpu-none/link').symlink_to('witness.txt'), 'symlink')
def wrong_exit(r, recs):
    b = json.dumps(dict(id='C-x-p3-cpu-none', tier='C', exit=1, source_sha=SRC)).encode()
    (r / 'C-x-p3-cpu-none/RUN.json').write_bytes(b)
    recs[0]['files'][0].update(bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
expect_fail(wrong_exit, 'RUN exit != 0 despite matching hash')
print('verify_tree controls: 1 accept + 5 rejects OK')
