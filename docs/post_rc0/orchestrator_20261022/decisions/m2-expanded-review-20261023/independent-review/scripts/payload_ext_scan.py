#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Header-only scan of tar archives (as committed at bbf) for image/movie payload member extensions.
Reads archive blobs via `git cat-file`, stream-mode tarfile (headers only); never extracts."""
import collections, json, os, subprocess, sys, tarfile
REPO, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(os.path.join(OUT, 'archives_and_refs.json')))
PAY = {'.mrc', '.mrcs', '.tif', '.tiff', '.eer', '.dm4', '.dm3', '.ser', '.st', '.map', '.npy', '.npz', '.bin', '.raw', '.zst', '.xz', '.gz', '.tgz', '.zip', '.so', '.a', '.o', '.exe'}
res = {}
for a in d['archives']:
    t = a.get('tar')
    if not (t and t.get('is_tar')):
        continue
    p = subprocess.Popen(['git', 'cat-file', 'blob', a['oid']], cwd=REPO, stdout=subprocess.PIPE)
    ext = collections.Counter(); exec_bits = 0; n = 0
    with tarfile.open(fileobj=p.stdout, mode='r|*') as tf:
        for m in tf:
            if m.isfile():
                n += 1
                e = os.path.splitext(m.name)[1].lower() or '(none)'
                ext[e] += 1
                if m.mode & 0o111: exec_bits += 1
    p.stdout.close(); p.wait()
    res[a['paths'][0]] = {'files': n, 'ext_counts': dict(ext.most_common()), 'payload_like_exts': {k: v for k, v in ext.items() if k in PAY},
                          'members_with_exec_bit': exec_bits}
json.dump(res, open(os.path.join(OUT, 'archive_member_extensions.json'), 'w'), indent=1)
for k, v in res.items():
    print(k.split('docs/')[-1][:70].ljust(70), v['files'], 'payload-like:', v['payload_like_exts'] or '-', 'exec-bit:', v['members_with_exec_bit'], 'exts:', dict(list(v['ext_counts'].items())[:6]))
