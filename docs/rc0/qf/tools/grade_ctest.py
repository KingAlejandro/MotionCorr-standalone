#!/usr/bin/env python3
"""QF items 1-4, 10, 16, 17: grade one CTest configuration written by run_ctest.sh (stdlib only).

usage: grade_ctest.py cpu|cuda|nvcomp [--rerun-tag TAG]
Required: QF_W (holds src/, the frozen checkout, build-<cfg>/ and ctest-<cfg>.*), QF_SHA.
Read-only: collection is taken with `ctest --show-only=json-v1` on a temporary copy of the build's
CTestTestfile.cmake files, because ctest rewrites <build>/Testing/Temporary/LastTest.log even for
--show-only. No test runs, no GPU.
Writes $QF_W/ctest-<cfg>.grade.json; exit 0 only when the verdict is PASS.

The expected collection is derived, not assumed: the set of tests `ctest --show-only` lists for the
frozen build must equal the JUnit test cases of the run, every one must pass (none skipped or not
run), and every name in the frozen source's own required lists (DEFAULT_REQUIRED_TESTS, plus
CUDA_REQUIRED_TESTS when the build has CUDA:BOOL=ON and the list exists) must be among them. The
reference counts below are a cross-check that the frozen composition is the one this runbook
describes; a different count is a FAIL that is resolved by revising the runbook, never by
relaxing a check.

D11 (#228) case, from the six files #228 changes (D11_MARKERS): 'with_d11' when the frozen source has
all of them (the production FailedMovieCudaErrorGuard, the shim's genuine-allocation fault, the control
script, its CMake registration, CUDA_REQUIRED_TESTS and test_ci_fail_closed's restated CUDA suite);
'without_d11' when it has none; anything else, including the production guard without its test
integration, is a FAIL. In 'with_d11' on a CUDA build
the grader also shows that the frozen validator enforces CUDA_REQUIRED_TESTS on this build directory:
CUDA is detected from its CMakeCache.txt, the run's log says the CUDA-only tests were required, and
the same collection minus CudaStaleErrorAfterOom is rejected.

--rerun-tag: the load-sensitive tests named per configuration in the runbook may be rerun once with
`run_ctest.sh <cfg> <TAG> '^(name|...)$'`. A main-run failure confined to them passes only if that rerun
completed (its .exit is 0 and its log ends with `ctest rc=0`), ran after the main run on the same SHA and
binary, wrote its JUnit file during that invocation (mtime between the log's start time and the .exit
file), and that JUnit file holds exactly the failed tests, all passed. Both results are kept in the grade
file. The frozen validator is loaded with bytecode writing disabled, so nothing is written under src/.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REFERENCE_COUNTS = {  # main cb3699ac without / with #228 (D11)
    'without_d11': {'cpu': 74, 'cuda': 107, 'nvcomp': 110},
    'with_d11': {'cpu': 74, 'cuda': 108, 'nvcomp': 111},
}
D11_TEST = 'CudaStaleErrorAfterOom'
D11_TESTED_HEAD = '8cc1a377'  # #228's tested source head; later commits on its branch are docs only
D11_MARKERS = {  # file -> text #228 adds there (checked against 71ab841e..5b430d4b)
    'src/motioncorr_runner.cpp': 'struct FailedMovieCudaErrorGuard',
    'tests/cuda_fault_inject_shim.cpp': 'MC_ALIGN_ALLOC_FAULT',
    'tests/run_stale_cuda_error_controls.py': None,  # presence of the file
    'CMakeLists.txt': f'NAME {D11_TEST}',
    'tools/validate_test_collection.py': None,  # D11_TEST in CUDA_REQUIRED_TESTS (from the module)
    'tools/test_ci_fail_closed.py': f'CUDA_SUITE = ["{D11_TEST}"]',
}
LOAD_SENSITIVE = {'cpu': {'ProfilingKit'}, 'cuda': {'ProfilingKit', 'MultiGpuScheduling'},
                  'nvcomp': {'ProfilingKit', 'MultiGpuScheduling'}}
# Tests the runbook names per item; each must be collected and pass in the listed configurations.
NAMED = {
    'item4_F3': (('cpu', 'cuda', 'nvcomp'), ['TruncatedMrcMovie', 'TruncatedGainDefect']),
    'item4_F3_cuda': (('cuda', 'nvcomp'), ['TruncatedMrcMovieCuda', 'TruncatedGainDefectCuda']),
    'item10_dose': (('cpu', 'cuda', 'nvcomp'), ['CpuDoseSymmetry', 'CpuDoseSymmetryBase']),
    'item12_retry': (('cpu', 'cuda', 'nvcomp'), ['PatchRetryState']),
    'item12_retry_cuda': (('cuda', 'nvcomp'), ['CudaResidentRetryFailures']),
    'item15_D10': (('cpu', 'cuda', 'nvcomp'), ['EerMemorySafety']),
    'item16_D13': (('cpu', 'cuda', 'nvcomp'), ['ReportPlotUndefinedAxis']),
    'item3_T3': (('nvcomp',), ['CudaNvcompAcceptanceFailures', 'CudaNvcompReconstructionFailures', 'CudaAdler32']),
}


def junit_status(path):
    out = {}
    for tc in ET.parse(path).getroot().iter('testcase'):
        st = 'passed'
        if tc.find('failure') is not None or tc.find('error') is not None or tc.get('status') in ('fail', 'timeout'):
            st = 'failed'
        elif tc.find('skipped') is not None:
            st = 'skipped'
        elif tc.get('status') in ('notrun', 'disabled'):
            st = 'not_run'
        out[tc.get('name')] = st
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def check_rerun(rpre, cfg, sha, binary_sha, main_exit, failed):
    """Statuses of the failed tests in the rerun, and every reason the rerun cannot excuse them."""
    log, junit, ex = Path(f'{rpre}.log'), Path(f'{rpre}.junit.xml'), Path(f'{rpre}.exit')
    missing = [str(f.name) for f in (log, junit, ex) if not f.is_file()]
    if missing:
        return {}, [f'missing {missing}']
    probs = []
    text = log.read_text(errors='replace')
    m = re.match(r'start (\S+) cfg=(\S+) HEAD=(\S+) status=(\d+)', text)
    if not (m and m.group(2) == cfg and m.group(3) == sha and m.group(4) == '0'):
        probs.append(f'log header is not cfg={cfg} HEAD={sha} status=0')
    if f'binary sha256: {binary_sha}' not in text:
        probs.append('logged binary differs from build-<cfg>/motioncorr')
    rc = ex.read_text().strip()
    if rc != '0' or not re.search(r'^ctest rc=0 end ', text, re.M):
        probs.append(f'rerun exit {rc!r} (log: {re.findall(r"^ctest rc=.*", text, re.M)})')
    if m:
        start = datetime.datetime.strptime(m.group(1), '%Y-%m-%dT%H:%M:%SZ').replace(
            tzinfo=datetime.timezone.utc).timestamp()
        if start < int(main_exit.stat().st_mtime):
            probs.append('rerun started before the main run finished')
        jt = junit.stat().st_mtime
        if not start <= jt <= ex.stat().st_mtime:
            probs.append('JUnit file was not written by this rerun invocation (mtime outside its start..exit)')
    st = junit_status(junit)
    if sorted(st) != sorted(failed):
        probs.append(f'rerun JUnit holds {sorted(st)}, not exactly the failed tests {sorted(failed)}')
    statuses = {n: st.get(n, 'absent') for n in failed}
    if any(v != 'passed' for v in statuses.values()):
        probs.append(f'rerun statuses {statuses}')
    return statuses, probs


def git(src, *args):  # GIT_OPTIONAL_LOCKS=0: `git status` must not refresh the frozen checkout's index
    return subprocess.run(['git', '-C', str(src), *args], capture_output=True, text=True,
                          env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cfg', choices=('cpu', 'cuda', 'nvcomp'))
    ap.add_argument('--rerun-tag')
    a = ap.parse_args()
    W, SHA = Path(os.environ['QF_W']), os.environ['QF_SHA']
    src, build, pre = W / 'src', W / f'build-{a.cfg}', W / f'ctest-{a.cfg}'
    fails, g = [], {'cfg': a.cfg, 'qf_sha': SHA}

    def need(cond, msg):
        if not cond:
            fails.append(msg)
        return cond

    head = git(src, 'rev-parse', 'HEAD').stdout.strip()
    need(head == SHA, f'src HEAD {head} != QF_SHA')
    need(git(src, 'status', '--porcelain').stdout == '', 'src tree not clean')
    g['src_head'] = head

    # frozen validator: its required lists are the derived expectation
    sys.dont_write_bytecode = True  # no src/tools/__pycache__ in the frozen checkout
    spec = importlib.util.spec_from_file_location('qf_vtc', src / 'tools' / 'validate_test_collection.py')
    vtc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vtc)
    cuda_build = vtc.build_has_cuda(build) if hasattr(vtc, 'build_has_cuda') else None
    cache = (build / 'CMakeCache.txt').read_text(errors='replace')
    cache_cuda = re.search(r'^CUDA:BOOL=(\S+)', cache, re.M)
    cache_cuda = bool(cache_cuda) and cache_cuda.group(1).upper() in ('ON', '1', 'TRUE', 'YES', 'Y')
    need(cache_cuda == (a.cfg != 'cpu'), f'build-{a.cfg} CUDA:BOOL does not match the configuration')
    cuda_list = list(getattr(vtc, 'CUDA_REQUIRED_TESTS', []))

    # D11 case from the frozen source
    marks = {}
    for rel, text in D11_MARKERS.items():
        f = src / rel
        if rel == 'tools/validate_test_collection.py':
            marks[rel] = D11_TEST in cuda_list
        elif text is None:
            marks[rel] = f.is_file()
        else:
            marks[rel] = f.is_file() and text in f.read_text(errors='replace')
    case = 'with_d11' if all(marks.values()) else 'without_d11' if not any(marks.values()) else 'inconsistent'
    need(case != 'inconsistent', f'D11 markers inconsistent: {marks}')
    anc = git(src, 'merge-base', '--is-ancestor', D11_TESTED_HEAD, 'HEAD').returncode
    g['d11'] = {'case': case, 'markers': marks,
                f'{D11_TESTED_HEAD}_is_ancestor': {0: True, 1: False}.get(anc, 'unknown')}

    # collection of the frozen build
    with tempfile.TemporaryDirectory(prefix='qf-collect-') as tmp:
        for f in build.rglob('CTestTestfile.cmake'):
            (Path(tmp) / f.relative_to(build)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, Path(tmp) / f.relative_to(build))
        p = subprocess.run(['ctest', '--test-dir', tmp, '--show-only=json-v1'], capture_output=True, text=True)
    need(p.returncode == 0, f'ctest --show-only rc {p.returncode}')
    data = json.loads(p.stdout) if p.returncode == 0 else {'tests': []}
    collected = [t['name'] for t in data.get('tests', [])]
    required = list(vtc.DEFAULT_REQUIRED_TESTS) + (cuda_list if cache_cuda else [])
    g['collected'] = len(collected)
    g['required'] = len(required)
    g['reference_count'] = REFERENCE_COUNTS.get(case, {}).get(a.cfg)
    need(len(collected) == len(set(collected)), 'duplicate test names in the collection')
    need(not [r for r in required if r not in collected], f'required tests not collected: {[r for r in required if r not in collected]}')
    need(g['reference_count'] == len(collected),
         f'collected {len(collected)} != runbook reference {g["reference_count"]} for {case}: revise the runbook for this composition')
    if case == 'without_d11':
        need(D11_TEST not in collected, f'{D11_TEST} collected although the source has no D11 markers')

    # the run
    log = Path(f'{pre}.log').read_text(errors='replace')
    first = log.splitlines()[0] if log else ''
    need(f'HEAD={SHA}' in first and 'status=0' in first, f'log header not HEAD={SHA} status=0: {first!r}')
    m = re.search(r'binary sha256: ([0-9a-f]{64})', log)
    g['binary_sha256'] = sha256(build / 'motioncorr')
    need(bool(m) and m.group(1) == g['binary_sha256'], 'logged binary sha256 differs from build-<cfg>/motioncorr now')
    need('=== CTest Collection Validation: PASS' in log and 'validate_test_collection rc=0' in log,
         'validate_test_collection did not PASS with rc 0')
    if a.cfg == 'cpu':
        need('test_ci_fail_closed rc=0' in log, 'test_ci_fail_closed rc != 0')
    exit_rc = Path(f'{pre}.exit').read_text().strip()
    g['ctest_exit'] = exit_rc
    st = junit_status(f'{pre}.junit.xml')
    need(sorted(st) == sorted(collected), f'JUnit test set != collection (missing {sorted(set(collected) - set(st))}, '
                                         f'extra {sorted(set(st) - set(collected))}); a -R run is not a full run')
    counts = {k: sum(v == k for v in st.values()) for k in ('passed', 'failed', 'skipped', 'not_run')}
    g['counts'] = counts
    bad = sorted(n for n, v in st.items() if v != 'passed')
    reruns, rerun_problems = {}, []
    if bad and a.rerun_tag and set(bad) <= LOAD_SENSITIVE[a.cfg] and all(st[n] == 'failed' for n in bad):
        reruns, rerun_problems = check_rerun(W / f'ctest-{a.cfg}-{a.rerun_tag}', a.cfg, SHA,
                                             g['binary_sha256'], Path(f'{pre}.exit'), bad)
        if not rerun_problems:
            bad = []
    g['load_sensitive_reruns'] = {'tests': reruns, 'problems': rerun_problems}
    for prob in rerun_problems:
        fails.append(f'rerun does not count: {prob}')
    need(not bad, f'tests not passed: {bad}')
    need(exit_rc == '0' or (reruns and not rerun_problems and not bad), f'ctest exit {exit_rc}')

    named = {}
    for item, (cfgs, names) in NAMED.items():
        if a.cfg in cfgs:
            named.update({n: st.get(n, 'absent') for n in names})
    if case == 'with_d11' and a.cfg != 'cpu':
        named[D11_TEST] = st.get(D11_TEST, 'absent')
    g['named_tests'] = named
    need(all(v == 'passed' for v in named.values()), f'named tests not passed: {[k for k, v in named.items() if v != "passed"]}')

    # item 17: the validator enforces CUDA_REQUIRED_TESTS on this build (with_d11 only)
    if case == 'with_d11':
        line = 'CUDA-only required tests: ' + ('required' if a.cfg != 'cpu' else 'not required')
        enf = {'build_has_cuda': cuda_build, 'log_line': line in log}
        need(cuda_build == (a.cfg != 'cpu'), f'validator build_has_cuda={cuda_build} on build-{a.cfg}')
        need(enf['log_line'], f'run log lacks "{line}"')
        if a.cfg != 'cpu':
            minus = dict(data, tests=[t for t in data['tests'] if t['name'] != D11_TEST])
            ok_full, _ = vtc.validate_tests(data, min_count=23, cuda=cuda_build)
            ok_minus, rep = vtc.validate_tests(minus, min_count=23, cuda=cuda_build)
            enf.update(full_collection_passes=ok_full, minus_d11_rejected=not ok_minus,
                       minus_d11_missing=rep.get('missing_tests'))
            need(ok_full and not ok_minus and rep.get('missing_tests') == [D11_TEST],
                 'validator does not reject this CUDA collection without CudaStaleErrorAfterOom')
        g['d11']['validator_enforcement'] = enf

    g['failures'] = fails
    g['verdict'] = 'FAIL' if fails else 'PASS'
    Path(f'{pre}.grade.json').write_text(json.dumps(g, indent=1) + '\n')
    print(f"{a.cfg}: {g['verdict']} collected={g['collected']} reference={g['reference_count']} d11={case} "
          f"counts={counts}" + ''.join(f'\n  - {f}' for f in fails))
    return 0 if not fails else 1


if __name__ == '__main__':
    sys.exit(main())
