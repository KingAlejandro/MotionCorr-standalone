#!/usr/bin/env python3
"""Copy the corpus inputs into a tmpfs data root and verify every file against corpus.md.

Usage: stage_inputs.py CORPUS_MD FAMILIES_JSON DATA_ROOT HELD_ROOT TUTORIAL_DIR [--evidence OUT.json]

Held families are copied (read-only on the source) from HELD_ROOT, which has the
EMPIAR-* trees of the #96 corpus; tutorial files come from TUTORIAL_DIR (Movies/ and
gain.mrc). Files already present under DATA_ROOT (the two added families, fetched
separately) are only verified. The SHA-256 of the *copy* is checked, so a pass
identifies both the source and the tmpfs file. Exit status 1 on any mismatch.
"""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    md, fam_json, data, held, tut = (Path(x) for x in sys.argv[1:6])
    evidence = Path(sys.argv[sys.argv.index('--evidence') + 1]) if '--evidence' in sys.argv else None
    expected = {}
    for line in md.read_text().splitlines():
        m = re.match(r'\|\s*\S+\s*\|\s*`([^`]+)`\s*\|\s*([\d,]+)\s*\|\s*`([0-9a-f]{64})`\s*\|', line)
        if m:
            expected[m.group(1)] = (int(m.group(2).replace(',', '')), m.group(3))
    fams = json.loads(fam_json.read_text())['families']
    wanted = []
    for fam in fams:
        wanted += fam['movies'] + ([fam['gain']] if fam.get('gain') else [])
    wanted = list(dict.fromkeys(wanted))
    records, ok = [], True
    for rel in wanted:
        if rel not in expected:
            print('NOT IN corpus.md:', rel)
            ok = False
            continue
        size, want = expected[rel]
        dst = data / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            if rel.startswith('tutorial/'):
                src = tut / rel[len('tutorial/'):]
            else:
                src = held / rel
            if not src.is_file():
                print('MISSING source:', src)
                ok = False
                continue
            shutil.copyfile(src, dst)
        got = sha256(dst)
        rec = {'path': rel, 'bytes': dst.stat().st_size, 'expected_bytes': size,
               'sha256': got, 'expected_sha256': want, 'pass': got == want and dst.stat().st_size == size}
        ok &= rec['pass']
        records.append(rec)
        print('%s %s' % ('PASS' if rec['pass'] else 'FAIL', rel), flush=True)
    if evidence:
        evidence.write_text(json.dumps({'all_pass': ok, 'files': records}, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
