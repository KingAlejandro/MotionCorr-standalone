#!/usr/bin/env python3
"""One-shot CPU plumbing pilot. No campaign, gate changes, retries or endpoint math."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import struct
import subprocess
import sys

BASE = 'c0ee115c8348df54732f47dbef930b541b2a364a'
PLAN = Path('/mnt/clathrin/mc-i61-plan-c0ee115c-dbe9tcqr/plan')
PROJECT = Path('/home/alex/mc-issue61/proj/cpu')
HISTORY = Path('/home/alex/mc-issue61')
BIN = Path('/home/alex/relion-container-tests/bin/relion-container-bin-r2')
IMAGE = Path('/home/alex/relion-container-tests/sifs/relion-5.1.0-cuda12.8-sm80-full-plus-tomo-r2.sif')
RUNNER = Path('/home/alex/relion-container-tests/src/docker-relion-cpu/scripts/relion-container-run')
THREADS = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'BLIS_NUM_THREADS')
EXPECTED = {
    str(BIN/'relion_reconstruct'): 'f8fe0e90056d656e286e58d946117275bc07aac3683168041733875dd39b46fd',
    str(BIN/'relion_postprocess'): '6809c6977f7c3d4e11261fc438a0ed829d0577c0313d5f78ba9f429340713100',
    str(IMAGE): 'b4f659198f78a0a909882d17e254dcaf185c20c68e6f9079e87be303ee225c3c',
    str(PROJECT/'MaskCreate/job020/mask.mrc'): '48a32f4dc7baa2285bbd81ead93281b80387f54cec12e496d3c656dd3507a975',
    str(PROJECT/'mtf_k2_200kV.star'): '8027b174b87bb74888d3b8514223ddf9bd3e493fac43c65756e61b0bc5da2d4c',
}


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def digest(path, offset=0):
    h = hashlib.sha256()
    with path.open('rb') as f:
        f.seek(offset)
        for block in iter(lambda: f.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def identity(path, mrc=False):
    before = path.stat()
    result = {'path': str(path), 'resolved': str(path.resolve(strict=True)),
              'size': before.st_size, 'sha256': digest(path)}
    if mrc:
        with path.open('rb') as f:
            h = f.read(1024)
        nx, ny, nz, mode = struct.unpack_from('<4i', h)
        mx, my, mz = struct.unpack_from('<3i', h, 28)
        cell = struct.unpack_from('<3f', h, 40)
        nsymbt = struct.unpack_from('<i', h, 92)[0]
        assert min(nx, ny, nz, mx, my, mz) > 0 and mode in (1, 2, 6, 12)
        assert nsymbt >= 0
        bpp = {1: 2, 2: 4, 6: 2, 12: 2}[mode]
        assert before.st_size == 1024 + nsymbt + nx*ny*nz*bpp, str(path)
        result.update(geometry={'shape': [nx, ny, nz], 'mode': mode, 'nsymbt': nsymbt,
                                'sampling': [cell[0]/mx, cell[1]/my, cell[2]/mz]},
                      core_header_sha256=hashlib.sha256(h[:224]).hexdigest(),
                      payload_sha256=digest(path, 1024+nsymbt))
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    return result


def executable(name):
    found = shutil.which(name)
    if found is None:
        raise FileNotFoundError(f"executable unavailable on PATH: {name}")
    return Path(found).resolve(strict=True)


def probe(argv):
    p = subprocess.run(argv, capture_output=True, text=True)
    return {'argv': argv, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}


def environment(root):
    e = os.environ.copy()
    # A private writable home/tmp; all historical project/data mounts are read-only.
    args = ['--cleanenv', '--bind', '/home/alex/mc-issue61:/home/alex/mc-issue61:ro',
            '--bind', '/home/alex/relion-container-tests:/home/alex/relion-container-tests:ro',
            '--bind', f'{PROJECT}:{PROJECT}:ro', '--bind', f'{PLAN.parent}:{PLAN.parent}:ro', '--bind', f'{root}:{root}',
            '--env', 'CUDA_VISIBLE_DEVICES=', '--env', f'TMPDIR={root}/tmp',
            '--env', f'HOME={root}/home']
    for k in THREADS:
        args += ['--env', k+'=1']
        e[k] = '1'
    e.update(CUDA_VISIBLE_DEVICES='', RELION_CONTAINER_IMAGE=str(IMAGE),
             RELION_CONTAINER_RUNTIME='apptainer', RELION_CONTAINER_RUN_ARGS=' '.join(args),
             APPTAINER_TMPDIR=str(root/'tmp'), APPTAINER_CACHEDIR=str(root/'tmp'))
    for k in ('SINGULARITYENV_HOME', 'APPTAINERENV_HOME', 'APPTAINER_CONTAINER', 'SINGULARITY_CONTAINER'):
        e.pop(k, None)
    return e


def selected_jobs(jobs, root):
    selected = [j for j in jobs if j['subset'] == 'held']
    assert len(selected) == 4
    assert {(j['arm'], j['half']) for j in selected} == {(a, h) for a in ('baseline', 'thinned') for h in (1, 2)}
    out = []
    for j in selected:
        assert j['cwd'] == str(PROJECT) and j['status'] == 'UNRUN' and j['omitted_movie'] is None
        expected = [str(BIN/'relion_reconstruct'), '--i', str(PLAN/'stars'/j['arm']/'held.star'),
                    '--o', str(PLAN/j['output']), '--sym', 'D2', '--subset', str(j['half']), '--pad', '2', '--ctf']
        assert j['argv'] == expected
        staged = dict(j, original_argv=j['argv'], argv=list(j['argv']))
        staged['argv'][4] = str(root/j['output'])  # Only the output moves; input/cwd/settings stay exact.
        out.append(staged)
    return out


def preflight(root):
    assert set(os.sched_getaffinity(0)) == {14, 15}
    src = root/'sources'
    source_hashes = json.loads((src/'source_hashes.json').read_text())
    for name, value in source_hashes.items():
        assert digest(src/name) == value
    spec = importlib.util.spec_from_file_location('frozen_planner', src/'i61_thinning_plan.py')
    planner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(planner)
    m = json.loads((PLAN/'manifest.json').read_text())
    jobs = json.loads((PLAN/'jobs.json').read_text())
    assert digest(PLAN/'jobs.json') == m['jobs_sha256'] and len(jobs) == m['job_count'] == 92
    assert all(j['status'] == 'UNRUN' for j in jobs) and not list((PLAN/'rec').rglob('*.mrc'))
    assert digest(src/'i61_thinning_plan.py') == m['planner_sha256']
    assert digest(PLAN.parent/'i61_thinning_plan.py') == m['planner_sha256']
    assert m['selection']['seed'] == 61 and m['selection']['requested_fraction'] == '19/20'
    assert m['scientific_verdict'] == 'INCONCLUSIVE' and m['scientific_certification_accepted'] is False
    assert m['gate_policy'] is None and m['design_truth_status'] == 'UNVALIDATED'
    assert len(m['selection']['held_movies']) == 22 and len(m['subsets']) == 46
    for item in m['inputs'].values():
        assert digest(Path(item['path'])) == item['sha256']
    source = Path(m['inputs']['particles']['path'])
    lines, cols, rows = planner.read_particles(source.read_bytes())
    assert len(rows) == 4452
    held = set(m['selection']['held_movies'])
    thin = set()
    for s in m['selection']['strata']:
        group = [r for r in rows if r['movie'] == s['movie'] and r['half'] == str(s['half'])]
        assert len(group) == s['input_count'] and len(s['selected_rows']) == s['retained_count'] == len(group)*19//20
        for chosen in s['selected_rows']:
            r = rows[chosen['index']]
            assert r in group and r['row_sha256'] == chosen['sha256']
            assert r['index'] not in thin
            thin.add(r['index'])
    assert len(thin) == 3870
    subsets = []
    for s in m['subsets']:
        p = PLAN/s['star']
        eligible = {r['index'] for r in rows if r['movie'] in held and r['movie'] != s['omitted_movie']}
        keep = eligible if s['arm'] == 'baseline' else eligible & thin
        assert digest(p) == s['sha256']
        assert p.read_bytes() == planner.subset_bytes(lines, rows, keep)
        assert len(keep) == s['count']
        subsets.append({'star': s['star'], 'sha256': s['sha256'], 'count': len(keep),
                        'halves': dict(Counter(rows[i]['half'] for i in keep))})
    stacks, physical_ids = {}, set()
    image_col = cols.index('_rlnImageName')
    for row in rows:
        index, name = planner.image_identity(row['values'][image_col])
        p = PROJECT/name
        real = p.resolve(strict=True)
        if str(real) not in stacks:
            stacks[str(real)] = identity(p, mrc=True)
        item = stacks[str(real)]
        assert item['geometry']['shape'][:2] == [256, 256]
        assert int(index) <= item['geometry']['shape'][2]
        st = p.stat()
        key = (st.st_dev, st.st_ino, int(index))
        assert key not in physical_ids
        physical_ids.add(key)
    inputs = []
    for name, expected in EXPECTED.items():
        item = identity(Path(name), mrc=name.endswith('.mrc'))
        inputs.append(item)
        assert item['sha256'] == expected, f'historical identity mismatch: {name}'
    inputs += [identity(RUNNER), identity(source), identity(PLAN/'manifest.json'), identity(PLAN/'jobs.json'),
               identity(PLAN.parent/'design.json'), identity(PLAN.parent/'PLAN_RUN.json'),
               identity(PLAN.parent/'PILOT_INTENT.json'), identity(Path(sys.executable)), identity(executable('apptainer'))]
    # Establish exact historical command, omitted-option defaults, and observed threshold.
    command_lines = [x for x in (HISTORY/'jobs_postprocess.txt').read_text().splitlines()
                     if '/rec/cpu/held22_half1_class001_unfil.mrc' in x]
    assert len(command_lines) == 1
    t = shlex.split(command_lines[0])
    opts = ['--mask', 'MaskCreate/job020/mask.mrc', '--angpix', '1.244531', '--mtf', 'mtf_k2_200kV.star',
            '--mtf_angpix', '0.885', '--auto_bfac', '--autob_lowres', '10']
    assert t == ['cd', str(PROJECT), '&&', str(BIN/'relion_postprocess'), '--i',
                 str(HISTORY/'rec/cpu/held22_half1_class001_unfil.mrc'), '--o', str(HISTORY/'pp/cpu/held22'),
                 *opts, '>', str(HISTORY/'logs/pp_cpu_held22.log'), '2>&1']
    default_probe = json.loads((root/'defaults.json').read_text())
    assert default_probe['exit'] == 0
    helptext = default_probe['stdout'] + default_probe['stderr']
    assert '--randomize_at_fsc (0.8)' in helptext and '--random_seed (0)' in helptext
    old_log = (HISTORY/'logs/pp_cpu_held22.log').read_text()
    assert 'randomize phases beyond:       16.7684 Angstroms' in old_log
    pp = []
    for arm in ('baseline', 'thinned'):
        # Keep historical threshold/seed defaults, rather than adding a new resolution or seed.
        pp.append({'arm': arm, 'cwd': str(PROJECT), 'argv': [str(BIN/'relion_postprocess'), '--i',
                   str(root/f'rec/{arm}/held_half1_class001_unfil.mrc'), '--o',
                   str(root/f'pp/{"cpu" if arm == "baseline" else "thinned"}/held22'), *opts],
                   'log': f'logs/pp_{arm}_held22.log', 'status': 'UNRUN'})
    staged = {'source_commit': BASE, 'reconstruct': selected_jobs(jobs, root), 'postprocess': pp,
              'original_plan': str(PLAN), 'seed': 61, 'requested_count_fraction': '19/20',
              'phase_randomization_seed': 0, 'phase_randomization_fsc_threshold': 0.8,
              'scientific_verdict': 'INCONCLUSIVE', 'analysis': 'POSTHOC_EXPLORATORY_POINT_ONLY'}
    save(root/'execution_plan.json', staged)
    historical = {n: identity(HISTORY/n) for n in ['jobs_postprocess.txt', 'logs/pp_cpu_held22.log',
                                                  'results/environment.txt', 'scripts/i61_stageB_pp.py']}
    for n in historical:
        (root/('historical_'+Path(n).name)).write_bytes((HISTORY/n).read_bytes())
    # Probe, then immediately release the historical global lock; never hold it over this pilot.
    global_probe = probe(['flock', '-n', '/tmp/motioncorr-bench.lock', 'true'])
    e = environment(root)
    receipt = {'utc': utc(), 'status': 'PASS', 'source_commit': BASE, 'hostname': socket.gethostname(),
               'affinity': sorted(os.sched_getaffinity(0)), 'no_controlled_timings': True,
               'environment': {k: e[k] for k in (*THREADS, 'CUDA_VISIBLE_DEVICES', 'RELION_CONTAINER_IMAGE',
                             'RELION_CONTAINER_RUNTIME', 'RELION_CONTAINER_RUN_ARGS', 'APPTAINER_TMPDIR', 'APPTAINER_CACHEDIR')},
               'inputs': inputs, 'stacks': list(stacks.values()), 'source_hashes': source_hashes,
               'subsets': subsets, 'historical': historical, 'global_lock_probe': global_probe,
               'occupancy': probe(['ps', '-eo', 'pid,psr,pcpu,args', '--sort=-pcpu']),
               'gpu_inventory_readonly': probe(['nvidia-smi', '--query-gpu=index,uuid,name', '--format=csv,noheader']),
               'gpu_processes_readonly': probe(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,process_name', '--format=csv,noheader']),
               'execution_plan_sha256': digest(root/'execution_plan.json')}
    save(root/'preflight.json', receipt)
    print('PREFLIGHT PASS', root, flush=True)


def execute(root):
    assert set(os.sched_getaffinity(0)) == {14, 15}
    # Exclusive start marker forbids re-entering a failed or interrupted pilot.
    save(root/'STARTED.json', {'utc': utc(), 'pid': os.getpid(), 'affinity': sorted(os.sched_getaffinity(0))})
    receipt = json.loads((root/'preflight.json').read_text())
    assert receipt['status'] == 'PASS' and digest(root/'execution_plan.json') == receipt['execution_plan_sha256']
    # Reconcile exact files after preflight, immediately before any numerical work.
    for item in receipt['inputs'] + receipt['stacks']:
        assert digest(Path(item['path'])) == item['sha256'], item['path']
    for s in receipt['subsets']:
        assert digest(PLAN/s['star']) == s['sha256']
    plan = json.loads((root/'execution_plan.json').read_text())
    env = environment(root)
    save(root/'launch_resources.json', {'utc': utc(), 'affinity': sorted(os.sched_getaffinity(0)),
         'pid': os.getpid(), 'occupancy': probe(['ps','-eo','pid,psr,pcpu,args','--sort=-pcpu']),
         'gpu_inventory_readonly': probe(['nvidia-smi','--query-gpu=index,uuid,name','--format=csv,noheader']),
         'gpu_processes_readonly': probe(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,process_name','--format=csv,noheader']),
         'cpu_lock': '/tmp/motioncorr-i61-cpu-14-15.lock', 'CUDA_VISIBLE_DEVICES': ''})
    for d in ('rec/baseline', 'rec/thinned', 'pp/cpu', 'pp/thinned', 'logs', 'results'):
        (root/d).mkdir(parents=True, exist_ok=True)
    records = []
    for i, job in enumerate(plan['reconstruct'] + plan['postprocess']):
        log = root/job['log']
        record = {'index': i, 'argv': job['argv'], 'cwd': job['cwd'], 'start_utc': utc(), 'status': 'RUNNING'}
        save(root/f'job_{i}_started.json', record)
        with log.open('xb') as out:
            p = subprocess.Popen(job['argv'], cwd=job['cwd'], env=env, stdout=out, stderr=subprocess.STDOUT)
            save(root/f'job_{i}_pid.json', {'pid': p.pid, 'utc': utc(), 'affinity': sorted(os.sched_getaffinity(p.pid))})
            code = p.wait()
        text = log.read_text(errors='replace')
        record.update(exit=code, end_utc=utc(), log=str(log), log_sha256=digest(log),
                      status='PASS' if code == 0 and 'ERROR' not in text else 'FAIL')
        save(root/f'job_{i}_exit.json', record)
        records.append(record)
        print(i, record['status'], code, flush=True)
        assert record['status'] == 'PASS', 'failed job; no retries, remaining jobs UNRUN'
        if i < 4:
            image = identity(Path(job['argv'][4]), mrc=True)
            assert image['geometry']['shape'] == [256, 256, 256] and image['geometry']['mode'] == 2
            save(root/f'map_{i}.json', image)
    # Run the existing analyser unchanged; it may refuse this deliberately incomplete JK set.
    aenv = env.copy()
    aenv.update(I61_ROOT=str(root), I61_OUT='pilot_point_only_attempt.json', I61_REAL='cpu thinned',
                I61_CTRL='', I61_SENSITIVITY_CERT='')
    cmd = [sys.executable, str(root/'sources/i61_analyse_B.py')]
    p = subprocess.run(cmd, env=aenv, capture_output=True, text=True)
    save(root/'analyser_attempt.json', {'argv': cmd, 'environment': {k: aenv[k] for k in ['I61_ROOT','I61_OUT','I61_REAL','I61_CTRL','I61_SENSITIVITY_CERT']},
         'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
         'status': 'PASS' if p.returncode == 0 else 'INCOMPATIBLE_WITH_POINT_ONLY_PILOT'})
    analyser_exit = p.returncode
    products = []
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.suffix in ('.mrc','.star','.eps','.pdf','.log') and not p.is_relative_to(root/'sources'):
            products.append(identity(p, mrc=p.suffix == '.mrc'))
    save(root/'products.json', products)
    save(root/'DONE.json', {'utc': utc(), 'execution_status': 'PASS', 'reconstructions': 4, 'postprocess': 2,
         'scientific_verdict': 'INCONCLUSIVE', 'analysis_status': 'POINT_ONLY', 'jackknife': 'UNRUN',
         'B1_analysis': 'UNRUN' if analyser_exit else 'SEE_ANALYSER', 'SE_CI_power_sensitivity': 'UNRUN'})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage', choices=['preflight','execute'])
    ap.add_argument('root', type=Path)
    args = ap.parse_args()
    root = args.root.resolve(strict=True)
    assert str(root).startswith('/mnt/clathrin/mc-i61-pilot-c0ee115c-') and root != PLAN.parent
    with open('/tmp/motioncorr-i61-cpu-14-15.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            (preflight if args.stage == 'preflight' else execute)(root)
        except BaseException as exc:
            save(root/f'{args.stage}_FAIL.json', {'utc': utc(), 'pid': os.getpid(), 'error': repr(exc)})
            raise


if __name__ == '__main__':
    main()
