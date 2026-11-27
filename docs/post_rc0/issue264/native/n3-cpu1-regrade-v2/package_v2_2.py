# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a narrow package from exact committed Git blobs; no clone, input corpus or remote operation.
python3 -I -B package_v2_2.py --revision EXACT_SHA --out NEW_DIRECTORY
"""
import argparse, hashlib, io, json, os, pathlib, subprocess, tarfile

HERE = pathlib.Path(__file__).resolve().parent
PREFIX = 'docs/post_rc0/issue264/native/n3-cpu1-regrade-v2/'
MEMBERS = {name: PREFIX + name for name in (
    'regrade_v2_2.py', 'remote_run_v2_2.py', 'CONTRACT.md', 'AMENDMENT-1.md',
    'AMENDMENT-2.md', 'EXPECT_LIVE.json', 'EVIDENCE_MANIFEST.json', 'REMOTE-PLAN-v2.2.md')}
MEMBERS['predictions_iter2.json'] = 'docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json'
CAP = 1 << 20
sha = lambda b: hashlib.sha256(b).hexdigest()


def git(*args):
    return subprocess.run(['/usr/bin/git', '-C', str(HERE), *args], check=True, capture_output=True,
                          env={'PATH': '/usr/bin:/bin', 'GIT_OPTIONAL_LOCKS': '0'}, timeout=15).stdout


def build(revision, out):
    commit = git('rev-parse', '--verify', revision + '^{commit}').decode().strip()
    if revision != commit:
        raise ValueError('revision must be the exact full commit SHA')
    data, pins = {}, {}
    for name, path in MEMBERS.items():
        data[name] = git('show', f'{commit}:{path}')
        pins[name] = {'git_path': path, 'git_blob': git('rev-parse', f'{commit}:{path}').decode().strip(),
                      'size': len(data[name]), 'sha256': sha(data[name])}
    manifest = {'kind': 'cpu1-regrade-v2.2 narrow package', 'source_commit': commit, 'files': pins,
                'content_bytes': sum(len(b) for b in data.values()), 'cap_bytes': CAP}
    data['PACKAGE.json'] = (json.dumps(manifest, indent=1, sort_keys=True) + '\n').encode()
    if sum(map(len, data.values())) > CAP:
        raise ValueError('package content exceeds 1 MiB')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as t:
        for name, raw in sorted(data.items()):
            m = tarfile.TarInfo(name); m.size = len(raw); m.mode = 0o444
            t.addfile(m, io.BytesIO(raw))
    raw = buf.getvalue()
    if len(raw) > CAP:
        raise ValueError('package archive exceeds 1 MiB')
    out = pathlib.Path(out).absolute()
    if str(out.parent.resolve()) != str(out.parent):
        raise ValueError('non-canonical output parent')
    out.mkdir(exist_ok=False)
    (out / 'package.tar').write_bytes(raw)
    receipt = {'source_commit': commit, 'package_sha256': sha(raw), 'package_bytes': len(raw),
               'package_manifest_sha256': sha(data['PACKAGE.json']), 'manifest': manifest,
               'packer_sha256': sha(pathlib.Path(__file__).read_bytes())}
    (out / 'PACKAGE-RECEIPT.json').write_text(json.dumps(receipt, indent=1) + '\n')
    print(json.dumps({k: v for k, v in receipt.items() if k != 'manifest'}))
    return receipt


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--revision', required=True); ap.add_argument('--out', required=True)
    a = ap.parse_args(); build(a.revision, a.out)
