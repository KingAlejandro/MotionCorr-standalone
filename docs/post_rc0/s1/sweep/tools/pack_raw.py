#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Package raw run logs/STARs with a hash index; keep JSON/CSV directly reviewable."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('evidence', type=Path)
a = p.parse_args()
index = {}
if (a.evidence / 'raw_files.json').exists():
    raise SystemExit('Refusing to repack an already packaged tree')
files = sorted(path for path in a.evidence.rglob('*.gz')
               if 'runs' in path.relative_to(a.evidence).parts or
               ('analysis' in path.relative_to(a.evidence).parts and path.name.endswith('.log.gz')))
groups = {}
for path in files:
    rel = path.relative_to(a.evidence)
    assert path.name.endswith(('.star.gz', '.log.gz', '.txt.gz')), rel
    group = rel.parts[1] if rel.parts[0] == 'scarf' else '4GPUs'
    groups.setdefault(group, []).append(path)
for group, paths in groups.items():
    archive = 'raw-' + group + '.tar.gz'
    with (a.evidence / archive).open('wb') as out:
        with gzip.GzipFile(filename='', fileobj=out, mode='wb', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as tar:
                for path in paths:
                    rel = str(path.relative_to(a.evidence))
                    data = path.read_bytes()
                    meta = tarfile.TarInfo(rel)
                    meta.size = len(data)
                    meta.mode = 0o644
                    tar.addfile(meta, io.BytesIO(data))
                    index[rel] = dict(archive=archive, member=rel, sha256=hashlib.sha256(data).hexdigest())
    with tarfile.open(a.evidence / archive) as tar:
        for member in tar:
            assert member.isfile() and member.name in index
            assert hashlib.sha256(tar.extractfile(member).read()).hexdigest() == index[member.name]['sha256']
(a.evidence / 'raw_files.json').write_text(json.dumps(index, indent=2, sort_keys=True) + '\n')
for path in files:
    path.unlink()
print('Packaged', len(files), 'raw files into', len(groups), 'archives; no MRCs or binaries')
