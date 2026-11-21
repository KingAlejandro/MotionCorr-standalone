#!/usr/bin/env python3
"""Read-only prerequisites of the CPU-only plan. usage: cpu1c_prereq.py CHAIN_SCRIPT IDS.json EXPECTED_TOOLS.sha256 PINS_DIR OUT.json   (exit 0 only if every check passes)"""
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
for d in ('t24-cpu1c', 'census', 'census-ref-cpu', 'v2/cpu-unset', 'v2/cpuF-unset'): check(f'fresh_{d}', not (SC / d).exists(), d)
# the stage wrapper has already created this stage's own receipts (cpu1c-prereq.*); every other cpu1b stage name must not exist yet
check('fresh_stage_names', not [p.name for p in (SC / 'logs').glob('cpu1c-*') if not p.name.startswith('cpu1c-prereq.')], None)
text = Path(sys.argv[1]).read_text()
code = '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))
check('chain_has_no_gpu_helper', not re.search(r'nvidia-smi|c1_gpu_run|c1_occupancy|c1_health|--gpu|GPU_LOCK|CUDA_VISIBLE_DEVICES=[^ \n]*[A-Za-z0-9]', code), None)
check('chain_sets_empty_cuda_visible_devices', 'export CUDA_VISIBLE_DEVICES=' in code, None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cpu1c_sums as S
try:
    ids = S.load_ids(sys.argv[2])
    ok = ids['all'] == fx and ids['control'] == [f'dose1-s{i:02d}' for i in range(10)] and len(ids['all']) == 100
    check('identities_frozen_100_and_10', ok, {'all': len(ids['all']), 'control': ids['control'][:2] + ['...'], 'sha256': sha(sys.argv[2])})
except Exception as exc:
    check('identities_frozen_100_and_10', False, str(exc))
# whole-chain CPU pinning (the chain must be launched under taskset -c 8-9)
allowed = next((l.split(':', 1)[1].strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('Cpus_allowed_list')), None)
check('cpus_allowed_list_is_8-9', allowed == '8-9', allowed)
# deployed tool directory: exact file set and hashes against the frozen git-derived manifest; every script the chain invokes must be in it
V = SC / 'tools-cpu1c-run'
expected = dict(reversed(l.split(None, 1)) for l in Path(sys.argv[3]).read_text().splitlines() if l.strip())
expected = {k.strip(): v for k, v in expected.items()}
deployed = {p.name: sha(p) for p in V.iterdir()}
diff = sorted(k for k in set(expected) | set(deployed) if expected.get(k) != deployed.get(k))
check('deployed_tools_equal_frozen_manifest', not diff and len(expected) > 30, {'files': len(deployed), 'differing': diff, 'manifest_sha256': sha(sys.argv[3])})
used = sorted(set(re.findall(r'\$V/([A-Za-z0-9_.\-]+)', code)))
check('chain_scripts_present_in_deployed_set', all(u in deployed and u in expected for u in used), {'used': used, 'missing': [u for u in used if u not in deployed]})
# original F-cpu baseline runs: pinned copies, frozen binary, exact argv/cwd/mask
FSHA = '43cab2b74e97e948172c656d2b3041b562d24e733de1a5727a54624c12749b42'
BASE = ['--i', 'movies.star', '--o', None, '--j', '2', '--use_own', '--dose_weighting', '--dose_per_frame', '1.277', '--bfactor', '150', '--seed', '1', '--expected_frames', '24', '--gainref', 'Movies/gain.mrc']
for c in 'GL':
    live = SC / f't24/F-cpu-{c}/RUN.json'; pin = Path(sys.argv[4]) / f'F-cpu-{c}.RUN.json'
    j = json.loads(live.read_text())
    want = [f'{SC}/t24/F-cpu-{c}/out/' if a is None else a for a in BASE] + (['--patch_x', '5', '--patch_y', '5'] if c == 'L' else [])
    check(f'f_cpu_run_pinned_{c}', sha(live) == sha(pin) and j['binary_sha256'] == FSHA and j['args'] == want and j['cwd'] == f'{SC}/t24/F-cpu-{c}/cwd' and j['cpu_mask'] == '8-9'
          and j['rc'] == 0 and j['gpu_run'] is False and j['env'].get('OMP_NUM_THREADS') == '2', {'rc': j['rc'], 'binary': j['binary_sha256'][:12], 'args_equal': j['args'] == want, 'live_sha256': sha(live)})
Path(sys.argv[5]).write_text(json.dumps({'checks': res, 'failed': bad}, indent=1, default=str) + '\n')
for k, v in res.items(): print('PASS' if v['ok'] else 'FAIL', k)
sys.exit(1 if bad else 0)
