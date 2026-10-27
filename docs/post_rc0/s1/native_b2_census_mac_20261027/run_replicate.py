#!/usr/bin/env python3
"""Mac replicate census, not hash-identical to the frozen census.

Serial five-arm producer; immutable inputs/source/binaries; no automatic retries.
The worker subcommands call the pinned generator without modifying it.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import traceback

REPO = Path(__file__).resolve().parents[4]
STAGE = Path('/tmp/motioncorr-b2-census-mac-20261027').resolve()
SRC = STAGE / 'source'
WORK = STAGE / 'replicate'
BIN = STAGE / 'build/motioncorr'
FWBIN = Path('/tmp/mc-mac-pilot-20261027/build-numpy253/motioncorr')
PINS = {
    str(BIN): 'e978af21352295bfe2cf756fa2916703d2b7e6c6b34c352d58630e7975155946',
    str(FWBIN): 'd57432b87cdeb034c13e52ed920b19c0f819185f6ee92f04f44314337151f546',
}
GEN_SHA = 'a10f694abafc71c146d0e0f2eeb2b1cf2c58131b2dbf6c1b66800405bd126380'
CHECK_SHA = 'b0ab099a256e458b1c8aea6c2ff5d9ceacab10dd81945b025e96e5c8a87b7ff9'
ORDER = ['dose1', 'dose05', 'dose2', 'dose4', 'pedestal0', 'pedestal32',
         'contrast025', 'contrast4', 'outmodel', 'nonsquare']
ARMS = {'OFF': (BIN, 'none', []),
        'B2': (BIN, 'none', ['--experimental_local_b2']),
        'UP': (FWBIN, 'both', ['--experimental_coupled_peak', 'all']),
        'UPFW': (FWBIN, 'both', ['--experimental_coupled_peak', 'all',
                               '--experimental_local_full_width_weight']),
        'FW': (FWBIN, 'none', ['--experimental_local_full_width_weight']),
        'IDENTITY_OFF': (FWBIN, 'none', [])}
MIN_FREE = 10 * 1024**3
LABEL = 'Mac replicate census, not hash-identical to the frozen census'
sys.path[:0] = [str(SRC / 'tools'), str(SRC / 'test-data')]
import numpy as np
import scipy
import generate_realistic_motion as gen
import check_realistic_motion as check


def digest(path, offset=0):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        f.seek(offset)
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def gate(metrics):
    return 'PASS' if all(metrics[k] <= v for k, v in
                         [('rms', .20), ('p95', .40), ('max', .80)]) else 'FAIL'


def moments(receipt):
    r = receipt['recipe']
    n = r['frames'] * r['ny'] * r['nx']
    total = n * receipt['mean']
    squares = n * (receipt['std']**2 + receipt['mean']**2)
    grid = 4 if r['scale'] == .25 else 1
    total_grid = round(total * grid) / grid
    squares_grid = round(squares * grid**2) / grid**2
    # Invert pixels = pedestal + scale * (Poisson_counts - dose), diagnostic only.
    scale, offset = r['scale'], r['pedestal'] - r['scale'] * r['dose']
    underlying_total = (total_grid - n * offset) / scale
    underlying_squares = (squares_grid - 2 * offset * total_grid + n * offset**2) / scale**2
    return dict(n=n, total_unrounded=total, squared_sum_unrounded=squares,
                total=total_grid, squared_sum=squares_grid, grid=grid,
                underlying_Poisson_total=round(underlying_total),
                underlying_Poisson_squared_sum=round(underlying_squares))


def environment():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('MC_DIAG_', 'MC_EXPERIMENT_'))}
    env.update(OMP_NUM_THREADS='8', OPENBLAS_NUM_THREADS='1',
               VECLIB_MAXIMUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    return env


def run_guarded(argv, cwd, env, log, record):
    free = shutil.disk_usage(WORK).free
    if free < MIN_FREE:
        raise RuntimeError('disk below 10 GiB before launch')
    if len(list(WORK.glob('movie*/movie.mrcs'))) > 2:
        raise RuntimeError('more than two task movies on disk')
    start = time.monotonic()
    samples, minimum, stopped = 0, free, False
    with log.open('w') as stream:
        child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while True:
                free = shutil.disk_usage(WORK).free
                minimum = min(minimum, free)
                samples += 1
                if free < MIN_FREE:
                    stopped = True
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    rc = child.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    if stopped:
                        os.killpg(child.pid, signal.SIGKILL)
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            raise
    data = dict(argv=list(map(str, argv)), cwd=str(cwd), exit=rc,
                seconds=time.monotonic() - start, disk_guard=dict(
                    limit_free_bytes=MIN_FREE, minimum_sampled_free_bytes=minimum,
                    samples=samples, stopped=stopped, interval_seconds=1))
    write(record, data)
    if stopped:
        raise RuntimeError('disk guard stopped child below 10 GiB')
    return data


def reference():
    archive = REPO / 'docs/post_rc0/s1/km_truth/raw.tar.gz'
    index_path = REPO / 'docs/post_rc0/s1/km_truth/FIXTURE_INDEX.json'
    index = json.loads(index_path.read_text())
    rows = {}
    with tarfile.open(archive) as t:
        for pin in index:
            name = pin['name']
            paths = [f'raw/fixtures/{name}/RECEIPT.json',
                     f'raw/results/{name}/cpu-none/metrics.json']
            raw_r, raw_m = [t.extractfile(p).read() for p in paths]
            assert hashlib.sha256(raw_r).hexdigest() == pin['receipt_sha256']
            r, m = json.loads(raw_r), json.loads(raw_m)
            assert m['checker_sha256'] == CHECK_SHA
            rows[name] = dict(receipt=r, receipt_sha256=pin['receipt_sha256'],
                              metrics_sha256=hashlib.sha256(raw_m).hexdigest(),
                              archive_members=paths, moments=moments(r),
                              runtime=m['field']['angstrom'],
                              STAR=m['serialized_field']['angstrom'],
                              runtime_gate=m['field_distance_status'],
                              STAR_gate=gate(m['serialized_field']['angstrom']))
    result = dict(label=LABEL, reference_arm='frozen #269 cpu-none',
                  archive_sha256=digest(archive), index_sha256=digest(index_path), movies=rows)
    write(WORK / 'frozen_reference.json', result)
    return rows


def shrink(directory):
    removed = {}
    for p in sorted((directory / 'output').glob('*')):
        if p.is_file() and p.suffix.lower() in ('.mrc', '.mrcs', '.pdf', '.eps'):
            removed[p.name] = dict(bytes=p.stat().st_size, sha256=digest(p))
            if p.suffix.lower() in ('.mrc', '.mrcs'):
                removed[p.name]['payload_sha256'] = digest(p, 1024)
            p.unlink()
    write(directory / 'removed-products.json', removed)


def run_arm(name, arm, fixture):
    binary, dc, extra = ARMS[arm]
    assert digest(binary) == PINS[str(binary)]
    d = WORK / 'runs' / name / arm
    d.mkdir(parents=True, exist_ok=False)
    occupancy = subprocess.check_output(['ps', '-axo', 'pid,pcpu,rss,comm', '-r'], text=True)
    (d / 'occupancy-before.txt').write_text('\n'.join(occupancy.splitlines()[:24]) + '\n')
    out = d / 'output'
    argv = [str(binary), '--i', 'movie.star', '--o', str(out), '--use_own', '--j', '8',
            '--patch_x', '5', '--patch_y', '5', '--group_frames', '1', '--bin_factor', '1',
            '--seed', '1', '--skip_defect', '--save_noDW', '--first_frame_sum', '1',
            '--last_frame_sum', '40', '--skip_logfile', '--ingest', 'float', *extra]
    env = environment()
    env.update(MC_EXPERIMENT_CCF_DC_ARM=dc, MC_DIAG_MODEL_OUT=str(d / 'runtime.json'))
    rr = run_guarded(['/usr/bin/time', '-l', *argv], fixture, env,
                     d / 'stdout.log', d / 'RUN.json')
    rr.update(label=LABEL, arm=arm, native_argv=argv, binary_sha256=digest(binary),
              environment={k: env[k] for k in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                  'VECLIB_MAXIMUM_THREADS', 'MC_EXPERIMENT_CCF_DC_ARM', 'MC_DIAG_MODEL_OUT']},
              input_receipt_sha256=digest(fixture / 'RECEIPT.json'),
              publication={p.name: dict(bytes=p.stat().st_size, sha256=digest(p))
                           for p in sorted(out.glob('*')) if p.is_file()})
    write(d / 'RUN.json', rr)
    if rr['exit'] != 0:
        raise RuntimeError(f'{name}/{arm} native failure {rr["exit"]}; retained, not retried')
    for p in [d / 'runtime.json', out / 'movie.star', out / 'movie.log', out / 'movie.mrc']:
        if not p.exists():
            raise RuntimeError(f'{name}/{arm} missing publication: {p.name}')
    score_argv = [sys.executable, '-I', str(SRC / 'tools/check_realistic_motion.py'),
                  '--receipt', str(fixture / 'RECEIPT.json'), '--runtime', str(d / 'runtime.json'),
                  '--star', str(out / 'movie.star'), '--log', str(out / 'movie.log'),
                  '--json', str(d / 'metrics.json')]
    sr = run_guarded(score_argv, fixture, environment(), d / 'score.stdout', d / 'SCORE.json')
    if sr['exit'] != 0:
        raise RuntimeError(f'{name}/{arm} scoring failure {sr["exit"]}; producer not retried')
    m = json.loads((d / 'metrics.json').read_text())
    rt = json.loads((d / 'runtime.json').read_text())
    stdout = (d / 'stdout.log').read_text()
    log = (out / 'movie.log').read_text()
    peak = re.findall(r'(\d+)\s+maximum resident set size', stdout)
    dc_lines = re.findall(r'MC_EXPERIMENT_CCF_DC arm=(\w+) cpu.global=(\d+)/(\d+) cpu.local=(\d+)/(\d+)', stdout)
    result = dict(seconds=rr['seconds'], native_exit=rr['exit'], score_exit=sr['exit'],
                  runtime=m['field']['angstrom'], STAR=m['serialized_field']['angstrom'],
                  runtime_gate=m['field_distance_status'], STAR_gate=gate(m['serialized_field']['angstrom']),
                  sampling=m['sampling_status'], local_enabled=m['local_enabled'],
                  convergence=m['convergence'], star_roundtrip_loss=m['star_roundtrip_loss']['px'],
                  maximum_rss_bytes=int(peak[-1]) if peak else None,
                  manipulation=dict(dc_lines=dc_lines,
                      coupled_lines=[line for line in stdout.splitlines() if '[coupled_peak]' in line],
                      full_width_witnesses=[line.strip() for line in log.splitlines()
                                            if 'EXPERIMENTAL local full-width weight:' in line]))
    print(name, arm, result['runtime_gate'], result['STAR_gate'],
          'rms', round(result['runtime']['rms'], 6), 'seconds', round(rr['seconds'], 2), flush=True)
    return d, result, rt


def identity(off, other, recipe):
    a = json.loads((off / 'runtime.json').read_text())
    b = json.loads((other / 'runtime.json').read_text())
    x, y = np.meshgrid(np.linspace(32, recipe['nx'] - 33, 129),
                       np.linspace(32, recipe['ny'] - 33, 129))
    delta = check.runtime_field(a, recipe, x.ravel(), y.ravel()) - check.runtime_field(b, recipe, x.ravel(), y.ravel())
    rows = {}
    for p in sorted((off / 'output').glob('*')):
        q = other / 'output' / p.name
        row = dict(present_other=q.exists(), raw_identical=q.exists() and digest(p) == digest(q))
        if q.exists() and p.suffix == '.star':
            row['output_root_normalized_identical'] = p.read_bytes().replace(str(off / 'output').encode(), b'@OUTPUT@') == q.read_bytes().replace(str(other / 'output').encode(), b'@OUTPUT@')
        if q.exists() and p.suffix == '.mrc':
            with p.open('rb') as f, q.open('rb') as g:
                row['core_header_224_identical'] = f.read(224) == g.read(224)
            row['payload_identical'] = digest(p, 1024) == digest(q, 1024)
        rows[p.name] = row
    result = dict(label=LABEL, movie='dose1-s00', reference_binary=PINS[str(BIN)],
                  second_binary=PINS[str(FWBIN)], runtime_JSON_equal=a == b,
                  runtime_raw_bytes_equal=digest(off / 'runtime.json') == digest(other / 'runtime.json'),
                  runtime_max_vector_difference_px=float(np.linalg.norm(delta, axis=-1).max()),
                  products=rows, reference_remains='OFF from e978af21 regardless of identity result')
    write(WORK / 'first-movie-binary-identity.json', result)


def worker(mode, recipe_file, destination):
    recipe = json.loads(Path(recipe_file).read_text())
    destination = Path(destination)
    if mode == 'expectation':
        proof = gen.expected(recipe, destination)
        write(destination.with_suffix('.json'), dict(recipe=recipe, proof=proof))
    elif mode == 'movie':
        gen.generate(recipe, WORK / 'expectation.npy', destination)
    else:
        raise ValueError(mode)


def main():
    assert np.__version__ == '2.5.4' and scipy.__version__ == '1.18.1'
    assert digest(SRC / 'test-data/generate_realistic_motion.py') == GEN_SHA
    assert digest(SRC / 'tools/check_realistic_motion.py') == CHECK_SHA
    for path, pin in PINS.items():
        assert digest(path) == pin
    assert subprocess.check_output(['git', 'show', 'HEAD:docs/post_rc0/s1/native_b2_census_mac_20261027/REPLICATE_AMENDMENT_v2.md'], cwd=REPO)
    WORK.mkdir(exist_ok=False)
    write(WORK / 'admission.json', dict(label=LABEL,
        pre_run_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        amendment_v1_commit='154661ba1bd733ac7993281fa895bfcd3a26b222',
        amendment_v2_commit='8f5e92556dbd338de058666d541d4a901aa276a5',
        binary_pins=PINS, generator_sha256=GEN_SHA, checker_sha256=CHECK_SHA,
        python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
        runner_sha256=digest(Path(__file__)),
        environment={k: environment()[k] for k in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                       'VECLIB_MAXIMUM_THREADS', 'PYTHONDONTWRITEBYTECODE']},
        free_bytes=shutil.disk_usage(WORK).free,
        source_note='Unmodified git archive source and two supplied Mac binaries; no Linux byte-identity claim'))
    refs = reference()
    rows, expectation_key = [], None
    for condition in ORDER:
        for seed in range(10):
            name = f'{condition}-s{seed:02d}'
            recipe = gen.recipe(condition, seed)
            assert recipe == refs[name]['receipt']['recipe']
            inp = WORK / 'inputs' / name
            inp.mkdir(parents=True, exist_ok=False)
            recipe_file = inp / 'recipe.json'
            write(recipe_file, recipe)
            key = 'outmodel' if condition == 'outmodel' else ('nonsquare' if condition == 'nonsquare' else 'inmodel')
            if key != expectation_key:
                for p in [WORK / 'expectation.npy', WORK / 'expectation.json']:
                    if p.exists():
                        p.unlink()
                er = run_guarded([sys.executable, '-I', str(Path(__file__).resolve()), 'expectation', str(recipe_file), str(WORK / 'expectation.npy')], WORK, environment(), inp / 'expectation-generation.log', inp / 'EXPECTATION_RUN.json')
                if er['exit'] != 0:
                    raise RuntimeError(f'{name} expectation generation failed')
                expectation_key = key
                shutil.copyfile(WORK / 'expectation.json', WORK / f'expectation-{key}.json')
            fixture = WORK / 'movie'
            gr = run_guarded([sys.executable, '-I', str(Path(__file__).resolve()), 'movie', str(recipe_file), str(fixture)], WORK, environment(), inp / 'generation.log', inp / 'GENERATION_RUN.json')
            if gr['exit'] != 0:
                raise RuntimeError(f'{name} movie generation failed')
            receipt = json.loads((fixture / 'RECEIPT.json').read_text())
            assert receipt['recipe'] == recipe
            local_hash = digest(fixture / 'movie.mrcs')
            assert local_hash == receipt['files']['movie.mrcs']
            for filename in ['RECEIPT.json', 'input.star']:
                shutil.copyfile(fixture / filename, inp / filename)
            shutil.copyfile(fixture / 'input.star', fixture / 'movie.star')
            mm, fm = moments(receipt), refs[name]['moments']
            p6 = dict(Mac=mm, frozen=fm, total_difference=mm['total'] - fm['total'],
                      squared_sum_difference=mm['squared_sum'] - fm['squared_sum'])
            p6['flagged'] = p6['total_difference'] != 0 or abs(p6['squared_sum_difference']) > 1000
            write(inp / 'P6.json', p6)
            row = dict(movie=name, condition=condition, seed=seed,
                       in_model=condition not in ('outmodel', 'pedestal32'),
                       recipe=recipe, movie_sha256=local_hash,
                       movie_bytes=(fixture / 'movie.mrcs').stat().st_size,
                       local_receipt_sha256=digest(inp / 'RECEIPT.json'),
                       expectation_sha256=receipt['expectation_sha256'],
                       generation_seconds=gr['seconds'], P6=p6, arms={})
            off_dir, off_result, off_rt = run_arm(name, 'OFF', fixture)
            row['arms']['OFF'] = off_result
            if not rows:
                other, extra_result, _ = run_arm(name, 'IDENTITY_OFF', fixture)
                identity(off_dir, other, recipe)
                write(WORK / 'identity-arm-summary.json', extra_result)
                shrink(other)
            shrink(off_dir)
            globals_by_arm = {'OFF': off_rt['global']}
            for arm in ['B2', 'UP', 'UPFW', 'FW']:
                directory, result, rt = run_arm(name, arm, fixture)
                row['arms'][arm] = result
                globals_by_arm[arm] = rt['global']
                shrink(directory)
            row['pair_globals_identical'] = dict(B2_OFF=globals_by_arm['B2'] == globals_by_arm['OFF'], UPFW_UP=globals_by_arm['UPFW'] == globals_by_arm['UP'], FW_OFF=globals_by_arm['FW'] == globals_by_arm['OFF'])
            write(WORK / 'rows' / (name + '.json'), row)
            rows.append(row)
            write(WORK / 'census.json', dict(label=LABEL, completed=len(rows), movies=rows))
            shutil.rmtree(fixture)
            print('COMPLETE', len(rows), '/100', name, 'P6', p6['flagged'], 'dTotal', p6['total_difference'], 'dSquares', p6['squared_sum_difference'], flush=True)
    for p in [WORK / 'expectation.npy', WORK / 'expectation.json']:
        if p.exists():
            p.unlink()
    write(WORK / 'COMPLETE.json', dict(label=LABEL, movies=100, native_runs=501,
          binary_final_hashes={p: digest(p) for p in PINS}, free_bytes=shutil.disk_usage(WORK).free))


if __name__ == '__main__':
    if len(sys.argv) > 1:
        worker(*sys.argv[1:])
    else:
        try:
            main()
        except BaseException as error:
            if WORK.exists():
                write(WORK / 'STOP.json', dict(label=LABEL, error=str(error), traceback=traceback.format_exc()))
            raise
