#!/usr/bin/env python3
"""Check generated declarations, separately from native binary availability.

SPDX-License-Identifier: GPL-2.0-or-later
A focused build leaves unrelated C++ helpers unbuilt; CTest omits their command
from JSON. Do not manufacture executable placeholders or call that a runnable
suite. Validate the actual generated command declarations and drop-one gate.
"""
import json
from pathlib import Path
import shlex
import subprocess
import sys

NAMES = ['RunnerFitBoundary', 'RunnerFitBoundaryMutant_sign',
         'RunnerFitBoundaryMutant_axis-normalization', 'RunnerFitBoundaryMutant_frame-origin']


def main():
    src, build, receipts = map(Path, sys.argv[1:])
    entries = []
    for line in (build/'CTestTestfile.cmake').read_text().splitlines():
        if line.startswith('add_test('):
            tokens = shlex.split(line[len('add_test('):-1])
            assert len(tokens) >= 2
            entries.append(dict(name=tokens[0], command=tokens[1:]))
    actual = subprocess.run(['ctest','--test-dir',str(build),'--show-only=json-v1'],capture_output=True,text=True)
    assert actual.returncode == 0, actual.stderr
    collected = json.loads(actual.stdout)
    assert sorted(t['name'] for t in collected['tests']) == sorted(t['name'] for t in entries)
    inventory = dict(tests=entries)
    (receipts/'declared-collection.json').write_text(json.dumps(inventory,indent=2)+'\n')
    validator = src/'tools/validate_test_collection.py'
    records = []
    for name in [None] + NAMES:
        data = dict(inventory)
        if name:
            data['tests'] = [t for t in entries if t['name'] != name]
            assert len(data['tests']) == len(entries)-1
            data['tests'].append(dict(name='AdditiveFillerTest',command=['/bin/true']))
        cmd = [sys.executable,str(validator)]
        r = subprocess.run(cmd,input=json.dumps(data),capture_output=True,text=True)
        label = 'declared-full' if name is None else 'declared-drop-'+name
        (receipts/(label+'.stdout')).write_text(r.stdout)
        (receipts/(label+'.stderr')).write_text(r.stderr)
        records.append(dict(argv=cmd,case=label,exit=r.returncode))
        assert r.returncode == (0 if name is None else 1), r.stdout+r.stderr
        if name:
            assert 'Missing required test(s): '+name in r.stdout
    (receipts/'registration-check.json').write_text(json.dumps(dict(
        status='PASS',scope='static generated declarations; not built/runnable full suite',
        count=len(entries),commands=records),indent=2)+'\n')
    print(f'PASS {len(entries)} generated declarations, all four drop-one controls')


if __name__ == '__main__':
    main()
