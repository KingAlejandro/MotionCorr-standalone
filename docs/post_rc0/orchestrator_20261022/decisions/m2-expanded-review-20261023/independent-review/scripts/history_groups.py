#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Group reachable-new-history blobs (main..tip) by name-hint component, split tip vs history-only.
Git object metadata only. usage: history_groups.py REPO OUTDIR"""
import collections, json, os, subprocess, sys
REPO, OUT = sys.argv[1], sys.argv[2]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
MAIN = '3691374061f782bc84531fd1c79d017ddcb5a7c2'
TIP = 'bbf24607dec537bd13351f061047ea38bd38237b'
def git(*a, stdin=None):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO, env=ENV, input=stdin, stdout=subprocess.PIPE, check=True).stdout.decode()
names = {}
for l in git('rev-list', '--objects', f'{MAIN}..{TIP}').splitlines():
    o, _, n = l.partition(' '); names[o] = n
tip_oids = set()
for rec in git('ls-tree', '-r', '-z', TIP).split('\0')[:-1]:
    meta, _ = rec.split('\t', 1); tip_oids.add(meta.split()[2])
blobs = {}
for l in git('cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)', stdin=('\n'.join(names) + '\n').encode()).splitlines():
    o, t, s = l.split()
    if t == 'blob': blobs[o] = (names[o], int(s))
def comp(n):
    parts = n.split('/')
    if n.startswith('docs/post_rc0/s1/km_truth/'): return 'docs/post_rc0/s1/km_truth'
    if n.startswith('docs/'): return '/'.join(parts[:3])
    return parts[0] + ('/' + parts[1] if len(parts) > 2 and parts[0] in ('src', 'tests', 'tools') else '')
g = collections.defaultdict(lambda: {'tip': [0, 0], 'history_only': [0, 0]})
for o, (n, s) in blobs.items():
    k = 'tip' if o in tip_oids else 'history_only'
    g[comp(n)][k][0] += 1; g[comp(n)][k][1] += s
rows = sorted(g.items(), key=lambda kv: -(kv[1]['tip'][1] + kv[1]['history_only'][1]))
json.dump({k: v for k, v in rows}, open(os.path.join(OUT, 'history_groups_bbf.json'), 'w'), indent=1)
print('range', f'{MAIN[:8]}..{TIP[:8]}', 'blobs', len(blobs), 'bytes', sum(s for _, s in blobs.values()))
for k, v in rows[:14]:
    print(k.ljust(48), 'tip', v['tip'], 'history-only', v['history_only'])
km = g['docs/post_rc0/s1/km_truth']
print('KM share: tip', km['tip'], 'hist-only', km['history_only'], 'total bytes', km['tip'][1] + km['history_only'][1])
