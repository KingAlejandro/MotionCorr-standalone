#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""For each archive blob, find where the repository itself records its full sha256 (git grep of the
64-hex digest at the ref that carries the archive). Git metadata only. usage: recorded_digests.py REPO OUTDIR"""
import json, os, subprocess, sys
REPO, OUT = sys.argv[1], sys.argv[2]
d = json.load(open(os.path.join(OUT, 'archives_and_refs.json')))
REF = {k: v['sha'] for k, v in d['pinned_presence'].items()}
res = []
for a in d['archives']:
    tips = [t for t in ('bbf', 'e77', 'pr273', 'pr274') if t in a['in_tip_changed_vs_main']]
    ref = REF[tips[0]]
    r = subprocess.run(['git', 'grep', '-n', '-I', '-F', a['sha256'], ref, '--', 'docs'], cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    hits = [l.split(':', 3)[1] + ':' + l.split(':', 3)[2] for l in r.stdout.decode().splitlines()]
    res.append({'archive': a['paths'][0], 'oid': a['oid'], 'bytes': a['bytes'], 'sha256': a['sha256'], 'searched_at': tips[0],
                'full_digest_recorded_in': hits[:4], 'full_digest_recorded': bool(hits)})
json.dump(res, open(os.path.join(OUT, 'recorded_digests.json'), 'w'), indent=1)
for x in res:
    print(('REC ' if x['full_digest_recorded'] else 'NOT ') + x['archive'].replace('docs/', '')[:78].ljust(78), x['full_digest_recorded_in'][:2])
