#!/usr/bin/env python3
"""24-tutorial-movie arms against the frozen RC0 baseline (docs/post_rc0/c1-20261022/QUALIFICATION_PLAN.md row T24).

  c1_tutorial24.py run ARM BINARY G|L [--cpu]     one arm, command as RC0 QF's s0 reference (--j 2 on the 2-CPU lane, + --ingest_witness)
  c1_tutorial24.py compare BASE_TREE CAND_TREE LABEL   compare_output_trees --products-only, JSON under $C1_SCR/t24/compare/
  c1_tutorial24.py attribute CFG                  which differing products each single-fix arm reproduces, from the compare JSONs
Inputs are read in place: the tutorial movies and gain are symlinked into a per-arm cwd; nothing is written to the data directory.
"""
import json, os, subprocess, sys
from pathlib import Path

SCR = Path(os.environ['C1_SCR']); SRC = SCR / 'src'; T24 = SCR / 't24'
DATA = Path(os.environ['C1_TUTORIAL']); FROZEN = Path(os.environ['C1_FROZEN_RC0'])
sys.path.insert(0, str(SRC / 'docs/rc0/qf/tools'))
import qual_lib as q  # noqa: E402  (QF_* variables are set by c1_env.sh)

CMP = SRC / 'docs/issue85_laneC/compare_output_trees.py'
BASE_ARGS = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150', '--seed', '1',
             '--expected_frames', '24', '--gainref', 'Movies/gain.mrc', '--ingest', 'auto']


def run(arm, binary, cfg, cpu=False):
    d = T24 / f'{arm}-{cfg}'; cwd = d / 'cwd'
    if d.exists(): raise SystemExit(f'{d} exists; refusing to overwrite (new iteration needs a new arm name)')
    cwd.mkdir(parents=True); os.symlink(DATA / 'Movies', cwd / 'Movies')
    (cwd / 'movies.star').write_bytes((DATA / 'movies.star').read_bytes())
    args = ['--i', 'movies.star', '--o', f'{d}/out/', '--j', '2', *BASE_ARGS]
    if cfg == 'L': args += ['--patch_x', '5', '--patch_y', '5']
    wit = d / 'ingest-witness.txt'
    if not cpu: args += ['--gpu', '0']
    args += ['--ingest_witness', str(wit)]
    rec = q.run_case(f'{arm}-{cfg}', binary, args, cwd, d / 'logs', gpu=not cpu,
                     extra_env={'OMP_NUM_THREADS': '2'}, witness=wit)
    rec['input_star_sha256'] = q.sha256_file(DATA / 'movies.star')
    (d / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(arm, cfg, 'rc', rec.get('rc'), 'wall_s', rec.get('wall_s'), 'witness', rec.get('ingest_witness', [])[:1])
    sys.exit(0 if rec.get('rc') == 0 else 1)


def compare(base, cand, label):
    manifest = next((p for p in [Path(base) / '../manifest.json', Path(base).parent / 'manifest.json'] if p.exists()), None)
    manifest = manifest or FROZEN / ('multigpu/' + ('L' if label.endswith('L') else 'G') + '/manifest.json')
    out = T24 / 'compare'; out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, '-I', str(CMP), str(base), str(cand), '--manifest', str(manifest),
                        '--input-star', str(DATA / 'movies.star'), '--products-only', '--json-out', str(out / f'{label}.json')],
                       capture_output=True, text=True)
    print(label, 'rc', r.returncode, r.stdout.strip().splitlines()[-1:] or r.stderr.strip()[-300:])
    sys.exit(r.returncode)


def attribute(cfg):
    """Per changed product (F -> C1), which of the arms reproduces C1's product bytes."""
    cmpd = T24 / 'compare'
    def diff(label):
        p = cmpd / f'{label}.json'
        return set(json.loads(p.read_text()).get('different_products', [])) if p.exists() else None
    out = {'cfg': cfg, 'arms': {}}
    f_c1 = diff(f'F-fresh_vs_c1-{cfg}')
    out['F_fresh_vs_C1_changed'] = sorted(f_c1) if f_c1 is not None else None
    for arm in ('N', 'only254', 'only260', 'only270'):
        d_f = diff(f'F-fresh_vs_{arm}-{cfg}')           # what this arm changes relative to F
        d_c = diff(f'{arm}_vs_c1-{cfg}')                # where this arm still differs from C1
        out['arms'][arm] = {'changed_vs_F': sorted(d_f) if d_f is not None else None, 'differs_from_C1': sorted(d_c) if d_c is not None else None}
    if f_c1 is not None:
        rows = {}
        for prod in sorted(f_c1):
            reproduced = [a for a, v in out['arms'].items() if v['differs_from_C1'] is not None and prod not in v['differs_from_C1']]
            rows[prod] = reproduced
        out['product_reproduced_by'] = rows
        out['unattributed_to_any_arm'] = sorted(p for p, r in rows.items() if not r)
    (T24 / f'attribution-{cfg}.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in out.items()}))


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'run': run(sys.argv[2], sys.argv[3], sys.argv[4], '--cpu' in sys.argv)
    elif c == 'compare': compare(*sys.argv[2:5])
    elif c == 'attribute': attribute(sys.argv[2])
