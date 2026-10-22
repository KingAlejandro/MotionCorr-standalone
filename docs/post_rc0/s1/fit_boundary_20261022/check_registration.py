#!/usr/bin/env python3
"""Check generated declarations, separately from native binary availability.

SPDX-License-Identifier: GPL-2.0-or-later
A focused build leaves unrelated C++ helpers unbuilt; CTest omits their command
from JSON. Do not manufacture executable placeholders or call that a runnable
suite. Validate the actual generated command declarations and drop-one gate.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

NAMES = ['RunnerFitBoundary', 'RunnerFitBoundaryMutant_sign',
         'RunnerFitBoundaryMutant_axis-normalization', 'RunnerFitBoundaryMutant_frame-origin']


def declarations(text):
    """Read single-line generated add_test calls, not general CMake source.

    CMake 3.28 bracket-quotes names; other versions emit quoted or bare
    names. Keep command parsing as before and fail closed on unsupported or
    malformed declarations. CTest's canonical names are checked below.
    """
    entries = []
    for line in text.splitlines():
        if not re.match(r'\s*add_test\b', line):
            continue
        call = re.fullmatch(r'\s*add_test\((.*)\)\s*', line)
        if not call:
            raise ValueError('malformed generated add_test call')
        args = call[1].lstrip()
        if args.startswith('['):
            opening = re.match(r'\[(=*)\[', args)
            if not opening:
                raise ValueError('malformed bracket-quoted test name')
            closing = ']' + opening[1] + ']'
            end = args.find(closing, opening.end())
            if end < 0:
                raise ValueError('unterminated bracket-quoted test name')
            name, rest = args[opening.end():end], args[end+len(closing):]
        else:
            token = re.match(r'"(?:\\.|[^"\\])*"|[^\s()"\[\]\\]+', args)
            if not token:
                raise ValueError('malformed test name')
            name = shlex.split(token[0])[0]
            rest = args[token.end():]
        if not name or not rest or not rest[0].isspace():
            raise ValueError('empty name or missing command separator')
        command = shlex.split(rest)
        if not command or not command[0].strip():
            raise ValueError('missing declared command')
        entries.append(dict(name=name, command=command))
    names = [t['name'] for t in entries]
    if not names or len(names) != len(set(names)):
        raise ValueError('empty or duplicate generated test names')
    return entries


def main():
    src, build, receipts = map(Path, sys.argv[1:])
    entries = declarations((build/'CTestTestfile.cmake').read_text())
    actual = subprocess.run(['ctest','--test-dir',str(build),'--show-only=json-v1'],capture_output=True,text=True)
    assert actual.returncode == 0, actual.stderr
    collected = json.loads(actual.stdout)
    canonical = [t['name'] for t in collected['tests']]
    assert all(isinstance(name, str) and name for name in canonical), 'invalid CTest name'
    assert len(canonical) == len(set(canonical)), 'duplicate canonical CTest name'
    by_name = {t['name']: t for t in entries}
    assert set(canonical) == set(by_name), 'generated and canonical CTest names differ'
    entries = [dict(name=name, command=by_name[name]['command']) for name in canonical]
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
