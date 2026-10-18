#!/usr/bin/env python3
"""W-D11 in-product harness: one motioncorr job on GPU3 (by UUID) under an optional VRAM balloon.

usage: d11_run.py <binary> <label> <input_dir> <star> <free_gib|none> <ingest> [extra motioncorr args...]
Run inside: flock /tmp/motioncorr-gpu3-correctness.lock. Checks the bench lock is free first.
Writes runs/<label>/{out/,stdout.txt,witness.txt,timeline.csv,result.json}.
"""
import json, os, subprocess, sys, threading, time, hashlib
from pathlib import Path

W = Path('/mnt/clathrin/alex-motioncorr-rc0/W-D11')
BALLOON = W / 'balloon'
UUID = 'GPU-b2cb2c39-8524-17fb-73a8-80cd61dbf83d'
CPUS = '88-95'
BASE = ['--use_own', '--dose_weighting', '--dose_per_frame', '1.0', '--bfactor', '150', '--seed', '1',
        '--j', '8', '--gpu', '0', '--patch_x', '5', '--patch_y', '5']


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def gpu_free_used():
    r = sh(['nvidia-smi', '-i', UUID, '--query-gpu=memory.free,memory.used', '--format=csv,noheader,nounits'])
    return [int(x) for x in r.stdout.strip().split(',')]


def apps():
    r = sh(['nvidia-smi', '-i', UUID, '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'])
    out = {}
    for line in r.stdout.strip().splitlines():
        if ',' in line:
            p, m = line.split(',')
            out[int(p)] = int(m)
    return out


def start_balloon(mib):
    env = dict(os.environ, CUDA_VISIBLE_DEVICES=UUID)
    p = subprocess.Popen(['taskset', '-c', CPUS, str(BALLOON), str(mib)], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, env=env)
    line = p.stdout.readline()
    if 'BALLOON_READY' not in line:
        p.kill(); raise RuntimeError('balloon failed: ' + line)
    time.sleep(0.5)
    return p


def main():
    binary, label, inp, star, free, ingest = sys.argv[1:7]
    extra = sys.argv[7:]
    if sh(['flock', '-n', '/tmp/motioncorr-bench.lock', 'true']).returncode != 0:
        sys.exit('bench lock held; not running')
    run = W / 'runs' / label
    if run.exists():
        subprocess.run(['rm', '-rf', str(run)])
    (run / 'out').mkdir(parents=True)
    res = {'label': label, 'binary': binary, 'binary_sha256': hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
           'input_dir': inp, 'star': star, 'ingest': ingest, 'target_free_gib': free, 'gpu_uuid': UUID, 'cpus': CPUS}
    assert not apps(), 'GPU3 has compute apps before the run: %s' % apps()
    balloon = None
    try:
        if free != 'none':
            target = int(float(free) * 1024)
            f0, _ = gpu_free_used()
            n = f0 - target - 500           # first guess; corrected once from the measured free
            balloon = start_balloon(n)
            f1, _ = gpu_free_used()
            if abs(f1 - target) > 64:
                balloon.kill(); balloon.wait(); time.sleep(1)
                n += f1 - target
                balloon = start_balloon(n)
            res['balloon_mib'] = n
        res['free_mib_at_launch'], res['used_mib_at_launch'] = gpu_free_used()
        cmd = ['taskset', '-c', CPUS, binary] + BASE + ['--i', star, '--o', str(run / 'out') + '/',
               '--ingest', ingest, '--ingest_witness', str(run / 'witness.txt')] + extra
        res['cmd'] = ' '.join(cmd)
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=UUID)
        env.pop('GLIBC_TUNABLES', None)
        t0 = time.time()
        with open(run / 'stdout.txt', 'w') as so:
            p = subprocess.Popen(cmd, cwd=inp, stdout=so, stderr=subprocess.STDOUT, env=env)
            samples = []
            def sample():
                while p.poll() is None:
                    a = apps()
                    samples.append((round(time.time() - t0, 2), a.get(p.pid, 0)))
                    time.sleep(0.2)
            th = threading.Thread(target=sample); th.start()
            rc = p.wait(); th.join()
        res['wall_s'] = round(time.time() - t0, 2)
        res['exit'] = rc
        (run / 'timeline.csv').write_text('t_s,motioncorr_used_mib\n' + ''.join(f'{t},{m}\n' for t, m in samples))
        res['peak_motioncorr_mib'] = max([m for _, m in samples] or [0])
    finally:
        if balloon:
            balloon.kill(); balloon.wait()
    time.sleep(1)
    res['after_free_used_mib'] = gpu_free_used()
    res['after_apps'] = apps()
    res['witness'] = (run / 'witness.txt').read_text().split('\n') if (run / 'witness.txt').exists() else []
    (run / 'result.json').write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ('label', 'exit', 'wall_s', 'free_mib_at_launch', 'witness', 'after_apps') if k in res}))


if __name__ == '__main__':
    main()
