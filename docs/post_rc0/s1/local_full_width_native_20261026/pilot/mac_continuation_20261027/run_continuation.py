#!/usr/bin/env python3
"""Run only the four unlaunched cases via the retained Mac driver."""
import importlib.util
from pathlib import Path
import traceback
here = Path(__file__).resolve().parent
original = here.parent / 'mac_admission_20261027' / 'run_mac_pilot.py'
spec = importlib.util.spec_from_file_location('mac_driver_r1', original)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.ROOT = Path('/tmp/mc-mac-pilot-20261027').resolve() / 'mac-native-r2'
mod.CASES = ['integer', 'fractional', 'flat', 'repeated']
if mod.ROOT.exists():
    raise RuntimeError('continuation namespace already exists; no retry')
try:
    mod.main()
except Exception:
    mod.ROOT.mkdir(parents=True, exist_ok=True)
    (mod.ROOT / 'STOP.txt').write_text(traceback.format_exc())
    raise
