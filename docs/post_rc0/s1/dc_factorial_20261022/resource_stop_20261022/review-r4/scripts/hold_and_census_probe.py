# Data-only: (1) hold_lease with an unwritable receipt dir: does it hold, or raise (=> process exit => lease released)?
# (2) census edge cases. No subprocess, no signals (signal.signal/pause replaced by recorders for the probe).
import importlib.util, json, sys, tempfile, types
from pathlib import Path
spec = importlib.util.spec_from_file_location('w_probe', sys.argv[1]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = {}
calls = []
real_signal, real_pause = m.signal.signal, m.signal.pause
m.signal.signal = lambda *a: calls.append(('signal.signal', a[0]))
class Reached(Exception): pass
def pause(): raise Reached('signal.pause reached (lease would be held)')
m.signal.pause = pause
w = object.__new__(m.Worker)
w.runs = Path(tempfile.gettempdir()) / 'r4-probe-nonexistent-dir' / 'runs'; w.binding = None; w.log = None; w.lock_path = Path('/x/lock')
try:
    w.hold_lease('probe', job='J0'); out['hold_lease_unwritable_receipt'] = 'returned'
except Reached as e: out['hold_lease_unwritable_receipt'] = 'HELD: ' + str(e)
except Exception as e: out['hold_lease_unwritable_receipt'] = 'RAISED %s (no signal ignoring, no pause): lease would be released on process exit' % type(e).__name__
out['signal_calls_before_raise'] = calls
m.signal.signal, m.signal.pause = real_signal, real_pause
with tempfile.TemporaryDirectory() as t:
    w = object.__new__(m.Worker); w.runs = Path(t); w.a = types.SimpleNamespace(expected_jobs=8)
    vals = {'A': '[]', 'B': 'null', 'C': '{"status": ["x"]}', 'D': '{"status": "EXITED"}', 'E': '{"status": "EXITED", "exit": null}',
            'F': '{"status": "CLEANUP_FAILED", "exit": 0}', 'G': '', 'H': '{"status": "EXITED", "exit": 0}'}
    for k, v in vals.items(): (Path(t) / k).mkdir(); (Path(t) / k / 'RUN.json').write_text(v)
    try:
        c = w.census([dict(id=k) for k in vals]); out['census'] = dict(counts=c['counts'], complete=c['complete'])
    except Exception as e: out['census'] = 'RAISED ' + repr(e)
print(json.dumps(out, indent=1))
