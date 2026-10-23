# SPDX-License-Identifier: GPL-2.0-or-later
"""N3 iteration 2 driver: the frozen iteration-1 runner and grader (../tools/n3.py) with the
iteration-2 predictions and a separate output directory (n3-iter2/). TEST-ONLY overlay builds.

  n3_iter2.py run cpu|gpu    (gpu: caller holds the GPU1 lock)
  n3_iter2.py grade
"""
import json, sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / 'tools'
sys.path.insert(0, str(TOOLS))
import runlib  # noqa: E402
import n3  # noqa: E402

PRED_PATH = runlib.SCR / 'src-cand/docs/post_rc0/issue264/native/n3-iter2/predictions_iter2.json'
n3.PRED = json.loads(PRED_PATH.read_text())['n3']
n3.CASES = list(n3.PRED) + ['Z_no_overlay']
n3.N3 = runlib.SCR / 'n3-iter2'

if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'run': sys.exit(n3.run(sys.argv[2]))
    if c == 'grade':
        n3.N3.mkdir(parents=True, exist_ok=True)
        sys.exit(n3.grade())
    raise SystemExit('unknown command')
