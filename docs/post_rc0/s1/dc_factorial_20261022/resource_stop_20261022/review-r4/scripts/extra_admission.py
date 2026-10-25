# Data-only R4 synthetic admission cases beyond the author's 11. No process is spawned or signalled.
import importlib.util, json, sys
runner, = sys.argv[1:2]
spec = importlib.util.spec_from_file_location('runner_v5_r4', runner); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
SID = '8864b6f5-c104-4b3b-8024-85b7fde2b670'; B = (1792712345, 967305)   # tuple, as ProcessTable.read returns on macOS
CL = 'claude --output-format stream-json --resume=%s' % SID
WD = "/bin/sh -c { trap '' TERM; } exec \"$@\" " + CL
def T(extra=(), owner_cmd=CL, owner_start=B, parent_of_owner=1):
    rows = [dict(pid=1, ppid=0, uid=0, cmd='/sbin/launchd'),
            dict(pid=100, ppid=1, uid=502, cmd='t3-parent'),
            dict(pid=23920, ppid=parent_of_owner, uid=502, cmd=owner_cmd, start=owner_start),
            dict(pid=23952, ppid=23920, uid=502, cmd=WD),
            dict(pid=14052, ppid=23920, uid=502, cmd='/bin/zsh -c python3 -B run_v5_controls.py BASE'),
            dict(pid=70000, ppid=14052, uid=502, cmd='python3 -B run_v5_controls.py BASE --session-id %s' % SID)]
    return rows + list(extra)
cases = [
 ('owner birth tuple (macOS ProcessTable form) vs JSON list birth', T(), 23920, list(B), True),
 ('owner uses space form --resume ID (own token) admitted', T(owner_cmd='claude --resume %s --x' % SID), 23920, list(B), True),
 ('parent of owner carries the exact token (outside owner family) -> refused as other author',
  T(parent_of_owner=100) [:1] + [dict(pid=100, ppid=1, uid=502, cmd='t3-wrapper --resume=%s' % SID)] + T(parent_of_owner=100)[2:], 23920, list(B), False),
 ('owner row missing from process table', [r for r in T() if r['pid'] != 23920], 23920, list(B), False),
 ('ppid cycle among ancestors does not loop', T() + [dict(pid=5, ppid=6, uid=0, cmd='x'), dict(pid=6, ppid=5, uid=0, cmd='y')], 23920, list(B), True),
 ('foreign process with token joined by quotes in a shell string', T([dict(pid=9, ppid=1, uid=502, cmd='bash -c "claude --resume=%s"' % SID)]), 23920, list(B), False),
 ('token with trailing suffix is not the token (unrelated)', T([dict(pid=9, ppid=1, uid=502, cmd='cat x --resume=%s.bak' % SID)]), 23920, list(B), True),
 ('control name as argv of a sibling reader (less run_v5_controls.py) is refused (fail-safe false positive)',
  T([dict(pid=9, ppid=23920, uid=502, cmd='less tools/run_v5_controls.py')]), 23920, list(B), False),
 ('path under another gpu_worker_v4_controls namespace is refused', T([dict(pid=9, ppid=1, uid=502, cmd='python3 /b/gpu_worker_v4_controls/a/x.py')]), 23920, list(B), False),
]
res = []
for name, rows, owner, birth, want in cases:
    ok, reason, d = m.admission(rows, 70000, owner, birth, SID)
    res.append(dict(case=name, admitted=ok, expected=want, result='PASS' if ok == want else 'FAIL', reason=reason))
    print(('PASS ' if ok == want else 'FAIL ') + name, '->', reason)
json.dump(res, open(sys.argv[2], 'w'), indent=1)
