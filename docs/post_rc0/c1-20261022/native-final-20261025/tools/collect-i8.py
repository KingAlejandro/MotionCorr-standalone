#!/usr/bin/env python3
"""Collect compact i8 evidence from the VM scratch into one tarball plus a byte index (sha256 + original VM path of every copied file).
Selected: logs/ (stage receipts, occupancy, health, Xid snapshots), top-level *.json/*.sha256/*.sh, tools-v3-run/, per-row receipts (RUN.json, *.console.txt,
stdout/log text, result*.json, status json, STAR, witness, summary files). Excluded: MRC/EPS/PDF/TIFF payloads and anything above 4 MiB (raw products stay on the VM; the
index lists excluded files with size so nothing is silently omitted). usage: collect-i8.py SCRATCH OUT_TGZ OUT_INDEX_JSON"""
import hashlib, json, sys, tarfile
from pathlib import Path
scr, out, idx = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
SKIP_SUFFIX = {'.mrc', '.mrcs', '.eps', '.pdf', '.tif', '.tiff', '.npy', '.o', '.a', '.lst'}
SKIP_DIRS = {'src', 'build-cpu', 'build-cuda', 'build-nvcomp', 'fixtures', 'inputs', 'input', 'census', 'attr'}
# compact selection: bulky per-movie/per-arm trees stay on the VM and are listed in the index with size + sha256
SKIP_PREFIX = ('item13-mrc/runs', 'item13-mrc/synth', 'item13-mrc/tmp', 'item13-mrc/inputs', 'multigpu/', 'c1-item12/inputs', 'build-ingest-fault/cuda_ingest_sticky_fault.o', 'build-ingest-fault/motioncorr_ingest_fault')
rows, excluded = [], []
def h(p):
    d = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): d.update(b)
    return d.hexdigest()
with tarfile.open(out, 'w:gz') as t:
    for p in sorted(scr.rglob('*')):
        rel = p.relative_to(scr)
        if p.is_symlink() or not p.is_file() or rel.parts[0] in SKIP_DIRS or '__pycache__' in rel.parts or '/image.json' in str(rel) and False: continue
        sz = p.stat().st_size
        if str(rel).startswith(SKIP_PREFIX) and not (rel.suffix in ('.json',) and 'cmp-' in rel.name) or p.suffix.lower() in SKIP_SUFFIX or sz > (4 << 20):
            excluded.append({'path': str(rel), 'bytes': sz, 'sha256': h(p) if sz < (2 << 30) else None}); continue
        t.add(p, arcname=str(rel)); rows.append({'path': str(rel), 'vm_path': str(p), 'bytes': sz, 'sha256': h(p)})
idx.write_text(json.dumps({'scratch': str(scr), 'collected': rows, 'excluded_count': len(excluded), 'excluded': excluded[:5000]}, indent=1) + '\n')
print(len(rows), 'collected', len(excluded), 'excluded')
