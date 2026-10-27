"""Verifies the staged source tree against the git blob list of the pinned commit (every file, no extras). Usage: verify_source.py SOURCE_DIR source.blobs"""
import hashlib, os, sys
from pathlib import Path
src, blobs = Path(sys.argv[1]), Path(sys.argv[2])
want = {}
for line in blobs.read_text().splitlines():
    meta, path = line.split('\t', 1); mode, typ, sha = meta.split(); want[path] = (mode, typ, sha)
bad = []; seen = set()
for p in src.rglob('*'):
    if p.is_dir(): continue
    rel = str(p.relative_to(src)); seen.add(rel)
    if rel not in want: bad.append(('extra', rel)); continue
    mode, typ, sha = want[rel]
    data = os.readlink(p).encode() if p.is_symlink() else p.read_bytes()
    if hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest() != sha: bad.append(('differs', rel))
bad += [('missing', r) for r in want if r not in seen]
print('files', len(want), 'mismatches', len(bad), bad[:5])
sys.exit(1 if bad else 0)
