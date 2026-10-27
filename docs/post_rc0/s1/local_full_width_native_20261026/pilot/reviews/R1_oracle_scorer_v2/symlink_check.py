"""Discriminating rerun of the symlink-escape negative (absolute link target)."""
import hashlib, json, shutil, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, '/tmp/mc-local-full-width-pilot-20261026')
import score_fields_v2 as S
d = Path(sys.argv[1]).resolve() / 'symlink_abs'
if d.exists(): shutil.rmtree(d)
(d / 'output').mkdir(parents=True)
sha = lambda b: hashlib.sha256(b).hexdigest()
pub = {}
for rel in ['noisy.star', 'noisy.mrc', 'noisy.log', 'corrected_micrographs.star', 'logfile.pdf']:
    b = rel.encode(); (d / 'output' / rel).write_bytes(b); pub[rel] = dict(bytes=len(b), sha256=sha(b))
t = d / 'outside.txt'; t.write_bytes(b'outside'); (d / 'output' / 'link.txt').symlink_to(t.resolve())
pub['link.txt'] = dict(bytes=7, sha256=sha(b'outside'))
(d / 'RUN.json').write_text(json.dumps(dict(case='noisy', exit=0, binary_sha256='a' * 64, publication=pub))); (d / 'runtime.json').write_text('{}')
assert (d / 'output' / 'link.txt').is_file()  # link is live: only the escape check can reject it
try: S.complete_publication(d, 'noisy', 'a' * 64); print('ADMIT'); sys.exit(1)
except ValueError as e: print('REJECT', e); assert 'escapes' in str(e)
