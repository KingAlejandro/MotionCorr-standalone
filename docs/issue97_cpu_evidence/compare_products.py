#!/usr/bin/env python3
"""Compare issue-97 validation arms (v2).

v1 only looked at the top level of each arm directory and therefore compared
just the joint corrected_micrographs.star. motioncorr mirrors the input path
under the output directory, so the actual per-movie products (.mrc image and
.star motion model) are nested. Match recursively, by basename, because the
synthetic input lives under src-base/ vs src-fixed/ and so the nested relative
paths differ between arms by construction.

Whole-file hashes are not usable: the MRC header carries a creation timestamp.
Compare the pixel payload after the 1024-byte header plus NSYMBT.
"""
import re
import struct
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

MODE_DTYPE = {0: 'i1', 1: 'i2', 2: 'f4', 6: 'u2', 12: 'f2'}


def mrc_payload(path):
    raw = path.read_bytes()
    if len(raw) < 1024:
        return None, raw
    mode, = struct.unpack_from('<i', raw, 12)
    nsymbt, = struct.unpack_from('<i', raw, 92)
    return mode, raw[1024 + max(0, nsymbt):]


def compare_mrc(a, b):
    mode_a, pay_a = mrc_payload(a)
    mode_b, pay_b = mrc_payload(b)
    if len(pay_a) != len(pay_b):
        return False, f'payload size differs ({len(pay_a)} vs {len(pay_b)})'
    if pay_a == pay_b:
        return True, f'pixel payload IDENTICAL ({len(pay_a)} bytes, mode {mode_a})'
    detail = 'pixel payload DIFFERS'
    if np is not None and mode_a == mode_b and mode_a in MODE_DTYPE:
        x = np.frombuffer(pay_a, dtype=MODE_DTYPE[mode_a]).astype('f8')
        y = np.frombuffer(pay_b, dtype=MODE_DTYPE[mode_b]).astype('f8')
        d = np.abs(x - y)
        nz = int((d != 0).sum())
        rng = float(x.max() - x.min()) if x.size else 0.0
        detail += (f': {nz}/{d.size} px ({100.0 * nz / d.size:.3f}%), '
                   f'max|d|={d.max():.6g}, mean|d|={d.mean():.6g}, '
                   f'range={rng:.6g}, relmax={(d.max() / rng if rng else 0):.3e}')
    return False, detail


# Path tokens legitimately differ between arms (the synthetic input lives under src-base/
# vs src-fixed/). Earlier revisions dropped any LINE containing a path -- which silently
# discarded the single STAR data row, because rlnAccumMotion* values sit on the same row as
# the micrograph path. That made the joint-STAR comparison structurally unable to see the
# numbers it was supposed to compare. Normalise path TOKENS instead, so numeric fields on a
# path-bearing row are still compared.
PATH_TOKEN = re.compile(r'(^/|/.*/|\.mrcs?$|\.star$|\.tiffs?$|\.tif$)')
DATE_LINE = re.compile(r'\d{4}-\d{2}-\d{2}')


def normalize(line):
    out = []
    for tok in line.split():
        out.append('<PATH>' if PATH_TOKEN.search(tok) else tok)
    return ' '.join(out)


def compare_star(a, b):
    la = [l.rstrip() for l in a.read_text(errors='replace').splitlines()]
    lb = [l.rstrip() for l in b.read_text(errors='replace').splitlines()]
    if la == lb:
        return True, f'STAR byte-identical ({len(la)} lines)'
    ka = [normalize(l) for l in la if not DATE_LINE.search(l)]
    kb = [normalize(l) for l in lb if not DATE_LINE.search(l)]
    if ka == kb:
        return True, f'STAR identical after normalising path tokens ({len(ka)} lines compared, values included)'
    diffs = [(i, x, y) for i, (x, y) in enumerate(zip(ka, kb)) if x != y]
    head = ' | '.join(f'{x.strip()[:40]} -> {y.strip()[:40]}' for _, x, y in diffs[:4])
    return False, f'STAR DIFFERS in {len(diffs)}/{len(ka)} compared lines. e.g. {head}'


def products(d):
    out = {}
    for p in d.rglob('*'):
        if p.is_file() and p.suffix in ('.mrc', '.star'):
            out.setdefault(p.name, p)
    return out


def compare_arm(root, left, right, expect, label):
    print(f'\n=== {label}: {left} vs {right}   [expect {expect}] ===')
    dl, dr = root / left, root / right
    if not dl.is_dir() or not dr.is_dir():
        print('  MISSING ARM'); return None
    pl, pr = products(dl), products(dr)
    names = sorted(set(pl) | set(pr))
    if not names:
        print('  NO PRODUCTS'); return None
    all_equal = True
    for n in names:
        if n not in pl or n not in pr:
            print(f'  ONLY-ONE-ARM {n}'); all_equal = False; continue
        same, detail = compare_mrc(pl[n], pr[n]) if n.endswith('.mrc') else compare_star(pl[n], pr[n])
        all_equal &= same
        print(f'  {"EQUAL  " if same else "DIFFER "} {n}: {detail}')
    verdict = 'EQUAL' if all_equal else 'DIFFERENT'
    ok = (verdict == expect)
    print(f'  --> {verdict} ({"as expected" if ok else "*** UNEXPECTED ***"})')
    return ok


def main():
    root = Path(sys.argv[1])
    res = {}
    for tag, desc in (('syn', 'synthetic 128x128 8f, 3x3 patches'),
                      ('mov', 'real movie 20170629_00026, 5x5 patches')):
        res[f'{tag}: option-OFF base vs fixed'] = compare_arm(
            root, f'{tag}-base-off', f'{tag}-fixed-off', 'EQUAL',
            f'{desc} -- DEFAULT-OFF EXACTNESS CONTROL')
        res[f'{tag}: option-ON  base vs fixed'] = compare_arm(
            root, f'{tag}-base-on', f'{tag}-fixed-on', 'DIFFERENT',
            f'{desc} -- INTENTIONAL OPTION-ON BUGFIX CHANGE')
        compare_arm(root, f'{tag}-fixed-off', f'{tag}-fixed-on', 'DIFFERENT',
                    f'{desc} -- informational: two different modes, not a control')

    print('\n================ SUMMARY ================')
    bad = 0
    for k, v in res.items():
        print(f'  {k:36s} {{True: "as expected", False: "UNEXPECTED", None: "not run"}}'.format() if False else
              f'  {k:36s} ' + {True: 'as expected', False: 'UNEXPECTED', None: 'not run'}[v])
        if v is not True:
            bad += 1
    print(f'\nGATE: {"PASS" if bad == 0 else f"ATTENTION ({bad} not as expected)"}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
