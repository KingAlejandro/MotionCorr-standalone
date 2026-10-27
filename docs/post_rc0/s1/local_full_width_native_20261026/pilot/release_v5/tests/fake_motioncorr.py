#!/usr/bin/env python3
"""Test-only stand-in for the binary: obeys the frozen argv shape, writes tiny synthetic products. Modes come from fake_modes.json next to it."""
import json, os, sys, time
from pathlib import Path
sys.dont_write_bytecode = True
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import fake_products as fp
a = sys.argv[1:]
star = a[a.index('--i') + 1]; out = a[a.index('--o') + 1]
case = star[:-len('.star')]
arm = 'ON' if '--experimental_local_full_width_weight' in a else 'OFF'
modes = {}
mf = here / 'fake_modes.json'
if mf.exists():
    modes = json.loads(mf.read_text()).get('%s/%s' % (case, arm), {})
print('FAKE cwd=%s files=%s' % (os.getcwd(), sorted(os.listdir('.'))))
if modes.get('sleep'):
    time.sleep(modes['sleep'])
fp.write_output(out, case, arm, witness_delta=modes.get('witness_delta', 0), payload=modes.get('payload_bytes', '').encode()[:16] or None)
if modes.get('extra_output'):
    (Path(out) / 'stray.txt').write_text('x')
if not modes.get('no_runtime'):
    Path(os.environ['MC_DIAG_MODEL_OUT']).write_bytes(fp.runtime_bytes(case, arm, ulp=modes.get('global_ulp', False)))
if modes.get('no_dc'):
    sys.stdout.write(fp.stdout_text(case, dc=False))
elif modes.get('dc_zero'):
    sys.stdout.write(fp.stdout_text(case, g=(0, 0)))
elif modes.get('local_work'):
    sys.stdout.write(fp.stdout_text('noisy'))
else:
    sys.stdout.write(fp.stdout_text(case))
sys.exit(modes.get('exit', 0))
