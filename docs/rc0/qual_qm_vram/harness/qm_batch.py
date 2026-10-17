#!/usr/bin/env python3
"""W-QM harness: run (movie, config, ingest, free-VRAM) cases on GPU1 under a VRAM balloon.

Case spec:  <family>-<G|L>-<auto|compact|float>@<free GiB | none>[:tag]
Multi-movie families: mmA (10441 then tutorial), mmB (10441 then e10361), no gain, no --expected_frames.

Run under:  flock /tmp/motioncorr-gpu1-correctness.lock python3 -I qm_batch.py <spec>...
Every motioncorr run is pinned to CPUs 104-111 and CUDA_VISIBLE_DEVICES=1. The balloon is this
script's own child and is killed in a finally block.
"""
import json, os, re, shutil, signal, subprocess, sys, threading, time
from pathlib import Path

W = Path('/mnt/clathrin/alex-motioncorr-rc0/W-QM')
SRC = W / 'src'
BIN = W / 'build-nvcomp' / 'motioncorr'
BALLOON = W / 'balloon'
PY = '/home/alex/.mc-venv/bin/python3'
CMP = SRC / 'docs/issue85_laneC/compare_output_trees.py'
UUID = 'GPU-cd5b9f86-26e6-0a03-bdd2-effcfa0fe42d'
CPUS = '104-111'
RUNS = W / 'runs'
INPUTS = W / 'inputs'
DROOT = W / 'dataroot'
V = Path.home() / 'motioncorr-validation-20261011-vm'
MM = {'mmA': ['e10441', 'tutorial'], 'mmB': ['e10441', 'e10361'], 'mmC': ['e10441', 'tutorial', 'e10361']}
PICK = {  # which corpus movie per family
    'tutorial': 0, 'e10441': 0, 'e10216': 0, 'e10361': 0, 'e10028': 0, 'e10164': 0,
    'e10474f4': 0, 'e10474f3': 0, 'e12963': 0,
}


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def smi(query):
    r = sh(['nvidia-smi', '-i', UUID, f'--query-gpu={query}', '--format=csv,noheader,nounits'])
    return [int(x) for x in r.stdout.strip().split(',')]


def smi_apps():
    r = sh(['nvidia-smi', '-i', UUID, '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'])
    out = {}
    for line in r.stdout.strip().splitlines():
        if ',' in line:
            p, m = line.split(',')
            try:
                out[int(p)] = int(m)
            except ValueError:
                pass
    return out


def sha256_file(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def setup_dataroot():
    DROOT.mkdir(exist_ok=True)
    links = {'tutorial': V / 'tutorial-data'}
    for acc in ('EMPIAR-10028', 'EMPIAR-10361', 'EMPIAR-10441', 'EMPIAR-10474', 'EMPIAR-10641', 'EMPIAR-12963'):
        links[acc] = V / 'corpus/data-https' / acc
    for acc in ('EMPIAR-10164', 'EMPIAR-10216'):
        links[acc] = Path('/mnt/clathrin/alex-motioncorr-rc0/W-QUAL/data') / acc
    for n, t in links.items():
        l = DROOT / n
        if l.is_symlink():
            l.unlink()
        os.symlink(t, l)


def families():
    d = json.loads((SRC / 'docs/workload_corpus/families.json').read_text())['families']
    return {f['id']: f for f in d}


def link_movie(fam, d, droot, idx=0, with_gain=True):
    rel = fam['movies'][idx]
    src = droot / rel
    name = src.name
    if fam.get('link_rename') and name.endswith('.mrc'):
        name = name[:-4] + fam['link_rename']
    stem, dot, suffix = name.rpartition('.')
    name = stem.replace('.', '_') + dot + suffix
    (d / 'Movies').mkdir(parents=True, exist_ok=True)
    link = d / 'Movies' / name
    if link.is_symlink() or link.exists():
        link.unlink()
    os.symlink(src.resolve(), link)
    ident = {'movie': 'Movies/' + name, 'source': str(src.resolve()), 'bytes': src.stat().st_size}
    if with_gain and fam.get('gain'):
        g = droot / fam['gain']
        gl = d / fam['gain_link']
        if gl.is_symlink() or gl.exists():
            gl.unlink()
        os.symlink(g.resolve(), gl)
        ident['gain'] = fam['gain_link']
    return ident


def write_star(d, fam, movies):
    s = ['# version 30001', '', 'data_optics', '', 'loop_', '_rlnOpticsGroupName #1', '_rlnOpticsGroup #2',
         '_rlnMicrographOriginalPixelSize #3', '_rlnVoltage #4', '_rlnSphericalAberration #5',
         '_rlnAmplitudeContrast #6', 'opticsGroup1 1 %s %s %s 0.1' % (fam['angpix'], fam['voltage'], fam['cs']), '',
         '# version 30001', '', 'data_movies', '', 'loop_', '_rlnMicrographMovieName #1', '_rlnOpticsGroup #2']
    s += ['%s 1' % m for m in movies] + ['']
    (d / 'movies.star').write_text('\n'.join(s))


def prepare(fid, fams):
    """Return (inputs_dir, [movie rel paths], args_without_o, identity dict)."""
    setup_dataroot()
    if fid in MM:
        first = fams[MM[fid][0]]
        d = INPUTS / fid
        movies, ident = [], {}
        for sub in MM[fid]:
            i = link_movie(fams[sub], d, DROOT, PICK[sub], with_gain=False)
            movies.append(i['movie'])
            ident[sub] = i
        write_star(d, first, movies)
        a = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.0', '--bfactor', '150', '--seed', '1',
             '--i', 'movies.star', '--j', '8']
        return d, movies, a, ident
    fam = fams[fid]
    d = INPUTS / fid
    i = link_movie(fam, d, DROOT, PICK[fid])
    write_star(d, fam, [i['movie']])
    a = ['--use_own', '--dose_weighting', '--dose_per_frame', repr(fam['dose']), '--bfactor', '150', '--seed', '1',
         '--expected_frames', str(fam['frames']), '--i', 'movies.star', '--j', '8']
    if i.get('gain'):
        a += ['--gainref', i['gain']]
    if fam.get('eer_grouping'):
        a += ['--eer_grouping', str(fam['eer_grouping']), '--eer_upsampling', '1']
    return d, [i['movie']], a, {fid: i}


def wait_bench_lock():
    waited = 0
    while sh(['flock', '-n', '/tmp/motioncorr-bench.lock', 'true']).returncode != 0:
        time.sleep(15)
        waited += 15
        print(f'  bench lock held, waiting ({waited}s)', flush=True)
    return waited


class Balloon:
    ctx_overhead = None  # MiB used by the balloon's own CUDA context, calibrated once

    def __init__(self):
        self.p = None
        self.held = 0

    def start(self, hold_mib):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES='1')
        self.p = subprocess.Popen([str(BALLOON), str(hold_mib)], env=env, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, preexec_fn=os.setsid)
        line = self.p.stdout.readline()
        if not line.startswith('BALLOON_READY'):
            err = self.p.stderr.read() if self.p.poll() is not None else ''
            raise RuntimeError(f'balloon failed: {line!r} {err!r}')
        self.held = hold_mib

    def stop(self):
        if self.p is None:
            return
        try:
            os.killpg(os.getpgid(self.p.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.p.wait()
        self.p = None
        self.held = 0


def settle_free(expected=None, tries=20):
    last = None
    for _ in range(tries):
        f = smi('memory.free')[0]
        if last is not None and f == last:
            return f
        last = f
        time.sleep(0.5)
    return last


def acquire_free(balloon, target_mib):
    """Leave ~target_mib free on GPU1 using the balloon; returns the measured free MiB."""
    base = settle_free()
    if Balloon.ctx_overhead is None:
        Balloon.ctx_overhead = 420  # first guess; refined below
    for attempt in range(4):
        hold = base - target_mib - Balloon.ctx_overhead
        balloon.start(hold)
        free = settle_free()
        if abs(free - target_mib) <= 48:
            return free
        Balloon.ctx_overhead += target_mib - free  # true overhead = overhead + target - free
        balloon.stop()
        time.sleep(1.0)
        base2 = settle_free()
        if abs(base2 - base) > 64:
            raise RuntimeError(f'GPU1 free changed unexpectedly after balloon stop: {base} -> {base2} (foreign user?)')
    raise RuntimeError('could not calibrate balloon')


def log_witness_lines(outdir):
    pat = re.compile(r'WARNING|falling back|Falling|fallback|streaming|resident|Peak|VRAM|out of memory|cudaMalloc|'
                     r'Failed|failed|Refus|insufficient|Ingest|ingest|nvCOMP|Staging this movie|Released native|Materialized|admission|budget', re.I)
    out = {}
    for p in sorted(Path(outdir).glob('Movies/*.log')):
        lines = [l.strip() for l in p.read_text(errors='replace').splitlines() if pat.search(l)]
        out[p.name] = lines[:60]
    return out


def run_case(spec, fams, timeout=2400):
    m = re.match(r'^(?P<fam>[\w]+)-(?P<cfg>[GL])-(?P<ing>auto|compact|float)@(?P<free>none|[\d.]+)(?::(?P<tag>\w+))?$', spec)
    if not m:
        raise SystemExit(f'bad spec {spec}')
    fid, cfg, ing, free, tag = m['fam'], m['cfg'], m['ing'], m['free'], m['tag']
    free_gib = None if free == 'none' else float(free)
    cid = re.sub(r'[^\w.@-]', '_', spec)
    root = RUNS / cid
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    out = root / 'out'
    inputs, movies, base_args, ident = prepare(fid, fams)
    args = base_args + ['--o', f'{out}/', '--gpu', '0', '--ingest', ing, '--ingest_witness', str(root / 'witness.txt')]
    if cfg == 'L':
        args += ['--patch_x', '5', '--patch_y', '5']
    cmd = ['/usr/bin/time', '-v', '-o', str(root / 'time.txt'), 'taskset', '-c', CPUS, str(BIN)] + args
    rec = {'spec': spec, 'family': fid, 'config': cfg, 'ingest': ing, 'target_free_gib': free_gib,
           'movies': movies, 'identity': ident, 'cmd': ' '.join(cmd[4:]), 'binary_sha256_head': None}
    rec['bench_lock_wait_s'] = wait_bench_lock()
    balloon = Balloon()
    samples = {'peak_used': 0, 'peak_app': 0, 'n': 0, 'min_free': 10 ** 9}
    timeline = []
    stop = threading.Event()
    app_pids = set()

    def sampler(base_used):
        while not stop.is_set():
            try:
                used, free_ = smi('memory.used,memory.free')
                apps = smi_apps()
            except Exception:
                continue
            samples['n'] += 1
            timeline.append((round(time.time() - t0, 2), used, apps))
            samples['peak_used'] = max(samples['peak_used'], used)
            samples['min_free'] = min(samples['min_free'], free_)
            mine = sum(v for k, v in apps.items() if k in app_pids or k not in balloon_pids)
            samples['peak_app'] = max(samples['peak_app'], mine)
            time.sleep(0.15)

    balloon_pids = set()
    try:
        rec['gpu_free_before_balloon_mib'] = settle_free()
        if free_gib is not None:
            rec['free_vram_after_balloon_mib'] = acquire_free(balloon, int(free_gib * 1024))
            balloon_pids.add(balloon.p.pid)
            rec['balloon_held_mib'] = balloon.held
            # actual pid of the balloon's CUDA process is its own pid (no wrapper)
        else:
            rec['free_vram_after_balloon_mib'] = rec['gpu_free_before_balloon_mib']
        base_used = smi('memory.used')[0]
        rec['gpu_used_before_run_mib'] = base_used
        t0 = time.time()
        th = threading.Thread(target=sampler, args=(base_used,), daemon=True)
        th.start()
        env = dict(os.environ, CUDA_VISIBLE_DEVICES='1')
        p = subprocess.Popen(cmd, cwd=inputs, env=env, stdout=open(root / 'stdout.txt', 'w'),
                             stderr=subprocess.STDOUT, preexec_fn=os.setsid)
        try:
            rc = p.wait(timeout=timeout)
            rec['timed_out'] = False
        except subprocess.TimeoutExpired:
            rec['timed_out'] = True
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            rc = p.wait()
        except BaseException:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            raise
        rec['wall_s'] = round(time.time() - t0, 2)
        stop.set()
        th.join(timeout=5)
        with open(root / 'timeline.csv', 'w') as tf:
            for t_, u_, a_ in timeline:
                tf.write(f'{t_},{u_},' + ';'.join(f'{k}:{v}' for k, v in a_.items()) + '\n')
        rec['exit'] = rc
        stop.set()
        th.join(timeout=5)
        rec['sampled'] = {'n': samples['n'], 'peak_gpu_used_mib': samples['peak_used'],
                          'peak_motioncorr_above_baseline_mib': samples['peak_used'] - base_used,
                          'peak_compute_app_mib': samples['peak_app'], 'min_free_mib': samples['min_free']}
    finally:
        stop.set()
        balloon.stop()
    time.sleep(1.5)
    rec['balloon_gone'] = (balloon.p is None)
    rec['gpu_used_after_mib'] = smi('memory.used')[0]
    rec['gpu_apps_after'] = smi_apps()
    # products
    stems = [Path(x).stem for x in movies]
    prods = {}
    for s in stems:
        prods[s] = {ext: (out / 'Movies' / f'{s}{ext}').exists() for ext in ('.mrc', '.star', '.log')}
    rec['products'] = prods
    rec['joint_star'] = (out / 'corrected_micrographs.star').exists()
    rec['witness'] = (root / 'witness.txt').read_text().splitlines() if (root / 'witness.txt').exists() else []
    rec['log_lines'] = log_witness_lines(out)
    tail = (root / 'stdout.txt').read_text(errors='replace').splitlines()
    rec['stdout_tail'] = [l for l in tail if l.strip() and '~~(,_,' not in l][-14:]
    tm = (root / 'time.txt').read_text(errors='replace') if (root / 'time.txt').exists() else ''
    mm_ = re.search(r'Maximum resident set size \(kbytes\): (\d+)', tm)
    rec['max_rss_mib'] = round(int(mm_.group(1)) / 1024) if mm_ else None
    rec['all_products'] = rec['exit'] == 0 and all(all(v.values()) for v in prods.values())
    # compare vs unconstrained baseline of the same case
    rec['compare'] = compare_to_baseline(fid, cfg, ing, free_gib, root, inputs, movies, stems, spec)
    (root / 'result.json').write_text(json.dumps(rec, indent=1))
    # drop bulk products from constrained candidates (baseline trees keep theirs)
    if free_gib is not None:
        for q in root.rglob('*.mrc'):
            rec.setdefault('deleted_mrc', []).append(str(q.relative_to(root)))
            q.unlink()
        for q in root.rglob('*.pdf'):
            q.unlink()
        (root / 'result.json').write_text(json.dumps(rec, indent=1))
    return rec


def mrc_dims(path):
    import struct
    with open(path, 'rb') as f:
        h = f.read(1024)
    return list(struct.unpack_from('<3i', h, 0))


def baseline_dir(fid, cfg, ing):
    return RUNS / f'{fid}-{cfg}-{ing}@none'


def compare_to_baseline(fid, cfg, ing, free_gib, root, inputs, movies, stems, spec):
    if free_gib is None:
        return {'note': 'this is the unconstrained baseline'}
    base = baseline_dir(fid, cfg, ing)
    cand = root
    if not (base / 'result.json').exists():
        return {'note': 'NO BASELINE'}
    b = json.loads((base / 'result.json').read_text())
    if not b.get('all_products'):
        return {'note': 'baseline did not complete'}
    c = json.loads((root / 'result.json').read_text()) if (root / 'result.json').exists() else None
    cres = {}
    if len(movies) > 1:
        return compare_mm(base, cand, inputs, movies, stems)
    if not all(all(v.values()) for v in
               {s: {e: (cand / 'out' / 'Movies' / f'{s}{e}').exists() for e in ('.mrc', '.star', '.log')} for s in stems}.values()) \
            or not (cand / 'out' / 'corrected_micrographs.star').exists():
        return {'note': 'candidate tree incomplete; strict whole-tree comparison not applicable'}
    dims = mrc_dims(base / 'out' / 'Movies' / f'{stems[0]}.mrc')
    man = {'schema_version': 1, 'input_star_sha256': sha256_file(inputs / 'movies.star'), 'expected_shape_xyz': dims,
           'joint_star': 'corrected_micrographs.star', 'movies': movies}
    if len(movies) > 1:
        return compare_mm(base, cand, inputs, movies, stems)
    (cand / 'manifest.json').write_text(json.dumps(man))
    for name, extra in (('strict', []), ('products', ['--products-only'])):
        r = sh([PY, '-I', str(CMP), str(base / 'out'), str(cand / 'out'), '--manifest', str(cand / 'manifest.json'),
                '--input-star', str(inputs / 'movies.star'), '--json-out', str(cand / f'identity-{name}.json'), *extra])
        cres[name + '_rc'] = r.returncode
        cres[name + '_tail'] = (r.stdout + r.stderr)[-600:]
    cres['log_line_diff'] = log_line_diff(base / 'out', cand / 'out', stems[0])
    return cres


def compare_mm(base, cand, inputs, movies, stems):
    """Per-movie identity for multi-movie jobs. Each movie gets a one-movie view tree per arm
    (copied .mrc/.star/.log of that movie plus the baseline's joint STAR filtered to that movie's row,
    used for BOTH arms because a failed job writes no joint STAR) and is run through
    compare_output_trees.py, strict and products-only."""
    import shutil as sh_
    res = {}
    star_text = (base / 'out' / 'corrected_micrographs.star').read_text()
    for mv, stem in zip(movies, stems):
        entry = {}
        cand_has = all((cand / 'out' / 'Movies' / f'{stem}{e}').exists() for e in ('.mrc', '.star', '.log'))
        entry['candidate_products_present'] = cand_has
        if not cand_has:
            res[stem] = entry
            continue
        vroot = cand / 'view' / stem
        if vroot.exists():
            sh_.rmtree(vroot)
        for arm, root in (('base', base), ('cand', cand)):
            (vroot / arm / 'Movies').mkdir(parents=True)
            for e in ('.mrc', '.star', '.log'):
                sh_.copy2(root / 'out' / 'Movies' / f'{stem}{e}', vroot / arm / 'Movies' / f'{stem}{e}')
            keep = []
            for line in star_text.splitlines():
                if 'Movies/' in line and f'Movies/{stem}.' not in line:
                    continue
                keep.append(line)
            (vroot / arm / 'corrected_micrographs.star').write_text(
                ('\n'.join(keep) + '\n').replace(str(base / 'out'), str(vroot / arm)))
        write_star_for_view = vroot / 'movies.star'
        fam_first = None
        vtxt = (inputs / 'movies.star').read_text()
        for other in [m for m in movies if m != mv]:
            vtxt = vtxt.replace(other + ' 1\n', '')
        write_star_for_view.write_text(vtxt)
        dims = mrc_dims(base / 'out' / 'Movies' / f'{stem}.mrc')
        man = {'schema_version': 1, 'input_star_sha256': sha256_file(write_star_for_view),
               'expected_shape_xyz': dims, 'joint_star': 'corrected_micrographs.star', 'movies': [mv]}
        (vroot / 'manifest.json').write_text(json.dumps(man))
        for name, extra in (('strict', []), ('products', ['--products-only'])):
            r = sh([PY, '-I', str(CMP), str(vroot / 'base'), str(vroot / 'cand'), '--manifest', str(vroot / 'manifest.json'),
                    '--input-star', str(write_star_for_view), '--json-out', str(vroot / f'identity-{name}.json'), *extra])
            entry[name + '_rc'] = r.returncode
            entry[name + '_tail'] = (r.stdout + r.stderr)[-500:]
        entry['log_line_diff'] = log_line_diff(base / 'out', cand / 'out', stem)
        for q_ in vroot.rglob('*.mrc'):
            q_.unlink()
        res[stem] = entry
    return {'per_movie': res}


def log_line_diff(a_root, b_root, stem):
    def lines(root):
        p = Path(root) / 'Movies' / f'{stem}.log'
        txt = p.read_text(errors='replace') if p.exists() else ''
        drop = ('Full movie wall time', 'execution time:', 'transfer time:', 'Total GPU alignment time:', 'Kernel:', ' ms')
        return [l.strip() for l in txt.splitlines() if l.strip() and not any(m in l for m in drop)]
    la, lb = lines(a_root), lines(b_root)
    return {'only_in_baseline': [l for l in la if l not in lb][:20], 'only_in_candidate': [l for l in lb if l not in la][:20]}


def main():
    fams = families()
    specs = sys.argv[1:]
    for s in specs:
        # ensure baseline exists before any constrained case
        m = re.match(r'^([\w]+)-([GL])-(auto|compact|float)@(none|[\d.]+)', s)
        if m and m[4] != 'none' and not (baseline_dir(m[1], m[2], m[3]) / 'result.json').exists():
            print(f'== baseline for {s}', flush=True)
            r = run_case(f'{m[1]}-{m[2]}-{m[3]}@none', fams)
            print(summ(r), flush=True)
        print(f'== {s}', flush=True)
        r = run_case(s, fams)
        print(summ(r), flush=True)


def summ(r):
    c = r.get('compare', {})
    if 'per_movie' in c:
        c = dict(note='per-movie ' + '; '.join(f"{k[-12:]}: present={v['candidate_products_present']} strict={v.get('strict_rc')} products={v.get('products_rc')}" for k, v in c['per_movie'].items()))
    return (f"  exit={r['exit']} timeout={r['timed_out']} wall={r['wall_s']}s free_before={r['free_vram_after_balloon_mib']}MiB "
            f"peak_above_base={r['sampled']['peak_motioncorr_above_baseline_mib']}MiB peak_app={r['sampled']['peak_compute_app_mib']}MiB "
            f"witness={[w.split()[-1] for w in r['witness']]} products={r['all_products']} balloon_gone={r['balloon_gone']} "
            f"strict_rc={c.get('strict_rc')} products_rc={c.get('products_rc')} note={c.get('note')}")


if __name__ == '__main__':
    main()
