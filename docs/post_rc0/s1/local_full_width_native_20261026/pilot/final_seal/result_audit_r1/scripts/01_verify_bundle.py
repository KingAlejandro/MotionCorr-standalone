"""Verify every file in the audit bundle against MANIFEST.json (bytes + sha256); list extra/missing files."""
import hashlib, json, sys, os
from pathlib import Path
B = Path(sys.argv[1]); exp_manifest = sys.argv[2]
raw = (B/'MANIFEST.json').read_bytes()
mh = hashlib.sha256(raw).hexdigest()
m = json.loads(raw)
bad, ok = [], 0
for rel, e in m['files'].items():
    p = B/rel
    if not p.is_file(): bad.append(('MISSING', rel)); continue
    b = p.read_bytes()
    if len(b) != e['bytes'] or hashlib.sha256(b).hexdigest() != e['sha256']: bad.append(('MISMATCH', rel))
    else: ok += 1
on_disk = {str(p.relative_to(B)) for p in B.rglob('*') if p.is_file()}
extra = sorted(on_disk - set(m['files']))
writable = [str(p.relative_to(B)) for p in B.rglob('*') if os.access(p, os.W_OK)]
print(json.dumps({'manifest_sha256': mh, 'manifest_matches_expected': mh == exp_manifest, 'n_files_declared': m['n_files'], 'n_entries': len(m['files']),
                  'ok': ok, 'bad': bad, 'extra_on_disk': extra, 'writable_paths': writable[:20], 'n_writable': len(writable)}, indent=1))
