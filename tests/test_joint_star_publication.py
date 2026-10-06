#!/usr/bin/env python3
"""Exercise checked STAR publication and its actual runner call site.

GPL-2.0-or-later. All injected faults stay in a private temporary directory.
The helper's finite hard file limit is confined to its subprocess. Acceptance
uses explicit checks, also when Python's optimized interpreter is selected.
"""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

from test_hotpixel_rng_determinism import write_movie, write_star


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(command, work):
    return subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=60)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--helper', required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for case in ('healthy', 'open', 'rename', 'limit', 'write-limit'):
            result = run([str(args.helper.resolve()), case, str(work / (case + '.star'))], work)
            require(result.returncode == 0, result.stdout + result.stderr)
            require('PASS joint STAR ' + case in result.stdout, 'helper did not execute ' + case)
            print(result.stdout.strip())
        write_movie(work / 'a.mrc', 17, None, [])
        write_star(work / 'movies.star', ['a.mrc'])
        out = work / 'out'
        command = [str(args.binary.resolve()), '--i', 'movies.star', '--o', str(out) + '/',
                   '--use_own', '--j', '1', '--patch_x', '1', '--patch_y', '1',
                   '--seed', '1', '--skip_logfile', '--write_resume_receipts']
        healthy = run(command, work)
        require(healthy.returncode == 0, 'healthy runner failed: ' + healthy.stdout + healthy.stderr)
        joint = out / 'corrected_micrographs.star'
        require(joint.is_file(), 'healthy runner omitted joint STAR')
        joint_bytes = joint.read_bytes()
        products = [out / 'a.mrc', out / 'a.star']
        before = [(digest(p), p.stat().st_mtime_ns) for p in products]
        joint.unlink()
        joint.mkdir()
        failed = run(command + ['--only_do_unfinished'], work)
        require(failed.returncode > 0, 'false success: runner joint STAR destination-directory failure')
        require('Failed to rename temporary STAR file' in failed.stderr and str(joint) in failed.stderr,
                'runner did not report the named STAR rename failure: ' + failed.stderr)
        require('Written: ' + str(joint) not in failed.stdout, 'runner claimed joint STAR publication after failure')
        require(joint.is_dir(), 'failed runner replaced the destination directory')
        require(not Path(str(joint) + '.tmp').exists(), 'failed runner retained temporary STAR')
        require([(digest(p), p.stat().st_mtime_ns) for p in products] == before,
                'joint publication failure altered completed movie products')
        joint.rmdir()
        recovered = run(command + ['--only_do_unfinished'], work)
        require(recovered.returncode == 0, 'repaired publication failed: ' + recovered.stderr)
        require(joint.read_bytes() == joint_bytes, 'healthy resume changed joint STAR bytes')
        require([(digest(p), p.stat().st_mtime_ns) for p in products] == before,
                'repaired publication recomputed completed movie products')
    print('PASS joint STAR actual runner failure and repair; completed products unchanged')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
