#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic process-table controls for run_v5_controls.admission (R3-M1). Data only: no process is
spawned or signalled. The base tree is the refused r2 attempt's tree (review-r3/replay).

usage: test_run_v5_admission.py --json OUT.json [--runner PATH]
"""
import argparse, hashlib, importlib.util, json, sys
from pathlib import Path

SID = '8864b6f5-c104-4b3b-8024-85b7fde2b670'
BIRTH = [1792710345, 123456]
CLAUDE = 't3-claude /Users/x/.local/bin/claude-unified --output-format stream-json --resume=%s --add-dir /wt' % SID
WATCHDOG = ("/bin/sh -c { trap '' TERM; read -r _ <&3; kill -TERM 0; sleep 5; kill -KILL 0; } </dev/null >/dev/null 2>&1 &\\012"
            'exec "$@" 3<&- ' + CLAUDE)
RUNNER = 'python3 -B run_v5_controls.py BASE --session-id %s --owner-pid 23920 --owner-birth [..] --expect-worker W' % SID
ME = 70000


def tree(extra=(), owner_cmd=CLAUDE, owner_birth=BIRTH):
    rows = [dict(pid=1, ppid=0, uid=0, cmd='/sbin/launchd'),
            dict(pid=23920, ppid=1, uid=502, cmd=owner_cmd, start=owner_birth),
            dict(pid=23952, ppid=23920, uid=502, cmd=WATCHDOG),
            dict(pid=16404, ppid=23920, uid=502, cmd='/bin/zsh -c -l eval cd /wt'),
            dict(pid=16516, ppid=16404, uid=502, cmd='/bin/zsh'),
            dict(pid=14052, ppid=16516, uid=502, cmd='/bin/zsh -c python3 -B run_v5_controls.py BASE --session-id ' + SID),
            dict(pid=ME, ppid=14052, uid=502, cmd=RUNNER)]
    return rows + list(extra)


CASES = [
    ('refused r2 tree (watchdog child of the owner) is admitted', tree(), 23920, BIRTH, True, None),
    ('orphan duplicate Claude with the same --resume (PPID 1) is refused',
     tree([dict(pid=75362, ppid=1, uid=502, cmd=CLAUDE)]), 23920, BIRTH, False, 'another process of the author session'),
    ('space-separated --resume token outside the owner tree is refused',
     tree([dict(pid=75363, ppid=1, uid=502, cmd='claude --resume %s' % SID)]), 23920, BIRTH, False, 'another process of the author session'),
    ('wrong owner birth is refused', tree(), 23920, [1, 2], False, 'owner birth does not match'),
    ('owner PID that is not an ancestor is refused',
     tree([dict(pid=75362, ppid=1, uid=502, cmd=CLAUDE, start=BIRTH)]), 75362, BIRTH, False, 'not an ancestor'),
    ('owner without the exact token (different id) is refused',
     tree(owner_cmd=CLAUDE.replace(SID, SID + 'x')), 23920, BIRTH, False, 'lacks the exact --resume token'),
    ('unrelated commands mentioning the id are admitted',
     tree([dict(pid=5001, ppid=1, uid=502, cmd='tail -f /Users/x/.claude/projects/p/%s.jsonl' % SID),
           dict(pid=5002, ppid=1, uid=502, cmd='grep --session-id %s notes.txt' % SID)]), 23920, BIRTH, True, None),
    ('unrelated launcher.py / smi.py are admitted',
     tree([dict(pid=5555, ppid=1, uid=502, cmd='python3 /opt/other/launcher.py'),
           dict(pid=5556, ppid=1, uid=502, cmd='python3 /opt/other/smi.py')]), 23920, BIRTH, True, None),
    ('a live foreign v5 harness is refused',
     tree([dict(pid=6001, ppid=1, uid=502, cmd='python3 -B /x/tools/test_gpu_worker_v5.py --json o.json')]), 23920, BIRTH, False, 'control process'),
    ('a live control under the owner but outside the runner chain is refused',
     tree([dict(pid=6002, ppid=16516, uid=502, cmd='python3 -B /x/tools/run_v4_controls_r2.py B')]), 23920, BIRTH, False, 'control process'),
    ('a mock process in another gpu_worker_v5_controls namespace is refused',
     tree([dict(pid=6003, ppid=1, uid=502, cmd='python3 /b/gpu_worker_v5_controls/attempt-x/tmp/t/mock_job ok')]), 23920, BIRTH, False, 'control process'),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--json', required=True)
    ap.add_argument('--runner', default=str(Path(__file__).resolve().parent / 'run_v5_controls.py')); a = ap.parse_args()
    spec = importlib.util.spec_from_file_location('runner_v5', a.runner)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    results = []
    for name, rows, owner, birth, want_ok, want_reason in CASES:
        ok, reason, det = m.admission(rows, ME, owner, birth, SID)
        passed = ok == want_ok and (want_reason is None or want_reason in reason)
        results.append(dict(control=name, result='PASS' if passed else 'FAIL', admitted=ok, reason=reason,
                            other_authors=[r['pid'] for r in det.get('other_authors', [])],
                            control_processes=[r['pid'] for r in det.get('control_processes', [])]))
        print(('PASS ' if passed else 'FAIL ') + name, '->', reason)
    Path(a.json).write_text(json.dumps(dict(schema='run-v5-admission-units/1', runner=a.runner,
        runner_sha256=hashlib.sha256(Path(a.runner).read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), results=results), indent=1) + '\n')
    sys.exit(0 if all(r['result'] == 'PASS' for r in results) else 1)


if __name__ == '__main__':
    main()
