#!/usr/bin/env python3
"""Archive only campaign receipts/scripts; leave raw dumps and SDK private/in place."""
import argparse, hashlib, json, pathlib, tarfile


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--archive',type=pathlib.Path,required=True);p.add_argument('--manifest',type=pathlib.Path,required=True);p.add_argument('include',nargs='+');a=p.parse_args()
root=a.root.resolve();paths=set()
for name in a.include:
    source=(root/name).resolve()
    if not source.is_relative_to(root):raise RuntimeError('archive input outside root')
    for path in source.rglob('*') if source.is_dir() else [source]:
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts:continue
        if path.suffix not in {'.json','.jsonl','.log','.txt','.csv','.utc','.py','.sh','.sbatch','.md','.sha256','.make','.diff'}:continue
        paths.add(path)
if a.archive.exists() or a.manifest.exists():raise RuntimeError('never overwrite retained evidence')
files={str(path):digest(path) for path in sorted(paths)}
with tarfile.open(a.archive,'w:gz') as tar:
    for path in sorted(paths):tar.add(path,arcname=str(path.relative_to(root)),recursive=False)
a.manifest.write_text(json.dumps({'root':str(root),'archive':str(a.archive),'archive_sha256':digest(a.archive),'files':files,'scope':'Receipt/script archive only; raw native dumps remain in place; no SDK/header/library/binary redistribution'},indent=2)+'\n')
print(json.dumps({'archive':str(a.archive),'archive_sha256':digest(a.archive),'manifest':str(a.manifest),'manifest_sha256':digest(a.manifest),'file_count':len(files)},indent=2))
