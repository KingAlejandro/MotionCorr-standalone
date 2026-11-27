#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""M2 Git metadata inventory: C1 documentation tree and reachable history.

Local object metadata only. Uses `git ls-tree`, `diff`, `merge-base`, `rev-list`,
`cat-file --batch-check` and `log`; never reads blob contents, never extracts or
executes an archive, and never touches the network or the worktree. Standard
library only, one process at a time.

Example (all inputs explicit; nothing is read from beside this script):

  python3 -B inventory_c1_docs.py --repo /path/to/repo \\
    --candidate e77a51a220cb0d91f4ac3c7fac211876d0c6833f \\
    --base 3691374061f782bc84531fd1c79d017ddcb5a7c2 \\
    --pr 273=805d9de27898b4a10e6212e65098d5995a40fdb1:docs/post_rc0/parallel_20261022/numerics \\
    --pr 274=a1036901bbc17900a0c515ad047efb50449c14f7:docs/rc0/issue226/integration_20261022 \\
    --focus docs/post_rc0/s1/km_truth \\
    --ancestor 269=1b29b7f9eea1976a0b7a9e2ef5f9ca00477324b1 \\
    --tree-out tree.json --history-out history.json

Semantics:
  * tree inventory: two-dot tree diff `base candidate -- docs/` (ACMR) with sizes
    from the candidate tree. It equals the three-dot diff only when base is an
    ancestor of candidate; the history output records which holds.
  * "unique" PR paths: files under the given prefixes at the pinned PR head that
    are absent (by path) from the base tree.
  * history: `rev-list --objects base..candidate` (the objects an ordinary merge
    of the candidate imports into a repository that already has base). Sizes are
    logical (uncompressed) blob sizes. The `docs/` split uses the first path
    name rev-list reports for a blob, so it is a hint. `objectsize:disk` depends
    on this repository's packing and is kept under `machine_specific`.
"""
import argparse, collections, hashlib, json, os, platform, subprocess, sys

ARCH = ('.gz', '.tgz', '.tar', '.zip', '.xz', '.bz2', '.zst')
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')


def git(repo, *a, stdin=None):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=repo, env=ENV,
                          input=stdin, stdout=subprocess.PIPE, check=True).stdout


def lines(repo, *a):
    return git(repo, *a).decode().split('\0' if '-z' in a else '\n')[:-1]


def ls_tree(repo, rev, *paths):
    rows = {}
    for rec in lines(repo, 'ls-tree', '-r', '-l', '-z', rev, '--', *paths):
        meta, path = rec.split('\t', 1)
        _, typ, oid, size = meta.split()
        if typ == 'blob':
            rows[path] = {'path': path, 'oid': oid, 'bytes': int(size)}
    return rows


def rev_objects(repo, rng):
    names = {}
    for l in lines(repo, 'rev-list', '--objects', rng):
        o, _, n = l.partition(' ')
        names[o] = n
    kinds = collections.defaultdict(lambda: {'count': 0, 'logical_bytes': 0})
    disk = collections.Counter()
    blobs = {}
    out = git(repo, 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize) %(objectsize:disk)',
              stdin=('\n'.join(names) + '\n').encode()).decode().splitlines()
    for l in out:
        o, typ, size, d = l.split()
        kinds[typ]['count'] += 1
        kinds[typ]['logical_bytes'] += int(size)
        disk[typ] += int(d)
        if typ == 'blob':
            blobs[o] = (names[o], int(size), int(d))
    return names, dict(kinds), disk, blobs


def blob_summary(blobs):
    docs = sum(s for n, s, _ in blobs.values() if n.startswith('docs/'))
    tot = sum(s for _, s, _ in blobs.values())
    return {'blobs': len(blobs), 'blob_logical_bytes': tot, 'blob_logical_bytes_docs_name_hint': docs,
            'blob_logical_bytes_other_name_hint': tot - docs}


def tree_inventory(a, base_docs_paths_by_pr):
    repo, head, base = a.repo, a.candidate, a.base
    paths = lines(repo, 'diff', '--name-only', '-z', '--diff-filter=ACMR', base, head, '--', 'docs/')
    tree = ls_tree(repo, head, 'docs/')
    rows = [tree[p] for p in paths]
    archive = [r for r in rows if r['path'].endswith(ARCH)]
    by = {}
    for r in rows:
        g = by.setdefault('/'.join(r['path'].split('/')[:4]), {'files': 0, 'logical_bytes': 0})
        g['files'] += 1
        g['logical_bytes'] += r['bytes']
    d = {'kind': 'M2 current committed C1 tree inventory; no retention decision/deletion',
         'candidate': head, 'main': base, 'changed_doc_files': len(rows),
         'changed_logical_bytes': sum(r['bytes'] for r in rows),
         'changed_unique_blob_bytes': sum({r['oid']: r['bytes'] for r in rows}.values()),
         'bulk_archive_files': len(archive), 'bulk_archive_logical_bytes': sum(r['bytes'] for r in archive),
         'largest_archives': sorted(archive, key=lambda r: r['bytes'], reverse=True),
         'groups': dict(sorted(by.items(), key=lambda kv: kv[1]['logical_bytes'], reverse=True)),
         'excluded_integration_packet_checks': {}}
    for name, (sha, prefixes) in a.pr.items():
        uniq = base_docs_paths_by_pr[name]
        cand = ls_tree(repo, head, *prefixes)
        d['excluded_integration_packet_checks'][name] = {
            'head': sha, 'unique_doc_paths': len(uniq),
            'unique_doc_paths_in_c1': sorted(p for p in uniq if p in cand),
            'unique_directories': sorted({os.path.dirname(p) for p in uniq})}
    d['decision'] = 'UNDECIDED; no file removed and no retention policy adopted'
    return d, rows, tree, archive


def history_inventory(a, rows, archive):
    repo, C, B = a.repo, a.candidate, a.base
    tip = ls_tree(repo, C)
    base_docs = ls_tree(repo, B, 'docs/')
    tip_oids = {r['oid'] for r in tip.values()}
    names, kinds, disk, new_blobs = rev_objects(repo, f'{B}..{C}')
    in_tip = {o: v for o, v in new_blobs.items() if o in tip_oids}
    hist_only = {o: v for o, v in new_blobs.items() if o not in tip_oids}
    top = sorted(new_blobs.items(), key=lambda kv: kv[1][1], reverse=True)[:10]
    res = {
        'inputs': {'candidate': C, 'base': B, 'merge_base': git(repo, 'merge-base', B, C).decode().strip(),
                   'base_is_ancestor_of_candidate': subprocess.run(
                       ['git', 'merge-base', '--is-ancestor', B, C], cwd=repo, env=ENV).returncode == 0,
                   'candidate_parents': git(repo, 'log', '-1', '--format=%P', C).decode().split(),
                   'commits_base_to_candidate': int(git(repo, 'rev-list', '--count', f'{B}..{C}')),
                   'merge_commits_base_to_candidate': int(git(repo, 'rev-list', '--merges', '--count', f'{B}..{C}'))},
        'layers': {
            '1_base_tree_docs': {'files': len(base_docs),
                                 'logical_bytes': sum(r['bytes'] for r in base_docs.values())},
            '2_candidate_tip_changed_docs': {'files': len(rows), 'logical_bytes': sum(r['bytes'] for r in rows),
                                             'archive_files': len(archive),
                                             'archive_logical_bytes': sum(r['bytes'] for r in archive)},
            '4_reachable_new_history_base_to_candidate': {
                'objects': kinds, **blob_summary(new_blobs),
                'blobs_present_in_candidate_tip_tree': blob_summary(in_tip),
                'blobs_history_only_not_in_candidate_tip_tree': blob_summary(hist_only),
                'tip_archive_blobs_in_new_history': sum(1 for r in archive if r['oid'] in new_blobs),
                'largest_new_blobs': [{'oid': o, 'name_hint': n, 'bytes': s, 'in_tip_tree': o in tip_oids}
                                      for o, (n, s, _) in top]}},
        'focus': {}, 'ancestors': {}, 'pr_heads': {}}
    machine = {'layer_5_local_packed_disk_bytes_new_blobs': sum(d for _, _, d in new_blobs.values()),
               'layer_5_local_packed_disk_bytes_by_type': dict(disk),
               'note': 'objectsize:disk of this repository pack/loose state; not a transfer or remote-storage size',
               'git_version': git(repo, '--version').decode().strip(), 'python': platform.python_version()}
    for f in a.focus:
        at_b, at_c = ls_tree(repo, B, f), ls_tree(repo, C, f)
        big = max(at_c.values(), key=lambda r: r['bytes'], default=None)
        res['focus'][f] = {'files_at_base': len(at_b), 'files_at_candidate': len(at_c),
                           'logical_bytes_at_candidate': sum(r['bytes'] for r in at_c.values()),
                           'largest_file_at_candidate': big,
                           'commits_adding_largest_file': lines(repo, 'log', '--format=%H', '--diff-filter=A',
                                                                 f'{B}..{C}', '--', big['path']) if big else []}
    for n, sha in a.ancestor.items():
        theirs = {r['oid'] for r in ls_tree(repo, sha, *a.focus).values()} if a.focus else set()
        cand_focus = [r for f in a.focus for r in ls_tree(repo, C, f).values()]
        res['ancestors'][n] = {
            'head': sha, 'is_ancestor_of_candidate': subprocess.run(
                ['git', 'merge-base', '--is-ancestor', sha, C], cwd=repo, env=ENV).returncode == 0,
            'focus_blobs_at_candidate_also_at_this_head': sum(1 for r in cand_focus if r['oid'] in theirs)}
    for n, (sha, prefixes) in a.pr.items():
        at_b = ls_tree(repo, B, *prefixes)
        u = {p: r for p, r in ls_tree(repo, sha, *prefixes).items() if p not in at_b}
        big = max(u.values(), key=lambda r: r['bytes'], default=None)
        arch = [r for r in u.values() if r['path'].endswith(ARCH)]
        entry = {'head': sha, 'prefixes': prefixes, 'merge_base_with_base': git(repo, 'merge-base', B, sha).decode().strip(),
                 'merge_base_with_candidate': git(repo, 'merge-base', C, sha).decode().strip(),
                 'is_ancestor_of_candidate': subprocess.run(['git', 'merge-base', '--is-ancestor', sha, C],
                                                            cwd=repo, env=ENV).returncode == 0,
                 '3_unique_tree': {'files': len(u), 'logical_bytes': sum(r['bytes'] for r in u.values()),
                                   'unique_blob_bytes': sum({r['oid']: r['bytes'] for r in u.values()}.values()),
                                   'archive_files': len(arch), 'archive_logical_bytes': sum(r['bytes'] for r in arch),
                                   'largest_file': big,
                                   'blobs_already_in_candidate_new_history': sum(1 for r in u.values() if r['oid'] in new_blobs),
                                   'blobs_already_at_candidate_tip': sum(1 for r in u.values() if r['oid'] in tip_oids)}}
        for label, lo in (('4a_new_history_if_merged_after_candidate', C), ('4b_new_history_if_merged_onto_base', B)):
            _, k, dk, bl = rev_objects(repo, f'{lo}..{sha}')
            entry[label] = {'range': f'{lo}..{sha}', 'objects': k, **blob_summary(bl)}
            machine[f'pr{n}_{label}_local_packed_disk_bytes_blobs'] = sum(d for _, _, d in bl.values())
        res['pr_heads'][n] = entry
    return res, machine


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--repo', required=True)
    ap.add_argument('--candidate', required=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--pr', action='append', default=[], metavar='NAME=SHA:PREFIX[,PREFIX]')
    ap.add_argument('--focus', action='append', default=[], metavar='PREFIX')
    ap.add_argument('--ancestor', action='append', default=[], metavar='NAME=SHA')
    ap.add_argument('--tree-out')
    ap.add_argument('--history-out')
    a = ap.parse_args()
    a.pr = {n: (s, p.split(',')) for n, v in (x.split('=', 1) for x in a.pr) for s, p in [v.split(':', 1)]}
    a.ancestor = dict(x.split('=', 1) for x in a.ancestor)
    for r in (a.candidate, a.base, *(s for s, _ in a.pr.values()), *a.ancestor.values()):
        assert len(r) == 40, f'pass full 40-hex SHAs, not {r!r}'
    uniq = {}
    for n, (s, pf) in a.pr.items():
        at_b = ls_tree(a.repo, a.base, *pf)
        uniq[n] = sorted(p for p in ls_tree(a.repo, s, *pf) if p not in at_b)
    d, rows, tree, archive = tree_inventory(a, uniq)
    res, machine = history_inventory(a, rows, archive)
    if a.tree_out:
        open(a.tree_out, 'w').write(json.dumps(d, indent=2) + '\n')
    if a.history_out:
        script = hashlib.sha256(open(__file__, 'rb').read()).hexdigest()
        h = {'kind': 'M2 Git history/object metadata inventory; local object metadata only; no retention decision/deletion',
             'recipe': {'script': 'inventory_c1_docs.py', 'script_sha256': script,
                        'args': {'candidate': a.candidate, 'base': a.base,
                                 'pr': {n: f'{s}:{",".join(p)}' for n, (s, p) in a.pr.items()},
                                 'focus': a.focus, 'ancestor': a.ancestor}},
             'results': res, 'machine_specific': machine,
             'decision': 'UNDECIDED; no file removed and no retention policy adopted'}
        open(a.history_out, 'w').write(json.dumps(h, indent=2) + '\n')
    print(json.dumps({k: v for k, v in d.items() if k not in ('groups', 'largest_archives')}, indent=2))


if __name__ == '__main__':
    main()
