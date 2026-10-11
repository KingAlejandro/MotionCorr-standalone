#!/usr/bin/env python3
"""Runner control for the dose-weighting scratch alias (docs/vram_live_ranges.md).

The resident dose-weighted reconstruction carves its scratch from the real-space
movie only when nothing reads that movie afterwards: neither --save_noDW nor
--even_odd_split. The per-movie log line is the witness, and the dose-weighted
micrograph must be byte-identical whether or not the scratch was carved.

--mutant-binary takes the runner built with the predicate replaced by `true`:
its --save_noDW run must log the borrow, or the absence check proves nothing.
Its products stay correct (the unweighted sums are read before dose weighting),
so the log line is the only thing that can see this mutant.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hotpixel_rng_determinism import read_mrc_pixels, write_movie, write_star  # noqa: E402

BORROW = 'Dose-weighting scratch borrowed from the consumed real-space movie'
RESIDENT = 'Dose weighting and summing frames (CUDA in-VRAM)...'
ARMS = {'default': (), 'save_noDW': ('--save_noDW',), 'even_odd': ('--even_odd_split',)}


def invoke(binary: Path, work: Path, name: str, extra):
    out = work / name
    args = [str(binary.resolve()), '--i', 'movies.star', '--o', str(out) + '/', '--use_own',
            '--j', '1', '--seed', '1', '--gpu', '0', '--angpix', '1.0',
            '--dose_weighting', '--dose_per_frame', '1', '--patch_x', '1', '--patch_y', '1', *extra]
    res = subprocess.run(args, cwd=work, text=True, capture_output=True, timeout=300)
    assert res.returncode == 0, f'{name}: rc={res.returncode}\n{res.stdout}\n{res.stderr}'
    log = (out / 'a.log').read_text()
    assert RESIDENT in log, f'{name}: did not take the resident dose-weighting path'
    mrc = out / 'a.mrc'
    data = mrc.read_bytes()
    return log, read_mrc_pixels(mrc), data[:224]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--mutant-binary', type=Path)
    a = p.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        write_movie(work / 'a.mrc', 31, None, [])
        write_star(work / 'movies.star', ['a.mrc'])
        runs = {name: invoke(a.binary, work, name, extra) for name, extra in ARMS.items()}
        assert BORROW in runs['default'][0], 'default run did not carve the dose-weighting scratch'
        for name in ('save_noDW', 'even_odd'):
            assert BORROW not in runs[name][0], f'{name}: carved scratch from a movie that is read later'
            assert runs[name][1] == runs['default'][1], f'{name}: dose-weighted pixels differ from default'
            assert runs[name][2] == runs['default'][2], f'{name}: core header differs from default'
        print('PASS dose-weighting alias: carved by default, not with --save_noDW/--even_odd_split, '
              'dose-weighted micrograph identical')
        if a.mutant_binary:
            log, _, _ = invoke(a.mutant_binary, work, 'mutant_save_noDW', ARMS['save_noDW'])
            assert BORROW in log, 'mutant did not carve with --save_noDW: the absence check cannot discriminate'
            print('PASS mutant predicate carves with --save_noDW and is detected')


if __name__ == '__main__':
    main()
