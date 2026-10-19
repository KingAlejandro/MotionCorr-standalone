#!/usr/bin/env python3
"""Probe: `multigpu_publication.py --dry-run` performs no side effect on either path.

Every call that could change the filesystem or start work (subprocess, rmtree, symlink, unlink,
mkdir, write_text/write_bytes, copytree, run_case, run_tool, build_mixed_inputs, filtered_copy) is
replaced by a stub that records the call and raises. Dry runs (non-mixed and --mixed) must finish
with zero recorded calls. Control: the same stubs on a non-dry --mixed run must record a call, so
the probe can observe the side effects it is checking for. Exit 0 only if all three hold.

Run on the QF host (the non-mixed path reads the tutorial movies.star):
  QF_W=... taskset -c $QF_CPUS ~/.mc-venv/bin/python3 tools/probe_multigpu_dryrun.py
"""
import os
import pathlib
import shutil
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import multigpu_publication as mg  # noqa: E402


class SideEffect(Exception):
    pass


calls = []


def stub(name):
    def f(*a, **k):
        calls.append(name)
        raise SideEffect(name)
    return f


STUBS = [(subprocess, 'run'), (subprocess, 'Popen'), (shutil, 'rmtree'), (shutil, 'copytree'), (shutil, 'copy'),
         (os, 'symlink'), (os, 'unlink'), (pathlib.Path, 'mkdir'), (pathlib.Path, 'write_text'),
         (pathlib.Path, 'write_bytes'), (pathlib.Path, 'unlink'), (pathlib.Path, 'symlink_to'),
         (mg, 'run_case'), (mg, 'run_tool'), (mg, 'build_mixed_inputs'), (mg, 'filtered_copy'), (mg, 'dump')]
for obj, attr in STUBS:
    setattr(obj, attr, stub(f'{getattr(obj, "__name__", obj)}.{attr}'))


def attempt(argv):
    calls.clear()
    sys.argv = ['multigpu_publication.py', *argv]
    try:
        mg.main()
        outcome = 'returned'
    except SideEffect as e:
        outcome = f'side effect: {e}'
    return outcome, list(calls)


results = {
    'dry_run_G_L': attempt(['--configs', 'G,L', '--dry-run']),
    'dry_run_mixed': attempt(['--mixed', '--dry-run']),
    'control_mixed_not_dry': attempt(['--mixed']),
}
ok = (results['dry_run_G_L'][1] == [] and results['dry_run_mixed'][1] == []
      and results['control_mixed_not_dry'][1] != [])
for k, (outcome, c) in results.items():
    print(f'{k}: {outcome}; recorded side-effect calls: {c}')
print('PROBE', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
