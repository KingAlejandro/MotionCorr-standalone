#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Actual gain-cache header ownership controls and powered mutants, without CUDA.

Runs this same driver under normal and optimized Python. No assertion is used
for acceptance. Old production and mutants must compile and fail at the intended
runtime ownership assertion. These controls do not establish native GPU output.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


PREDECESSOR_COMMIT = 'd06428ddc590d67985281cc8cbf93e4521138fb1'
PREDECESSOR_SHA256 = '755b96b484e716e17999ea0767045c2143b3f89fd09c7409643be5ec16b76d11'

def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def execute(args, root, work):
    work.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.cxx)
    require(compiler is not None, 'C++17 compiler unavailable: ' + args.cxx)
    path = 'src/acc/cuda/cuda_plan_pool.h'
    source = (root / path).read_text()
    # Exact GPL predecessor retained in-tree: CI shallow clones need no history.
    old = (root / 'tests/gain_cache_host_mock/predecessor_cuda_plan_pool.h').read_text()
    require(hashlib.sha256(old.encode()).hexdigest() == PREDECESSOR_SHA256, 'retained predecessor header hash mismatch')
    if args.verify_old_ref:
        historical = subprocess.run(['git', '-C', str(root), 'show', args.verify_old_ref + ':' + path], capture_output=True, text=True, check=True).stdout
        require(historical == old, 'retained predecessor differs from requested Git source')
    selection = '            if (!context.selected()) return false;'
    lease = '        if (lease_holder_ != nullptr && lease_holder_ != holder) return false;'
    require(source.count(selection) == 1, 'owner selection mutation anchor missing/ambiguous')
    require(source.count(lease) == 1, 'live lease mutation anchor missing/ambiguous')
    cases = [
        ('candidate', source, 'all', None, []),
        ('old-production-selection', old, 'selection', 'selection failure freed owned gain', ['-DGAIN_SELECTION_ONLY']),
        ('omit-owner-selection', source.replace(selection, '            // MUTANT: ignore owning-device selection failure', 1), 'selection', 'selection failure freed owned gain', []),
        ('omit-live-lease', source.replace(lease, '        // MUTANT: permit a different live holder', 1), 'lease', 'second session acquired live gain lease', []),
    ]
    records = []
    for name, text, selector, expected, flags in cases:
        folder = work / name
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        binary = folder / 'host-control'
        command = [compiler, '-std=c++17', '-D_CUDA_ENABLED'] + flags + [
            '-I' + str(folder), '-I' + str(root / 'tests/gain_cache_host_mock'),
            '-I' + str(root), str(root / 'tests/cuda_gain_cache_host.cpp'), '-o', str(binary)]
        build = subprocess.run(command, capture_output=True, text=True)
        (folder / 'build.log').write_text(build.stdout + build.stderr)
        require(build.returncode == 0, 'host control build failed: ' + name + '\n' + build.stderr)
        run = subprocess.run([str(binary), '--case', selector], capture_output=True, text=True, timeout=30)
        output = run.stdout + run.stderr
        (folder / 'run.log').write_text(output)
        ok = (run.returncode == 0 and 'PASS: actual gain header host controls case=all' in output) if expected is None else (run.returncode == 1 and 'FAIL: ' + expected in output)
        require(ok, 'control did not discriminate ' + name + '\n' + output)
        records.append({'case': name, 'selector': selector, 'source_sha256': hashlib.sha256(text.encode()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'command': command, 'returncode': run.returncode, 'expected_failure': expected, 'pass': ok})
        print('PASS: ' + name, flush=True)
    result = {'scope': 'actual production header / host API doubles; native UNRUN', 'python_optimized': bool(sys.flags.optimize), 'old_ref': PREDECESSOR_COMMIT, 'old_header_sha256': PREDECESSOR_SHA256, 'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'records': records}
    (work / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    if not args.optimized_child:
        command = [sys.executable, '-O', str(Path(__file__).resolve()), '--cxx', args.cxx,
                   '--root', str(root), '--work', str(work / 'optimized'), '--optimized-child']
        optimized = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (work / 'optimized-driver.log').write_text(optimized.stdout + optimized.stderr)
        require(optimized.returncode == 0, 'optimized interpreter controls failed\n' + optimized.stdout + optimized.stderr)
        optimized_result = json.loads((work / 'optimized/result.json').read_text())
        require(optimized_result['python_optimized'] and len(optimized_result['records']) == len(records) and all(row['pass'] for row in optimized_result['records']), 'optimized interpreter omitted controls')
        print('PASS: optimized interpreter reran all actual-header controls', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cxx', '--compiler', dest='cxx', default='clang++')
    p.add_argument('--work', type=Path)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    p.add_argument('--verify-old-ref', help='Optional local Git confirmation; not required by CI')
    p.add_argument('--optimized-child', action='store_true', help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.work:
        execute(args, args.root.resolve(), args.work.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix='mc-gain-cache-host-') as tmp:
            execute(args, args.root.resolve(), Path(tmp))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
