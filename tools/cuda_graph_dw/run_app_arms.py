#!/usr/bin/env python3
"""Complete-application arms for the dose-weighting submission experiment.

One binary, three arms selected by MC_DW_MODE (product / async / graph), run
round-robin with the arm order rotated per round so run-order bias is spread
across all three. Products are compared exactly between arms.
"""
import argparse, hashlib, json, os, subprocess, time
from pathlib import Path

ARMS = ["prod", "async", "graph"]
OPTS = ['--i', 'movies.star', '--use_own', '--dose_weighting', '--dose_per_frame', '1.277',
        '--patch_x', '5', '--patch_y', '5', '--bfactor', '150', '--gainref', 'Movies/gain.mrc',
        '--seed', '1', '--gpu', '0', '--j', '6', '--max_io_threads', '6', '--ingest', 'nvcomp']


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--input-dir', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--cpus', default='96-103')
    p.add_argument('--gpu-uuid', required=True)
    p.add_argument('--rounds', type=int, required=True)
    a = p.parse_args()
    a.root.mkdir(parents=True, exist_ok=True)

    env_base = dict(os.environ)
    env_base['CUDA_VISIBLE_DEVICES'] = a.gpu_uuid

    (a.root / 'provenance.json').write_text(json.dumps({
        'binary': str(a.binary), 'binary_sha256': sha(a.binary),
        'input_star_sha256': sha(a.input_dir / 'movies.star'),
        'options': OPTS, 'cpus': a.cpus, 'gpu_uuid': a.gpu_uuid,
        'gpu': subprocess.run(['nvidia-smi', '--query-gpu=index,uuid,name,clocks.max.sm',
                               '--format=csv'], capture_output=True, text=True).stdout,
    }, indent=2))

    records = []
    for r in range(1, a.rounds + 1):
        order = ARMS[(r - 1) % 3:] + ARMS[:(r - 1) % 3]
        for arm in order:
            d = a.root / f'{arm}-{r}'
            out = d / 'output'
            out.mkdir(parents=True, exist_ok=True)
            env = dict(env_base)
            if arm == 'prod':
                env.pop('MC_DW_MODE', None)
            else:
                env['MC_DW_MODE'] = arm
            # Foreign occupancy on the target device is recorded, not asserted
            # away: this box carries other tenants and an abort-on-any-app
            # preflight never fires here.
            occ = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory',
                                  '--format=csv,noheader'], capture_output=True, text=True).stdout
            (d / 'occupancy_before.txt').write_text(occ)
            cmd = ['/usr/bin/time', '-v', '-o', str(d / 'resource.txt'),
                   'taskset', '-c', a.cpus, str(a.binary), *OPTS, '--o', str(out) + '/']
            t0 = time.monotonic()
            with open(d / 'run.log', 'w') as lf:
                rc = subprocess.call(cmd, cwd=a.input_dir, stdout=lf, stderr=subprocess.STDOUT,
                                     env=env)
            wall = time.monotonic() - t0
            logs = sorted(out.rglob('*.log'))
            witness = sum(1 for q in logs
                          if 'DW submission mode: ' + arm in q.read_text(errors='replace'))
            foreign = sum(1 for q in logs
                          for m in ARMS if m != arm and 'DW submission mode: ' + m in q.read_text(errors='replace'))
            records.append({'round': r, 'arm': arm, 'order': order, 'rc': rc,
                            'wall_s': wall, 'logs': len(logs),
                            'mode_witness_logs': witness, 'foreign_mode_logs': foreign})
            print(json.dumps(records[-1]), flush=True)
    (a.root / 'runs.json').write_text(json.dumps(records, indent=2))

    # Exact product comparison, every arm against the product arm of the same round.
    manifest = a.source / 'docs/issue85_laneC/tutorial_24_movie_manifest.json'
    cmp_tool = a.source / 'docs/issue85_laneC/compare_output_trees.py'
    results = []
    for r in range(1, a.rounds + 1):
        base = a.root / f'prod-{r}' / 'output'
        for arm in ('async', 'graph'):
            cand = a.root / f'{arm}-{r}' / 'output'
            js = a.root / f'cmp-{arm}-{r}.json'
            cmd = ['python3', str(cmp_tool), str(base), str(cand),
                   '--manifest', str(manifest), '--input-star', str(a.input_dir / 'movies.star'),
                   '--allow-added-log-line', 'DW submission mode:',
                   '--json-out', str(js)]
            cp = subprocess.run(cmd, capture_output=True, text=True)
            status = 'UNKNOWN'
            if js.exists():
                status = json.loads(js.read_text()).get('status', 'UNKNOWN')
            results.append({'round': r, 'arm': arm, 'rc': cp.returncode, 'status': status,
                            'stderr': cp.stderr.strip()[-400:]})
            print(json.dumps(results[-1]), flush=True)
    (a.root / 'compare.json').write_text(json.dumps(results, indent=2))
    print('APP_ARMS_DONE')


if __name__ == '__main__':
    main()
