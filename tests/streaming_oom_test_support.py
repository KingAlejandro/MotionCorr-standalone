"""Shared D3 fixtures/receipts; all fault switches are test-binary link wrappers."""
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from test_gain_cache import synthetic_frames, write_mrc, write_star
from run_stale_cuda_error_controls import inventory, check_reference, compare_movie, products


def prepare(root):
    root.mkdir(parents=True, exist_ok=False)
    (root / 'Movies').mkdir()
    frames = synthetic_frames()
    for name in ('a', 'b'):
        write_mrc(root / f'Movies/{name}.mrcs', frames)
    write_star(root / 'reference.star', ['Movies/b.mrcs'])
    write_star(root / 'batch.star', ['Movies/a.mrcs', 'Movies/b.mrcs'])
    (root / 'inputs.json').write_text(json.dumps({
        'geometry': [48, 40, len(frames)],
        'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(root.rglob('*')) if p.suffix in ('.mrcs', '.star')}
    }, indent=2) + '\n')
    return frames


def run(binary, root, label, env, star='batch.star'):
    output = root / label
    base_env = {k: v for k, v in os.environ.items() if not k.startswith('MC_')}
    base_env.update(env)
    cmd = [str(binary), '--i', star, '--o', str(output) + '/', '--use_own',
           '--gpu', '0', '--ingest', 'float', '--j', '1', '--seed', '1']
    # Optional external resource guard: invoked before and after EVERY native
    # process, including failed controls, by the bounded qualification harness.
    guard = os.environ.get('MC_D3_SAMPLE_GUARD')
    def health(phase):
        if guard:
            subprocess.run([guard, phase, str(root / (label + '-' + phase))], check=True)
    health('pre')
    receipt = dict(argv=cmd, cwd=str(root), fault_env=env,
                   binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                   numeric_threads={k: base_env.get(k) for k in
                                    ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
                   cuda_visible_devices=base_env.get('CUDA_VISIBLE_DEVICES'),
                   affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None)
    started = time.time()
    with (root / (label + '.log')).open('w') as log:
        process = subprocess.Popen(cmd, cwd=root, env=base_env, stdout=log,
                                   stderr=subprocess.STDOUT, text=True)
        receipt['pid'] = process.pid
        (root / (label + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
        try:
            code = process.wait(timeout=90)
        except subprocess.TimeoutExpired:
            process.kill()  # Only this owned control, never any foreign process.
            process.wait()
            raise
        finally:
            receipt.update(exit=process.returncode, elapsed_seconds=time.time() - started)
            (root / (label + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
            health('post')
    snapshot = {}
    for movie in ('a', 'b'):
        found, problems = products(output, movie)
        snapshot[movie] = dict(problems=problems, products={
            key: dataclasses.asdict(value) if dataclasses.is_dataclass(value)
            else hashlib.sha256(value).hexdigest() for key, value in found.items()})
    receipt['products'] = snapshot
    receipt['inventory'] = sorted(map(str, inventory(output)))
    (root / (label + '.json')).write_text(json.dumps(receipt, indent=2) + '\n')
    return code, (root / (label + '.log')).read_text(), output


def reference(binary, root):
    code, text, output = run(binary, root, 'reference', {}, 'reference.star')
    expected, problems = check_reference(output)
    if code != 0 or problems:
        raise AssertionError(f'reference exit={code}: {problems}\n{text}')
    return expected


def failed_products(output, expected):
    wanted = {Path('Movies/b.mrc'), Path('Movies/b.star')}
    problems = compare_movie(output, 'b', expected)
    if inventory(output) != wanted:
        problems.append(f'failed batch inventory {sorted(map(str, inventory(output)))}; expected b only')
    return problems
