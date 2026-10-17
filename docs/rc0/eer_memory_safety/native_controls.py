#!/usr/bin/env python3
"""Read-only replay of V-EER fixtures into W-D10. Logs and summaries survive grading."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

W = Path('/mnt/clathrin/alex-motioncorr-rc0/W-D10')
FX = W.parent/'V-EER/fixtures'
MASK = '80-87'


def probe():
    while subprocess.run(['flock', '-n', '/tmp/motioncorr-bench.lock', 'true']).returncode:
        print('bench lock held', flush=True)
        time.sleep(60)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


STAR_HEADER = """# version 30001

data_optics

loop_
_rlnOpticsGroupName #1
_rlnOpticsGroup #2
_rlnMicrographOriginalPixelSize #3
_rlnVoltage #4
_rlnSphericalAberration #5
_rlnAmplitudeContrast #6
opticsGroup1 1 0.85 300.0 2.7 0.1

# version 30001

data_movies

loop_
_rlnMicrographMovieName #1
_rlnOpticsGroup #2
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm', required=True, choices=['main-cpu', 'main-asan', 'fix-cpu', 'fix-asan'])
    ap.add_argument('--ups', type=int, default=1)
    a = ap.parse_args()
    binary = W/f'build-{a.arm}/motioncorr'
    result_dir = W/f'controls/{a.arm}-up{a.ups}'
    result_dir.mkdir(parents=True, exist_ok=True)
    results = []
    inputs = {p.name: digest(p) for p in sorted(FX.iterdir()) if p.is_file()}
    (result_dir/'inputs.json').write_text(json.dumps(inputs, indent=2)+'\n')
    for source in sorted(FX.iterdir()):
        if not source.is_file():
            continue
        probe()
        work = result_dir/source.stem
        work.mkdir(exist_ok=True)
        bad = work/source.name
        if not bad.exists():
            bad.symlink_to(source)
        good = work/'healthy.eer'
        if not good.exists():
            good.symlink_to(FX/('f3_valid12.eer' if a.ups == -1 else 'syn_65002_valid12.eer'))
        (work/'input.star').write_text(STAR_HEADER + f'{source.name} 1\nhealthy.eer 1\n')
        command = ['taskset', '-c', MASK, str(binary), '--i', 'input.star', '--o', 'out/',
                   '--use_own', '--eer_grouping', '4', '--eer_upsampling', str(a.ups), '--j', '4',
                   '--skip_report_pdf', '--angpix', '0.85']
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                   UBSAN_OPTIONS='print_stacktrace=1:halt_on_error=0')
        begin = time.time()
        with (work/'stdout.txt').open('w') as stdout, (work/'stderr.txt').open('w') as stderr:
            try:
                p = subprocess.run(command, cwd=work, stdout=stdout, stderr=stderr, env=env, timeout=180)
                rc = p.returncode
            except subprocess.TimeoutExpired:
                rc = 124
        log = (work/'stdout.txt').read_text()+(work/'stderr.txt').read_text()
        reports = [l for l in log.splitlines() if any(x in l for x in ['AddressSanitizer', 'runtime error:', 'LeakSanitizer', 'SUMMARY:'])]
        out = work/'out'
        products = sorted(str(p.relative_to(out)) for p in out.rglob('*') if p.is_file())
        row = dict(fixture=source.name, command=command, cwd=str(work), rc=rc,
                   seconds=time.time()-begin, reports=reports, products=products,
                   warnings=log.count('This frame is skipped'),
                   healthy=(out/'healthy.star').exists() and (out/'healthy.mrc').exists(),
                   joint=(out/'corrected_micrographs.star').exists(),
                   failed_products=[p for p in products if p.startswith(source.stem+'.') and not p.endswith('.log')])
        row['controlled'] = rc in (0, 1) and row['healthy'] and not reports
        row['publication'] = (row['joint'] if rc == 0 else not row['joint'] and not row['failed_products'])
        results.append(row)
        (work/'result.json').write_text(json.dumps(row, indent=2)+'\n')
        (result_dir/'results.json').write_text(json.dumps(results, indent=2)+'\n')
        # Only bulk products in this script's own per-case output directory.
        for p in out.rglob('*.mrc'):
            p.unlink()
        print(a.arm, a.ups, source.name, rc, row['warnings'], 'healthy', row['healthy'], 'reports', len(reports), flush=True)
    if a.arm.startswith('fix'):
        assert all(r['controlled'] and r['publication'] for r in results), 'fix control/publication failure; see results.json'


if __name__ == '__main__':
    main()
