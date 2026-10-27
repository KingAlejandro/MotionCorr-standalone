"""Expected-file rule vs the real old capture listing (read-only)."""
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1])
import capture_witness as C
cap = Path(sys.argv[2]); tot = 0; ok = True
for d in sorted(p for p in cap.iterdir() if p.is_dir()):
    n = json.loads((d / 'alignment-complete.json').read_text())['iterations']
    act = sorted(p.name for p in d.iterdir()); exp = sorted(C.expected_patch_files(n) + ['patch-files.json'])
    ok &= act == exp and json.loads((d / 'patch-files.json').read_text())['files'] == C.expected_patch_files(n); tot += len(act); print(d.name, n, len(act), act == exp)
print('total', tot, 'all_equal', ok)
