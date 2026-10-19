#!/usr/bin/env python3
"""Per-test pass/fail/skip table from a CTest JUnit file + the ctest log (stdlib only).

usage: summarize_ctest.py ctest-<cfg>.junit.xml ctest-<cfg>.log > ctest-<cfg>.summary.json
"""
import json
import re
import sys
import xml.etree.ElementTree as ET

junit, log = sys.argv[1], sys.argv[2]
root = ET.parse(junit).getroot()
tests = []
for tc in root.iter('testcase'):
    status = 'passed'
    if tc.find('failure') is not None or tc.find('error') is not None:
        status = 'failed'
    elif tc.find('skipped') is not None:
        status = 'skipped'
    else:
        st = tc.get('status')
        if st in ('fail', 'timeout'):
            status = 'failed'
        elif st in ('notrun', 'disabled'):
            status = 'not_run'
    tests.append({'name': tc.get('name'), 'status': status, 'time_s': float(tc.get('time', 0))})
text = open(log, errors='replace').read()
m = re.search(r'(\d+)% tests passed, (\d+) tests failed out of (\d+)', text)
counts = {s: sum(t['status'] == s for t in tests) for s in ('passed', 'failed', 'skipped', 'not_run')}
collected = re.search(r'Total Tests: (\d+)', text)
out = {'collected': int(collected.group(1)) if collected else None, 'junit_testcases': len(tests), 'counts': counts,
       'ctest_summary_line': m.group(0) if m else None,
       'validate_test_collection': re.search(r'CTest Collection Validation: (\w+)', text).group(1)
       if re.search(r'CTest Collection Validation: (\w+)', text) else None,
       'tests': tests}
print(json.dumps(out, indent=1))
