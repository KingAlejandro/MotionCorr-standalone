#!/usr/bin/env python3
"""Probe: product_campaign.refusal_publications() sees every product a refused movie must not have.

Builds throwaway output trees: empty (control, must report nothing), a corrected MRC, a per-movie
STAR, and a joint STAR row naming the movie (each must be reported). Exit 0 only if all hold.
  QF_W=... QF_CPUS=... QF_GPU_UUID=... QF_GPU_LOCK=... python3 tools/probe_campaign_refusal.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import product_campaign as pc  # noqa: E402

STEM = '031_movie'
CASES = {
    'empty tree (control)': ([], False),
    'corrected MRC': ([f'Movies/{STEM}.mrc'], True),
    'noDW MRC only': ([f'Movies/{STEM}_noDW.mrc'], True),
    'per-movie STAR': ([f'Movies/{STEM}.star'], True),
    'joint STAR naming the movie': (['corrected_micrographs.star'], True),
}
ok = True
with tempfile.TemporaryDirectory() as tmp:
    for i, (name, (files, expect)) in enumerate(CASES.items()):
        out = Path(tmp) / f'out{i}'
        (out / 'Movies').mkdir(parents=True)
        for f in files:
            (out / f).write_text(f'Movies/{STEM}.mrc Movies/{STEM}.star\n' if f.endswith('micrographs.star') else 'x')
        found = pc.refusal_publications(out, STEM)
        good = bool(found) == expect
        ok &= good
        print(f"{'ok ' if good else 'BAD'} {name}: {found}")
print('PROBE', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
