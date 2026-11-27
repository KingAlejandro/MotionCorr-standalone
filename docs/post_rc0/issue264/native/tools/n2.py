# SPDX-License-Identifier: GPL-2.0-or-later
"""N2: 24 tutorial movies, base 36913740 vs candidate, same options, one backend at a time.

  n2.py inputs                      hash movies.star, gain and the 24 movies in place
  n2.py run ARM BINARY cpu|gpu      one arm (RC0 QF L command, --j 1); gpu needs the GPU1 lock held by the caller
  n2.py compare BASE CAND LABEL     compare_output_trees --products-only (gate) and full (informational)
Inputs are read in place through a symlink; nothing is written to the data directory.
"""
import json, os, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import runlib as r  # noqa: E402

DATA = Path(os.environ['G_TUTORIAL']); FROZEN_L = Path(os.environ['G_FROZEN_L'])
N2 = r.SCR / 'n2'
CMP = r.SCR / 'src-cand/docs/issue85_laneC/compare_output_trees.py'
ARGS = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150', '--seed', '1',
        '--expected_frames', '24', '--gainref', 'Movies/gain.mrc', '--patch_x', '5', '--patch_y', '5']
GUARD = 'could not fit a reasonable local motion model'


def inputs():
    star = (DATA / 'movies.star').read_text()
    movies = re.findall(r'(Movies/\S+\.tiff)', star)
    rec = {'movies_star_sha256': r.sha256_file(DATA / 'movies.star'), 'gain_sha256': r.sha256_file(DATA / 'Movies/gain.mrc'),
           'n_movies': len(movies), 'distinct': len(set(movies)),
           'movies': {m: r.sha256_file(DATA / m) for m in movies}}
    N2.mkdir(parents=True, exist_ok=True)
    (N2 / 'INPUTS.json').write_text(json.dumps(rec, indent=1) + '\n')
    print('movies', len(movies), 'distinct', len(set(movies)))
    return 0 if len(movies) == 24 == len(set(movies)) else 1


def run(arm, binary, backend):
    d = N2 / arm; cwd = d / 'cwd'
    if d.exists():
        raise SystemExit(f'{d} exists; a new iteration needs a new arm name')
    cwd.mkdir(parents=True); os.symlink(DATA / 'Movies', cwd / 'Movies')
    (cwd / 'movies.star').write_bytes((DATA / 'movies.star').read_bytes())
    gpu = backend == 'gpu'
    args = [binary, '--i', 'movies.star', '--o', f'{d}/out/', '--j', '1', *ARGS]
    wit = d / 'ingest-witness.txt'
    if gpu:
        args += ['--ingest', 'auto', '--gpu', '0', '--ingest_witness', str(wit)]
    rec = r.run(arm, args, cwd, d / 'logs', gpu)
    stdout, stderr = Path(rec['stdout']).read_text(errors='replace'), Path(rec['stderr']).read_text(errors='replace')
    stars = sorted((d / 'out/Movies').glob('*_frameImage.star'))
    rec.update({'binary_sha256': r.sha256_file(binary), 'input_star_sha256': r.sha256_file(DATA / 'movies.star'),
                'guard_lines': stdout.count(GUARD) + stderr.count(GUARD),
                'movie_stars': len(stars),
                'local_model_blocks': sum('data_local_motion_model' in s.read_text() for s in stars),
                'cuda_marker': 'Using CUDA acceleration on GPU device 0' in stdout,
                'ingest_witness': wit.read_text().splitlines()[:3] if wit.exists() else []})
    problems = []
    if rec['rc'] != 0: problems.append(f"rc {rec['rc']}")
    if rec['guard_lines'] != 0: problems.append('guard message present (predicted none)')
    if rec['movie_stars'] != 24 or rec['local_model_blocks'] != 24: problems.append('expected 24 STARs with local models')
    if gpu and (rec['gpu_uuids_witnessed'] != [r.UUID] or not rec['cuda_marker']): problems.append('GPU1 not witnessed')
    if not gpu and (rec['gpu_uuids_witnessed'] or '[CUDA' in stdout): problems.append('CUDA activity in a CPU arm')
    rec['problems'] = problems; rec['verdict'] = 'PASS' if not problems else 'FAIL'
    (d / 'RUN.json').write_text(json.dumps(rec, indent=1) + '\n')
    print(arm, rec['verdict'], problems, 'wall_s', rec['wall_s'])
    return 0 if not problems else 1


def compare(base, cand, label):
    out = N2 / 'compare'; out.mkdir(parents=True, exist_ok=True)
    rcs = {}
    for mode in ('products', 'full'):
        extra = ['--products-only'] if mode == 'products' else []
        p = subprocess.run([os.environ['G_PY'], '-I', str(CMP), str(N2 / base / 'out'), str(N2 / cand / 'out'),
                            '--manifest', str(FROZEN_L / 'manifest.json'), '--input-star', str(DATA / 'movies.star'),
                            *extra, '--json-out', str(out / f'{label}-{mode}.json')], capture_output=True, text=True)
        (out / f'{label}-{mode}.txt').write_text(p.stdout + '\n--stderr--\n' + p.stderr)
        rcs[mode] = p.returncode
        print(label, mode, 'rc', p.returncode, (p.stdout.strip().splitlines() or [''])[-1][:200])
    return rcs['products']


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'inputs': sys.exit(inputs())
    if c == 'run': sys.exit(run(sys.argv[2], sys.argv[3], sys.argv[4]))
    if c == 'compare': sys.exit(compare(*sys.argv[2:5]))
    raise SystemExit('unknown command')
