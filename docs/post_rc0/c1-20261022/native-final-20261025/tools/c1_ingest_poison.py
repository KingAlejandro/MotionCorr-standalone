#!/usr/bin/env python3
"""Genuine CUDA context poisoning inside the nvCOMP device-ingest path (C1 iteration i8; qualification tooling, not production source).

Binary: motioncorr_ingest_fault, built out of tree by c1_ingest_build.sh from the tested e77a51a2 core library plus cuda_ingest_sticky_fault.cu.
The fixture is a 48x40, 6-frame Adobe-Deflate TIFF (the encoding the fast path accepts), MOTIONCORR_NVCOMP_CHUNK_FRAMES=2 (3 chunks per movie).
The interposer launches an illegal device write before the ingest gain launch with process-wide index MC_INGEST_STICKY_LAUNCH (default 1, the second
chunk), so the fault is genuine, happens inside ingestCompressedTiffStrips and the product's own launch must observe the broken context.

Phases (the destructive phase is `fault`, run once; `pre` never poisons anything):
  pre    healthy_single, healthy_multi (3 movies), notarget: MC_INGEST_STICKY_FAULT=1 with --ingest float (the host reader never enters the ingest, so the
         interposer must stay silent and the run is healthy). Checks fixture eligibility (witness nvcomp for every movie, 3 gain launches per movie).
  fault  --pre-dir PRE: fault_pinned_single (--ingest nvcomp, 1 movie), fault_pinned_multi (3 movies), fault_auto_multi (--ingest auto, 3 movies), then the
         native negative controls: fault_verdict applied to PRE's healthy_multi and notarget logs must REJECT both.
Fault verdict (every item must hold; see fault_verdict): fault executed exactly once at launch index 1; native completion 700; the product launch observed 700;
exit status 1; attributed on one line 'CUDA device became unusable during device movie ingestion for Movies/control.tiff: ... Refusing CPU fallback after a fatal device error.';
no host-reader/compact fallback line and no non-nvcomp witness; final 'Motion correction failed for N movie(s)' records name every movie; no kernel launch attempt
after the fault; only index 0 and 1 ingest launches seen; no non-log file published. Each arm's GPU health (c1_health_check.py) is checked before and after.
Environment: C1_SCR, C1_GPU_UUID (full UUID, also CUDA_VISIBLE_DEVICES), C1_PY; run under taskset by the wrapper (c1_ingest.sh).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPTIONS = ['--use_own', '--gpu', '0', '--j', '1', '--max_io_threads', '1', '--patch_x', '2', '--patch_y', '2', '--max_iter', '1',
           '--bfactor', '150', '--seed', '1', '--angpix', '1.0', '--voltage', '300']
MOVIES = ['Movies/control.tiff', 'Movies/after1.tiff', 'Movies/after2.tiff']
HOST_FALLBACK = ['Device ingestion failed recoverably', 're-reading the movie with the host reader', 'using the host reader',
                 'Staging this movie as native', 'Materialized native', 'falling back to', 'ingestion declined', 'ingestion refused']
# src/motioncorr_runner.cpp: a fatal FatalDeviceFailure from ingestMovie reaches discard_preprocessing_session("device movie ingestion"), whose
# refuse_fallback_if_fatal() throws this REPORT_ERROR (the later 'Refusing any fallback ...' text is unreachable).
# One line (REPORT_ERROR_STR): no re.S, so two different lines can never be joined into a match.
FATAL_REFUSAL = re.compile(r'CUDA device became unusable during device movie ingestion for [^\n]*Movies/control\.tiff: [^\n]*Refusing CPU fallback after a fatal device error\.')
FAIL_RECORD = re.compile(r'Motion correction failed for (\d+) movie\(s\): (.+)\. Successful per-movie outputs were retained; joint output was not generated\.')
FAIL_PREFIX = re.compile(r'Motion correction failed for[^\r\n]*')
EXIT_SUMMARY = re.compile(r'\[ingeststicky\] exit gain-launches=(\d+) faulted=(\d+)')


class Reject(Exception):
    """A verdict requirement does not hold."""


class ArmAborted(Exception):
    """The arm was interrupted (timeout, signal, error); its child session was terminated and reaped. Carries the partial record."""
    def __init__(self, rec, message):
        super().__init__(message)
        self.rec = rec


def require(cond, message):
    if not cond:
        raise Reject(message)


def witness_routes(text):
    routes = []
    for line in (text or '').splitlines():
        tok = line.split()
        if len(tok) >= 2:
            routes.append(tok[1])
    return routes


def launch_indices(console):
    return [int(m) for m in re.findall(r'\[ingeststicky\] gain-launch index=(\d+)', console)]


def logs_text(out):
    return '\n'.join(p.read_text(errors='replace') for p in sorted(Path(out).rglob('*.log')))


def fault_verdict(rc, console, out, count, witness=None):
    """Raise Reject unless the run shows a genuine ingest-site poisoning with the documented fatal, non-published, non-fallback outcome."""
    text = console + '\n' + logs_text(out)
    require(console.count('[ingeststicky] launch illegal write before ingest gain launch 1') == 1,
            'fault did not execute exactly once at ingest gain-launch index 1 in the product process')
    completions = re.findall(r'\[ingeststicky\] fault completion=(-?\d+) ', console)
    require(completions == ['700'], f'illegal write completion records {completions}, expected exactly one native cudaErrorIllegalAddress (700)')
    results = re.findall(r'\[ingeststicky\] product launch result=(-?\d+) ', console)
    require(results == ['700'], f'product ingest launch result records {results}, expected exactly one sticky error 700')
    require(rc == 1, f'documented fatal status must be 1, got {rc}')
    require(FATAL_REFUSAL.search(text),
            "fatal ingest refusal ('CUDA device became unusable during device movie ingestion for Movies/control.tiff ... Refusing CPU fallback') missing")
    for needle in HOST_FALLBACK:
        require(needle not in text, f'host/compact fallback or decline after poisoning: {needle!r}')
    # Route witnesses are appended only after a successful ingest decision (runner), so a fatal ingest of the first movie and the refusals after it write none.
    require((witness or '') == '', f'a route witness was published for a movie of a fatally poisoned job: {witness!r}')
    prefixes = FAIL_PREFIX.findall(text)
    require(prefixes, 'job did not attribute failed/unprocessed movies')
    expected = set(MOVIES[:count])
    for record in prefixes:   # every copy must be well-formed and complete: one correct record beside a malformed one is not acceptable
        match = FAIL_RECORD.fullmatch(record)
        require(match is not None, f'malformed final movie failure record: {record!r}')
        movies = match[2].split()
        require(int(match[1]) == count and len(movies) == count and set(movies) == expected,
                'final failure record has missing, duplicate or unexpected movies')
    require('[ingeststicky] PRODUCT_KERNEL_AFTER_FAULT' not in console, 'a kernel launch was attempted on the poisoned context')
    require(launch_indices(console) == [0, 1], f'ingest launches seen in order {launch_indices(console)}, expected exactly [0, 1]')
    summaries = EXIT_SUMMARY.findall(console)   # atexit line: absence is tolerated (abnormal exit), a contradictory or repeated line is not
    require(all(x == ('2', '1') for x in summaries) and len(summaries) <= 1, f'inconsistent interposer exit summary {summaries}')
    unexpected = [str(p.relative_to(out)) for p in Path(out).rglob('*') if p.is_file() and p.suffix != '.log']
    require(not unexpected, f'failed movies published products/partial products: {unexpected}')


def healthy_verdict(rc, console, out, count, witness):
    require(rc == 0, f'healthy arm exit {rc}')
    require('[ingeststicky] launch illegal write' not in console and 'fault completion' not in console, 'healthy arm shows a fault')
    require('PRODUCT_KERNEL_AFTER_FAULT' not in console, 'launch after a fault in a healthy arm')
    out = Path(out)
    for m in MOVIES[:count]:
        stem = Path(m).stem
        require((out / 'Movies' / f'{stem}.mrc').is_file() and (out / 'Movies' / f'{stem}.star').is_file(), f'products missing for {m}')
    require((out / 'corrected_micrographs.star').is_file(), 'joint STAR missing')
    require('Refusing CPU fallback' not in console + logs_text(out), 'healthy arm refused')


def ingest_healthy_verdict(rc, console, out, count, witness):
    healthy_verdict(rc, console, out, count, witness)
    require(witness_routes(witness) == ['nvcomp'] * count, f'witness {witness!r}: every movie must take the nvcomp route')
    require(launch_indices(console) == list(range(3 * count)), f'ingest gain launches {launch_indices(console)}, expected 3 per movie')


def notarget_verdict(rc, console, out, count, witness):
    healthy_verdict(rc, console, out, count, witness)
    require(not launch_indices(console), 'host-reader arm entered the nvCOMP ingest (gain launches seen)')
    require('nvcomp' not in witness_routes(witness), f'host-reader arm witness: {witness!r}')


# ---------------------------------------------------------------------------------------------------------------------------------
def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def health(label):
    env = dict(os.environ)
    r = subprocess.run([env.get('C1_PY', sys.executable), str(HERE / 'c1_health_check.py'), label], capture_output=True, text=True, timeout=120, env=env)
    return {'label': label, 'rc': r.returncode, 'msg': (r.stdout + r.stderr)[-300:]}


def run_arm(name, args, star, ingest, fault, work, inp, chunk_frames=2, timeout=180):
    out = work / name
    out.mkdir(parents=True)
    witness = work / f'{name}.witness'
    cmd = [str(args.binary), '--i', star, '--o', str(out) + '/', *OPTIONS, '--ingest', ingest, '--ingest_witness', str(witness)]
    env = dict(os.environ, OMP_NUM_THREADS='1', MOTIONCORR_NVCOMP_CHUNK_FRAMES=str(chunk_frames), MC_INGEST_STICKY_FAULT='1' if fault else '0',
               CUDA_VISIBLE_DEVICES=os.environ['C1_GPU_UUID'], CUDA_DEVICE_ORDER='PCI_BUS_ID')
    env.pop('MC_INGEST_STICKY_LAUNCH', None)
    rec = {'arm': name, 'argv': cmd, 'cwd': str(inp), 'fault_env': env['MC_INGEST_STICKY_FAULT'], 'chunk_frames': chunk_frames,
           'cuda_visible_devices': env['CUDA_VISIBLE_DEVICES'], 'start_utc': time.strftime('%FT%TZ', time.gmtime())}
    t0 = time.monotonic()
    cfh = open(work / f'{name}.console.txt', 'w')
    p = subprocess.Popen(cmd, cwd=inp, env=env, stdout=cfh, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        p.wait(timeout=timeout)
    except BaseException as exc:      # timeout, SIGINT/SIGTERM (converted below), anything: the child's own session is terminated and reaped before we leave
        for sig, wait in ((signal.SIGTERM, 30), (signal.SIGKILL, 10)):
            try:
                os.killpg(p.pid, sig)
            except ProcessLookupError:
                break
            try:
                p.wait(timeout=wait)
                break
            except subprocess.TimeoutExpired:
                continue
        rec['aborted'] = f'{type(exc).__name__}: {exc}'
        rec['rc'] = p.poll()
        cfh.close()
        raise ArmAborted(rec, f'{name}: aborted ({type(exc).__name__}); child session terminated; console retained') from exc
    cfh.close()
    console = (work / f'{name}.console.txt').read_text()
    rec.update(rc=p.returncode, wall_s=round(time.monotonic() - t0, 2))
    rec['witness'] = witness.read_text() if witness.exists() else ''
    left = subprocess.run(['pgrep', '-g', str(p.pid)], capture_output=True, text=True).stdout.split()
    rec['leftover_pids'] = left
    return rec, console, out


def prepare_inputs(work, py_tests):
    sys.path.insert(0, str(py_tests))
    from run_nvcomp_reconstruction_controls import write_deflate_tiff   # noqa: E402
    from test_gain_cache import synthetic_frames, write_star            # noqa: E402
    inp = work / 'input'
    (inp / 'Movies').mkdir(parents=True)
    write_deflate_tiff(inp / 'Movies/control.tiff', [[int(v) for v in f] for f in synthetic_frames()])
    for i in (1, 2):
        shutil.copyfile(inp / 'Movies/control.tiff', inp / f'Movies/after{i}.tiff')
    write_star(inp / 'single.star', MOVIES[:1])
    write_star(inp / 'multi.star', MOVIES)
    (work / 'input-sha256.json').write_text(json.dumps({str(p.relative_to(inp)): sha256(p) for p in sorted(inp.rglob('*')) if p.is_file()}, indent=2) + '\n')
    return inp


def grade(rec, verdict, count, out, console):
    try:
        verdict(rec['rc'], console, out, count, rec['witness'])
        rec['verdict'] = 'PASS'
    except Reject as exc:
        rec['verdict'] = 'FAIL'
        rec['problem'] = str(exc)
    except Exception as exc:     # a verdict bug must not lose the arm record or the post-run health result
        rec['verdict'] = 'FAIL'
        rec['problem'] = f'verdict raised {type(exc).__name__}: {exc}'
    if rec['leftover_pids']:
        rec['verdict'] = 'FAIL'
        rec['problem'] = (rec.get('problem', '') + f' leftover processes {rec["leftover_pids"]}').strip()
    return rec


def expect_reject(label, verdict, rc, console, out, count, witness):
    try:
        verdict(rc, console, out, count, witness)
    except Reject as exc:
        return {'control': label, 'verdict': 'PASS', 'rejected_because': str(exc)}
    return {'control': label, 'verdict': 'FAIL', 'problem': 'fault_verdict accepted a run that did not poison the context'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--binary', required=True, type=Path)
    ap.add_argument('--workdir', required=True, type=Path)
    ap.add_argument('--phase', required=True, choices=['pre', 'fault'])
    ap.add_argument('--pre-dir', type=Path, help='the pre phase workdir (fault phase: negative controls read its healthy logs)')
    ap.add_argument('--tests-dir', type=Path, default=Path(os.environ.get('C1_SCR', '.')) / 'src' / 'tests')
    args = ap.parse_args()
    uuid = os.environ.get('C1_GPU_UUID', '')
    require(re.fullmatch(r'GPU-[0-9a-fA-F-]{36}', uuid), 'C1_GPU_UUID must be one full GPU UUID')
    require(len(os.sched_getaffinity(0)) <= 8, 'run under an at-most-eight-CPU taskset cap')
    args.binary = args.binary.resolve()
    def interrupted(signum, _frame):
        raise RuntimeError(f'driver interrupted by signal {signum}')
    signal.signal(signal.SIGTERM, interrupted)
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    inp = prepare_inputs(work, args.tests_dir)
    result = {'phase': args.phase, 'binary': str(args.binary), 'binary_sha256': sha256(args.binary), 'uuid': uuid,
              'cpus': sorted(os.sched_getaffinity(0)), 'utc': time.strftime('%FT%TZ', time.gmtime()), 'arms': [], 'controls': []}

    def save():
        (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    def do(name, star, count, ingest, fault, verdict):
        pre = health(f'{name}-pre')
        if pre['rc']:
            result['arms'].append({'arm': name, 'verdict': 'NOT_RUN', 'problem': f'pre-run health failed: {pre}'})
            save(); raise SystemExit(f'{name}: pre-run health failed {pre}')
        rec = console = out = None
        err = None
        try:
            rec, console, out = run_arm(name, args, star, ingest, fault, work, inp)
        except ArmAborted as exc:
            rec, err = exc.rec, exc
        except BaseException as exc:
            rec, err = {'arm': name}, exc
        try:   # the post-run health check runs on every path, while the wrapper still holds the GPU lease
            post = health(f'{name}-post')
        except BaseException as hexc:
            post = {'label': f'{name}-post', 'rc': None, 'msg': f'health check raised {hexc!r}'}
            err = err or hexc
        rec['health_pre'], rec['health_post'] = pre, post
        if err is not None:   # keep the ORIGINAL error; the partial record is saved first
            rec['verdict'] = 'ABORTED'; rec['problem'] = f'{type(err).__name__}: {err}'
            result['arms'].append(rec); result['verdict'] = 'ABORTED'; save()
            raise err
        grade(rec, verdict, count, out, console)
        if post['rc']:
            rec['verdict'] = 'FAIL'; rec['problem'] = (rec.get('problem', '') + f' post-run health failed {post}').strip()
        result['arms'].append(rec); save()
        print(name, rec['verdict'], rec.get('problem', ''), flush=True)
        if post['rc']:   # a GPU that is not healthy after an arm stops the phase: no later arm may run on it
            result['verdict'] = 'ABORTED'; save()
            raise SystemExit(f'{name}: post-run health failed {post}; phase stopped')
        return rec, console, out

    if args.phase == 'pre':
        do('healthy_single', 'single.star', 1, 'nvcomp', False, ingest_healthy_verdict)
        do('healthy_multi', 'multi.star', 3, 'nvcomp', False, ingest_healthy_verdict)
        do('notarget', 'multi.star', 3, 'float', True, notarget_verdict)
    else:
        require(args.pre_dir and (args.pre_dir / 'result.json').is_file(), '--pre-dir with a completed pre phase is required')
        pre_ok = json.loads((args.pre_dir / 'result.json').read_text())
        require(pre_ok['phase'] == 'pre' and pre_ok.get('verdict') == 'PASS' and [a['arm'] for a in pre_ok['arms']] == ['healthy_single', 'healthy_multi', 'notarget']
                and all(a['verdict'] == 'PASS' for a in pre_ok['arms']), 'pre phase is not a complete PASS of the three expected arms')
        require(pre_ok['binary_sha256'] == result['binary_sha256'] and pre_ok['uuid'] == uuid,
                'pre phase ran a different binary or GPU than this destructive run')
        require((args.pre_dir / 'input-sha256.json').read_text() == (work / 'input-sha256.json').read_text(), 'fixture hashes differ between pre and fault phases')
        do('fault_pinned_single', 'single.star', 1, 'nvcomp', True, fault_verdict)
        do('fault_pinned_multi', 'multi.star', 3, 'nvcomp', True, fault_verdict)
        do('fault_auto_multi', 'multi.star', 3, 'auto', True, fault_verdict)
        for name, count in (('healthy_multi', 3), ('notarget', 3)):
            pre_arm = args.pre_dir / name
            con = (args.pre_dir / f'{name}.console.txt').read_text()
            wit = (args.pre_dir / f'{name}.witness').read_text() if (args.pre_dir / f'{name}.witness').exists() else ''
            result['controls'].append(expect_reject(f'fault_verdict_on_{name}', fault_verdict, 0, con, pre_arm, count, wit))
    save()
    ok = all(a['verdict'] == 'PASS' for a in result['arms']) and all(c['verdict'] == 'PASS' for c in result['controls'])
    result['verdict'] = 'PASS' if ok else 'FAIL'
    save()
    print('INGEST_POISON_' + args.phase.upper() + ':', result['verdict'])
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
