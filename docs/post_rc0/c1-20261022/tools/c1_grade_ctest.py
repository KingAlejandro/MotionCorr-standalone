#!/usr/bin/env python3
"""Grade one CTest run of C1: usage c1_grade_ctest.py cpu|cuda|nvcomp  (reads $C1_SCR/ctest-<cfg>.{log,junit.xml,exit}).

PASS only when: the JUnit test set equals the frozen expected collection (expected_collection.json, derived from the
merged PR heads) and the build's own `ctest -N` listing, every test passed (none failed, skipped or not run), the
required lists are all present, validate_test_collection rc 0 (and test_ci_fail_closed rc 0 for cpu), ctest rc 0.
No count or test is excused; nothing here changes a gate.
"""
import json, os, re, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

cfg = sys.argv[1]; SCR = Path(os.environ['C1_SCR'])
exp = json.loads((SCR / 'expected_collection.json').read_text())['cfg'][cfg]
x = ET.parse(SCR / f'ctest-{cfg}.junit.xml').getroot()
cases = {}
for c in x.iter('testcase'):
    st = c.get('status')
    if c.find('failure') is not None or c.find('error') is not None: st = 'fail'
    if c.find('skipped') is not None: st = 'skipped'
    cases[c.get('name')] = st
log = (SCR / f'ctest-{cfg}.log').read_text()
listing = set(re.findall(r'Test\s+#\d+:\s+(\S+)', subprocess.run(['ctest', '--test-dir', str(SCR / f'build-{cfg}'), '-N'], capture_output=True, text=True).stdout))
rc = lambda tag: (m.group(1) if (m := re.search(tag + r' rc=(\d+)', log)) else None)
# Named independently of every hardcoded required list: declared in CMake by merged PRs, absent from DEFAULT_REQUIRED_TESTS.
EXPLICIT = ['TestHygiene235', 'DatasetFinalization', 'RelionErrorOwnership', 'RelionErrorUnprinted']
v = {
    'explicit_required_not_passed': {t: cases.get(t, 'absent') for t in EXPLICIT if cases.get(t) != 'run'},
    'junit_count': len(cases), 'expected_count': exp['expected_count'], 'listing_count': len(listing),
    'not_run_in_junit': sorted(set(exp['expected']) - set(cases)),
    'unexpected_in_junit': sorted(set(cases) - set(exp['expected'])),
    'listing_vs_expected': {'missing': sorted(set(exp['expected']) - listing), 'extra': sorted(listing - set(exp['expected']))},
    'not_passed': {k: s for k, s in cases.items() if s != 'run'},
    'validate_test_collection_rc': rc('validate_test_collection'),
    'test_ci_fail_closed_rc': rc('test_ci_fail_closed') if cfg == 'cpu' else 'n/a',
    'ctest_rc': (SCR / f'ctest-{cfg}.exit').read_text().strip(),
    'attributed_new_tests_all_passed': {t: cases.get(t) for t in exp['added_by_pr']},
    'added_but_not_in_required_lists': exp['added_but_not_in_required_lists'],
}
ok = (not v['explicit_required_not_passed'] and not v['not_run_in_junit'] and not v['unexpected_in_junit'] and not v['not_passed'] and not any(v['listing_vs_expected'].values())
      and v['validate_test_collection_rc'] == '0' and v['ctest_rc'] == '0' and v['test_ci_fail_closed_rc'] in ('0', 'n/a'))
v['verdict'] = 'PASS' if ok else 'FAIL'
(SCR / f'ctest-{cfg}.c1grade.json').write_text(json.dumps(v, indent=1) + '\n')
print(cfg, v['verdict'], f"{len(cases) - len(v['not_passed'])}/{len(cases)} passed; expected {exp['expected_count']}")
sys.exit(0 if ok else 1)
