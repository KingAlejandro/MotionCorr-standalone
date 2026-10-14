#!/usr/bin/env python3
"""Bounded CPU process/thread experiment, including complete dataset publication.

This is a diagnostic fallback for hosts whose mounted /proc cannot identify
their own child processes. It is NOT a replacement for run_dataset.py and never
certifies host isolation, descendant containment or NUMA placement. Production
worker status files and their ownership gates are neither written nor changed.
Direct children set/read their own affinity before exec; wait4 records their
actual exits and rusage. Existing STAR partition, product-path, staging, joint
row-order and product-identity helpers are reused.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

import merge_workers
import output_digests
import partition_star
from run_multi_gpu import parse_cpu_list
import star_io

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'profiling'))
from lib import identity

ENV = {'OMP_DYNAMIC': 'FALSE', 'OMP_PROC_BIND': 'close', 'OMP_PLACES': 'cores',
       'OMP_WAIT_POLICY': 'PASSIVE', 'OPENBLAS_NUM_THREADS': '1',
       'MKL_NUM_THREADS': '1', 'BLIS_NUM_THREADS': '1',
       'NUMEXPR_NUM_THREADS': '1', 'VECLIB_MAXIMUM_THREADS': '1'}
OWNED_OPTIONS = {'--i', '--o', '--gpu', '--j', '--seed', '--aggregate_only',
                 '--only_do_unfinished', '--skip_report_pdf', '--profile'}


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def sha(path):
    return merge_workers.sha256_file(Path(path))


def validate(plan):
    if not isinstance(plan['cpu_budget'], int) or plan['cpu_budget'] < 1:
        raise ValueError('cpu_budget must be positive')
    available = set(os.sched_getaffinity(0))
    unions = []
    names = []
    for config in plan['configurations']:
        masks = [parse_cpu_list(mask) for mask in config['masks']]
        if not masks or any(not mask for mask in masks):
            raise ValueError('empty CPU mask')
        union = set().union(*masks)
        if sum(map(len, masks)) != len(union):
            raise ValueError('worker CPU masks overlap')
        if len(union) != plan['cpu_budget'] or not union <= available:
            raise ValueError('masks do not fit fixed CPU budget/allocation')
        if config['worker_rss_kib'] <= 0:
            raise ValueError('worker_rss_kib must be measured and positive')
        if not Path(config['binary']).is_file():
            raise ValueError('binary does not exist')
        unions.append(union)
        names.append(config['name'])
    if len(set(names)) != len(names) or any('/' in name or name in ('.', '..') for name in names):
        raise ValueError('configuration names must be unique path components')
    if not unions or any(union != unions[0] for union in unions):
        raise ValueError('every configuration must use exactly the same CPU IDs')
    if {arg.split('=', 1)[0] for arg in plan['worker_args']} & OWNED_OPTIONS:
        raise ValueError('experiment owns input, output, threads, seed and endpoint options')
    if '--use_own' not in plan['worker_args']:
        raise ValueError('--use_own is required for explicit CPU backend')
    if plan.get('seed', 1) < 0:
        raise ValueError('seed must be fixed and nonnegative')
    if plan.get('headroom_bytes', 0) < (1 << 30):
        raise ValueError('reserve at least 1 GiB for launcher, helpers and other memory')
    return unions[0]


def memory_preflight(plan, config):
    current = int(Path('/sys/fs/cgroup/memory.current').read_text())
    raw = Path('/sys/fs/cgroup/memory.max').read_text().strip()
    cgroup_limit = None if raw == 'max' else int(raw)
    budget = min(plan['memory_budget_bytes'], cgroup_limit or plan['memory_budget_bytes'])
    estimate = len(config['masks']) * config['worker_rss_kib'] * 1024
    # current includes cache and unrelated tasks. Deliberately conservative:
    # do not assume reclaimable cache, or count other tasks as available RAM.
    required = current + estimate + plan['headroom_bytes']
    return {'cgroup_current_bytes': current, 'cgroup_limit_bytes': cgroup_limit,
            'budget_bytes': budget, 'estimated_worker_peak_bytes': estimate,
            'headroom_bytes': plan['headroom_bytes'], 'required_bytes': required,
            'allowed': required <= budget,
            'method': 'current cgroup charge + sum of calibrated worker RSS + headroom; estimate, not simultaneous tree RSS'}


def check_inputs(plan):
    if not plan.get('input_sha256'):
        raise ValueError('declare immutable movie and gain input_sha256 hashes')
    for path, expected in plan['input_sha256'].items():
        if sha(path) != expected:
            raise RuntimeError(f'input bytes changed: {path}')
    if plan.get('star_sha256') and sha(plan['star']) != plan['star_sha256']:
        raise RuntimeError('input STAR changed since experiment started')


def launch(command, mask, log, witness, threads):
    """Fork one directly owned child; no process-name or /proc-based signaling."""
    log.parent.mkdir(parents=True, exist_ok=True)
    pid = os.fork()
    if pid == 0:
        try:
            os.sched_setaffinity(0, mask)
            actual = set(os.sched_getaffinity(0))
            if actual != mask:
                raise RuntimeError('child self-affinity differs from requested mask')
            env = dict(os.environ, **ENV, OMP_NUM_THREADS=str(threads))
            write(witness, {'pid': os.getpid(), 'requested': sorted(mask),
                            'actual_before_exec': sorted(actual), 'environment': {key: env[key] for key in (*ENV, 'OMP_NUM_THREADS')},
                            'LD_LIBRARY_PATH': env.get('LD_LIBRARY_PATH'),
                            'command': command, 'monotonic_before_exec': time.monotonic()})
            fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            os.dup2(fd, 1); os.dup2(fd, 2); os.close(fd)
            os.execvpe(command[0], command, env)
        except BaseException as exc:
            os.write(2, (str(exc) + '\n').encode())
            os._exit(125)
    # A pidfd continues to identify this child even after a PID could be reused.
    child = {'pid': pid, 'started': time.monotonic(), 'command': command,
             'witness': str(witness), 'log': str(log)}
    try:
        child['pidfd'] = os.pidfd_open(pid)
    except BaseException:
        # This directly forked child has not been reaped, so its numeric PID
        # cannot have been recycled. No process-table lookup is needed here.
        stop_owned([child])
        raise
    return child


def stop_owned(children):
    live = {child['pid']: child for child in children if 'ended' not in child}
    def send(child, signum):
        try:
            if 'pidfd' in child:
                signal.pidfd_send_signal(child['pidfd'], signum)
            else:
                # Only the pidfd-open failure path: this is our own unreaped
                # fork child, so its PID still cannot be recycled.
                os.kill(child['pid'], signum)
        except ProcessLookupError:
            pass  # wait4 below still records its exit and releases ownership.
    for child in live.values():
        send(child, signal.SIGTERM)
    deadline = time.monotonic() + 5.0
    while live:
        for pid, child in list(live.items()):
            got, status, usage = os.wait4(pid, os.WNOHANG)
            if not got and time.monotonic() >= deadline:
                send(child, signal.SIGKILL)
                got, status, usage = os.wait4(pid, 0)
            if got:
                child.update(returncode=os.waitstatus_to_exitcode(status), ended=time.monotonic(),
                             rss_hwm_kib=usage.ru_maxrss)
                if 'pidfd' in child:
                    os.close(child.pop('pidfd'))
                del live[pid]
        if live:
            time.sleep(0.05)


def wait_all(children):
    live = dict((child['pid'], child) for child in children)
    try:
        while live:
            for pid, child in list(live.items()):
                got, status, usage = os.wait4(pid, os.WNOHANG)
                if not got:
                    continue
                child.update(returncode=os.waitstatus_to_exitcode(status), ended=time.monotonic(),
                             rss_hwm_kib=usage.ru_maxrss, user_s=usage.ru_utime,
                             sys_s=usage.ru_stime, minor_faults=usage.ru_minflt,
                             major_faults=usage.ru_majflt)
                os.close(child.pop('pidfd'))
                del live[pid]
            if live:
                time.sleep(0.05)
    except BaseException:
        # Signal only kernel handles opened for our directly forked children.
        # Descendants are not signaled and containment is explicitly uncertified.
        stop_owned(list(live.values()))
        raise
    for child in children:
        child['wall_s'] = child['ended'] - child['started']
        witness = json.loads(Path(child['witness']).read_text())
        if witness['pid'] != child['pid'] or witness['requested'] != witness['actual_before_exec']:
            raise RuntimeError('child affinity witness failed')
    if any(child['returncode'] != 0 for child in children):
        raise RuntimeError('at least one direct child failed; see retained logs')


def stage_products(out, manifest, workers, suffixes):
    """SPA-only bounded staging using the production attribution/staging helpers."""
    if manifest.get('input_type', 'spa') != 'spa':
        raise ValueError('this diagnostic experiment supports SPA only')
    roots = {star_io.worker_relative_root(star_io.output_root(movie)): shard['index']
             for shard in manifest['shards'] for movie in shard['movies']}
    plots = {star_io.shift_plot_path(movie): star_io.worker_relative_root(star_io.output_root(movie))
             for movie in manifest['canonical_movies']}
    staged = {}
    out.mkdir()
    for index, worker in enumerate(workers):
        for rel, src in merge_workers.worker_files(worker).items():
            attribution = star_io.split_output_path(str(rel), roots)
            if str(rel) in plots:
                attribution = (plots[str(rel)], '_shifts', '.eps')
            if attribution is None:
                if merge_workers.is_aggregate(rel):
                    continue  # Retained in original worker directory as provenance.
                raise RuntimeError(f'unassigned product {rel}')
            if roots[attribution[0]] != index or rel in staged:
                raise RuntimeError(f'misrouted or duplicate product {rel}')
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            result = merge_workers.stage_one(src, dst, 'link', None)
            if 'problem' in result or 'fatal' in result:
                raise RuntimeError(f'staging failed: {result}')
            staged[str(rel)] = result
    for movie in manifest['canonical_movies']:
        for suffix in suffixes:
            rel = star_io.movie_output_path(movie, suffix)
            if rel not in staged:
                raise RuntimeError(f'missing required product {rel}')
    if staged:
        output_digests.ctime_barrier(out, max(item['dst_key'][4] for item in staged.values()),
                                     {item['dst_key'][0] for item in staged.values()})
    return staged


def observed_aggregate_scratch(raw_root):
    names = [f'corrected_micrographs_{kind}_rlnAccumMotion{period}.eps'
             for period in ('Total', 'Early', 'Late') for kind in ('all', 'hist')]
    lines = (raw_root / 'header.pdf.lst').read_text().splitlines()
    if len(lines) != len(names) or not lines[0].endswith('/' + names[0]):
        raise RuntimeError('unexpected aggregate header list membership')
    prefix = lines[0][:-len(names[0]) - 1]
    pattern = re.escape(str(raw_root)) + r'/\.aggregate-[A-Za-z0-9]{6}'
    if not re.fullmatch(pattern, prefix) or lines != [prefix + '/' + name for name in names]:
        raise RuntimeError('unexpected aggregate scratch paths or list order')
    return prefix


def canonical_comparison_view(raw_root, workers, view, scratch_prefix=None):
    """Keep every file; canonicalize only declared output/scratch path prefixes.

    Per-movie EPS titles name their original worker output, whereas aggregate
    list files name a mkdtemp report directory. Neither is a numeric datum.
    MRC/PDF/log bytes are linked untouched; all other bytes remain exact except
    these bounded path substitutions. Raw products are retained independently.
    """
    view.mkdir()
    changes = {}
    scratch_prefix = scratch_prefix or observed_aggregate_scratch(raw_root)
    scratch_in_view = str(view) + scratch_prefix[len(str(raw_root)):]
    roots = [str(raw_root), *(str(worker) for worker in workers)]
    for rel, source in merge_workers.worker_files(raw_root).items():
        target = view / rel; target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() in ('.mrc', '.mrcs', '.pdf', '.log'):
            os.link(source, target)
            continue
        original = source.read_bytes(); data = original
        for root in sorted(roots, key=len, reverse=True):
            data = re.sub(re.escape(root.encode()) + rb'(?=/|$)', str(view).encode(), data)
        if source.name in ('header.pdf.lst', 'logfile.pdf.lst'):
            pattern = (rb'^' + re.escape(scratch_in_view.encode()) + rb'/' +
                       rb'(corrected_micrographs_(?:all|hist)_rlnAccumMotion(?:Total|Early|Late)\.eps)(?=\r?$)')
            data = re.sub(pattern, lambda m: str(view).encode() + b'/.aggregate-<SCRATCH>/' + m[1],
                          data, flags=re.MULTILINE)
        target.write_bytes(data)
        if original != data:
            changes[str(rel)] = {'raw_sha256': hashlib.sha256(original).hexdigest(),
                                 'view_sha256': hashlib.sha256(data).hexdigest()}
    return changes


def one_run(plan, config, out):
    out.mkdir()
    status = {'certified': False, 'diagnostic_complete': False, 'name': config['name'],
              'limitation': 'self-affinity only before exec; no descendant tree, physical-host isolation or NUMA-placement certification',
              'binary': config['binary'], 'binary_sha256': sha(config['binary']),
              'input_star_sha256': sha(plan['star']), 'input_sha256': plan.get('input_sha256'),
              'source': config.get('source'), 'memory_preflight': memory_preflight(plan, config)}
    write(out / 'result.json', status)
    if not status['memory_preflight']['allowed']:
        status['skip'] = 'memory budget preflight refused launch'
        write(out / 'result.json', status)
        return status
    check_inputs(plan)  # Hashing immutable movie/gain bytes is outside timing.
    if config.get('binary_sha256', status['binary_sha256']) != status['binary_sha256']:
        raise RuntimeError('binary changed since experiment started')
    start = time.monotonic()
    children = []
    try:
        shard_dir = out / 'shards'
        n = len(config['masks'])
        rc = partition_star.main(['--star', plan['star'], '--n', str(n),
                                  '--outdir', str(shard_dir), '--prefix', 'shard'])
        if rc:
            raise RuntimeError('input partition refused')
        manifest = json.loads((shard_dir / 'shard_manifest.json').read_text())
        status['workers'] = children
        workers = []
        args = list(plan['worker_args']) + ['--seed', str(plan.get('seed', 1))]
        for index, mask_text in enumerate(config['masks']):
            worker = out / f'w{index}'; worker.mkdir(); workers.append(worker)
            mask = parse_cpu_list(mask_text)
            cmd = [config['binary'], '--i', str(shard_dir / f'shard_{n}way_{index}.star'),
                   '--o', str(worker) + '/', *args, '--j', str(len(mask)), '--skip_report_pdf']
            children.append(launch(cmd, mask, worker / 'launcher.console.log',
                                   out / f'affinity-w{index}.json', len(mask)))
        wait_all(children)
        status['worker_phase_wall_s'] = time.monotonic() - start
        status['all_worker_lifetimes_overlap_s'] = max(0.0, min(child['ended'] for child in children) -
                                                      max(child['started'] for child in children))
        status['achieved_worker_processes'] = len(children)
        status['concurrency_note'] = 'direct-child lifetimes overlap; this does not observe simultaneous CPU residency or runtime OpenMP team size'
        status['sum_worker_peak_rss_kib'] = sum(child['rss_hwm_kib'] for child in children)
        status['memory_note'] = 'sum of individual child ru_maxrss values is not simultaneous dataset-tree RSS; helper peaks are not measured as a tree'
        staged = stage_products(out / 'merged', manifest, workers, plan['required_products'])
        status['staging_wall_s'] = time.monotonic() - start - status['worker_phase_wall_s']
        all_cpus = set().union(*(parse_cpu_list(mask) for mask in config['masks']))
        command = [config['binary'], '--i', plan['star'], '--o', str(out / 'merged') + '/',
                   *args, '--j', str(len(all_cpus)), '--aggregate_only']
        aggregate = launch(command, all_cpus, out / 'aggregate.log', out / 'affinity-aggregate.json', len(all_cpus))
        children.append(aggregate)  # Also reaped if interrupted before wait_all.
        wait_all([aggregate]); status['aggregate'] = aggregate
        children.remove(aggregate)
        status['dataset_wall_s'] = time.monotonic() - start
        status['endpoint'] = 'partition + concurrent workers + checked staging + full aggregate STAR/report publication; postpublication verification excluded'
        if sha(config['binary']) != status['binary_sha256'] or sha(plan['star']) != status['input_star_sha256']:
            raise RuntimeError('binary or STAR changed during execution')
        check_inputs(plan)
        verify_unchanged(out / 'merged', staged)
        observed = {str(rel) for rel in merge_workers.worker_files(out / 'merged')
                    if str(rel) in plots_for(manifest) or star_io.split_output_path(str(rel),
                        {star_io.worker_relative_root(star_io.output_root(m)): 0 for m in manifest['canonical_movies']}) is not None}
        if observed != set(staged):
            raise RuntimeError('aggregate added or removed per-movie products')
        errors = merge_workers.joint_star_problems(out / 'merged', manifest, 'spa', {})
        pdf = (out / 'merged' / 'logfile.pdf').read_bytes()
        if errors or not pdf.startswith(b'%PDF-') or b'%%EOF' not in pdf[-1024:]:
            raise RuntimeError(f'aggregate publication verification failed: {errors}')
        status['n_movies'] = len(manifest['canonical_movies'])
        status['movies_per_s'] = status['n_movies'] / status['dataset_wall_s']
        status['staged_sha256'] = {rel: item['sha256'] for rel, item in staged.items()}
        status['observed_aggregate_scratch_prefix'] = observed_aggregate_scratch(out / 'merged')
        status['comparison_view_path_changes'] = canonical_comparison_view(
            out / 'merged', workers, out / 'comparison', status['observed_aggregate_scratch_prefix'])
        status['diagnostic_complete'] = True
    except Exception as exc:
        status['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        stop_owned(children)
        status['observed_until_s'] = time.monotonic() - start
        write(out / 'result.json', status)
    return status


def plots_for(manifest):
    return {star_io.shift_plot_path(movie) for movie in manifest['canonical_movies']}


def verify_unchanged(root, staged):
    for rel, item in staged.items():
        if output_digests.stat_key((root / rel).stat()) != item['dst_key']:
            raise RuntimeError(f'aggregate rewrote worker product {rel}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--execute-diagnostic', action='store_true')
    a = parser.parse_args()
    plan = json.loads(a.plan.read_text())
    mask = validate(plan)
    plan.setdefault('star_sha256', sha(plan['star']))
    for config in plan['configurations']:
        config.setdefault('binary_sha256', sha(config['binary']))
    if a.out.exists():
        parser.error('use a fresh output directory')
    a.out.mkdir(parents=True)
    write(a.out / 'plan.json', plan)
    write(a.out / 'preflight.json', {c['name']: memory_preflight(plan, c) for c in plan['configurations']})
    if not a.execute_diagnostic:
        return 0
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, interrupted)
    os.sched_setaffinity(0, mask)
    # Single external benchmark mutex, not one lock per worker.
    with open(plan.get('lock', '/tmp/motioncorr-bench.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = []
        reference = None
        for rep in range(-plan.get('warmups', 1), plan.get('replicates', 6)):
            configs = list(plan['configurations'])
            if rep % 2:
                configs.reverse()
            for config in configs:
                path = a.out / f'r{rep}-{config["name"]}'
                status = one_run(plan, config, path)
                status['replicate'] = rep; status['warmup'] = rep < 0
                if status['diagnostic_complete']:
                    if reference is None:
                        reference = path / 'comparison'
                    comparison = identity.compare_trees(str(reference), str(path / 'comparison'))
                    write(path / 'identity.json', comparison)
                    status['products_identical'] = comparison['identical']
                    if not comparison['identical']:
                        results.append(status)
                        write(a.out / 'results.json', results)
                        raise RuntimeError('product identity failed; refusing further timed work')
                results.append(status)
                write(a.out / 'results.json', results)
                if 'error' in status:
                    raise RuntimeError(status['error'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
