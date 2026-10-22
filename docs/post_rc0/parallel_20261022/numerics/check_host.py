#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused host controls and checker mutations. No native GPU claims."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[4]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=False)
records = []
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                  VECLIB_MAXIMUM_THREADS='1', MKL_NUM_THREADS='1')


def run(name, argv, expected=0, contains=None):
    p = subprocess.run(argv, cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out/(name+'.log')).write_text(p.stdout)
    record = dict(name=name, argv=argv, exit=p.returncode, expected=expected,
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  expected_diagnostic=contains, diagnostic_found=contains is None or contains in p.stdout)
    records.append(record)
    (out/'receipts.json').write_text(json.dumps(records, indent=2)+'\n')
    print(name, p.returncode, flush=True)
    if p.returncode != expected or not record['diagnostic_found']:
        raise RuntimeError(name+' failed')


build = out/'cmake'
run('occupancy', ['uptime'])
run('configure', ['cmake','-S',str(repo),'-B',str(build),'-DCUDA=OFF',
    '-DBUILD_TESTING=ON','-DCMAKE_BUILD_TYPE=Release','-DPython3_EXECUTABLE='+sys.executable])
run('build', ['cmake','--build',str(build),'--target','hermitian_projection_oracle',
    'peak_fit_arithmetic','realspace_border_validation','--parallel','2'])
run('ctest', ['ctest','--test-dir',str(build),'-R',
    '^(HermitianProjectionOracle|PeakFitArithmetic.*|RealspaceBorderValidation)$',
    '-j','1','-V','--output-on-failure'])
for name in ['test_motion_diagnostics','test_combined_eval','test_realistic_image',
             'test_realistic_motion','test_known_motion_verdicts','test_known_motion_runner']:
    # Only existing entry points are selected; a renamed/missing tool fails closed.
    run(name, [sys.executable,str(repo/'tools'/(name+'.py')),'-v'])

header = (repo/'tests/hermitian_projection_oracle.h').read_text()
interior = 'interior_bad += !same_input_bytes(buf[i], f + 2 * i);'
passthrough = 'differing += !same_input_bytes(buf[i], f + 2 * i);'
numeric = '(buf[i].x != f[2 * i] || buf[i].y != f[2 * i + 1]);'
for name, changes in [('zero-interior', [(interior, 'interior_bad += '+numeric)]),
                      ('zero-passthrough', [(passthrough, 'differing += '+numeric)]),
                      ('zero-both', [(interior, 'interior_bad += '+numeric),
                                     (passthrough, 'differing += '+numeric)])]:
    d=out/name; d.mkdir(); h=header
    for before, after in changes:
        assert h.count(before) == 1
        h=h.replace(before,after)
    (d/'hermitian_projection_oracle.h').write_text(h)
    (d/'test.cpp').write_bytes((repo/'tests/test_hermitian_projection_oracle.cpp').read_bytes())
    run(name+'-compile',['c++','-std=c++17','-O3','-DNDEBUG',str(d/'test.cpp'),'-o',str(d/'check')])
    run(name+'-raw',[str(d/'check')],expected=1,contains='zero sign accepted')

header=(repo/'tests/realspace_border_validation.h').read_text()
guard='!std::isfinite(actual) || !std::isfinite(expected)'
for name, replacement in [('nonfinite-none','false'),('nonfinite-actual','!std::isfinite(actual)'),
                          ('nonfinite-expected','!std::isfinite(expected)')]:
    d=out/name; d.mkdir(); assert header.count(guard)==1
    (d/'realspace_border_validation.h').write_text(header.replace(guard,replacement))
    (d/'test.cpp').write_bytes((repo/'tests/test_realspace_border_validation.cpp').read_bytes())
    run(name+'-compile',['c++','-std=c++17','-O3','-DNDEBUG',str(d/'test.cpp'),'-o',str(d/'check')])
    run(name+'-raw',[str(d/'check')],expected=1,contains='accepted nonfinite actual or expected pixel')
for mutation in ['float-denominator','early-store','wrong-scale']:
    run('peak-'+mutation+'-raw',[str(build/'peak_fit_arithmetic'),mutation],expected=1)
(out/'binaries.json').write_text(json.dumps({str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in out.rglob('*') if p.is_file() and os.access(p,os.X_OK)},indent=2)+'\n')
