#!/usr/bin/env python3
"""Launcher abort control (review of 5b430d4b, P2-2): a window that fails must stop the campaign.

Runs `<launcher> windows` with CONFIRM_PY pointing at a stub driver that records every invocation and
fails every `run`. Required: exactly one `run` invocation (tutG window 1), no later window, the launcher
exits non-zero.

usage: control_launcher.py --launcher PATH --work DIR
"""
import argparse, json, os, stat, subprocess, sys
from pathlib import Path


def launcher_abort(launcher, work):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    log = work / 'invocations.txt'
    log.write_text('')
    stub = work / 'stub-driver'
    stub.write_text(f'#!/bin/sh\necho "$*" >> {log}\ncase " $* " in *" run "*) exit 1 ;; esac\nexit 0\n')
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    r = subprocess.run(['bash', str(launcher), 'windows'], env=dict(os.environ, CONFIRM_PY=str(stub)),
                       capture_output=True, text=True, timeout=60)
    calls = [l for l in log.read_text().splitlines() if l]
    runs = [l for l in calls if ' run ' in f' {l} ']
    ok = len(runs) == 1 and '--workload tutG --window 1' in runs[0] and r.returncode != 0
    return ok, {'launcher_rc': r.returncode, 'run_invocations': len(runs), 'runs': [x[:80] for x in runs],
                'all_invocations': len(calls)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--launcher', required=True); ap.add_argument('--work', required=True)
    o = ap.parse_args()
    ok, detail = launcher_abort(o.launcher, o.work)
    print(('PASS' if ok else 'FAIL'), json.dumps(detail))
    sys.exit(0 if ok else 1)
