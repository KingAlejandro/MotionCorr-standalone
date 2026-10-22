#!/usr/bin/env python3
"""24-tutorial-movie arms against the frozen RC0 baseline (QUALIFICATION_PLAN.md rows T24, D12). Tools v2: fail-closed comparison handling.

  c1_tutorial24.py run ARM BINARY G|L [--cpu]       one arm, command as RC0 QF's s0 reference (--j 2, + --ingest_witness on CUDA); nonblocking GPU3 lease
  c1_tutorial24.py dataset ARM BINARY G|L           one-worker run_dataset.py endpoint (needs the lease held by c1_gpu_run.sh: C1_LEASE_HELD=1)
  c1_tutorial24.py compare BASE_TREE CAND_TREE LABEL    comparator + validation; writes compare/LABEL.{json,run.json,class.json}; exit 0 IDENTICAL, 1 DIFFERENT, 2 INVALID
  c1_tutorial24.py attribute CFG                    attribution from the validated class files only; exit 0 complete, 1 complete with blockers, 2 invalid
A comparison is DIFFERENT only when the comparator wrote a complete, internally consistent products report (24 movies, expected product names only, no
duplicates, status/rc agree). Anything else (missing/truncated/malformed report, 'reason' errors, rc outside 0/1, wrong counts) is INVALID and never
counts as identity or as a difference. N reproduces the combination of #254+#260+#270: it is not attribution to an individual fix.
"""
import hashlib, json, os, subprocess, sys
from pathlib import Path

SCR = Path(os.environ['C1_SCR']); SRC = SCR / 'src'; T24 = SCR / os.environ.get('C1_T24_DIR', 't24')   # a new iteration uses a new directory
DATA = Path(os.environ['C1_TUTORIAL']); FROZEN = Path(os.environ['C1_FROZEN_RC0'])
sys.path.insert(0, str(SRC / 'docs/rc0/qf/tools'))
import qual_lib as q  # noqa: E402  (QF_* variables are set by c1_env.sh)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import c1_lane; c1_lane.install()  # noqa: E402

CMP = SRC / 'docs/issue85_laneC/compare_output_trees.py'
BASE_ARGS = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150', '--seed', '1',
             '--expected_frames', '24', '--gainref', 'Movies/gain.mrc', '--ingest', 'auto']


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(arm, binary, cfg, cpu=False):
    d = T24 / f'{arm}-{cfg}'; cwd = d / 'cwd'
    if d.exists(): raise SystemExit(f'{d} exists; refusing to overwrite (new iteration needs a new arm name)')
    cwd.mkdir(parents=True); os.symlink(DATA / 'Movies', cwd / 'Movies')
    (cwd / 'movies.star').write_bytes((DATA / 'movies.star').read_bytes())
    args = ['--i', 'movies.star', '--o', f'{d}/out/', '--j', '2', *BASE_ARGS]
    if cfg == 'L': args += ['--patch_x', '5', '--patch_y', '5']
    wit = d / 'ingest-witness.txt'
    if not cpu: args += ['--gpu', '0', '--ingest_witness', str(wit)]
    else:       # CPU-only binaries have no ingest route: drop the CUDA-route options
        i = args.index('--ingest'); del args[i:i + 2]
    rec = c1_lane.run_case_nb(f'{arm}-{cfg}', binary, args, cwd, d / 'logs', gpu=not cpu,
                              extra_env={'OMP_NUM_THREADS': '2'}, witness=None if cpu else wit)
    rec['input_star_sha256'] = q.sha256_file(DATA / 'movies.star')
    (d / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(arm, cfg, 'rc', rec.get('rc'), rec.get('error') or '', 'wall_s', rec.get('wall_s'), 'witness', (rec.get('ingest_witness') or [])[:1])
    sys.exit(0 if rec.get('rc') == 0 else 1)


def _load(p):
    try: return json.loads(Path(p).read_text())
    except (OSError, ValueError): return None


def dataset(arm, binary, cfg):
    if os.environ.get('C1_LEASE_HELD') != '1': raise SystemExit('dataset needs the GPU3 lease held by c1_gpu_run.sh (C1_LEASE_HELD=1); refusing to run unleased')
    d = T24 / f'{arm}-ds-{cfg}'; cwd = d / 'cwd'
    if d.exists(): raise SystemExit(f'{d} exists; refusing to overwrite')
    cwd.mkdir(parents=True); os.symlink(DATA / 'Movies', cwd / 'Movies')
    (cwd / 'movies.star').write_bytes((DATA / 'movies.star').read_bytes())
    wargs = [*BASE_ARGS, *(['--patch_x', '5', '--patch_y', '5'] if cfg == 'L' else []), '--j', '2']
    out = d / 'out'
    cmd = ['taskset', '-c', q.CPUS, q.PY, str(SRC / 'tools/multi_gpu/run_dataset.py'), '--binary', str(binary), '--star', 'movies.star',
           '--out', str(out), f"--launcher-args=--devices {q.LANE_GPU_UUID} --cpus '{q.CPUS}'", '--', *wargs]
    env = q.base_env(False); env['OMP_NUM_THREADS'] = '2'
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    (d / 'driver.log').write_text(p.stdout + '\n--stderr--\n' + p.stderr)
    ds, ws = _load(out / 'dataset_status.json'), _load(out / 'workers/status.json')
    probs = []
    if p.returncode: probs.append(f'driver rc {p.returncode}')
    if not ds or not ws: probs.append('missing dataset_status.json or workers/status.json')
    else:
        if not (ds.get('verdict') == 'PASS' and ds.get('dataset_ready') and ds.get('workers_complete')): probs.append(f'dataset {ds.get("verdict")}/{ds.get("dataset_ready")}')
        if ws.get('verdict') != 'PASS' or ws.get('n_workers') != 1: probs.append(f'workers {ws.get("verdict")} n={ws.get("n_workers")}')
        gw = ws.get('gpu_witness') or {}
        if not gw.get('all_pids_witnessed_on_intended_distinct_devices') or gw.get('distinct_devices_witnessed') != 1: probs.append(f'device witness {gw}')
        if [x.get('uuid') for x in ws.get('devices') or []] != [q.LANE_GPU_UUID]: probs.append('worker device is not the lane GPU3 UUID')
        pc = ws.get('process_cleanup') or {}
        if not pc.get('complete') or pc.get('unexpected_descendants'): probs.append(f'cleanup {pc}')
        if ds.get('process_ownership_errors'): probs.append('process ownership errors')
    merged = out / 'merged'
    nm = len(list((merged / 'Movies').glob('*.mrc'))) if merged.exists() else 0
    if nm != 24 or not (merged / 'corrected_micrographs.star').exists(): probs.append(f'merged tree: {nm} mrc, joint STAR {(merged / "corrected_micrographs.star").exists()}')
    rec = {'arm': arm, 'cfg': cfg, 'binary': str(binary), 'binary_sha256': q.sha256_file(binary), 'problems': probs}
    base = T24 / f'{arm}-{cfg}' / 'out'
    if merged.exists() and base.exists():
        label = f'{arm}-ds-{cfg}_vs_{arm}-standalone-{cfg}'
        state = _compare(base, merged, label, cfg)
        rec['products_vs_standalone'] = state
        if state['state'] != 'IDENTICAL': probs.append(f'products vs the standalone {arm}-{cfg} arm: {state["state"]} {state.get("reasons") or state.get("products")}')
    else:
        probs.append('no standalone arm to compare with')
    rec['verdict'] = 'PASS' if not probs else 'FAIL'
    (d / 'DATASET.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(arm, cfg, rec['verdict'], probs)
    sys.exit(0 if not probs else 1)


def expected_products(manifest):
    names = set()
    for m in manifest.get('movies') or []:
        stem = Path(str(m)).stem
        names |= {f'Movies/{stem}.mrc', f'Movies/{stem}.star'}
    names.add(manifest.get('joint_star') or 'corrected_micrographs.star')
    return names


def classify(rc, report, manifest):
    """Pure validation of one comparator invocation. Returns {'state': IDENTICAL|DIFFERENT|INVALID, 'products': [...], 'reasons': [...]}."""
    bad = []
    if rc not in (0, 1): bad.append(f'comparator rc {rc} is neither 0 (identical) nor 1 (differences)')
    if not isinstance(report, dict): return {'state': 'INVALID', 'products': [], 'reasons': bad + ['report missing or not a JSON object']}
    if 'reason' in report: bad.append(f'comparator error: {report.get("reason")}')
    status = report.get('status')
    if status not in ('PASS', 'FAIL'): bad.append(f'status {status!r}')
    n = len(manifest.get('movies') or [])
    for side in ('base', 'candidate'):
        s = report.get(side)
        if not isinstance(s, dict) or s.get('movie_count') != n or s.get('mrc_count') != n or s.get('star_count') != n:
            bad.append(f'{side} validation summary missing or not {n} movies/MRC/STAR')
    if report.get('comparison_scope') != 'products': bad.append(f'comparison_scope {report.get("comparison_scope")!r}')
    mrc = report.get('mrc_sha256')
    if not isinstance(mrc, dict) or len(mrc) != n: bad.append('mrc_sha256 map missing or incomplete')
    prods, files = report.get('different_products'), report.get('different_files')
    for name, v in (('different_products', prods), ('different_files', files)):
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v): bad.append(f'{name} missing or not a list of strings')
        elif len(set(v)) != len(v): bad.append(f'{name} has duplicates')
    if not bad:
        exp = expected_products(manifest)
        if not set(prods) <= set(files): bad.append('different_products not a subset of different_files')
        if not set(prods) <= exp: bad.append(f'products outside the expected inventory: {sorted(set(prods) - exp)[:5]}')
        if (status == 'PASS') != (rc == 0): bad.append(f'status {status} inconsistent with rc {rc}')
        if status == 'PASS' and (prods or files): bad.append('PASS report lists differences')
        if status == 'FAIL' and not files: bad.append('FAIL report lists no differences')
    if bad: return {'state': 'INVALID', 'products': [], 'reasons': bad}
    return {'state': 'IDENTICAL' if status == 'PASS' else 'DIFFERENT', 'products': sorted(prods), 'reasons': []}


def _manifest(label, base):
    cfg = 'L' if label.endswith('L') else 'G'
    for p in (Path(base).parent / 'manifest.json', FROZEN / f'multigpu/{cfg}/manifest.json'):
        if p.exists(): return p
    return FROZEN / f'multigpu/{cfg}/manifest.json'


def _compare(base, cand, label, cfg=None):
    out = T24 / 'compare'; out.mkdir(parents=True, exist_ok=True)
    mp = _manifest(label, base) if cfg is None else FROZEN / f'multigpu/{cfg}/manifest.json'
    rep = out / f'{label}.json'
    if rep.exists(): raise SystemExit(f'{rep} exists; refusing to overwrite a comparison report')
    cmd = [sys.executable, '-I', str(CMP), str(base), str(cand), '--manifest', str(mp), '--input-star', str(DATA / 'movies.star'),
           '--products-only', '--json-out', str(rep)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    manifest = _load(mp) or {}
    cls = classify(r.returncode, _load(rep), manifest) if mp.exists() else {'state': 'INVALID', 'products': [], 'reasons': ['manifest missing']}
    run = {'cmd': cmd, 'rc': r.returncode, 'stdout': r.stdout, 'stderr': r.stderr, 'base': str(base), 'candidate': str(cand), 'manifest': str(mp),
           'manifest_sha256': _sha(mp) if mp.exists() else None, 'input_star_sha256': _sha(DATA / 'movies.star'), 'comparator_sha256': _sha(CMP),
           'report_sha256': _sha(rep) if rep.exists() else None}
    (out / f'{label}.run.json').write_text(json.dumps(run, indent=1) + '\n')
    (out / f'{label}.class.json').write_text(json.dumps(cls, indent=1) + '\n')
    return cls


def compare(base, cand, label):
    cls = _compare(base, cand, label)
    print(label, cls['state'], cls['reasons'] or f'{len(cls["products"])} differing products')
    sys.exit({'IDENTICAL': 0, 'DIFFERENT': 1}.get(cls['state'], 2))


def attribute(cfg):
    """Per changed product (F -> C1): which arm reproduces C1's bytes. Reads only validated class files; invalid/missing input is never identity."""
    def get(label):
        try:
            c = json.loads((T24 / 'compare' / f'{label}.class.json').read_text())
        except (OSError, ValueError):
            return None, f'{label}: class file missing or unreadable'
        if c.get('state') not in ('IDENTICAL', 'DIFFERENT'):
            return None, f'{label}: {c.get("state")} {c.get("reasons")}'
        return set(c.get('products') or []), None
    problems, out = [], {'cfg': cfg, 'status': 'INVALID', 'note': 'N reproduces the combination #254+#260+#270; it is not attribution to an individual fix'}
    arms = ('N', 'only254', 'only260', 'only270')
    f_c1, e = get(f'F-fresh_vs_c1-{cfg}')
    if e: problems.append(e)
    f_arm, arm_c1 = {}, {}
    for a in arms:
        f_arm[a], e1 = get(f'F-fresh_vs_{a}-{cfg}')
        arm_c1[a], e2 = get(f'{a}_vs_c1-{cfg}')
        problems += [x for x in (e1, e2) if x]
    lane, e = get(f'F-fresh_vs_F-retained-{cfg}')
    out['lane_control_F_fresh_vs_F_retained'] = ('MISSING_OR_INVALID: ' + e) if e else ('IDENTICAL' if not lane else f'DIFFERENT {sorted(lane)[:5]}')
    if problems:
        out['problems'] = problems
        (T24 / f'attribution-{cfg}.json').write_text(json.dumps(out, indent=1) + '\n')
        return out
    rows, blockers = {}, []
    for prod in sorted(f_c1):
        repro = [a for a in arms if prod not in arm_c1[a]]
        incons = [a for a in repro if prod not in f_arm[a]]
        if incons: blockers.append(f'{prod}: comparator inconsistency for {incons} (reproduces C1 bytes yet equals F)')
        singles = [a for a in repro if a != 'N']
        if len(singles) == 1: cls = f'SINGLE_FIX_REPRODUCES:{singles[0]}'
        elif len(singles) > 1: cls = f'AMBIGUOUS_MULTIPLE_SINGLE_ARMS:{singles}'
        elif 'N' in repro: cls = 'COMBINED_NUMERICS_COMPOSITION_ONLY: #254+#260+#270 together reproduce it; per-fix attribution unresolved (interaction or composition)'
        else: cls = 'UNATTRIBUTED: no numerics arm reproduces this change'; blockers.append(f'{prod}: unattributed change')
        rows[prod] = {'reproduced_by': repro, 'classification': cls}
    n_c1 = sorted(arm_c1['N'])
    if n_c1: blockers.append(f'N differs from C1 in {len(n_c1)} products: D2/D3 or an independent fix changed products unexpectedly: {n_c1[:5]}')
    out.update(status='COMPLETE', changed_F_to_C1=len(f_c1), product_attribution=rows, N_vs_C1_unexpected_changes=n_c1, blockers=blockers,
               arms={a: {'changed_vs_F': len(f_arm[a]), 'differs_from_C1': len(arm_c1[a])} for a in arms})
    (T24 / f'attribution-{cfg}.json').write_text(json.dumps(out, indent=1) + '\n')
    return out


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'run': run(sys.argv[2], sys.argv[3], sys.argv[4], '--cpu' in sys.argv)
    elif c == 'dataset': dataset(sys.argv[2], sys.argv[3], sys.argv[4])
    elif c == 'compare': compare(*sys.argv[2:5])
    elif c == 'attribute':
        r = attribute(sys.argv[2]); print(json.dumps({k: v for k, v in r.items() if k != 'product_attribution'}, indent=1))
        sys.exit(2 if r['status'] != 'COMPLETE' else (1 if r['blockers'] else 0))
