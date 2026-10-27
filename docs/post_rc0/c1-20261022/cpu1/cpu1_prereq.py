#!/usr/bin/env python3
"""Read-only prerequisites of the CPU-only plan. usage: cpu1_prereq.py CHAIN_SCRIPT OUT.json   (exit 0 only if every check passes)"""
import hashlib, json, os, re, shutil, subprocess, sys
from pathlib import Path
SC = Path(os.environ['C1_SCR']); SHA = os.environ['C1_SHA']
F = Path('/mnt/clathrin/alex-motioncorr-rc0/W-QF'); KM = Path('/mnt/clathrin/alex-motioncorr-km-truth')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
res, bad = {}, []
def check(name, ok, detail=None):
    res[name] = {'ok': bool(ok), 'detail': detail}
    if not ok: bad.append(name)
g = lambda *a: subprocess.run(['git', '-C', str(SC / 'src'), *a], capture_output=True, text=True).stdout.strip()
check('source_exact_clean', g('rev-parse', 'HEAD') == SHA and g('status', '--porcelain') == '', g('rev-parse', 'HEAD'))
cpu, fcpu = SC / 'build-cpu/motioncorr', F / 'build-cpu/motioncorr'
check('c1_cpu_binary', sha(cpu) == '5692c6dc5eaca953357bf7a1161338b99ca320369f0b6c6ab025d9aaa7f9dc3c', sha(cpu))
check('f_cpu_binary', sha(fcpu) == '43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42', sha(fcpu))
for b in (cpu, fcpu):
    ldd = subprocess.run(['ldd', str(b)], capture_output=True, text=True).stdout
    check(f'no_cuda_linkage_{b.parent.parent.name}', not re.search(r'cuda|nvcomp|cufft|cudart', ldd, re.I), None)
for c in 'GL':
    j = json.loads((SC / f't24/F-cpu-{c}/RUN.json').read_text())
    out = SC / f't24/F-cpu-{c}/out'
    check(f'f_cpu_baseline_{c}', j['rc'] == 0 and not j['gpu_run'] and len(list(out.glob('Movies/*.mrc'))) == 24 and len(list(out.rglob('*.star'))) == 25, {'rc': j['rc'], 'wall_s': j['wall_s']})
fx = sorted(p.name for p in (KM / 'fixtures').iterdir() if (p / 'RECEIPT.json').exists())
check('census_fixtures_100', len(fx) == 100, len(fx))
tars = sorted(KM.glob('retained-cpu-products/*.tar.zst')); side = sorted(KM.glob('retained-cpu-products/*.tar.zst.json'))
check('retained_cpu_products_100', len(tars) == 100 and len(side) == 100 and sorted(p.name[:-8] for p in tars) == fx, (len(tars), len(side)))
scipy = Path('/mnt/clathrin/alex-motioncorr-synth-combined/venv/bin/python3')
r = subprocess.run([str(scipy), '-c', 'import scipy,numpy;print(scipy.__version__,numpy.__version__)'], capture_output=True, text=True)
check('scipy_venv', r.returncode == 0, r.stdout.strip()); check('zstd_tar', bool(shutil.which('zstd') and shutil.which('tar')), None)
for d in ('t24-cpu1', 'census', 'census-ref-cpu', 'v2/cpu-unset', 'v2/cpuF-unset'): check(f'fresh_{d}', not (SC / d).exists(), d)
check('fresh_stage_names', not list((SC / 'logs').glob('cpu1-*')), None)
text = Path(sys.argv[1]).read_text()
code = '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))
check('chain_has_no_gpu_helper', not re.search(r'nvidia-smi|c1_gpu_run|c1_occupancy|c1_health|--gpu|GPU_LOCK|CUDA_VISIBLE_DEVICES=[^ \n]*[A-Za-z0-9]', code), None)
check('chain_sets_empty_cuda_visible_devices', 'export CUDA_VISIBLE_DEVICES=' in code, None)
Path(sys.argv[2]).write_text(json.dumps({'checks': res, 'failed': bad}, indent=1, default=str) + '\n')
for k, v in res.items(): print('PASS' if v['ok'] else 'FAIL', k)
sys.exit(1 if bad else 0)
