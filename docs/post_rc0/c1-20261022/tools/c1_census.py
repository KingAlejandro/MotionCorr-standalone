#!/usr/bin/env python3
"""#269 100-movie census on the C1 binaries (arm 'none' only; C1 has no MC_DIAG hooks), lane GPU3 + CPUs 8-9.

  c1_census.py run BACKEND BINARY RESULTS_NAME     wraps c1_census_runner.py (tools/run_realistic_motion_census.py with --j 2 and GPU3 only)
  c1_census.py compare RESULTS_NAME REF_ROOT REF_ARM BACKEND OUT.json
        exact comparison (decoded sum payload + STAR text) of every C1 movie against a retained arm directory layout
        REF_ROOT/<movie>/<REF_ARM>/output/movie.{mrc,star}; also STAR-serialised field metrics vs injected truth for both sides
  c1_census.py metrics RESULTS_NAME BACKEND OUT.json    per-movie/condition STAR-serialised field metrics (px, A) vs injected truth
Fixtures are read in place through a symlink (their receipts are hash-checked by the runner); nothing is written under them.
"""
import fcntl, json, os, sys
from pathlib import Path
import numpy as np

SCR = Path(os.environ['C1_SCR']); SRC = SCR / 'src'; ROOT = SCR / 'census'
sys.path[:0] = [str(SRC / 'tools'), str(SRC / 'test-data')]


def run(backend, binary, results):
    ROOT.mkdir(exist_ok=True)
    if not (ROOT / 'fixtures').exists(): os.symlink(os.environ['C1_KM_FIXTURES'], ROOT / 'fixtures')
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import c1_census_runner as m          # lane-adapted derivative (make_c1_derived.py): --j 2, GPU3-only lease
    sys.argv = ['census', '--root', str(ROOT), '--binary', binary, '--backend', backend, '--cpus', os.environ['C1_CPUS'],
                '--dc-arms', 'none', '--double-conditions', '--results', results, '--max-idle-seconds', '600']
    m.main()


def mrc(path):
    from motion_field import read_mrc
    return read_mrc(path)[0]


def field_metrics(star, receipt):
    import generate_realistic_motion as gen
    from check_motion_diagnostics import vector_metrics
    from motion_field import read_motion_star
    r = json.loads(Path(receipt).read_text())['recipe']
    x, y = np.meshgrid(np.linspace(32, r['nx'] - 33, 129), np.linspace(32, r['ny'] - 33, 129)); x, y = x.ravel(), y.ravel()
    truth = -np.stack([gen.displacement(r, f, x, y) for f in range(r['frames'])])
    s = read_motion_star(Path(star))
    e = s.field(s.frames, x, y) - truth
    return dict(px=vector_metrics(e), angstrom=vector_metrics(e * r['pixel_size']))


def movies(results):
    return sorted(p.name for p in (ROOT / results).iterdir() if p.is_dir())


def compare(results, ref_root, ref_arm, backend, out):
    rows = []
    for name in movies(results):
        a = ROOT / results / name / f'{backend}-none'
        b = Path(ref_root) / name / ref_arm
        row = {'movie': name}
        try:
            row['exit'] = json.loads((a / 'RUN.json').read_text())['exit']
            ma, mb = mrc(a / 'output/movie.mrc'), mrc(b / 'output/movie.mrc')
            row['sum_equal'] = bool(ma.shape == mb.shape and np.array_equal(ma, mb))
            row['sum_max_abs_diff'] = None if ma.shape != mb.shape else float(np.max(np.abs(ma.astype(np.float64) - mb)))
            row['star_equal'] = (a / 'output/movie.star').read_bytes() == (b / 'output/movie.star').read_bytes()
            fixture = ROOT / 'fixtures' / name
            row['field_c1'] = field_metrics(a / 'output/movie.star', fixture / 'RECEIPT.json')
            row['field_ref'] = field_metrics(b / 'output/movie.star', fixture / 'RECEIPT.json')
        except Exception as exc:                       # retained as a row, never skipped
            row['error'] = f'{type(exc).__name__}: {exc}'
        rows.append(row)
    summary = {'n': len(rows), 'errors': sum('error' in r for r in rows), 'sum_equal': sum(r.get('sum_equal') is True for r in rows),
               'star_equal': sum(r.get('star_equal') is True for r in rows), 'nonzero_exit': sum(r.get('exit') not in (0, None) for r in rows)}
    Path(out).write_text(json.dumps({'ref_root': str(ref_root), 'ref_arm': ref_arm, 'backend': backend, 'summary': summary, 'rows': rows}, indent=1) + '\n')
    print(json.dumps(summary))


def metrics(results, backend, out):
    rows = []
    for name in movies(results):
        a = ROOT / results / name / f'{backend}-none'
        row = {'movie': name}
        try:
            row['exit'] = json.loads((a / 'RUN.json').read_text())['exit']
            row['field'] = field_metrics(a / 'output/movie.star', ROOT / 'fixtures' / name / 'RECEIPT.json')
            log = (a / 'stdout.log').read_text()
            row['converged_lines'] = {'global_no': log.count('Global Alignment] completed; converged=no'), 'patch_no': log.count('Patch Alignment] completed; converged=no')}
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
        rows.append(row)
    Path(out).write_text(json.dumps(rows, indent=1) + '\n'); print('rows', len(rows), 'errors', sum('error' in r for r in rows))


if __name__ == '__main__':
    {'run': lambda: run(*sys.argv[2:5]), 'compare': lambda: compare(*sys.argv[2:7]), 'metrics': lambda: metrics(*sys.argv[2:5])}[sys.argv[1]]()
