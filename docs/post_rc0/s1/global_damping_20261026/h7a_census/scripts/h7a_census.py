#!/usr/bin/env python3
"""H7a: flags-off (F) and DCb+H2a (C) on the SAME hook binary over the 100 #269 seeded motion-truth movies (the C1 K269 CPU census inputs).

usage: h7a_census.py WORKDIR BINARY C1REF_DIR SRC_ROOT [--only NAME ...]   (run on cpu64 inside the lane; workers are pinned to 8-CPU slices of 32-55)

Movies: the 100 inputs are the census fixtures of the C1 K269 CPU census. They were generated on cpu64 (generate_realistic_motion.py, numpy 2.5.4 + scipy 1.18.1 under
/home/ubuntu/mc-km-truth-20261021/deps, expectations/*.npy). 18 originals are still there and are used in place; the other 82 are regenerated with the same generator and
deps. EVERY movie, retained or regenerated, is accepted only if its sha256 equals the movie.mrcs hash in its RECEIPT.json (the receipts are identical to the 4GPUs
copies the C1 census read), and the regenerated copy is deleted after its runs.
Both arms use the C1 census command line exactly (patch 5x5, group_frames 1, bin_factor 1, seed 1, skip_defect, save_noDW, skip_logfile, ingest float) with --j 8
(the CPU build is bit-deterministic across --j; the F-arm STAR comparison to the C1 --j 2 reference checks that). C adds --experimental_coupled_peak all and
MC_EXPERIMENT_CCF_DC_ARM=both; F has MC_EXPERIMENT_CCF_DC_ARM=none. MC_DIAG_MODEL_OUT captures the runtime field. Truth scoring: tools/check_realistic_motion.py, unchanged.
STOP RULE: if the F STAR of any movie differs from the C1 CPU census STAR, F is re-run once at --j 2 for that movie (recorded), the campaign is stopped, and the
mismatch is reported as an identity defect.
"""
import concurrent.futures as cf, hashlib, json, math, multiprocessing as mp, os, re, shutil, subprocess, sys, time
from pathlib import Path
work, binary, c1ref, src = (Path(a).resolve() for a in sys.argv[1:5])
only = sys.argv[sys.argv.index('--only')+1:] if '--only' in sys.argv else None
KM = Path('/home/ubuntu/mc-km-truth-20261021'); RECEIPTS = Path('/home/ubuntu/mc-synth-eval/fixtures')
CONDITIONS = ['dose1', 'dose05', 'dose2', 'dose4', 'outmodel', 'nonsquare', 'pedestal0', 'pedestal32', 'contrast025', 'contrast4']
SLICES = ['32-39', '40-47', '48-55']
GOOD = [192, 216, 256, 288, 324, 384, 432, 486, 512, 576, 648, 768, 800, 864, 972, 1024, 1296, 1536, 1728, 1944, 2048, 2304, 2592, 3072, 3200, 3456, 3888, 4096, 4608, 5000, 5184, 6144, 6250, 6400, 6912, 7776, 8192, 9216, 10240, 12288, 12500]
STOPFILE = work/'STOP'
sha = lambda b: hashlib.sha256(b).hexdigest()

def digest(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
    return h.hexdigest()

def good(n):
    for g in GOOD:
        if g >= n: return g          # native: `if (good_numbers[i] < request) continue; else return`
    return n

def ccf_dims(nx, ny, B=150.0):
    """Native alignPatch crop: scale = sqrt(-ln 1e-8 / (2 B)); ccf_n = min(findGoodSize(int(n*scale)), n), made even."""
    s = math.sqrt(-math.log(1e-8)/(2*B)); cx = min(good(int(nx*s)), nx); cy = min(good(int(ny*s)), ny)
    cx += cx % 2; cy += cy % 2
    return dict(requested_scale=s, ccf_nx=cx, ccf_ny=cy, crop_x=cx/nx, crop_y=cy/ny, ccf_pixel_in_movie_px=[nx/cx, ny/cy])

def arm_cmd(cpus, j, arm_dir, frames, extra):
    return ['taskset', '-c', cpus, str(binary), '--i', 'input.star', '--o', str(arm_dir/'output'), '--use_own', '--j', str(j), '--patch_x', '5', '--patch_y', '5',
            '--group_frames', '1', '--bin_factor', '1', '--seed', '1', '--skip_defect', '--save_noDW', '--first_frame_sum', '1', '--last_frame_sum', str(frames),
            '--skip_logfile', '--ingest', 'float', '--ingest_witness', str(arm_dir/'ingest.txt')] + extra

def run_arm(name, fixture, cpus, j, arm, frames, binary_sha):
    arm_dir = work/'runs'/name/arm; arm_dir.mkdir(parents=True, exist_ok=False)
    dc, extra = ('none', []) if arm.startswith('F') else ('both', ['--experimental_coupled_peak', 'all'])
    env = os.environ.copy()
    for k in list(env):
        if k.startswith(('MC_DIAG_', 'MC_EXPERIMENT_')): del env[k]
    env.update(OMP_NUM_THREADS=str(j), OPENBLAS_NUM_THREADS='1', MC_EXPERIMENT_CCF_DC_ARM=dc, MC_DIAG_MODEL_OUT=str(arm_dir/'runtime.json'))
    cmd = arm_cmd(cpus, j, arm_dir, frames, extra); t = time.time()
    with (arm_dir/'stdout.log').open('w') as log:
        rc = subprocess.run(cmd, cwd=fixture, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
    row = dict(arm=arm, argv=cmd, exit=rc, seconds=time.time()-t, dc_arm=dc, binary_sha256=binary_sha)
    (arm_dir/'RUN.json').write_text(json.dumps(row, indent=1)+'\n')
    return arm_dir, row

def score(name, fixture, arm_dir):
    p = subprocess.run([sys.executable, str(src/'tools/check_realistic_motion.py'), '--receipt', str(fixture/'RECEIPT.json'), '--runtime', str(arm_dir/'runtime.json'),
                        '--star', str(arm_dir/'output/movie.star'), '--log', str(arm_dir/'output/movie.log'), '--json', str(arm_dir/'metrics.json')], capture_output=True, text=True)
    (arm_dir/'metrics.stderr.txt').write_text(p.stdout+p.stderr)
    return p.returncode

def shrink(arm_dir):
    """Keep STAR, log, runtime, metrics, stdout, witnesses; payload hash of the summed image first; drop the big products."""
    out = arm_dir/'output'; mrc = out/'movie.mrc'; ph = None
    if mrc.exists():
        with open(mrc, 'rb') as f:
            f.seek(1024); h = hashlib.sha256()
            for b in iter(lambda: f.read(8 << 20), b''): h.update(b)
        ph = h.hexdigest(); mrc.unlink()
    for g in ('*.eps', '*.pdf', '*.pdf.lst'):
        for q in out.glob(g): q.unlink()
    return ph

def guard_counts(arm_dir):
    t = (arm_dir/'stdout.log').read_text(); g = {'global': [0, 0], 'patch': [0, 0]}
    for sc, pk, fired in re.findall(r'\[coupled_peak\] scope=(\w+) peaks=(\d+) guard_fired=(\d+)', t):
        g[sc][0] += int(fired); g[sc][1] += int(pk)
    m = re.search(r'MC_EXPERIMENT_CCF_DC arm=(\w+) cpu.global=(\d+)/(\d+) cpu.local=(\d+)/(\d+)', t)
    dc = dict(arm=m.group(1), global_zeroed=int(m.group(2)), global_eligible=int(m.group(3)), patch_zeroed=int(m.group(4)), patch_eligible=int(m.group(5))) if m else None
    it = re.findall(r'\[align\] scope=global iterations=(\d+)', t)
    return dict(guard_fired_over_peaks=g, dc=dc, global_iterations=int(it[-1]) if it else None)

def process(args):
    name, cpus, binary_sha = args
    if STOPFILE.exists(): return dict(movie=name, skipped='campaign stopped')
    cond, seed = name.rsplit('-s', 1); seed = int(seed)
    receipt = json.loads((RECEIPTS/name/'RECEIPT.json').read_text()); want = receipt['files']['movie.mrcs']; r = receipt['recipe']
    row = dict(movie=name, condition=cond, seed=seed, nx=r['nx'], ny=r['ny'], frames=r['frames'], bin_factor=1, early_binning=False, movie_bytes=None,
               ccf_global=ccf_dims(r['nx'], r['ny']), cpus=cpus)
    ret = KM/'fixtures'/name
    if (ret/'movie.mrcs').exists():
        fixture = ret; row['source'] = 'retained original (in place, read-only)'
    else:
        fixture = work/'fixtures'/name; row['source'] = 'regenerated'
        key = 'outmodel' if cond == 'outmodel' else ('nonsquare' if cond == 'nonsquare' else 'inmodel')
        gen_code = ('import sys,time;from pathlib import Path;K=Path("%s");sys.path[:0]=[str(K/"v2/test-data"),str(K/"deps")];import generate_realistic_motion as g;'
                    'g.generate(g.recipe("%s",%d),K/"expectations"/"%s.npy",Path("%s"))') % (KM, cond, seed, key, fixture)
        t = time.time()
        p = subprocess.run(['taskset', '-c', cpus, sys.executable, '-c', gen_code], capture_output=True, text=True, env=dict(os.environ, OMP_NUM_THREADS='1'))
        row['generate_seconds'] = time.time()-t
        if p.returncode: row['error'] = 'generation failed: '+p.stderr[-400:]; return row
    row['movie_bytes'] = (fixture/'movie.mrcs').stat().st_size
    got = digest(fixture/'movie.mrcs'); row['movie_sha256'] = got; row['movie_sha256_equals_receipt'] = (got == want)
    if got != want:
        row['error'] = 'movie hash differs from the receipt; not used'
        if fixture != ret: shutil.rmtree(fixture, ignore_errors=True)
        return row
    ref = json.loads((c1ref/'c1_cpu_ref_index.json').read_text())[name]; refstar = (c1ref/name/'cpu-none/output/movie.star').read_bytes()
    try:
        for arm in ('F', 'C'):
            adir, rr = run_arm(name, fixture, cpus, 8, arm, r['frames'], binary_sha)
            sc = score(name, fixture, adir) if rr['exit'] == 0 else None
            ph = shrink(adir)
            res = dict(exit=rr['exit'], seconds=rr['seconds'], score_exit=sc, payload_sha256=ph, **guard_counts(adir))
            if rr['exit'] == 0 and sc == 0:
                m = json.loads((adir/'metrics.json').read_text())
                res.update(field_runtime=m['field']['angstrom'], field_star=m['serialized_field']['angstrom'], gate_runtime=m['field_distance_status'],
                           sampling=m['sampling_status'], global_converged=m['convergence']['global_converged'], global_iterations=m['convergence']['global_iterations'],
                           patches=[dict(converged=p['converged'], final_increment_px=p['final_increment_px']) for p in m['convergence']['patches']],
                           n_patches=len(m['convergence']['patches']), star_sha256=sha((adir/'output/movie.star').read_bytes()))
            row[arm] = res
            if arm == 'F':
                star = (adir/'output/movie.star').read_bytes() if (adir/'output/movie.star').exists() else b''
                res['star_equals_c1_census'] = (star == refstar); res['payload_equals_c1_census'] = (ph == ref['payload_sha256'])
                if not res['star_equals_c1_census']:
                    adir2, rr2 = run_arm(name, fixture, cpus, 2, 'F-j2-diagnostic', r['frames'], binary_sha)
                    star2 = (adir2/'output/movie.star').read_bytes() if (adir2/'output/movie.star').exists() else b''
                    res['diagnostic_j2_star_equals_c1_census'] = (star2 == refstar); shrink(adir2)
                    STOPFILE.write_text(f'{name}: F STAR differs from the C1 CPU census STAR (identity defect)\n'); row['stop'] = 'identity mismatch'
                    return row
    finally:
        if fixture != ret: shutil.rmtree(fixture, ignore_errors=True)
    return row

def main():
    work.mkdir(parents=True, exist_ok=True); (work/'runs').mkdir(exist_ok=True); (work/'fixtures').mkdir(exist_ok=True)
    binary_sha = digest(binary)
    names = [f'{c}-s{s:02d}' for c in CONDITIONS for s in range(10)]
    if only: names = [n for n in names if n in only]
    # one task queue, three 8-CPU slices: each worker takes the next movie when free
    rows = []
    import queue; free = queue.Queue()
    for s in SLICES: free.put(s)
    def task(n):
        s = free.get()
        try: return process((n, s, binary_sha))
        finally: free.put(s)
    with cf.ThreadPoolExecutor(max_workers=len(SLICES)) as ex:
        for row in ex.map(task, names):
            rows.append(row); (work/'rows.jsonl').open('a').write(json.dumps(row)+'\n')
            print(row['movie'], row.get('stop') or row.get('error') or row.get('skipped') or 'ok', flush=True)
    (work/'census.json').write_text(json.dumps(dict(binary=str(binary), binary_sha256=binary_sha, rows=rows), indent=1)+'\n')

if __name__ == '__main__': main()
