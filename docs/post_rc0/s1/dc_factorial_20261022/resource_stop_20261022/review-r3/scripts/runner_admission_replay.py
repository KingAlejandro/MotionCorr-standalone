# Data-only replay of run_v4_controls_r2.py main() admission with a synthetic process table.
# No process is spawned or signalled: processes() is replaced; expected hashes are wrong on purpose,
# so main() can only end in a REFUSED record and never copies inputs or launches the harness.
import importlib.util, os, sys
RUNNER, BASE, case = sys.argv[1], sys.argv[2], sys.argv[3]
SID = '8864b6f5-c104-4b3b-8024-85b7fde2b670'
spec = importlib.util.spec_from_file_location('runner_r2', RUNNER)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
me = os.getpid()
claude = 't3-claude /Users/x/.local/bin/claude-unified --output-format stream-json --resume=%s --add-dir /wt' % SID
watchdog = ("/bin/sh -c { trap '' TERM; read -r _ <&3; kill -TERM 0; sleep 5; kill -KILL 0; } </dev/null >/dev/null 2>&1 &\\012"
            'exec "$@" 3<&- ' + claude)
runner_cmd = 'python3 -B run_v4_controls_r2.py ATTEMPTS --session-id %s --expect-worker W --expect-harness H' % SID
if case == 'hypothetical_runner_argv_without_sid':   # positive control for the owner rule itself
    runner_cmd = 'python3 -B run_v4_controls_r2.py ATTEMPTS'
rows = [dict(pid=1, ppid=0, uid=0, cmd='/sbin/launchd'),
        dict(pid=23920, ppid=1, uid=502, cmd=claude),
        dict(pid=23952, ppid=23920, uid=502, cmd=watchdog),
        dict(pid=16404, ppid=23920, uid=502, cmd='/bin/zsh -c -l eval cd /wt'),
        dict(pid=16516, ppid=16404, uid=502, cmd='/bin/zsh'),
        dict(pid=14052, ppid=16516, uid=502, cmd='/bin/zsh -c python3 -B run_v4_controls_r2.py'),
        dict(pid=me, ppid=14052, uid=502, cmd=runner_cmd)]
if case == 'orphan_duplicate': rows.append(dict(pid=75362, ppid=1, uid=502, cmd=claude))
if case == 'unrelated_launcher': rows.append(dict(pid=5555, ppid=1, uid=502, cmd='python3 /opt/other/launcher.py'))
m.processes = lambda: rows
sys.argv = ['run_v4_controls_r2.py', BASE, '--session-id', SID, '--expect-worker', '0' * 64, '--expect-harness', '0' * 64]
try: m.main()
except SystemExit as e: print('case', case, 'SystemExit', e.code)
