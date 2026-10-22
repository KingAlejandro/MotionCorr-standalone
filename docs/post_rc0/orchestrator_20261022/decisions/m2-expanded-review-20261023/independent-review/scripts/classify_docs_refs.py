#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Classify every `docs` reference in src/tests/tools/CMakeLists.txt/.github at a pinned commit.

Read-only Git object access (`grep`, `cat-file -e`, `rev-parse`, `ls-tree`). The hit set is
`git grep -n -I -E 'docs/'` plus `git grep -n -I -w docs` (path joins such as `/ "docs" /`).
Classes are assigned by the explicit OVERRIDES table (reviewer's reading of each line in context,
with the registration that makes it run); every other hit defaults to COMMENT_OR_LINK and is
resolved against the tree so a dangling target is visible.

usage: classify_docs_refs.py REPO OUTDIR
"""
import csv, json, os, re, subprocess, sys

REPO, OUT = sys.argv[1], sys.argv[2]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', LC_ALL='C')
REF = {'main': '3691374061f782bc84531fd1c79d017ddcb5a7c2', 'e77': 'e77a51a220cb0d91f4ac3c7fac211876d0c6833f',
       'bbf': 'bbf24607dec537bd13351f061047ea38bd38237b', 'pr281': '1b15f10b423c246bd25a6cb7b9252954f7a97131'}
SCOPE = ['src', 'tests', 'tools', 'cmake', '.github', 'CMakeLists.txt']


def git(*a, check=True):
    return subprocess.run(['git', '-c', 'core.quotepath=off', *a], cwd=REPO, env=ENV, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=check).stdout.decode(errors='replace')


def exists(ref, path):
    return subprocess.run(['git', 'cat-file', '-e', f'{REF[ref]}:{path}'], cwd=REPO, env=ENV,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def oid(ref, path):
    r = git('rev-parse', '-q', '--verify', f'{REF[ref]}:{path}', check=False).strip()
    return r or None


def size(ref, path):
    o = oid(ref, path)
    t = git('cat-file', '-t', o, check=False).strip() if o else ''
    if t == 'blob':
        return int(git('cat-file', '-s', o))
    if t == 'tree':
        rows = git('ls-tree', '-r', '-l', REF[ref], '--', path).splitlines()
        return sum(int(r.split('\t')[0].split()[3]) for r in rows)
    return None


# (path, line) -> (class, registration/scenario, note)
CT_CPU = 'ctest (CPU build, run by CI `ctest`)'
OV = {}
def ov(path, lines, cls, scen, note=''):
    for l in (lines if isinstance(lines, (list, tuple)) else [lines]):
        OV[(path, l)] = (cls, scen, note)

ov('CMakeLists.txt', 1224, 'ACTIVE_BUILD_INPUT', 'add_test(CudaU16FailurePaths) argv[4]; only if -DMOTIONCORR_U16_TEST_MOVIE set (CUDA, hardware label, opt-in); script receives comparator path',
   'file is not checked at configure; used by tests/run_u16_failure_controls.sh')
ov('tests/run_enumeration_boundary_control.py', 27, 'ACTIVE_EXEC_READ', 'default --comparator, executed via subprocess (:112); NOT registered in CMake/CI (manual hardware control)')
ov('tests/run_preprocessing_failure_controls.py', 69, 'ACTIVE_EXEC_READ', 'only with --float-host (importlib exec of compare-native.py); --float-host is not registered in CMake')
ov('tests/run_preprocessing_failure_controls.py', 70, 'ACTIVE_EXEC_READ', 'default branch: importlib exec of compare_output_trees.py; ctest CudaPreprocessingFailurePaths (CUDA build, hardware label)')
ov('tests/run_stale_cuda_error_controls.py', 54, 'ACTIVE_EXEC_READ', 'importlib exec at import time; ctest CudaStaleErrorAfterOom (CUDA build, hardware label)')
ov('tests/run_tiff_identity_later_chunk_controls.py', 19, 'ACTIVE_EXEC_READ', 'sys.path insert + import compact_compare_output_trees; ctest CudaNvcompTiffIdentityLaterChunk (CUDA build, hardware label)')
ov('tests/test_compare_output_trees.py', 16, 'ACTIVE_EXEC_READ', 'importlib exec of comparator under test; ' + CT_CPU + ' OutputTreeComparator', 'path joins `/ "docs" /`; absent from the `docs/` regex')
ov('tests/test_sticky_cuda_process_lifecycle.py', 245, 'ACTIVE_EVIDENCE_FIXTURE', 'reads docs/issue213/evidence/control-{cuda,nvcomp}-final/{single,multi}.txt as retained console records; ' + CT_CPU + ' StickyCudaProcessLifecycle (UNIX)',
   'directory absent from main; arrives with C1')
ov('tools/test_combined_eval.py', 16, 'ACTIVE_EXEC_READ', 'subprocess runs docs/post_rc0/s1/synth_combined/eval_v2.py; CI step `python3 tools/test_combined_eval.py -v` (ci.yml:105); not in ctest', 'directory absent from main; arrives with C1')
ov('tools/gate_representations.py', [18, 19], 'ACTIVE_FILE_READ', 'reads docs/cuda_24_movies_gate2_rerun.json and docs/spa_24_movies_manifest.json; table regenerator, not registered in CMake/CI', 'path joins `REPO / "docs" /`')
ov('tools/nsys_analysis/selftest.py', [150, 207], 'ACTIVE_FILE_READ', 'reads docs/profiling_20261001/data24/arms24.json (fails the check if absent); selftest not registered in CMake/CI')
for f in ('run_dose_options.py', 'run_option_matrix.py'):
    ov(f'tools/single_gpu/{f}', [6, 7], 'ACTIVE_FILE_READ_USER_SOURCE_TREE', 'loads docs/issue85_laneC/{compare_output_trees.py,tutorial_24_movie_manifest.json} from required --source tree (a checkout supplied by the caller); not registered')
ov('tools/single_gpu/run_dose_pairs.py', [50, 135], 'ACTIVE_FILE_READ_USER_SOURCE_TREE', 'docs/issue85_laneC/... under --source (:50 only when --manifest absent); not registered')
ov('tools/single_gpu/run_pairs.py', [25, 97], 'ACTIVE_FILE_READ_USER_SOURCE_TREE', 'docs/issue85_laneC/... under --source; not registered')
ov('tools/single_gpu/refresh_profile.sh', 23, 'ACTIVE_FILE_READ_USER_SOURCE_TREE', 'reads $D/baseline-src/docs/issue85_laneC/... (a baseline source copy under the caller-chosen $D); not registered')
ov('tools/run_cuda_reconstruction_validation.py', 77, 'GENERATED_PATH', 'default value of --out-json (output written under docs/, never read)')
ov('src/motioncorr_runner.cpp', 143, 'STRING_LITERAL', 'CLI --profile help text names docs/stage_profile.md; no read')
ov('tests/test_native_movie_staging.cpp', 222, 'STRING_LITERAL', 'printf failure message names docs/issue95_staging; no read')
ov('tools/multi_gpu/merge_workers.py', 359, 'STRING_LITERAL', 'error-message text names docs/multi_gpu/AGGREGATE_STAGING.md; no read')
ov('tools/profiling/lib/report.py', 22, 'STRING_LITERAL', 'report label constant names docs/stage_profile.md; no read')
ov('src/float16.h', 53, 'FALSE_POSITIVE', 'URL `gcc.gnu.org/onlinedocs/`; not a repository path')
ov("src/error.h", 173, "FALSE_POSITIVE", "URL docs.amd.com inside an error-message string; not a repository path")
ov("tools/profiling/tests/fixtures/nsys_2024_6_schema.sql", 216, "FALSE_POSITIVE", "SQL column comment \"See docs for format\"; not a repository path")

hits = {}
for pat in (['-E', 'docs/'], ['-w', 'docs']):
    out = git('grep', '-n', '-I', *pat, REF['e77'], '--', *SCOPE, check=False)
    for l in out.splitlines():
        _, rest = l.split(':', 1)
        p, ln, text = rest.split(':', 2)
        hits[(p, int(ln))] = text

path_re = re.compile(r'docs/[A-Za-z0-9_.\-/]*[A-Za-z0-9_\-/]')
rows = []
for (p, ln), text in sorted(hits.items()):
    cls, scen, note = OV.get((p, ln), ('COMMENT_OR_LINK', 'comment/docstring/markdown link; not executed', ''))
    refs = sorted(set(path_re.findall(text)))
    if '"docs"' in text:  # path-join form: record the joined targets explicitly
        refs = sorted(set(re.sub(r'["\s]', '', m) for m in re.findall(r'"docs"(?:\s*/\s*"[^"]+")+', text)))
        refs = [r for r in refs if r]
    res = []
    for r in refs:
        r = r.rstrip('.')
        if cls == 'FALSE_POSITIVE':
            continue
        rec = {'path': r}
        for k in REF:
            rec[k] = oid(k, r)
        rec['bytes_e77'] = size('e77', r) if rec['e77'] else None
        res.append(rec)
    rows.append({'file': p, 'line': ln, 'class': cls, 'scenario': scen, 'note': note, 'text': text.strip()[:240], 'targets': res})

# supplementary: top-level dirs outside the requested scope that mention docs/ (not classified line by line)
supp = {}
for d in (['scripts'], ['automation'], ['test-data'], ['agents'], ['.agents'], ['skills'], ['README.md'], ['AGENTS.md'], ['CLAUDE.md'], ['SOURCE_MANIFEST.txt']):
    out = git('grep', '-c', '-I', '-E', 'docs/', REF['e77'], '--', *d, check=False)
    for l in out.splitlines():
        _, rest = l.split(':', 1)
        f, n = rest.rsplit(':', 1)
        supp[f] = int(n)

scope_trees = {k: {s: oid(k, s) for s in SCOPE + ['.github/workflows/ci.yml']} for k in ('main', 'e77', 'bbf')}
summary = {'hit_lines': len(rows), 'files': len({r['file'] for r in rows})}
byc = {}
for r in rows:
    byc.setdefault(r['class'], []).append(r)
summary['by_class_lines'] = {k: len(v) for k, v in sorted(byc.items())}
summary['by_class_files'] = {k: len({r['file'] for r in v}) for k, v in sorted(byc.items())}
dang = [(r['file'], r['line'], t['path']) for r in rows for t in r['targets']
        if r['class'] in ('COMMENT_OR_LINK', 'STRING_LITERAL') and not t['e77']]
summary['non_resolving_comment_or_string_targets_at_e77'] = [list(x) for x in dang]
active_missing_main = sorted({t['path'] for r in rows for t in r['targets'] if r['class'].startswith('ACTIVE') and t['e77'] and not t['main']})
summary['active_targets_absent_from_main_present_at_e77'] = active_missing_main
active_missing_e77 = sorted({t['path'] for r in rows for t in r['targets'] if r['class'].startswith('ACTIVE') and not t['e77']})
summary['active_targets_not_resolving_at_e77'] = active_missing_e77
summary['scope_tree_oids'] = scope_trees
summary['scope_oids_identical_main_vs_e77'] = {s: scope_trees['main'][s] == scope_trees['e77'][s] for s in scope_trees['e77']}
summary['scope_oids_identical_e77_vs_bbf'] = {s: scope_trees['e77'][s] == scope_trees['bbf'][s] for s in scope_trees['e77']}
summary['supplementary_out_of_scope_docs_mentions'] = supp
os.makedirs(OUT, exist_ok=True)
json.dump({'ref': REF['e77'], 'summary': summary, 'rows': rows}, open(os.path.join(OUT, 'docs_refs_classified.json'), 'w'), indent=1)
with open(os.path.join(OUT, 'docs_refs_classified.csv'), 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['file', 'line', 'class', 'targets(path|main|e77|bbf)', 'scenario', 'note', 'text'])
    for r in rows:
        tg = ';'.join(f"{t['path']}|{'Y' if t['main'] else 'N'}|{'Y' if t['e77'] else 'N'}|{'Y' if t['bbf'] else 'N'}" for t in r['targets'])
        w.writerow([r['file'], r['line'], r['class'], tg, r['scenario'], r['note'], r['text']])
print(json.dumps({k: summary[k] for k in ('hit_lines', 'files', 'by_class_lines', 'by_class_files',
                                           'active_targets_absent_from_main_present_at_e77',
                                           'active_targets_not_resolving_at_e77',
                                           'non_resolving_comment_or_string_targets_at_e77')}, indent=1))
