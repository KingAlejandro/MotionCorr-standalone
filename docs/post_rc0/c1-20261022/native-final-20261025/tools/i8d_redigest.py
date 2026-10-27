#!/usr/bin/env python3
"""Read-only supplementary re-digest of the retained i8 item-12 healthy dataset arms (d1, d2, dshim, d4), after stage i8c-mg-item12-regrade failed its
d1-vs-others comparison ONLY on tag-specific output paths embedded in the per-movie .log and *_shifts.eps files.
Cause: c1_item12.py's digest_tree() normalises the tag directory with the regex rb'item12-retry/dataset/[A-Za-z0-9]+' (the QF scratch name); the C1 derivative's ROOT is
'c1-item12', so the tag was never normalised. This script applies EXACTLY the same digest rules with the regex widened to (item12-retry|c1-item12), nothing else.
MRC files were deleted at the end of the earlier stage (as designed); their d1-vs-others equality (header-less payload + first 224 header bytes) was computed in that stage before
deletion and is retained in results/dataset-d1_d2_d4_d4poison_dpoison_dshim.json (no MRC/STAR in the differing lists). usage: i8d_redigest.py ROOT(c1-item12 dir) OUT.json"""
import hashlib, json, re, sys
from pathlib import Path
root = Path(sys.argv[1]) / 'dataset'


def digest_tree(r):
    out = {}
    for p in sorted(r.rglob('*')):
        if not p.is_file() or p.relative_to(r).parts[0] == '_workers':
            continue
        raw = p.read_bytes()
        raw = re.sub(rb'(?:item12-retry|c1-item12)/dataset/[A-Za-z0-9]+', b'DS', raw)   # the only change from c1_item12.digest_tree
        raw = re.sub(rb'workers/w[0-9]+', b'workers/wN', raw)
        raw = re.sub(rb'\.aggregate-[A-Za-z0-9_]+', b'.aggregate-X', raw)
        if p.suffix == '.mrc':
            h = hashlib.sha256(raw[:224] + raw[1024:]).hexdigest()
        elif p.suffix in ('.star', '.eps'):
            h = hashlib.sha256(raw.replace(str(r).encode(), b'<ROOT>')).hexdigest()
        elif p.suffix == '.log':
            lines = [l for l in raw.replace(str(r).encode(), b'<ROOT>').split(b'\n') if not any(
                m in l for m in (b' ms', b'time', b'Kernel', b'~~(,_,', b'sec .', b'free device memory', b'device memory in use rose'))]
            h = hashlib.sha256(b'\n'.join(lines)).hexdigest()
        else:
            h = 'present'
        out[str(p.relative_to(r))] = h
    return out


base = digest_tree(root / 'd1' / 'merged')
res = {'files_in_d1_merged': len(base), 'mrc_present': sum(k.endswith('.mrc') for k in base), 'cmp': {}}
for tag in ('d2', 'dshim', 'd4'):
    other = digest_tree(root / tag / 'merged')
    diff = sorted(k for k in set(base) | set(other) if base.get(k) != other.get(k))
    res['cmp'][tag] = {'files': len(other), 'differing': diff}
res['verdict'] = 'IDENTICAL' if base and all(not v['differing'] for v in res['cmp'].values()) else 'DIFFERENT'
Path(sys.argv[2]).write_text(json.dumps(res, indent=1) + '\n')
print(res['verdict'], {k: len(v['differing']) for k, v in res['cmp'].items()})
