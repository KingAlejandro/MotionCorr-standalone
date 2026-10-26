#!/usr/bin/env python3
"""#226 D3: plan-status classification, real handle cleanup, fatal precedence.

All fatal statuses are simulated returns, never actual poisoned GPU execution.
Each row fails a, then requires b's complete strict products against a reference.
"""
import argparse
import json
import re
from pathlib import Path
import tempfile

from streaming_oom_test_support import prepare, reference, run, failed_products

CASES = {
    'healthy-plan': 'healthy',
    'create-alloc': 'oom', 'create-error': 'error', 'create-fatal': 'fatal',
    'auto-alloc': 'oom', 'auto-error': 'error',
    'make-alloc': 'oom', 'make-error': 'error',
    'cleanup-alloc': 'oom', 'cleanup-error': 'error', 'cleanup-fatal': 'fatal',
    'make-fatal-cleanup-success': 'fatal',
    'make-fatal-cleanup-alloc': 'fatal',
    'auto-fatal-cleanup-alloc': 'fatal',
    'make-error-cleanup-alloc': 'error',
    'make-alloc-cleanup-fatal': 'fatal',
}


def controls(binary, root, cases):
    prepare(root)
    expected = reference(binary, root)
    failures, results = [], []
    for name in cases:
        verdict = CASES[name]
        code, text, output = run(binary, root, name,
            dict(MC_FAULT_ORDINAL='1', MC_STREAMING_PLAN_FAULT=name))
        problems = []
        fatal = 'Fatal CUDA error while planning streaming alignment' in text
        error = 'cuFFT failed while planning streaming alignment' in text
        oom = 'cuFFT workspace planning ran out of memory.' in text
        if verdict == 'healthy':
            from run_stale_cuda_error_controls import inventory, compare_movie, JOINT_STAR
            wanted = {Path(f'Movies/{m}{s}') for m in ('a', 'b') for s in ('.mrc', '.star')} | {JOINT_STAR}
            problems += compare_movie(output, 'a', expected) + compare_movie(output, 'b', expected)
            if inventory(output) != wanted or code != 0 or fatal or error or oom:
                problems.append('healthy planned streaming control failed/publication differs')
        else:
            problems += failed_products(output, expected)
            if code != 1:  # A signal/crash or timeout is never an accepted diagnostic.
                problems.append(f'exit {code}, expected ordinary job failure 1')
            if (fatal, error, oom) != (verdict == 'fatal', verdict == 'error', verdict == 'oom'):
                problems.append(f'classification fatal/error/oom={(fatal, error, oom)}, expected {verdict}')
            if verdict == 'oom' and not re.search(r'Out of GPU memory for Movies/a.mrcs: streaming global alignment requires at least \d+ bytes; available \d+ bytes', text):
                problems.append('missing named OOM with required/available bytes')
        wanted_count = 0 if name.startswith('create-') else 1
        if f'[streamplan] creates={wanted_count} destroys={wanted_count} owned=0' not in text:
            problems.append('missing balanced actual admission-plan ownership witness')
        if wanted_count and '[streamplan] destroy-real result=0' not in text:
            problems.append('real plan destruction did not succeed')
        if name.startswith('make-') or name.startswith('cleanup-') or name == 'healthy-plan':
            if '[streamplan] make-enter rank=2 batch=6' not in text:
                problems.append('planning branch not reached')
        if verdict == 'fatal' and '[streamplan] observed simulated cudaErrorIllegalAddress (peek)' not in text:
            problems.append('fatal runtime status was not observed by production')
        if '[faultinject] remaining-owned=0 stale-releases=0' not in text:
            problems.append('device ownership imbalance')
        if 'incompatible' in text.lower():
            problems.append('misleading incompatible-GPU diagnostic')
        print(f'{"FAIL" if problems else "PASS"}: {name}: {problems or verdict}', flush=True)
        results.append(dict(case=name, expected=verdict, exit=code, problems=problems))
        failures += [f'{name}: {p}' for p in problems]
    (root / 'grades.json').write_text(json.dumps(results, indent=2) + '\n')
    (root / 'result.txt').write_text('\n'.join(failures) + ('\n' if failures else 'PASS\n'))
    return bool(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--root', type=Path, help='new retained evidence directory')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    args = parser.parse_args()
    if args.root:
        return controls(args.binary.resolve(), args.root.resolve(), args.cases)
    with tempfile.TemporaryDirectory(prefix='mc-streamplan-') as tmp:
        return controls(args.binary.resolve(), Path(tmp) / 'controls', args.cases)


if __name__ == '__main__':
    raise SystemExit(main())
