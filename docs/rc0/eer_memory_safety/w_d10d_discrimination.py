#!/usr/bin/env python3
"""Run only the #231 P2-1/P3-1 cases of EerMemorySafety, one verdict per case.

The full test stops at its first failing assertion, and base 71ab841e already fails
earlier cases, so this rebuilds the same fixtures with the test module's own
encoder and writer and reports each new case separately.
"""
import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument('--tests', type=Path, required=True, help='directory holding test_eer_memory_safety.py')
ap.add_argument('--binary', type=Path, required=True)
ap.add_argument('--helper', type=Path, required=True)
ap.add_argument('--label', required=True)
ap.add_argument('--mem-limit-kib', type=int, default=16 << 20,
                help='ulimit -v for motioncorr runs (base may size buffers from the header)')
args = ap.parse_args()
args.binary, args.helper = args.binary.resolve(), args.helper.resolve()
sys.path.insert(0, str(args.tests.resolve()))
import test_eer_memory_safety as T  # noqa: E402

rows = []
with tempfile.TemporaryDirectory(prefix='w-d10d-', dir=Path.cwd()) as td:
    root = Path(td)
    for comp in (65000, 65001, 65002):
        width = 2048 if comp == 65002 else 4096
        first = [(0, 0), (131, 0), (width*width - 1, 3 if comp == 65002 else 15)]
        rng = random.Random(comp)
        nsym = 4 if comp == 65002 else 16
        picks = [(p, rng.randrange(nsym)) for p in sorted(rng.sample(range(width*width), 2000))]
        while True:
            whole = T.encode(comp, width, picks)
            decoded, used = T.decode(comp, whole, width*width)
            assert decoded == picks
            if used > 8 * (len(whole) - 1):
                break
            picks.pop()
        for k in range(1, 7):
            after = T.decode(comp, whole[-k:])[0]
            neighbour = T.encode(comp, width, after)
            assert neighbour[:k] == whole[-k:]
            T.write_eer(root/'borrow.eer', comp, [T.encode(comp, width, first), whole[:-k], neighbour], width)
            p = subprocess.run([str(args.helper), 'render_eer_groups', 'borrow.eer', 'render.bin', '1', '1', '2'],
                               cwd=root, capture_output=True, text=True, timeout=90)
            log = p.stdout + p.stderr
            expected = T.expected_image(width, 1, [[0], [1], [2]], [first, [], after])
            image_ok = (root/'render.bin').is_file() and (root/'render.bin').read_bytes() == expected
            skips = log.count('This frame is skipped')
            ok = p.returncode == 0 and skips == 1 and ' frame 2. ' in log and image_ok
            rows.append({'case': f'borrow-{comp}-k{k}', 'rc': p.returncode, 'skips': skips,
                         'frame2_skipped': ' frame 2. ' in log, 'image_equals_omitted': image_ok,
                         'pass': ok})

    strip = T.encode(65002, 2048, [(100, 0), (10000, 3), (100000, 1)])
    T.write_eer(root/'healthy.eer', 65002, [strip]*12, 2048)
    for order in '<>':
        head = bytearray(1024)
        T.struct.pack_into(order + '4i', head, 0, 65535, (1 << 31) - 1, (1 << 31) - 1, 2)
        name = f'dim-overflow-{"le" if order == "<" else "be"}.mrcs'
        (root/name).write_bytes(head)
        out = root/f'out-{name}'
        (root/'movies.star').write_text(T.STAR_HEADER + f'{name} 1\nhealthy.eer 1\n')
        cmd = ['bash', '-c', f'ulimit -v {args.mem_limit_kib} && exec "$@"', '_', str(args.binary), '--i', 'movies.star',
               '--o', str(out) + '/', '--use_own', '--eer_grouping', '4', '--j', '2',
               '--bin_factor', '8', '--angpix', '1', '--skip_report_pdf']
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=300)
            rc, log = p.returncode, p.stdout + p.stderr
        except subprocess.TimeoutExpired as e:
            rc, log = 'timeout', (e.stdout or b'').decode() + (e.stderr or b'').decode()
        stem = name[:-5]
        bad = sorted(q.name for q in out.glob(stem + '.*') if q.suffix != '.log') if out.is_dir() else []
        row = {'case': stem, 'rc': rc,
               'invalid_dimensions': f'readMRC: invalid dimensions in header of image {name}' in log,
               'failed_movie_reported': f'Motion correction failed for 1 movie(s): {name}.' in log,
               'healthy_complete': (out/'healthy.star').is_file() and (out/'healthy.mrc').is_file(),
               'joint_star': (out/'corrected_micrographs.star').exists(),
               'failed_movie_products': bad,
               'log_tail': [l for l in log.splitlines() if l.strip()][-6:]}
        row['pass'] = (rc == 1 and row['invalid_dimensions'] and row['failed_movie_reported'] and
                       row['healthy_complete'] and not row['joint_star'] and not bad)
        rows.append(row)

for r in rows:
    print(args.label, json.dumps(r))
print(args.label, 'SUMMARY', sum(r['pass'] for r in rows), '/', len(rows), 'pass')
