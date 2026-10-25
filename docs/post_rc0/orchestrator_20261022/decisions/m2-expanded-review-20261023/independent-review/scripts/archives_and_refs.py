#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only retention-review inventory: archives, pinned-ref presence, docs path resolution.

Reads Git objects only (`ls-tree`, `diff`, `cat-file`, `for-each-ref`, `merge-base`).
Archive blobs are streamed through hashlib and Python's tarfile in *stream* mode to list
member headers (name/size/type). No member is read, extracted, hashed or executed, and
nothing is written outside --out. Standard library only; one process.

usage: archives_and_refs.py REPO OUTDIR
"""
import collections, gzip, hashlib, io, json, os, subprocess, sys, tarfile

REPO, OUT = sys.argv[1], sys.argv[2]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
MAIN = '3691374061f782bc84531fd1c79d017ddcb5a7c2'
REFS = {
    'main': MAIN,
    'e77': 'e77a51a220cb0d91f4ac3c7fac211876d0c6833f',
    'bbf': 'bbf24607dec537bd13351f061047ea38bd38237b',
    'pr281': '1b15f10b423c246bd25a6cb7b9252954f7a97131',
    'pr269': '1b29b7f9eea1976a0b7a9e2ef5f9ca00477324b1',
    'pr273': '805d9de27898b4a10e6212e65098d5995a40fdb1',
    'pr274': 'a1036901bbc17900a0c515ad047efb50449c14f7',
}
ARCH = ('.gz', '.tgz', '.tar', '.zip', '.xz', '.bz2', '.zst')


def git(*a, stdin=None, check=True):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO, env=ENV, input=stdin,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def ls_tree(rev, *paths):
    rows = {}
    for rec in git('ls-tree', '-r', '-l', '-z', rev, '--', *paths).stdout.decode().split('\0')[:-1]:
        meta, path = rec.split('\t', 1)
        _, typ, oid, size = meta.split()
        if typ == 'blob':
            rows[path] = (oid, int(size))
    return rows


def changed_docs(base, head):
    names = git('diff', '--name-only', '-z', '--diff-filter=ACMR', base, head, '--', 'docs/').stdout.decode().split('\0')[:-1]
    return names


def stream_blob(oid):
    p = subprocess.Popen(['git', 'cat-file', 'blob', oid], cwd=REPO, env=ENV, stdout=subprocess.PIPE)
    return p


def digest_blob(oid, size):
    """sha256 of content and git-style sha1 (blob <size>\\0 + content) to confirm the object is intact."""
    p = stream_blob(oid)
    s256, s1, n = hashlib.sha256(), hashlib.sha1(), 0
    s1.update(b'blob %d\0' % size)
    for chunk in iter(lambda: p.stdout.read(1 << 20), b''):
        s256.update(chunk); s1.update(chunk); n += len(chunk)
    rc = p.wait()
    return {'sha256': s256.hexdigest(), 'git_sha1_recomputed': s1.hexdigest(),
            'git_oid_matches': s1.hexdigest() == oid, 'bytes_read': n, 'size_matches': n == size, 'cat_file_rc': rc}


def list_members(oid):
    """Header-only listing of a (possibly gzip) tar. Returns None when not a tar."""
    p = stream_blob(oid)
    try:
        tf = tarfile.open(fileobj=p.stdout, mode='r|*')
    except tarfile.TarError as e:
        p.stdout.close(); p.wait()
        return {'is_tar': False, 'reason': str(e)[:120]}
    types = collections.Counter(); names = []; total = 0; suspicious = []
    ext = collections.Counter(); biggest = []
    try:
        for m in tf:  # stream mode: iterates headers, skipping member data, never extracts
            t = ('file' if m.isfile() else 'dir' if m.isdir() else 'symlink' if m.issym() else
                 'hardlink' if m.islnk() else 'other')
            types[t] += 1
            names.append(m.name)
            if m.isfile():
                total += m.size
                ext[os.path.splitext(m.name)[1] or '(none)'] += 1
                biggest.append((m.size, m.name))
            if m.name.startswith('/') or '..' in m.name.split('/') or m.issym() or m.islnk() or m.isdev():
                suspicious.append({'name': m.name, 'type': t, 'linkname': m.linkname})
        err = None
    except Exception as e:  # truncated/corrupt
        err = repr(e)[:160]
    p.stdout.close(); p.wait()
    biggest.sort(reverse=True)
    top = collections.Counter(n.split('/')[0] for n in names)
    return {'is_tar': True, 'members': len(names), 'member_types': dict(types), 'sum_file_member_bytes': total,
            'member_ext_counts': dict(ext.most_common(12)), 'top_level_dirs': dict(top.most_common(8)),
            'largest_members': [{'name': n, 'bytes': s} for s, n in biggest[:5]],
            'suspicious_members': suspicious[:20], 'suspicious_count': len(suspicious),
            'list_error': err, '_names': names}


def single_gzip_info(oid):
    p = stream_blob(oid)
    n, h = 0, hashlib.sha256()
    try:
        with gzip.GzipFile(fileobj=p.stdout, mode='rb') as g:
            head = g.read(512)
            n += len(head); h.update(head)
            for chunk in iter(lambda: g.read(1 << 20), b''):
                n += len(chunk); h.update(chunk)
        err = None
    except Exception as e:
        err = repr(e)[:120]
    p.stdout.close(); p.wait()
    return {'decompressed_bytes': n, 'decompressed_sha256': h.hexdigest(), 'error': err,
            'looks_like_tar_header': head[257:262] == b'ustar' if n else False}


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {'git_version': git('--version').stdout.decode().strip(), 'refs': {}, 'pinned_presence': {}}
    for k, v in REFS.items():
        ok = git('cat-file', '-e', v + '^{commit}', check=False).returncode == 0
        contains = []
        if ok:
            contains = git('for-each-ref', '--contains', v, '--format=%(refname)').stdout.decode().split()
        res['pinned_presence'][k] = {'sha': v, 'commit_present_locally': ok,
                                     'refs_containing_count': len(contains),
                                     'refs_containing_sample': contains[:8],
                                     'local_branch_refs_containing': [c for c in contains if c.startswith('refs/heads/')][:8],
                                     'remote_tracking_refs_containing': [c for c in contains if c.startswith('refs/remotes/')][:8]}
        res['refs'][k] = {'sha': v, 'docs_tree': git('rev-parse', '--verify', '-q', v + ':docs', check=False).stdout.decode().strip()}
    res['remote_tracking_ref_count'] = len(git('for-each-ref', 'refs/remotes').stdout.decode().splitlines())
    res['tags_count'] = len(git('for-each-ref', 'refs/tags').stdout.decode().splitlines())
    # archives: changed docs (ACMR) base->head for the candidate tips and the unique PR trees
    tree = {k: ls_tree(REFS[k], 'docs/') for k in ('main', 'e77', 'bbf', 'pr281', 'pr269', 'pr273', 'pr274')}
    arch = collections.OrderedDict()  # oid -> info
    for tip in ('e77', 'bbf', 'pr281', 'pr273', 'pr274'):
        for p in changed_docs(MAIN, REFS[tip]):
            if p.endswith(ARCH):
                oid, size = tree[tip][p]
                a = arch.setdefault(oid, {'oid': oid, 'bytes': size, 'paths': {}, 'in_tip_changed_vs_main': {}})
                a['paths'].setdefault(p, [])
                a['in_tip_changed_vs_main'][tip] = True
    # presence of every archive oid under any path at each ref
    inv = {k: collections.defaultdict(list) for k in tree}
    for k, rows in tree.items():
        for p, (oid, _) in rows.items():
            inv[k][oid].append(p)
    for oid, a in arch.items():
        a['present_at'] = {k: sorted(inv[k].get(oid, []))[:3] for k in tree if inv[k].get(oid)}
        a['absent_from_main'] = oid not in inv['main']
    # detail: digests and member headers (header only)
    for oid, a in arch.items():
        a.update(digest_blob(oid, a['bytes']))
        names = [p.lower() for p in a['paths']]
        a['name_suffix'] = os.path.basename(next(iter(a['paths'])))
        if a['name_suffix'].endswith(('.tar.gz', '.tgz', '.tar')):
            m = list_members(oid)
            names_out = m.pop('_names', None)
            a['tar'] = m
            if names_out is not None and a['name_suffix'] == 'raw.tar.gz':
                json.dump(names_out, open(os.path.join(OUT, 'raw.tar.gz.member_names.json'), 'w'))
        else:
            a['gzip'] = single_gzip_info(oid)
        a['paths'] = sorted(a['paths'])
    res['archives'] = sorted(arch.values(), key=lambda a: -a['bytes'])
    json.dump(res, open(os.path.join(OUT, 'archives_and_refs.json'), 'w'), indent=1)
    print(json.dumps({'archives': len(arch), 'remote_tracking_ref_count': res['remote_tracking_ref_count'],
                      'tags': res['tags_count']}))


main()
