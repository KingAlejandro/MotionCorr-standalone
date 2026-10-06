#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Early child failure must retain raw diagnostics despite no movie log."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--script', type=Path,
                        default=Path(__file__).with_name('run_nvcomp_acceptance_controls.py'))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mc-nvcomp-diagnostics-') as tmp:
        root = Path(tmp)
        binary = root / 'startup-failure'
        binary.write_text('#!/bin/sh\necho startup-stdout\necho startup-stderr >&2\nexit 17\n')
        binary.chmod(0o700)
        evidence = root / 'evidence'
        result = subprocess.run([sys.executable, str(args.script.resolve()),
                                 '--binary', str(binary), '--workdir', str(evidence)],
                                text=True, capture_output=True, timeout=30)
        if result.returncode == 0 or 'actual movie diagnostic log missing' not in result.stderr:
            raise RuntimeError('must reject the actual missing movie log')
        log = evidence / 'healthy.log'
        if not log.is_file() or log.read_text() != 'startup-stdout\nstartup-stderr\n':
            raise RuntimeError('raw child stdout/stderr were not preserved')
        rows = json.loads((evidence / 'result.json').read_text())
        if len(rows) != 1 or rows[0]['returncode'] != 17 or rows[0]['pass'] is not False:
            raise RuntimeError('must retain the actual failed invocation verdict')
    print('PASS: missing movie log rejects with child streams and exit verdict retained')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
