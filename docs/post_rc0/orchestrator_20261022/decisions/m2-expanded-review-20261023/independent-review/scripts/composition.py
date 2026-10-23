#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Composition of the docs/ tree delta main->tip by content class and component (Git metadata only).
usage: composition.py REPO OUTDIR"""
import collections, json, os, subprocess, sys
REPO, OUT = sys.argv[1], sys.argv[2]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
MAIN = '3691374061f782bc84531fd1c79d017ddcb5a7c2'
TIPS = {'e77': 'e77a51a220cb0d91f4ac3c7fac211876d0c6833f', 'bbf': 'bbf24607dec537bd13351f061047ea38bd38237b'}
def git(*a):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO, env=ENV, stdout=subprocess.PIPE, check=True).stdout.decode()
def ls(rev):
    rows = {}
    for rec in git('ls-tree', '-r', '-l', '-z', rev, '--', 'docs/').split('\0')[:-1]:
        meta, path = rec.split('\t', 1); _, typ, oid, size = meta.split()
        if typ == 'blob': rows[path] = (oid, int(size))
    return rows
CODE = ('.py', '.sh', '.cpp', '.cu', '.h', '.hpp', '.cmake', '.patch', '.diff', '.c')
ARCH = ('.gz', '.tgz', '.tar', '.zip', '.xz', '.bz2', '.zst')
def cls(p):
    if p.endswith(ARCH): return 'archive'
    if p.endswith(CODE) or p.endswith('CMakeLists.txt'): return 'code'
    if p.endswith(('.md',)): return 'markdown'
    if p.endswith(('.json', '.jsonl')): return 'json'
    if p.endswith(('.csv', '.tsv')): return 'csv'
    if p.endswith(('.sha256', '.sha256sum')): return 'sha256'
    if p.endswith(('.png', '.svg', '.html', '.pdf', '.eps')): return 'figure/report'
    return 'text/log/other'
def comp(p):
    if p.startswith('docs/post_rc0/s1/km_truth/'): return 'km_truth (#269)'
    if p.startswith('docs/post_rc0/s1/synth_combined/'): return 'synth_combined (CI-read eval_v2.py)'
    if p.startswith('docs/issue213/evidence/'): return 'issue213/evidence (ctest-read)'
    if p.startswith('docs/post_rc0/c1-20261022/'): return 'c1-20261022 (bbf evidence)'
    if p.startswith('docs/rc0/issue226/'): return 'rc0/issue226 (d2/d3 layers)'
    if p.startswith('docs/post_rc0/issue25'): return 'post_rc0/issue253,257'
    if p.startswith('docs/issue215/'): return 'issue215'
    return 'other docs'
main = ls(MAIN)
out = {}
for k, sha in TIPS.items():
    tip = ls(sha)
    ch = {p: v for p, v in tip.items() if p not in main or main[p][0] != v[0]}
    cc = collections.defaultdict(lambda: [0, 0]); cm = collections.defaultdict(lambda: [0, 0]); cx = collections.defaultdict(lambda: [0, 0])
    for p, (o, s) in ch.items():
        cc[cls(p)][0] += 1; cc[cls(p)][1] += s
        cm[comp(p)][0] += 1; cm[comp(p)][1] += s
        cx[(comp(p), cls(p))][0] += 1; cx[(comp(p), cls(p))][1] += s
    out[k] = {'changed_files': len(ch), 'changed_bytes': sum(s for _, s in ch.values()),
              'by_class': {a: {'files': b[0], 'bytes': b[1]} for a, b in sorted(cc.items())},
              'by_component': {a: {'files': b[0], 'bytes': b[1]} for a, b in sorted(cm.items(), key=lambda kv: -kv[1][1])},
              'by_component_class': {f'{a[0]} | {a[1]}': {'files': b[0], 'bytes': b[1]} for a, b in sorted(cx.items(), key=lambda kv: -kv[1][1])[:30]},
              'deleted_or_modified_vs_main': sum(1 for p in ch if p in main)}
    # directory sizes at tip for CI/ctest-read dirs
    for d in ('docs/issue213/evidence/', 'docs/post_rc0/s1/synth_combined/', 'docs/issue85_laneC/', 'docs/rc0/qf/tools/', 'docs/issue69/evidence/ownership-20260929/', 'docs/profiling_20261001/data24/'):
        rows = [(p, v) for p, v in tip.items() if p.startswith(d)]
        out[k].setdefault('dir_sizes', {})[d] = {'files': len(rows), 'bytes': sum(v[1] for _, v in rows), 'files_in_main': sum(1 for p, _ in rows if p in main)}
json.dump(out, open(os.path.join(OUT, 'composition.json'), 'w'), indent=1)
for k, v in out.items():
    print(k, v['changed_files'], v['changed_bytes'], 'modified-vs-main', v['deleted_or_modified_vs_main'])
    for a, b in v['by_class'].items(): print('   class', a.ljust(16), b)
    for a, b in list(v['by_component'].items()): print('   comp ', a.ljust(40), b)
    for a, b in v['dir_sizes'].items(): print('   dir  ', a, b)
