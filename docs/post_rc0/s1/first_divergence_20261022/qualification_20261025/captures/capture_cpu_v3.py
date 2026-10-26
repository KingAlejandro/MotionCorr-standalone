#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Version3: remaining seven CPU13 captures after retained log-neutrality failure; no native retry."""
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tarfile


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(path, value):
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')
    tmp.rename(path)


def check_overlay_archive(path, expected):
    with tarfile.open(path) as t:
        members = t.getmembers()
        if len(expected) != 4 or len(members) != 4 or {m.name for m in members} != set(expected):
            raise RuntimeError('overlay source inventory')
        for m in members:
            if not m.isfile() or not 0 < m.size <= 1024 * 1024:
                raise RuntimeError('overlay source member type/size')
            b = t.extractfile(m).read(m.size + 1)
            if len(b) != m.size or hashlib.sha256(b).hexdigest() != expected[m.name]:
                raise RuntimeError('overlay source identity')


def identities(old, protocol):
    actual = {n: sha(old / n) for n in protocol['pins']}
    if actual != protocol['pins']:
        raise RuntimeError('pinned source/input/binary/baseline drift')
    log_name = 'runs/cpu-affine-on/out/affine.log'
    actual[log_name] = sha(old / log_name)
    if actual[log_name] != '793124b035353e0c5e45d68ac6bfbf2b97516c5fff7f936c00a6cb1b84955dd4':
        raise RuntimeError('retained patch-iteration log drift')
    expected = {n[4:]: h for n, h in protocol['pins'].items() if n.startswith('src/src/')}
    check_overlay_archive(old / 'mc-residual-overlay.tar.gz', expected)
    return actual


def occupancy():
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isascii() or not p.name.isdecimal():
            continue
        try:
            if (p / 'comm').read_text().strip() != 'motioncorr':
                continue
            uids = next(x for x in (p / 'status').read_text().splitlines()
                        if x.startswith('Uid:')).split()[1:]
            if int(uids[0]) != os.getuid():
                continue
            affinity = sorted(os.sched_getaffinity(int(p.name)))
            rows.append({'pid': int(p.name), 'affinity': affinity})
            if 13 in affinity:
                raise RuntimeError('CPU13 overlaps another MotionCorr process')
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def bytes_used(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file())


def normalized_log(path, output):
    lines = path.read_text().splitlines(keepends=True)
    written = 'Written aligned but non-dose weighted sum to '
    walls = re.compile(r'Full movie wall time: ([0-9]+(?:\.[0-9]+)?) s\n?\Z')
    n_written = n_wall = 0
    out = []
    for line in lines:
        if line.startswith(written):
            n_written += 1
            if line.rstrip('\n') != written + str(output / 'affine.mrc'):
                raise RuntimeError('log output path is not its own affine.mrc')
            out.append(written + '<OUTPUT>/affine.mrc\n')
        elif line.startswith('Full movie wall time:'):
            n_wall += 1
            m = walls.fullmatch(line)
            if m is None:
                raise RuntimeError('missing/malformed nonnegative finite wall time')
            # A bounded decimal token is finite here; reject overflow explicitly.
            if not __import__('math').isfinite(float(m[1])):
                raise RuntimeError('nonfinite wall time')
            out.append('Full movie wall time: <WALL_SECONDS> s\n')
        else:
            out.append(line)
    if n_written != 1 or n_wall != 1:
        raise RuntimeError('missing/duplicate output-path or wall-time log field')
    return ''.join(out)


def neutrality(old, run):
    base = old / 'runs/cpu-affine-on'
    checks = {}
    for n in ('global.txt', 'model.txt'):
        checks['state/' + n] = (base / 'state' / n).read_bytes() == (run / 'state' / n).read_bytes()
    checks['affine.log:version3_output_path_and_wall_only'] = normalized_log(base / 'out/affine.log', base / 'out') == normalized_log(run / 'out/affine.log', run / 'out')
    for suffix in ('*.star', '*.mrc', '*.mrcs'):
        a = {str(p.relative_to(base / 'out')): p for p in (base / 'out').rglob(suffix)}
        b = {str(p.relative_to(run / 'out')): p for p in (run / 'out').rglob(suffix)}
        checks[suffix + '-inventory'] = a.keys() == b.keys()
        for n in a.keys() & b.keys():
            x, y = a[n].read_bytes(), b[n].read_bytes()
            if suffix == '*.star':
                x = x.replace(str(base / 'out').encode(), b'<OUTPUT>')
                y = y.replace(str(run / 'out').encode(), b'<OUTPUT>')
                checks[n] = x == y
            else:
                checks[n + ':header_payload'] = x[:224] + x[1024:] == y[:224] + y[1024:]
                pattern = rb'Relion    [0-9]{2}-[A-Za-z]{3}-[0-9]{2}  [0-9]{2}:[0-9]{2}:[0-9]{2}'
                checks[n + ':labels'] = re.sub(pattern, b'Relion    DD-Mon-YY  HH:MM:SS', x[224:1024]) == re.sub(pattern, b'Relion    DD-Mon-YY  HH:MM:SS', y[224:1024])
    return checks


def captures(run, selector):
    files = sorted((run / 'capture').glob('*.json'))
    meta = [json.loads(p.read_text()) for p in files]
    if [p.name for p in files] != ['c1.json', 'c2.json']:
        raise RuntimeError('unexpected capture-call inventory')
    if not (meta[0]['tag'] == 'cpu-global' and meta[0]['patch_yx'] == [0, 0]
            and meta[0]['call'] == 1 and meta[0]['frames'] == 5
            and meta[1]['tag'] == 'cpu' and meta[1]['patch_yx'] == selector
            and meta[1]['call'] == 2 and meta[1]['frames'] == 5):
        raise RuntimeError('capture selector/route/frame mismatch')
    for stem in ('c1', 'c2'):
        arrays = list((run / 'capture').glob(stem + '-*.bin'))
        if not arrays or any(p.stat().st_size == 0 for p in arrays):
            raise RuntimeError('missing/empty capture arrays')
    return meta


def main(root, protocol):
    if os.uname().nodename != '4-gpu-vm' or os.getuid() != 1004:
        raise RuntimeError('wrong host/UID')
    if sorted(os.sched_getaffinity(0)) != protocol['cpu']:
        raise RuntimeError('wrong CPU affinity')
    old = Path(protocol['old_scratch'])
    if root.resolve() != root or root.parent != Path('/mnt/clathrin'):
        raise RuntimeError('scratch must be canonical direct child of /mnt/clathrin')
    if (root / 'campaign').exists() or (root / 'RESULT.json').exists():
        raise RuntimeError('existing attempt refused')
    with open(protocol['lock'], 'a') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = occupancy()
        if shutil.disk_usage(root).free < protocol['minimum_free_bytes']:
            raise RuntimeError('insufficient free space')
        pinned = identities(old, protocol)
        result = {'status': 'IN_PROGRESS', 'utc': now(), 'host': os.uname().nodename,
                  'uid': os.getuid(), 'pid': os.getpid(), 'affinity': sorted(os.sched_getaffinity(0)),
                  'lock': protocol['lock'], 'occupancy': rows, 'input_identities': pinned,
                  'driver_sha256': sha(Path(__file__)), 'protocol_sha256': sha(root / 'protocol.json'),
                  'launches': [], 'cuda': 'HELD_UNRUN', 'truth_fit_science': 'UNRUN_THIS_STAGE'}
        save(root / 'RESULT.json', result)
        (root / 'campaign').mkdir()
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(('MC_DIAG_', 'MC_CCF_', 'CUDA_'))}
        env.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1',
                   OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   NUMEXPR_NUM_THREADS='1', VECLIB_MAXIMUM_THREADS='1',
                   LD_LIBRARY_PATH='/usr/local/cuda-12.8/lib64')
        try:
            for selector in protocol['selectors']:
                occupancy()
                identities(old, protocol)
                if bytes_used(root) > protocol['scratch_cap_bytes']:
                    raise RuntimeError('scratch cap exceeded')
                d = root / 'campaign' / ('patch-%d-%d' % tuple(selector))
                d.mkdir()
                (d / 'state').mkdir()
                (d / 'capture').mkdir()
                arm = dict(env, MC_CCF_CAPTURE=str(d / 'capture'), MC_CCF_STATE=str(d / 'state'),
                           MC_CCF_PATCH=','.join(map(str, selector)))
                argv = [str(old / 'build-cpu/motioncorr'), '--i', 'affine.star', '--o', str(d / 'out'),
                        '--use_own', '--j', '1', '--patch_x', '3', '--patch_y', '3', '--bin_factor', '1',
                        '--seed', '1', '--skip_defect', '--save_noDW', '--first_frame_sum', '1',
                        '--last_frame_sum', '5', '--skip_logfile']
                row = {'selector': selector, 'argv': argv, 'cwd': str(old / 'fixtures'), 'start': now(),
                       'environment': {k: v for k, v in arm.items() if k.startswith(('MC_CCF_', 'CUDA_'))
                                       or k.endswith('NUM_THREADS') or k in ('VECLIB_MAXIMUM_THREADS', 'LD_LIBRARY_PATH', 'PYTHONDONTWRITEBYTECODE')}}
                result['launches'].append(row)
                if len(result['launches']) > protocol['maximum_native_launches']:
                    raise RuntimeError('launch budget exceeded')
                with (d / 'native.log').open('xb') as log:
                    child = subprocess.Popen(argv, cwd=old / 'fixtures', env=arm, stdout=log,
                                             stderr=subprocess.STDOUT, start_new_session=True)
                    row['pid'] = child.pid
                    try:
                        row.update(birth_ticks=Path('/proc/%d/stat' % child.pid).read_text().split(') ', 1)[1].split()[19],
                                   affinity=sorted(os.sched_getaffinity(child.pid)), pgid=os.getpgid(child.pid), sid=os.getsid(child.pid))
                        if row['pgid'] != child.pid or row['sid'] != child.pid:
                            raise RuntimeError('private process group/session not established')
                        save(d / 'STARTED.json', row)
                        try:
                            row['exit'] = child.wait(timeout=protocol['timeout_seconds'])
                        except subprocess.TimeoutExpired:
                            row['timeout'] = True
                    finally:
                        # A new session is created by Popen before exec; while the
                        # root is unreaped its PID/PGID cannot be recycled.
                        if child.poll() is None:
                            row['cleanup_signals'] = []
                            for sig in (signal.SIGTERM, signal.SIGKILL):
                                if child.poll() is not None:
                                    break
                                os.killpg(child.pid, sig)
                                row['cleanup_signals'].append(sig.name)
                                try:
                                    child.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    pass
                            if child.poll() is None:
                                row['cleanup'] = 'INCOMPLETE'
                                raise RuntimeError('CPU process cleanup incomplete')
                            row['cleanup'] = 'ROOT_REAPED'
                        row['exit'] = child.returncode
                        row['end'] = now()
                        save(d / 'RUN.json', row)
                save(d / 'RUN.json', row)
                if row.get('timeout') or row['exit'] != 0 or row['affinity'] != [13]:
                    raise RuntimeError('native exit/timeout/affinity failure')
                row['captures'] = captures(d, selector)
                row['neutrality'] = neutrality(old, d)
                identities(old, protocol)
                row['files'] = {str(p.relative_to(d)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
                                for p in sorted(d.rglob('*')) if p.is_file() and p.name != 'RUN.json'}
                if not all(row['neutrality'].values()):
                    raise RuntimeError('output/state neutrality mismatch')
                if bytes_used(root) > protocol['scratch_cap_bytes']:
                    raise RuntimeError('scratch cap exceeded')
                row['status'] = 'PASS'
                save(d / 'RUN.json', row)
                save(root / 'RESULT.json', result)
            result['final_identities'] = identities(old, protocol)
            result['final_occupancy'] = occupancy()
            result['status'] = 'PASS'
        except Exception as e:
            result['status'] = 'FAIL'
            result['error'] = type(e).__name__ + ': ' + str(e)
        result.update(end=now(), bytes_retained=bytes_used(root))
        save(root / 'RESULT.json', result)
        return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    root = Path(sys.argv[1])
    protocol = json.loads((root / 'protocol.json').read_text())
    sys.exit(main(root, protocol))
