"""Guard-removal controls for driver_v5_1 (scratch copies only; mac-testable guards). Linux-only guards (free-disk floor, parent-death signal) are covered by
real-process tests on cpu64 and are NOT mutated here. Shadowed guards would be declared up front. A mutant that kills the test process (rc without a TOTAL line) counts as killed."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
sys.dont_write_bytecode = True
V5 = Path(__file__).resolve().parent.parent
PILOT = V5.parent
REPO = PILOT.parents[4]
PY = sys.executable
D = 'driver_v5_1.py'
M = {
 'sampler_immediate_sample': ([("        rec.sample(p.pid, int((time.monotonic() - t0) * 1000))  # the first iteration is the immediate post-Popen sample\n", "        pass\n")], ['launch'], ['slow child: enough samples'], False),
 'sampler_poll_schedule': ([("time.sleep(min(0.02 if now - t0 < 1.0 else 0.1,", "time.sleep(min(0.5 if now - t0 < 1.0 else 0.5,")], ['launch'], ['slow child: enough samples'], False),
 'summary_threads': ([("            self.max_threads = max(self.max_threads, r['threads'])\n", "            pass\n")], ['sampler'], ['multi-thread child with a differing mask', 'truncation is flagged'], False),
 'failure_counting': ([("        self.failures += 1\n        if len(self.first_errors) < 5:", "        if len(self.first_errors) < 5:")], ['sampler'], ['a read failure gives PARTIAL'], False),
 'unobserved_status': ([("        if self.child_reads:\n            status =", "        if True:\n            status =")], ['sampler'], ['child gone before the first read gives UNOBSERVED'], False),
 'truncation_cap': ([("        if len(self.samples) < self.cap:\n", "        if True:\n")], ['sampler'], ['truncation is flagged'], False),
 'lease_ancestor': ([("    mine = [e for e in here if e[2] in ancestors]", "    mine = here")], ['parse'], ['lease control: peer-held is refused', 'lease control: lane holds an orphaned inode'], False),
 'lease_inode': ([("    here = [e for e in entries if e[5] == st_ino and", "    here = [e for e in entries if True and")], ['parse'], ['lease control: lane holds an orphaned inode'], False),
 'lease_mode': ([("e[0] == 'FLOCK' and e[1] == 'WRITE']", "e[0] == 'FLOCK']")], ['parse'], ['lease control: a read-mode entry is refused'], False),
 'lease_kind': ([("e[0] == 'FLOCK' and e[1] == 'WRITE']", "e[1] == 'WRITE']")], ['parse'], ['lease control: a POSIX lock is refused'], False),
 'cleanup_noop': ([("def _kill_own_group(p):\n    \"\"\"Terminate and reap only our own child's process group (the child is its own session/group leader); never a group we do not own.\"\"\"\n    if p.poll() is not None:\n        return", "def _kill_own_group(p):\n    \"\"\"x\"\"\"\n    return")], ['kbd'], ['own child is reaped after KeyboardInterrupt'], False),
 'ledger_base_exception': ([("    except BaseException as e:  # first failure (also KeyboardInterrupt/SIGTERM/SystemExit)", "    except (DriverStop, P5.PairError, V3.AdmissionError) as e:  # first failure (also KeyboardInterrupt/SIGTERM/SystemExit)")], ['kbd'], ['ledger keeps the real exception and a STOP'], False),
 'sigterm_handler': ([("    old_term = signal.signal(signal.SIGTERM, _on_term)", "    old_term = signal.getsignal(signal.SIGTERM)")], ['sigterm'], ['SIGTERM during the wait is raised inside the campaign'], False),
 'aborted_receipt': ([("        except BaseException as e:  # any other interruption (also KeyboardInterrupt/SIGTERM): our own child group only, reaped, then re-raised\n            aborted = repr(e)", "        except BaseException as e:  # any other interruption (also KeyboardInterrupt/SIGTERM): our own child group only, reaped, then re-raised\n            aborted = 'x'")], ['kbd', 'sigterm', 'sampler_error'], ['own child is reaped after KeyboardInterrupt', 'child reaped, aborted RUN.json'], False),
 'popen_error_kept': ([("            launch_error = repr(e)\n", "            launch_error = 'x'\n")], ['popen'], ['Popen failure keeps a RUN.json with the real exception'], False),
}
FILES = ['pair_decision_v5.py', 'driver_v5.py', 'driver_v5_1.py', 'ADMISSION_V5.json', 'COMMANDS_V5.json']
only = set(sys.argv[2:]) or None
out = {}
for name, (edits, groups, intended, shadowed) in M.items():
    if only and name not in only:
        continue
    with tempfile.TemporaryDirectory(prefix='mc-lfw-v51-mut-') as t:
        t = Path(t)
        pilot = t / 'a' / 'b' / 'c' / 'd' / 'pilot'; v5 = pilot / 'release_v5'; (v5 / 'tests').mkdir(parents=True)
        for f in ('score_fields_v2.py', 'score_fields_v3.py'):
            shutil.copy(PILOT / f, pilot / f)
        for f in FILES:
            shutil.copy(V5 / f, v5 / f)
        for f in (V5 / 'tests').glob('*.py'):
            shutil.copy(f, v5 / 'tests' / f.name)
        src = (v5 / D).read_text()
        for o, n in edits:
            assert src.count(o) == 1, (name, src.count(o))
            src = src.replace(o, n)
        (v5 / D).write_text(src)
        env = dict(os.environ, V5_PIN_PILOT_ROOT=str(PILOT), V5_PIN_REPO_ROOT=str(REPO))
        try:
            p = subprocess.run([PY, '-B', str(v5 / 'tests' / 'test_driver_v5_1.py'), str(t / 'r.json')] + groups, capture_output=True, text=True, env=env, timeout=300)
            stdout, rc = p.stdout, p.returncode
        except subprocess.TimeoutExpired as e:
            stdout, rc = (e.stdout or b'').decode() if isinstance(e.stdout, bytes) else (e.stdout or ''), -999
        failed = [l[5:].split(' :: ')[0] for l in stdout.splitlines() if l.startswith('FAIL ')]
        crashed = 'TOTAL ' not in stdout  # the mutant killed or hung the test process
        covered = [any(frag in f for f in failed) for frag in intended]
        status = 'KILLED' if (crashed or (intended and all(covered))) else 'SURVIVED'
        out[name] = {'status': status, 'groups': groups, 'intended': intended, 'covered': covered, 'failed_count': len(failed), 'crashed_or_hung': crashed, 'failed_tests': failed, 'exit': rc}
        print('%s %s | failed %d%s' % (status, name, len(failed), ' (test process died/hung)' if crashed else ''), flush=True)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
sys.exit(1 if any(v['status'] == 'SURVIVED' for v in out.values()) else 0)
