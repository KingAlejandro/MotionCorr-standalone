#!/usr/bin/env python3
"""Probe: grade_ctest.py on synthetic workspaces (R-QF findings on #233). Writes only in a temp dir.

usage: probe_grade_ctest.py --base-src DIR --d11-src DIR
  --base-src: a checkout of main without #228 (cb3699ac); --d11-src: the same plus #228 merged.
Each workspace gets a fresh git repo as src/ holding the six files #228 changes, each taken from one of
the two checkouts, and synthetic build-<cfg>/ (CMakeCache.txt, CTestTestfile.cmake, motioncorr) and
ctest-<cfg>.{log,junit.xml,exit}. Collection, JUnit and logs are synthetic; the validators, the D11
markers and grade_ctest.py are real. Needs ctest on PATH. Exit 0 only if every case has its expected
verdict:
  clean CPU / CUDA without #228, clean CUDA with #228                         PASS
  main run with ProfilingKit failed, no rerun / a complete passing rerun supplied   FAIL
             (the rerun's evidence is reported in the grade file and never changes the verdict)
  D11: production guard without its test integration / integration without guard   FAIL
  inventory: a grade adds only ctest-<cfg>.grade.json and no __pycache__ under src/   PASS,
             with a control showing the inventory sees the .pyc an unguarded import writes
"""
import argparse
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # the probe itself must not leave caches in src/ or tools/
HERE = Path(__file__).resolve().parent
GRADER = HERE / 'grade_ctest.py'
spec = importlib.util.spec_from_file_location('qf_grade', GRADER)
gc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)
FILES = list(gc.D11_MARKERS)


def load_validator(path):
    s = importlib.util.spec_from_file_location('qf_probe_vtc', path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def junit(path, status):
    tcs = []
    for n, st in status.items():
        if st == 'passed':
            tcs.append(f'<testcase name="{n}" status="run" time="0.1"><properties/></testcase>')
        else:
            tcs.append(f'<testcase name="{n}" status="fail" time="0.1"><failure message="x"/></testcase>')
    path.write_text(f'<?xml version="1.0"?><testsuite tests="{len(status)}">{"".join(tcs)}</testsuite>\n')


def make(root, name, sources, cfg, main_fail=(), rerun=None):
    """sources: file -> 'base'|'d11'. rerun: None or dict(exit=..., tests=[...])."""
    W = root / name
    src = W / 'src'
    for rel in FILES:
        f = Path(SRC[sources[rel]]) / rel
        if f.is_file():
            (src / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, src / rel)
    env = dict(os.environ, GIT_AUTHOR_NAME='p', GIT_AUTHOR_EMAIL='p@x', GIT_COMMITTER_NAME='p',
               GIT_COMMITTER_EMAIL='p@x')
    for cmd in (['init', '-q'], ['add', '-A'], ['commit', '-q', '-m', 'probe']):
        subprocess.run(['git', '-C', str(src), *cmd], check=True, env=env)
    sha = subprocess.run(['git', '-C', str(src), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    vtc = load_validator(src / 'tools' / 'validate_test_collection.py')
    with_d11 = all(sources[r] == 'd11' for r in FILES)
    cuda = cfg != 'cpu'
    names = list(vtc.DEFAULT_REQUIRED_TESTS) + (list(getattr(vtc, 'CUDA_REQUIRED_TESTS', [])) if cuda else [])
    for _, (cfgs, ns) in gc.NAMED.items():
        if cfg in cfgs:
            names += [n for n in ns if n not in names]
    target = gc.REFERENCE_COUNTS['with_d11' if with_d11 else 'without_d11'][cfg]
    names += [f'Filler_{k}' for k in range(target - len(names))]
    b = W / f'build-{cfg}'
    b.mkdir(parents=True)
    (b / 'CMakeCache.txt').write_text(f"CUDA:BOOL={'ON' if cuda else 'OFF'}\n")
    (b / 'CTestTestfile.cmake').write_text(''.join(f'add_test({n} "{sys.executable}" "-c" "pass")\n' for n in names))
    (b / 'motioncorr').write_bytes(b'probe ' + cfg.encode())
    bsha = gc.sha256(b / 'motioncorr')
    now = time.time()
    rc = 8 if main_fail else 0
    req = 'required' if cuda else 'not required'
    pre = W / f'ctest-{cfg}'
    Path(f'{pre}.log').write_text(
        f'start {iso(now - 300)} cfg={cfg} HEAD={sha} status=0\nbinary sha256: {bsha}\n'
        f'=== CTest Collection Validation: PASS === \n'
        + (f'  CUDA-only required tests: {req}\n' if hasattr(vtc, 'CUDA_REQUIRED_TESTS') else '')
        + f'validate_test_collection rc=0\ntest_ci_fail_closed rc=0\nctest rc={rc} end {iso(now - 200)}\n')
    junit(Path(f'{pre}.junit.xml'), {n: ('failed' if n in main_fail else 'passed') for n in names})
    Path(f'{pre}.exit').write_text(f'{rc}\n')
    if rerun is not None:
        r = W / f'ctest-{cfg}-rerun'
        Path(f'{r}.log').write_text(
            f'start {iso(now - 100)} cfg={cfg} HEAD={sha} status=0\nbinary sha256: {bsha}\n'
            f'ctest rc={rerun["exit"]} end {iso(now - 60)}\n')
        junit(Path(f'{r}.junit.xml'), {n: 'passed' for n in rerun['tests']})
        Path(f'{r}.exit').write_text(f'{rerun["exit"]}\n')
    return W, sha


def grade(W, sha, cfg, *extra):
    p = subprocess.run([sys.executable, '-I', str(GRADER), cfg, *extra], capture_output=True, text=True,
                       env=dict(os.environ, QF_W=str(W), QF_SHA=sha))
    g = json.loads((W / f'ctest-{cfg}.grade.json').read_text()) if (W / f'ctest-{cfg}.grade.json').exists() else {}
    return p.returncode, g, p.stdout + p.stderr


def inventory(W):
    return {str(p.relative_to(W)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in W.rglob('*') if '.git' not in p.relative_to(W).parts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-src', required=True)
    ap.add_argument('--d11-src', required=True)
    a = ap.parse_args()
    global SRC
    SRC = {'base': a.base_src, 'd11': a.d11_src}
    base = {r: 'base' for r in FILES}
    d11 = {r: 'd11' for r in FILES}
    prod_only = dict(base, **{'src/motioncorr_runner.cpp': 'd11'})
    no_prod = dict(d11, **{'src/motioncorr_runner.cpp': 'base'})
    PK = ['ProfilingKit']
    ok_rerun = dict(exit=0, tests=PK)  # a complete, passing rerun: still must not change the verdict
    cases = [  # name, sources, cfg, main_fail, rerun, rerun-tag?, expected verdict, expected d11 case
        ('clean-cpu-without', base, 'cpu', (), None, False, 'PASS', 'without_d11'),
        ('clean-cuda-without', base, 'cuda', (), None, False, 'PASS', 'without_d11'),
        ('clean-cuda-with', d11, 'cuda', (), None, False, 'PASS', 'with_d11'),
        ('main-failed-no-rerun', base, 'cuda', PK, None, False, 'FAIL', 'without_d11'),
        ('main-failed-passing-rerun-supplied', base, 'cuda', PK, ok_rerun, True, 'FAIL', 'without_d11'),
        ('d11-production-guard-only', prod_only, 'cuda', (), None, False, 'FAIL', 'inconsistent'),
        ('d11-integration-without-guard', no_prod, 'cuda', (), None, False, 'FAIL', 'inconsistent'),
    ]
    bad = 0
    with tempfile.TemporaryDirectory(prefix='qf-probe-grade-') as tmp:
        root = Path(tmp)
        for name, srcs, cfg, mf, rr, tag, want, want_case in cases:
            W, sha = make(root, name, srcs, cfg, mf, rr)
            rc, g, out = grade(W, sha, cfg, *(['--rerun-tag', 'rerun'] if tag else []))
            got, case = g.get('verdict'), g.get('d11', {}).get('case')
            hit = got == want and case == want_case and (rc == 0) == (want == 'PASS')
            if rr is not None:  # the rerun is reported as information
                info = g.get('rerun_info_not_graded', {})
                hit = hit and info.get('exit') == '0' and info.get('junit') == {n: 'passed' for n in rr['tests']}
            bad += not hit
            why = '; '.join(g.get('failures', []))[:240]
            print(f"{'ok ' if hit else 'BAD'} {name}: {got} rc={rc} d11={case} (want {want}/{want_case}) {why}")
        # inventory: fresh workspace, no cache anywhere under src/ before the grade
        W, sha = make(root, 'inventory', base, 'cpu')
        before = inventory(W)
        assert not [k for k in before if '__pycache__' in k], 'fixture already has a cache'
        rc, g, _ = grade(W, sha, 'cpu')
        after = inventory(W)
        added = sorted(set(after) - set(before))
        changed = sorted(k for k in before if k in after and before[k] != after[k])
        hit = rc == 0 and added == ['ctest-cpu.grade.json'] and not changed and set(before) <= set(after)
        bad += not hit
        print(f"{'ok ' if hit else 'BAD'} inventory: grade rc={rc}, added={added}, changed={changed}")
        # control: an import without the guard writes a .pyc, and the inventory sees it
        subprocess.run([sys.executable, '-c', 'import importlib.util,sys;'
                        's=importlib.util.spec_from_file_location("v",sys.argv[1]);'
                        'm=importlib.util.module_from_spec(s);s.loader.exec_module(m)',
                        str(W / 'src/tools/validate_test_collection.py')], check=True)
        pyc = sorted(k for k in set(inventory(W)) - set(after) if '__pycache__' in k)
        hit = bool(pyc)
        bad += not hit
        print(f"{'ok ' if hit else 'BAD'} inventory control (unguarded import): new files {pyc}")
    print('PROBE PASS' if not bad else f'PROBE FAIL ({bad})')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
