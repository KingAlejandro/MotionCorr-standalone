#!/usr/bin/env python3
"""Compile actual pool drops against host API doubles; no CUDA execution.

The SDK doubles expose wrong-context release calls. The positive candidate,
original drop source and four single-guard mutations use the same host oracle.
Native control remains in cuda_worker_pool --case device-cleanup.
"""
import argparse, hashlib, json, pathlib, shutil, subprocess, tempfile

p = argparse.ArgumentParser()
p.add_argument('--compiler', default='clang++')
p.add_argument('--work', type=pathlib.Path)
p.add_argument('--old-ref', default='1ae23cf77992c5e8161fc33181ba583ec8564f6a')
a = p.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
compiler = shutil.which(a.compiler)
if not compiler:
    raise SystemExit('C++17 host compiler unavailable: ' + a.compiler)
source = root / 'src/acc/cuda/cuda_worker_pool.cu'
text = source.read_text()
old = subprocess.run(['git', '-C', str(root), 'show', a.old_ref + ':src/acc/cuda/cuda_worker_pool.cu'], capture_output=True, text=True, check=True).stdout
cases = [('candidate', text, None), ('old-drops-current-header', old, 'resource=0 action=0')]
for index, (resource, device) in enumerate((('gain', 'device'), ('global', 'owned.device'), ('patch', 'owned.device'), ('dw', 'owned.device'))):
    guard = '    if (!selectDevice(' + device + ', "worker pool ' + resource + ' drop setDevice", failure)) return false;'
    if text.count(guard) != 1:
        raise SystemExit('mutation anchor missing/ambiguous: ' + resource)
    mutant = text.replace(guard, '    (void)selectDevice(' + device + ', "worker pool ' + resource + ' drop setDevice", failure); // MUTANT', 1)
    cases.append(('ignore-' + resource + '-device-selection', mutant, 'resource=' + str(index) + ' action=0'))

def execute(work):
    work.mkdir(parents=True, exist_ok=True)
    records = []
    for name, src, expected in cases:
        cu, binary = work / (name + '.cu'), work / name
        cu.write_text(src)
        command = [compiler, '-std=c++17', '-D_CUDA_ENABLED', '-I' + str(root / 'tests/cuda_worker_pool_cleanup_mock'), '-I' + str(root), '-x', 'c++', str(cu), str(root / 'tests/cuda_worker_pool_cleanup_host.cpp'), '-o', str(binary)]
        build = subprocess.run(command, capture_output=True, text=True)
        (work / (name + '-build.log')).write_text(build.stdout + build.stderr)
        if build.returncode:
            raise SystemExit('host build failed: ' + name + '\n' + build.stderr)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30)
        output = run.stdout + run.stderr
        (work / (name + '.log')).write_text(output)
        if expected is None:
            ok = run.returncode == 0 and 'ALL PASS:16 host ownership controls' in output
        else:
            ok = run.returncode != 0 and 'FAIL: selection failure issued wrong-context release ' + expected in output
        records.append({'case': name, 'source_sha256': hashlib.sha256(src.encode()).hexdigest(), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'command': command, 'returncode': run.returncode, 'expected_failure': expected, 'discriminated': ok})
        print(('PASS' if ok else 'FAIL') + ' ' + name, flush=True)
        if not ok:
            raise SystemExit('control failed to discriminate: ' + name + '\n' + output)
    (work / 'result.json').write_text(json.dumps({'scope': 'actual production source against host API doubles; native UNRUN', 'old_source_ref': a.old_ref, 'old_source_uses_current_header': True, 'controls': records}, indent=2))

if a.work:
    execute(a.work.resolve())
else:
    with tempfile.TemporaryDirectory(prefix='mc-pool-cleanup-') as tmp:
        execute(pathlib.Path(tmp))
