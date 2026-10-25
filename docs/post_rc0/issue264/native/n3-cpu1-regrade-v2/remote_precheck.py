# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only binding check before a remote regrade (REMOTE-PLAN.md). Writes nothing in the scratch.

  remote_precheck.py manifest --evidence-tar TAR --out EVIDENCE_MANIFEST.json   (local, from the retained archive)
  remote_precheck.py check --scratch-root DIR --manifest EVIDENCE_MANIFEST.json --out NEW_FILE
check: every manifest file in DIR is a regular non-symlink file with the recorded sha256; the 16 pair-member
MRCs exist as regular files (their sha256 are recorded, nothing to compare against). Exit 0 only if all hold.
"""
import argparse, hashlib, json, sys, tarfile
from pathlib import Path

CPU = ['ov-base-cpu', 'ov-cand-cpu', 'ov-mut-cpu']
sha = lambda b: hashlib.sha256(b).hexdigest()


def consumed(name, cases):
    if name in {f'build-{a}.binaries.sha256' for a in CPU} or name in ('n3-cpu1/known-observations.json', 'n3-cpu1/RESULTS.json'):
        return True
    parts = name.split('/')
    if len(parts) >= 4 and parts[0] == 'n3-cpu1' and parts[1] in CPU and parts[2] in cases:
        rest = '/'.join(parts[3:])
        return rest in ('RUN.json', 'out/km_local_nonsquare.star', f'logs/{parts[1]}-{parts[2]}.stdout', f'logs/{parts[1]}-{parts[2]}.stderr')
    return False


def manifest(tar_path, out):
    raw = Path(tar_path).read_bytes(); files = {}
    with tarfile.open(tar_path, 'r:') as t:
        names = [m.name for m in t if m.isfile()]
        cases = sorted({n.split('/')[2] for n in names if n.startswith('n3-cpu1/ov-') and n.count('/') >= 3})
        for m in t:
            if m.isfile() and consumed(m.name, cases):
                files[m.name] = sha(t.extractfile(m).read())
    rec = {'evidence_tar_sha256': sha(raw), 'cases': cases, 'files': files,
           'pair_mrcs': [f'n3-cpu1/{a}/{c}/out/km_local_nonsquare.mrc' for c in cases for a in CPU[:2]]}
    Path(out).write_text(json.dumps(rec, indent=1) + '\n'); print(len(files), 'files', len(cases), 'cases')
    return 0 if len(files) == 24 * 4 + 5 and len(cases) == 8 else 1


def check(root, man, out):
    root, m, problems, mrcs = Path(root).resolve(), json.loads(Path(man).read_text()), [], {}
    for rel, want in m['files'].items():
        p = root / rel
        if p.is_symlink() or not p.is_file(): problems.append(f'{rel} not a regular file'); continue
        if sha(p.read_bytes()) != want: problems.append(f'{rel} sha256 differs')
    for rel in m['pair_mrcs']:
        p = root / rel
        if p.is_symlink() or not p.is_file(): problems.append(f'{rel} not a regular file'); continue
        mrcs[rel] = {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
    rec = {'scratch_root': str(root), 'manifest_sha256': sha(Path(man).read_bytes()), 'checked_files': len(m['files']),
           'pair_mrcs': mrcs, 'problems': problems, 'verdict': 'PASS' if not problems else 'FAIL'}
    out = Path(out)
    if out.exists(): raise SystemExit(f'{out} exists; refusing')
    out.write_text(json.dumps(rec, indent=1) + '\n'); print('precheck', rec['verdict'], problems[:5])
    return 0 if not problems else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('cmd', choices=['manifest', 'check'])
    ap.add_argument('--evidence-tar'); ap.add_argument('--scratch-root'); ap.add_argument('--manifest'); ap.add_argument('--out', required=True)
    a = ap.parse_args()
    sys.exit(manifest(a.evidence_tar, a.out) if a.cmd == 'manifest' else check(a.scratch_root, a.manifest, a.out))
