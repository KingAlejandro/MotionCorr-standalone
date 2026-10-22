#!/usr/bin/env python3
"""Derive the expected CTest collection of C1 per configuration from the PR heads themselves.

For each configuration (cpu, cuda, nvcomp) and each ref (origin/main, every merged PR head, the C1 head)
a throwaway tree is archived and configured (no compilation) and `ctest -N` is parsed. Expected(C1) =
names(main) U union over PRs of (names(PR) - names(main)). The result is frozen into
expected_collection.json before any test is run. Run on 4GPUs from $C1_SCR under the C1 environment.
"""
import json, os, re, subprocess, sys
from pathlib import Path

SCR = Path(os.environ['C1_SCR']); SRC = SCR / 'src'; EU = SCR / 'eu'
PRS = [267, 269, 272, 254, 260, 270, 252, 251, 244, 248, 249, 245, 242, 241]
CUDA = ['-DCUDA=ON', '-DCMAKE_CUDA_ARCHITECTURES=80', '-DCMAKE_CUDA_COMPILER=/usr/local/cuda-12.8/bin/nvcc',
        '-DCUDAToolkit_ROOT=/usr/local/cuda-12.8']
CFG = {'cpu': ['-DCUDA=OFF'], 'cuda': CUDA + ['-DUSE_NVCOMP=OFF'],
       'nvcomp': CUDA + ['-DUSE_NVCOMP=ON', f"-DNVCOMP_ROOT={os.environ['C1_NVCOMP']}"]}
REFS = {'main': 'origin/main', **{f'pr{n}': f'refs/c1/pr{n}' for n in PRS}, 'c1': 'HEAD'}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def names(tree, cfg):
    b = tree / f'build-{cfg}'
    r = run(['taskset', '-c', os.environ['C1_CPUS'], 'cmake', '-S', str(tree / 'src'), '-B', str(b),
             '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_TESTING=ON', f"-DPython3_EXECUTABLE={os.environ['C1_PY']}", *CFG[cfg]])
    if r.returncode:
        raise SystemExit(f'configure failed {tree} {cfg}: {r.stderr[-800:]}')
    t = run(['ctest', '--test-dir', str(b), '-N']).stdout
    return sorted(re.findall(r'Test\s+#\d+:\s+(\S+)', t))


def main():
    out = {'refs': {}, 'cfg': {}}
    for key, ref in REFS.items():
        tree = EU / key; (tree / 'src').mkdir(parents=True, exist_ok=True)
        sha = run(['git', '-C', str(SRC), 'rev-parse', ref]).stdout.strip()
        out['refs'][key] = sha
        a = subprocess.Popen(['git', '-C', str(SRC), 'archive', ref], stdout=subprocess.PIPE)
        subprocess.run(['tar', '-x', '-C', str(tree / 'src')], stdin=a.stdout, check=True); a.wait()
    sys.path.insert(0, str(SRC / 'tools'))
    import validate_test_collection as v
    for cfg in CFG:
        n = {key: names(EU / key, cfg) for key in REFS}
        main = set(n['main'])
        added = {}
        for pr in PRS:
            for t in set(n[f'pr{pr}']) - main:
                added.setdefault(t, []).append(pr)
        expected = main | set(added)
        c1 = set(n['c1'])
        req = list(v.DEFAULT_REQUIRED_TESTS) + (list(v.CUDA_REQUIRED_TESTS) if cfg != 'cpu' else [])
        out['cfg'][cfg] = {
            'main_count': len(main), 'expected_count': len(expected), 'c1_configured_count': len(c1),
            'expected': sorted(expected), 'added_by_pr': {k: sorted(v_) for k, v_ in sorted(added.items())},
            'missing_from_c1': sorted(expected - c1), 'extra_in_c1': sorted(c1 - expected),
            'removed_by_any_pr': sorted({t for pr in PRS for t in main - set(n[f'pr{pr}'])}),
            'required_lists_not_in_c1': sorted(set(req) - c1),
            'added_but_not_in_required_lists': sorted(set(added) - set(req)),
            'required_list_names_checked': len(set(req)),
        }
    (SCR / 'expected_collection.json').write_text(json.dumps(out, indent=1) + '\n')
    bad = any(c['missing_from_c1'] or c['extra_in_c1'] or c['required_lists_not_in_c1'] for c in out['cfg'].values())
    for cfg, c in out['cfg'].items():
        print(cfg, 'main', c['main_count'], 'expected', c['expected_count'], 'C1', c['c1_configured_count'],
              'missing', len(c['missing_from_c1']), 'extra', len(c['extra_in_c1']),
              'required-not-collected', len(c['required_lists_not_in_c1']),
              'removed', len(c['removed_by_any_pr']), 'added-not-in-required-list', len(c['added_but_not_in_required_lists']))
    sys.exit(1 if bad else 0)


main()
